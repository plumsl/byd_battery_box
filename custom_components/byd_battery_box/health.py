"""Battery health analysis (no Home Assistant dependency, state is a plain dict).

Ideas
-----
* Relative capacity: the BMS modules of an LVL system are connected in parallel and
  therefore always share the same terminal voltage. Between two full charges every module
  is cycled through the same voltage window, so the energy each module delivers is
  proportional to its usable capacity - independent of the BMS' own SOC estimate.
* Current share: instantaneous share of the total current. It reflects capacity AND
  internal/connection resistance; a slow drift points to a deteriorating connection.
* Weakest cell: a low-capacity cell is the first to rise at the top of charge and the
  first to fall near the bottom. Deviations from the module mean are averaged at both ends.
* Internal resistance (experimental): dU/dI between two consecutive measurements with a
  load step in the flat part of the LFP curve.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Any

FULL_SOC = 99.5          # BMS SOC (0.1 % resolution) counted as "full"
FULL_RELEASE_SOC = 97.0  # leave the full state below this
MIN_CYCLE_DEPTH = 20.0   # % SOC a cycle must cover to be evaluated
MAX_CYCLE_DAYS = 7
CYCLES_KEPT = 30
CYCLES_USED = 10

TOP_SOC = 98.0           # snapshot "top of charge"
BOTTOM_SOC = 25.0        # snapshot "bottom"
EMA_ALPHA = 0.1
SHARE_MIN_CURRENT = 15.0  # A, total current needed for a current-share sample
SHARE_ALPHA = 0.02

R_SOC_MIN, R_SOC_MAX = 25.0, 85.0
R_MIN_STEP = 8.0          # A per BMS
R_MAX_GAP = timedelta(minutes=12)
R_MAX_SOC_DRIFT = 1.0
R_SAMPLES_KEPT = 100
R_MIN_SAMPLES = 5
MIN_SNAPSHOTS = 3


def empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "full": None,       # currently in full state?
        "cycle": None,      # open cycle {start, dis{}, chg{}, soc_min}
        "cycles": [],       # completed cycles
        "cells": {},        # bms -> {top:[16], n_top, bot:[16], n_bot}
        "share": {},        # bms -> {ema, n, last}
        "r": {},            # bms -> [mOhm]
        "prev": {},         # bms -> {t, soc, i, u}
    }


class HealthModel:
    """Feeds on every BMS detail update. All results are derived from `state`."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.state = state if state and state.get("version") == 1 else empty_state()

    # ------------------------------------------------------------------ update
    def update(self, now: datetime, bms: dict[int, Any]) -> None:
        if not bms:
            return
        self._cycle(now, bms)
        self._cells(bms)
        self._share(bms)
        self._resistance(now, bms)

    def _cycle(self, now: datetime, bms: dict[int, Any]) -> None:
        st = self.state
        socs = [b.soc for b in bms.values()]
        is_full = min(socs) >= FULL_SOC
        was_full = st["full"]
        if st["cycle"] is not None:
            st["cycle"]["soc_min"] = min(st["cycle"]["soc_min"], min(socs))
        if is_full and not was_full:
            self._close_cycle(now, bms)
            st["cycle"] = {
                "start": now.isoformat(),
                "dis": {str(i): b.discharge_energy for i, b in bms.items()},
                "chg": {str(i): b.charge_energy for i, b in bms.items()},
                "soc_min": min(socs),
            }
        if is_full:
            st["full"] = True
        elif max(socs) < FULL_RELEASE_SOC:
            st["full"] = False
        elif was_full is None:
            st["full"] = False

    def _close_cycle(self, now: datetime, bms: dict[int, Any]) -> None:
        cyc = self.state["cycle"]
        if not cyc:
            return
        start = datetime.fromisoformat(cyc["start"])
        depth = 100 - cyc["soc_min"]
        dis = {k: round(bms[int(k)].discharge_energy - v, 3) for k, v in cyc["dis"].items() if int(k) in bms}
        chg = {k: round(bms[int(k)].charge_energy - v, 3) for k, v in cyc["chg"].items() if int(k) in bms}
        if (
            depth < MIN_CYCLE_DEPTH
            or now - start > timedelta(days=MAX_CYCLE_DAYS)
            or sum(dis.values()) <= 0
            or any(v < 0 for v in dis.values())
        ):
            return
        self.state["cycles"] = (self.state["cycles"] + [{
            "start": cyc["start"], "end": now.isoformat(), "depth": round(depth, 1),
            "dis": dis, "chg": chg,
        }])[-CYCLES_KEPT:]

    def _cells(self, bms: dict[int, Any]) -> None:
        for i, b in bms.items():
            c = self.state["cells"].setdefault(str(i), {"top": None, "n_top": 0, "bot": None, "n_bot": 0})
            mean = sum(b.cell_voltages) / len(b.cell_voltages)
            dev = [v - mean for v in b.cell_voltages]
            if b.soc >= TOP_SOC and b.current <= 0:      # end of charge
                key = "top"
            elif b.soc <= BOTTOM_SOC and b.current >= 0:  # deep discharge
                key = "bot"
            else:
                continue
            old = c[key]
            c[key] = dev if old is None else [o + EMA_ALPHA * (d - o) for o, d in zip(old, dev)]
            c[f"n_{key}"] += 1

    def _share(self, bms: dict[int, Any]) -> None:
        total = sum(b.current for b in bms.values())
        if abs(total) < SHARE_MIN_CURRENT:
            return
        for i, b in bms.items():
            s = self.state["share"].setdefault(str(i), {"ema": None, "n": 0, "last": None})
            share = 100 * b.current / total
            s["last"] = round(share, 2)
            s["ema"] = share if s["ema"] is None else s["ema"] + SHARE_ALPHA * (share - s["ema"])
            s["n"] += 1

    def _resistance(self, now: datetime, bms: dict[int, Any]) -> None:
        for i, b in bms.items():
            key = str(i)
            cur = {"t": now.isoformat(), "soc": b.soc, "i": b.current, "u": sum(b.cell_voltages)}
            prev = self.state["prev"].get(key)
            self.state["prev"][key] = cur
            if not prev:
                continue
            gap = now - datetime.fromisoformat(prev["t"])
            d_i = cur["i"] - prev["i"]
            if (
                gap > R_MAX_GAP
                or abs(d_i) < R_MIN_STEP
                or abs(cur["soc"] - prev["soc"]) > R_MAX_SOC_DRIFT
                or not (R_SOC_MIN <= cur["soc"] <= R_SOC_MAX)
            ):
                continue
            r = -(cur["u"] - prev["u"]) / d_i  # mV / A = mOhm, positive current = discharge
            if 0 < r < 200:
                lst = self.state["r"].setdefault(key, [])
                lst.append(round(r, 2))
                del lst[:-R_SAMPLES_KEPT]

    # ----------------------------------------------------------------- results
    def relative_capacity(self, index: int, bms: dict[int, Any]) -> tuple[float | None, dict[str, Any]]:
        """Capacity of one BMS relative to the average of all (100 % = average)."""
        n = len(bms)
        attrs: dict[str, Any] = {}
        total = sum(b.discharge_energy for b in bms.values())
        if total > 0 and index in bms:
            attrs["lifetime"] = round(100 * n * bms[index].discharge_energy / total, 2)
        cycles = self.state["cycles"][-CYCLES_USED:]
        sums: dict[str, float] = {}
        for c in cycles:
            for k, v in c["dis"].items():
                sums[k] = sums.get(k, 0) + v
        tot = sum(sums.values())
        attrs["cycles_used"] = len(cycles)
        if cycles:
            last = cycles[-1]
            ltot = sum(last["dis"].values())
            if ltot > 0 and str(index) in last["dis"]:
                attrs["last_cycle"] = round(100 * n * last["dis"][str(index)] / ltot, 2)
                attrs["last_cycle_end"] = last["end"]
                attrs["last_cycle_depth"] = last["depth"]
        if len(cycles) >= MIN_SNAPSHOTS and tot > 0 and str(index) in sums:
            attrs["source"] = "cycles"
            return round(100 * n * sums[str(index)] / tot, 1), attrs
        if "lifetime" in attrs:
            attrs["source"] = "lifetime_counters"
            return round(attrs["lifetime"], 1), attrs
        return None, attrs

    def current_share(self, index: int) -> tuple[float | None, dict[str, Any]]:
        s = self.state["share"].get(str(index))
        if not s or s["ema"] is None:
            return None, {}
        return round(s["ema"], 1), {"last_sample": s["last"], "samples": s["n"]}

    def weakest_cell(self, index: int) -> tuple[int | None, dict[str, Any]]:
        c = self.state["cells"].get(str(index))
        if not c or (c["n_top"] < MIN_SNAPSHOTS and c["n_bot"] < MIN_SNAPSHOTS):
            n = (c or {}).get("n_top", 0)
            return None, {"top_snapshots": n, "bottom_snapshots": (c or {}).get("n_bot", 0)}
        top = c["top"] if c["n_top"] >= MIN_SNAPSHOTS else [0.0] * len(c["top"] or c["bot"])
        bot = c["bot"] if c["n_bot"] >= MIN_SNAPSHOTS else [0.0] * len(top)
        score = [t - b for t, b in zip(top, bot)]
        worst = max(range(len(score)), key=lambda k: score[k])
        ranking = sorted(range(len(score)), key=lambda k: -score[k])[:3]
        return worst + 1, {
            "score_mv": round(score[worst], 1),
            "ranking": [r + 1 for r in ranking],
            "scores_mv": [round(s, 1) for s in score],
            "top_snapshots": c["n_top"],
            "bottom_snapshots": c["n_bot"],
        }

    def internal_resistance(self, index: int) -> tuple[float | None, dict[str, Any]]:
        lst = self.state["r"].get(str(index), [])
        if len(lst) < R_MIN_SAMPLES:
            return None, {"samples": len(lst)}
        return round(median(lst), 1), {"samples": len(lst)}

    def last_cycle(self) -> tuple[float | None, dict[str, Any]]:
        if not self.state["cycles"]:
            return None, {}
        c = self.state["cycles"][-1]
        return round(sum(c["dis"].values()), 2), {
            "start": c["start"], "end": c["end"], "depth": c["depth"],
            "per_bms": c["dis"], "cycles_recorded": len(self.state["cycles"]),
        }
