"""Tests for the protocol module, using real frames of a Battery-Box LVL with 3 BMS.

Reference values come from Be Connect Plus (CSV export + screenshot) taken
at the same time (serial numbers anonymised).
"""

import asyncio
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location(
    "protocol", ROOT / "custom_components/byd_battery_box/protocol.py"
)
protocol = importlib.util.module_from_spec(spec)
sys.modules["protocol"] = protocol
spec.loader.exec_module(protocol)

FRAMES = json.loads((ROOT / "tests/fixtures/lvl_3bms_2026-09-30.json").read_text())


def rx(label_part: str, nth: int = 0) -> bytes:
    hits = [bytes.fromhex(f["rx"]) for f in FRAMES if label_part in f["label"]]
    return hits[nth]


def bms_blocks(index: int) -> list[bytes]:
    return [rx(f"BMS {index}: Detaildaten Block {n}") for n in range(1, 5)]


def test_requests_match_known_frames():
    assert protocol.req_read(0x0000, 0x66).hex() == "010300000066c5e0"
    assert protocol.req_read(0x0500, 0x19).hex() == "01030500001984cc"
    assert protocol.req_read(0x0558, 0x41).hex() == "01030558004104e5"
    assert protocol.req_write(0x0550, [3, 0x8100]).hex() == "01100550000204000381005993"


def test_bmu_info():
    info = protocol.parse_bmu_info(rx("Paket 0"))
    assert info.serial == "P020T020Z0000000001"
    assert info.bmu_firmware == "V1.35"
    assert info.bms_firmware == "V1.17"
    assert info.bms_count == 3
    assert info.battery_type == "LVL"
    assert info.inverter == "SMA LV"
    assert info.application == "On Grid"
    assert info.phase == "Three"


def test_bmu_status():
    st = protocol.parse_bmu_status(rx("Paket 1"))
    assert st.soc == 94
    assert st.soh == 96
    assert st.voltage == 53.0
    assert st.current == 24.9
    assert (st.max_cell_voltage, st.min_cell_voltage) == (3.32, 3.31)
    assert (st.max_cell_temp, st.min_cell_temp) == (29, 26)
    assert st.errors == [] and st.error_code == 0
    assert st.pt_version == "V0.11"
    assert round(st.charge_energy) == 11856
    assert round(st.discharge_energy) == 10794


def test_bms_values_match_be_connect():
    csv_cells = {
        1: [3319, 3319, 3319, 3319, 3319, 3318, 3318, 3319, 3320, 3320, 3319, 3319, 3319, 3320, 3319, 3319],
        2: [3319, 3318, 3318, 3318, 3319, 3319, 3318, 3318, 3320, 3319, 3319, 3318, 3319, 3319, 3318, 3319],
        3: [3317, 3316, 3316, 3316, 3317, 3316, 3316, 3317, 3317, 3317, 3317, 3317, 3317, 3317, 3317, 3317],
    }
    csv_temps = {
        1: [27, 27, 27, 27, 29, 29, 28, 28],
        2: [27, 27, 27, 27, 28, 29, 29, 29],
        3: [26, 26, 26, 27, 28, 28, 28, 28],
    }
    total_current = 0
    for i in (1, 2, 3):
        bms = protocol.parse_bms(i, bms_blocks(i))
        assert bms.serial == f"P022T010Z00000000{10 + i}"
        assert bms.temperatures == csv_temps[i]
        # CSV was taken ~1 min later while discharging: allow 3 mV
        assert all(abs(a - b) <= 3 for a, b in zip(bms.cell_voltages, csv_cells[i]))
        assert bms.soh == 96 and 94 <= bms.soc <= 95
        assert 52.5 < bms.voltage < 53.5
        assert bms.status == [] and bms.balancing_count == 0
        total_current += bms.current
    assert round(total_current, 1) == 24.7


def test_bms_energy_sums_to_bmu():
    st = protocol.parse_bmu_status(rx("Paket 1"))
    bms = [protocol.parse_bms(i, bms_blocks(i)) for i in (1, 2, 3)]
    assert abs(sum(b.charge_energy for b in bms) - st.charge_energy) < 1
    assert abs(sum(b.discharge_energy for b in bms) - st.discharge_energy) < 1


def test_negative_temperature():
    b = bytearray(bms_blocks(1)[2])
    b[103] = 0xFB  # -5 °C
    blocks = bms_blocks(1)
    blocks[2] = bytes(b)
    assert protocol.parse_bms(1, blocks).temperatures[0] == -5


def test_client_against_fragmenting_fake_bmu():
    """Full cycle over TCP with answers split into small chunks."""
    answers = {
        "010300000066c5e0": [rx("Paket 0")],
        "01030500001984cc": [rx("Paket 1")],
        "010305510001d517": [rx("Messstatus")],
    }
    state = {"bms": 1, "block": 0}

    async def handle(reader, writer):
        while True:
            try:
                head = await reader.readexactly(8)
            except asyncio.IncompleteReadError:
                break
            req = head
            if head[1] == 0x10:
                req += await reader.readexactly(head[6] + 1)
                state["bms"], state["block"] = req[8], 0
                resp = req[:6] + protocol.crc16_modbus(req[:6]).to_bytes(2, "little")
            elif head.hex() == "01030558004104e5":
                state["block"] += 1
                resp = rx(f"BMS {state['bms']}: Detaildaten Block {state['block']}")
            else:
                resp = answers[head.hex()][0]
            for i in range(0, len(resp), 7):
                writer.write(resp[i:i + 7])
                await writer.drain()
                await asyncio.sleep(0.001)
        writer.close()

    async def run():
        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        protocol.MEASURE_WAIT = 0
        client = protocol.BydClient("127.0.0.1", port, timeout=5)
        status = await client.read_status()
        info, bms = await client.read_details(3)
        server.close()
        return status, info, bms

    status, info, bms = asyncio.run(run())
    assert status.soc == 94
    assert info.bms_count == 3
    assert sorted(bms) == [1, 2, 3]
    assert bms[3].temperatures[0] == 26
