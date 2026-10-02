"""Tests for the health model with synthetic cycles (3 parallel BMS, BMS 1 has 95 % capacity)."""

import importlib.util
import pathlib
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace

ROOT = pathlib.Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("health", ROOT / "custom_components/byd_battery_box/health.py")
health = importlib.util.module_from_spec(spec)
sys.modules["health"] = health
spec.loader.exec_module(health)

CAP = {1: 0.95, 2: 1.0, 3: 1.0}
R = {1: 8.0, 2: 6.0, 3: 6.0}   # mOhm


def snapshot(soc, total_current, counters, weak_cell=None):
    """BMS objects at a common SOC; current split by capacity."""
    out = {}
    tot_cap = sum(CAP.values())
    for i, cap in CAP.items():
        cur = total_current * cap / tot_cap
        ocv = 3300 + (soc - 50) * 0.5
        cells = [ocv - R[i] / 16 * cur] * 16
        if weak_cell and i == 2:
            if soc >= 98:
                cells[weak_cell - 1] += 25
            elif soc <= 25:
                cells[weak_cell - 1] -= 30
        out[i] = SimpleNamespace(soc=soc, current=cur, cell_voltages=cells,
                                 discharge_energy=counters[i][0], charge_energy=counters[i][1])
    return out


def run_cycles(model, n_cycles, depth=60, weak_cell=None):
    t = datetime(2026, 10, 1, 12, 0)
    counters = {i: [1000.0, 1100.0] for i in CAP}
    for _ in range(n_cycles):
        # full, charging end
        for _ in range(4):
            model.update(t, snapshot(100.0, -5, counters, weak_cell)); t += timedelta(minutes=5)
        # discharge with load steps
        soc = 100.0
        k = 0
        while soc > 100 - depth:
            cur = 40 if k % 2 else 10
            for i in CAP:
                counters[i][0] += 46.08 * CAP[i] / 3 * 1.0 / 100  # 1 % of module energy
            soc -= 1.0
            model.update(t, snapshot(soc, cur, counters, weak_cell)); t += timedelta(minutes=5); k += 1
        # charge back
        while soc < 99:
            for i in CAP:
                counters[i][1] += 46.08 * CAP[i] / 3 * 2 / 100 / 0.95
            soc = min(100.0, soc + 2)
            model.update(t, snapshot(soc, -40, counters, weak_cell)); t += timedelta(minutes=5)
    model.update(t, snapshot(100.0, -5, counters, weak_cell))  # closes the last cycle
    return model


def test_relative_capacity_from_cycles():
    m = run_cycles(health.HealthModel(), 4)
    bms = snapshot(100, 0, {i: [2000, 2000] for i in CAP})
    v1, a1 = health.HealthModel(m.state).relative_capacity(1, bms)
    v2, _ = m.relative_capacity(2, bms)
    assert a1["source"] == "cycles" and a1["cycles_used"] == 4
    assert 96.0 < v1 < 97.5 and 101 < v2 < 102   # 0.95 / mean(0.95,1,1) = 96.6 %
    last, attrs = m.last_cycle()
    assert attrs["depth"] >= 59 and abs(last - 46.08 * 0.983 * 0.6) < 1


def test_relative_capacity_falls_back_to_counters():
    m = health.HealthModel()
    bms = {i: SimpleNamespace(discharge_energy=e) for i, e in {1: 3495.2, 2: 3664.2, 3: 3634.2}.items()}
    v, a = m.relative_capacity(1, bms)
    assert a["source"] == "lifetime_counters" and abs(v - 97.15) < 0.1


def test_shallow_cycles_are_ignored():
    m = run_cycles(health.HealthModel(), 3, depth=10)
    assert m.state["cycles"] == []


def test_current_share_and_resistance():
    m = run_cycles(health.HealthModel(), 2)
    share, a = m.current_share(1)
    assert 31.5 < share < 32.5 and a["samples"] > 50
    r1, ra = m.internal_resistance(1)
    r2, _ = m.internal_resistance(2)
    assert ra["samples"] >= 5 and 7.0 < r1 < 9.0 and 5.0 < r2 < 7.0


def test_weakest_cell():
    m = health.HealthModel()
    for _ in range(3):
        run_cycles(m, 1, depth=80, weak_cell=6)
    cell, a = m.weakest_cell(2)
    assert cell == 6 and a["score_mv"] > 40
    none, a = health.HealthModel().weakest_cell(1)
    assert none is None
