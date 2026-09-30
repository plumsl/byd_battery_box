"""Protocol client for BYD Battery-Box Premium (BMU + BMS) over LAN.

This module has no Home Assistant dependency so it can be tested standalone.

Transport: Modbus-RTU frames over plain TCP (default port 8080).
Register layout verified against a Battery-Box Premium LVL (3 BMS) and the
manufacturer software "Be Connect Plus" (see tests/ for the reference frames).
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from dataclasses import dataclass, field

_LOGGER = logging.getLogger(__name__)

SLAVE = 0x01

CELLS_PER_BMS = 16
TEMPS_PER_BMS = 8

# Wait after starting a BMS measurement (seconds). Verified: 4 s is sufficient.
MEASURE_WAIT = 4.0
DETAIL_BLOCKS = 4

BMU_ERRORS = (
    "High temperature during charging",
    "Low temperature during charging",
    "Overcurrent during discharging",
    "Overcurrent during charging",
    "Main circuit failure",
    "Short circuit alarm",
    "Cell imbalance",
    "Current sensor error",
    "Battery overvoltage",
    "Battery undervoltage",
    "Cell overvoltage",
    "Cell undervoltage",
    "Voltage sensor error",
    "Temperature sensor error",
    "High temperature during discharging",
    "Low temperature during discharging",
)

BMS_STATUS_BITS = (
    "Battery overvoltage",
    "Battery undervoltage",
    "Cell overvoltage",
    "Cell undervoltage",
    "Cell imbalance",
    "Charging high temperature",
    "Charging low temperature",
    "Discharging high temperature",
    "Discharging low temperature",
    "Charging overcurrent",
    "Discharging overcurrent",
    "Charging overcurrent (hardware)",
    "Short circuit",
    "Reverse connection",
    "Interlock switch abnormal",
    "Air switch abnormal",
)

LV_INVERTERS = (
    "Fronius HV", "Goodwe HV", "Goodwe HV", "Kostal HV", "Selectronic LV",
    "SMA SBS3.7/5.0", "SMA LV", "Victron LV", "Suntech LV", "Sungrow HV",
    "Kaco HV", "Studer LV", "Solar Edge LV", "Ingeteam HV", "Sungrow LV",
    "Schneider LV", "SMA SBS2.5 HV", "Solar Edge LV", "Solar Edge LV",
    "Solar Edge LV",
)

BATTERY_TYPES = {0: "LVL", 1: "HVM", 2: "HVS"}
APPLICATIONS = {0: "Off Grid", 1: "On Grid", 2: "Backup"}
PHASES = {0: "Single", 1: "Three"}


class BydError(Exception):
    """Base error."""


class BydConnectionError(BydError):
    """Battery not reachable or connection dropped."""


class BydProtocolError(BydError):
    """Malformed or unexpected answer."""


# --------------------------------------------------------------------------
# Frame helpers
# --------------------------------------------------------------------------
def crc16_modbus(data: bytes) -> int:
    """Return the Modbus CRC16 of data."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _with_crc(body: bytes) -> bytes:
    return body + struct.pack("<H", crc16_modbus(body))


def req_read(register: int, count: int) -> bytes:
    """Build a function 0x03 request."""
    return _with_crc(struct.pack(">BBHH", SLAVE, 0x03, register, count))


def req_write(register: int, values: list[int]) -> bytes:
    """Build a function 0x10 request."""
    payload = b"".join(struct.pack(">H", v) for v in values)
    return _with_crc(
        struct.pack(">BBHHB", SLAVE, 0x10, register, len(values), len(payload))
        + payload
    )


def _s16(d: bytes, p: int) -> int:
    return struct.unpack_from(">h", d, p)[0]


def _u16(d: bytes, p: int) -> int:
    return struct.unpack_from(">H", d, p)[0]


def _u32_swapped(d: bytes, p: int) -> int:
    """32-bit value stored low word first, each word big endian."""
    return _u16(d, p + 2) << 16 | _u16(d, p)


def _s8(value: int) -> int:
    return value - 256 if value > 127 else value


def _bits(value: int, names: tuple[str, ...]) -> list[str]:
    return [name for i, name in enumerate(names) if value & (1 << i)]


def _ascii(d: bytes) -> str:
    return d.decode("ascii", "replace").strip("\x00 x")


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------
@dataclass
class BmuInfo:
    """Static information of the BMU (register 0x0000)."""

    serial: str
    bmu_firmware_a: str
    bmu_firmware_b: str
    bmu_active: str
    bms_firmware: str
    inverter: str
    bms_count: int
    battery_type: str
    application: str
    phase: str

    @property
    def bmu_firmware(self) -> str:
        return self.bmu_firmware_a if self.bmu_active == "A" else self.bmu_firmware_b


@dataclass
class BmuStatus:
    """Live values of the BMU (register 0x0500)."""

    soc: int
    soh: int
    max_cell_voltage: float
    min_cell_voltage: float
    current: float
    voltage: float
    output_voltage: float
    max_cell_temp: int
    min_cell_temp: int
    error_code: int
    errors: list[str]
    pt_version: str
    charge_energy: float
    discharge_energy: float

    @property
    def power(self) -> float:
        """Power in W, positive = discharging."""
        return round(self.output_voltage * self.current, 1)

    @property
    def efficiency(self) -> float | None:
        if not self.charge_energy:
            return None
        return round(100 * self.discharge_energy / self.charge_energy, 2)


@dataclass
class BmsData:
    """Detail values of one BMS (register 0x0550 / 0x0558)."""

    index: int
    serial: str
    soc: float
    soh: int
    voltage: float
    output_voltage: float
    current: float
    max_cell_voltage: int
    min_cell_voltage: int
    max_cell_no: int
    min_cell_no: int
    max_temp: int
    min_temp: int
    max_temp_no: int
    min_temp_no: int
    balancing_bits: str
    balancing_count: int
    charge_energy: float
    discharge_energy: float
    status_code: int
    status: list[str]
    firmware_raw: str
    cell_voltages: list[int]
    temperatures: list[int]
    extra: dict = field(default_factory=dict)

    @property
    def power(self) -> float:
        return round(self.voltage * self.current, 1)

    @property
    def cell_spread(self) -> int:
        return max(self.cell_voltages) - min(self.cell_voltages)


# --------------------------------------------------------------------------
# Parsers
# --------------------------------------------------------------------------
def parse_bmu_info(d: bytes) -> BmuInfo:
    if len(d) < 41:
        raise BydProtocolError(f"BMU info too short ({len(d)} bytes)")
    inv = d[35]
    return BmuInfo(
        serial=_ascii(d[3:22]),
        bmu_firmware_a=f"V{d[27]}.{d[28]}",
        bmu_firmware_b=f"V{d[29]}.{d[30]}",
        bmu_active="A" if d[33] == 0 else "B",
        bms_firmware=f"V{d[31]}.{d[32]}",
        inverter=LV_INVERTERS[inv] if inv < len(LV_INVERTERS) else f"Unknown ({inv})",
        bms_count=d[36],
        battery_type=BATTERY_TYPES.get(d[37], f"Unknown ({d[37]})"),
        application=APPLICATIONS.get(d[38], f"Unknown ({d[38]})"),
        phase=PHASES.get(d[39], f"Unknown ({d[39]})"),
    )


def parse_bmu_status(d: bytes) -> BmuStatus:
    if len(d) < 50:
        raise BydProtocolError(f"BMU status too short ({len(d)} bytes)")
    error_code = _u16(d, 29)
    return BmuStatus(
        soc=_s16(d, 3),
        max_cell_voltage=_s16(d, 5) / 100,
        min_cell_voltage=_s16(d, 7) / 100,
        soh=_s16(d, 9),
        current=_s16(d, 11) / 10,
        voltage=_u16(d, 13) / 100,
        max_cell_temp=_s16(d, 15),
        min_cell_temp=_s16(d, 17),
        error_code=error_code,
        errors=_bits(error_code, BMU_ERRORS),
        pt_version=f"V{d[31]}.{d[32]}",
        output_voltage=_u16(d, 35) / 100,
        charge_energy=_u32_swapped(d, 37) / 1000,  # Wh -> kWh
        discharge_energy=_u32_swapped(d, 41) / 1000,
    )


def parse_bms(index: int, blocks: list[bytes]) -> BmsData:
    if len(blocks) < 3 or any(len(b) < 133 for b in blocks[:3]):
        raise BydProtocolError(f"BMS {index}: detail blocks incomplete")
    b1, b3 = blocks[0], blocks[2]
    status_code = _u16(b1, 59)
    cells = [_s16(b1, 101 + 2 * i) for i in range(CELLS_PER_BMS)]
    temps = [_s8(b3[103 + i]) for i in range(TEMPS_PER_BMS)]
    if not any(cells):
        raise BydProtocolError(f"BMS {index}: no cell voltages in answer")
    return BmsData(
        index=index,
        serial=_ascii(b1[71:90]),
        max_cell_voltage=_s16(b1, 5),
        min_cell_voltage=_s16(b1, 7),
        max_cell_no=b1[9],
        min_cell_no=b1[10],
        max_temp=_s16(b1, 11),
        min_temp=_s16(b1, 13),
        max_temp_no=b1[15],
        min_temp_no=b1[16],
        balancing_bits=b1[17:33].hex(),
        balancing_count=bin(int.from_bytes(b1[17:33], "big")).count("1"),
        charge_energy=_u32_swapped(b1, 33) / 1000,
        discharge_energy=_u32_swapped(b1, 37) / 1000,
        voltage=_s16(b1, 45) / 10,
        output_voltage=_s16(b1, 51) / 10,
        soc=_s16(b1, 53) / 10,
        soh=_s16(b1, 55),
        current=_s16(b1, 57) / 10,
        status_code=status_code,
        status=_bits(status_code, BMS_STATUS_BITS),
        firmware_raw=b1[65:69].hex(),
        cell_voltages=cells,
        temperatures=temps,
        extra={
            "unknown_b1_47": _u16(b1, 47),
            "unknown_b1_49": _u16(b1, 49),
            "unknown_b1_95": b1[95:99].hex(),
            "unknown_temps_b3": [_s8(v) for v in b3[111:114]],
            "unknown_b4_39": _u16(blocks[3], 39) if len(blocks) > 3 and len(blocks[3]) > 41 else None,
        },
    )


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------
class BydClient:
    """Connection to the BMU. One TCP connection per polling cycle."""

    def __init__(self, host: str, port: int = 8080, timeout: float = 10.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        # last raw frames, for diagnostics
        self.last_frames: dict[str, dict] = {}

    # -- low level ---------------------------------------------------------
    async def _open(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout
            )
        except (OSError, asyncio.TimeoutError) as err:
            raise BydConnectionError(
                f"Cannot connect to {self.host}:{self.port}: {err!r}"
            ) from err

    async def _close(self) -> None:
        writer, self._reader, self._writer = self._writer, None, None
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass

    async def _read_exact(self, n: int) -> bytes:
        assert self._reader
        return await asyncio.wait_for(self._reader.readexactly(n), self.timeout)

    async def _transact(self, label: str, request: bytes) -> bytes:
        assert self._writer
        try:
            self._writer.write(request)
            await self._writer.drain()
            head = await self._read_exact(2)
            func = head[1]
            if func & 0x80:
                frame = head + await self._read_exact(3)
            elif func == 0x03:
                length = await self._read_exact(1)
                frame = head + length + await self._read_exact(length[0] + 2)
            elif func == 0x10:
                frame = head + await self._read_exact(6)
            else:
                raise BydProtocolError(f"{label}: unexpected function 0x{func:02x}")
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as err:
            raise BydConnectionError(f"{label}: {err!r}") from err

        self.last_frames[label] = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "tx": request.hex(),
            "rx": frame.hex(),
        }
        if crc16_modbus(frame) != 0:
            raise BydProtocolError(f"{label}: CRC error")
        if frame[1] & 0x80:
            raise BydProtocolError(f"{label}: Modbus exception {frame[2]}")
        return frame

    # -- high level --------------------------------------------------------
    async def read_info(self) -> BmuInfo:
        async with self._lock:
            await self._open()
            try:
                return parse_bmu_info(
                    await self._transact("bmu_info", req_read(0x0000, 0x66))
                )
            finally:
                await self._close()

    async def read_status(self) -> BmuStatus:
        async with self._lock:
            await self._open()
            try:
                return parse_bmu_status(
                    await self._transact("bmu_status", req_read(0x0500, 0x19))
                )
            finally:
                await self._close()

    async def read_details(self, bms_count: int) -> tuple[BmuInfo, dict[int, BmsData]]:
        """Read BMU info and the detail data of every BMS in one connection."""
        async with self._lock:
            await self._open()
            try:
                info = parse_bmu_info(
                    await self._transact("bmu_info", req_read(0x0000, 0x66))
                )
                result: dict[int, BmsData] = {}
                for index in range(1, bms_count + 1):
                    await self._transact(
                        f"bms{index}_start", req_write(0x0550, [index, 0x8100])
                    )
                    await asyncio.sleep(MEASURE_WAIT)
                    await self._transact(f"bms{index}_state", req_read(0x0551, 1))
                    blocks = [
                        await self._transact(
                            f"bms{index}_block{n}", req_read(0x0558, 0x41)
                        )
                        for n in range(1, DETAIL_BLOCKS + 1)
                    ]
                    result[index] = parse_bms(index, blocks)
                return info, result
            finally:
                await self._close()
