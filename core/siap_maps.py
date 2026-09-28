"""SIAP data for the maps tab (tab 7), from the EloteSat 0.4.0 variant by
Claudia and Daniel (siap.py), trimmed to what the maps need.

Data: the `siap_avance` table of data/tamaulipas_elotesat.gpkg plus every
CSV downloaded with "Actualizar desde el SIAP", kept in the QGIS profile
folder (EloteSat/siap/). A downloaded cut replaces the shipped one.
"""

import datetime as dt
import math
import os
import re
import sqlite3
import unicodedata

from . import siap as siap_core
from .zones import DATA

CYCLES = {"OI": "Otoño - Invierno", "PV": "Primavera - Verano"}
REGIMES = {"riego": "Riego", "temporal": "Temporal"}
CROPS = {"maiz": "Maíz grano", "sorgo": "Sorgo grano"}
VARS = ("sembrada_ha", "cosechada_ha", "siniestrada_ha", "produccion")
SUMMARY_VARS = ("sembrada_ha", "cosechada_ha", "siniestrada_ha",
                "produccion", "rendimiento", "pct_siniestrada",
                "p50_siembra", "p50_cosecha")


def data_path():
    return DATA


def load(path=None):
    """All SIAP rows as dicts (only rows with a cut-off date): the shipped
    table, then the downloads in the profile folder (same key replaces)."""
    with _connect(path or data_path()) as c:
        c.row_factory = sqlite3.Row
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM siap_avance WHERE fecha_corte IS NOT NULL "
            "AND fecha_corte <> ''")]
    rows += siap_core.downloaded_rows_raw()
    out = {}
    for r in rows:
        if not r.get("cvegeo") or not r.get("fecha_corte"):
            continue
        r["fecha"] = dt.date.fromisoformat(str(r["fecha_corte"])[:10])
        for k in ("anio_agricola", "anio_consulta"):
            if r.get(k) not in (None, ""):
                r[k] = int(float(r[k]))
        for v in VARS:
            r[v] = float(r.get(v) or 0.0)
        key = (r["cvegeo"], str(r.get("anio_agricola")), r["ciclo"],
               r["modalidad"], r["cultivo"], r["fecha"])
        out[key] = r
    return list(out.values())


class SiapError(ValueError):
    pass


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode(
        "ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def _connect(path):
    if not os.path.exists(path):
        raise SiapError("no data: %s" % path)
    return sqlite3.connect(path)


def municipalities(path=None):
    """[(cvegeo, name)] sorted by name."""
    with _connect(path or data_path()) as c:
        rows = c.execute("SELECT cvegeo, municipio FROM municipios").fetchall()
    return sorted(rows, key=lambda r: norm(r[1]))


class Data:
    """SIAP rows indexed for quick queries."""

    def __init__(self, rows=None, path=None):
        self.path = path or data_path()
        self.rows = rows if rows is not None else load(self.path)
        self.queried = {int(r["anio_consulta"]) for r in self.rows
                        if r.get("anio_consulta") not in (None, "")}
        self.names = {}
        for r in self.rows:
            if r.get("cvegeo"):
                self.names[r["cvegeo"]] = r["municipio"]

    # ---- which cycles are complete
    def cycle_state(self, cycle, year):
        """(start_ok, end_ok): were the queries that hold the start and the
        end of this cycle downloaded?"""
        if cycle == "OI":
            return (year - 1) in self.queried, year in self.queried
        return year in self.queried, (year + 1) in self.queried

    def years(self, cycle):
        lab = CYCLES[cycle]
        return sorted({int(r["anio_agricola"]) for r in self.rows
                       if r["ciclo"] == lab and r.get("anio_agricola")})

    def complete_years(self, cycle):
        return [y for y in self.years(cycle) if all(self.cycle_state(cycle, y))]

    # ---- series
    def _select(self, cycle, year, regimes, crops, cvegeos=None):
        lab = CYCLES[cycle]
        regs = {REGIMES[r] for r in regimes}
        cps = {CROPS[c] for c in crops}
        return [r for r in self.rows
                if r["ciclo"] == lab and int(r["anio_agricola"] or 0) == year
                and r["modalidad"] in regs and r["cultivo"] in cps
                and (cvegeos is None or r["cvegeo"] in cvegeos)]

    def series(self, cycle, year, regimes, crops, cvegeos=None):
        """Sorted [(date, {var: value})] summed over the chosen
        municipalities, regimes and crops. A municipality missing from a
        cut-off counts as 0 (the web lists only non-zero rows)."""
        sel = self._select(cycle, year, regimes, crops, cvegeos)
        cuts = sorted({r["fecha"] for r in
                       self._select(cycle, year, regimes, crops)})
        acc = {d: {v: 0.0 for v in VARS} for d in cuts}
        for r in sel:
            for v in VARS:
                acc[r["fecha"]][v] += r[v]
        return [(d, acc[d]) for d in cuts]

    def closing(self, cycle, year, regimes, crops, cvegeos=None):
        s = self.series(cycle, year, regimes, crops, cvegeos)
        return s[-1][1] if s else None

    def value_at(self, cycle, year, regimes, crops, var, cut=None,
                 cvegeos=None):
        """Value at a cut-off (date) or at the close of the cycle (None)."""
        s = self.series(cycle, year, regimes, crops, cvegeos)
        if not s:
            return None
        if cut is None:
            return s[-1][1][var]
        for d, vals in s:
            if d == cut:
                return vals[var]
        return None

    def cutoffs(self, cycle, year):
        lab = CYCLES[cycle]
        return sorted({r["fecha"] for r in self.rows if r["ciclo"] == lab
                       and int(r["anio_agricola"] or 0) == year})


def anchor(cycle, year):
    """Day 0 of a cycle: 30 Sep of Y-1 (OI) or 31 Mar of Y (PV). The
    earliest SIAP cut-offs of a cycle are 31 Oct (OI) and 30 Apr (PV)."""
    return dt.date(year - 1, 9, 30) if cycle == "OI" else dt.date(year, 3, 31)


def fraction_curve(series, var, cycle, year, start_ok=True):
    """[(day, fraction of the closing value)] from day 0, linear between
    cut-offs (assumption: steady pace within a month). None if the closing
    value is 0. Without the start of the cycle the curve begins at the
    first cut-off (not at 0)."""
    if not series:
        return None
    total = series[-1][1][var]
    if total <= 0:
        return None
    a = anchor(cycle, year)
    pts = [(0, 0.0)] if start_ok else []
    for d, vals in series:
        pts.append(((d - a).days, min(1.0, vals[var] / total)))
    # cumulative figures can be revised down; keep the curve monotone
    out, top = [], 0.0
    for day, f in pts:
        top = max(top, f)
        out.append((day, top))
    return out


def curve_day(curve, p):
    """First day at which the curve reaches p (interpolated), or None."""
    if not curve or curve[0][1] >= p and curve[0][0] > 0:
        return None
    for i in range(1, len(curve)):
        (d0, f0), (d1, f1) = curve[i - 1], curve[i]
        if f1 >= p:
            return d0 + (0 if f1 == f0 else (p - f0) / (f1 - f0) * (d1 - d0))
    return None


def summary(data, cycle, year, regimes, crops, var, cut=None):
    """{cvegeo: value} for every municipality with data. `cut` is a
    cut-off date or None (close of the cycle). Dates (p50_*) come back as
    ISO strings; the rest as floats."""
    out = {}
    cvs = {r["cvegeo"] for r in data._select(cycle, year, regimes, crops)}
    start_ok = data.cycle_state(cycle, year)[0]
    for cv in cvs:
        s = data.series(cycle, year, regimes, crops, {cv})
        if cut is not None:
            s = [x for x in s if x[0] <= cut]
        if not s:
            continue
        last = s[-1][1]
        if var in VARS:
            val = last[var]
        elif var == "rendimiento":
            val = last["produccion"] / last["cosechada_ha"] \
                if last["cosechada_ha"] > 0 else None
        elif var == "pct_siniestrada":
            val = 100.0 * last["siniestrada_ha"] / last["sembrada_ha"] \
                if last["sembrada_ha"] > 0 else None
        elif var in ("p50_siembra", "p50_cosecha"):
            v = "sembrada_ha" if var == "p50_siembra" else "cosechada_ha"
            c = fraction_curve(s, v, cycle, year, start_ok)
            d = curve_day(c, 0.5)
            val = None if d is None else (anchor(cycle, year) + dt.timedelta(
                days=int(round(d)))).isoformat()
        else:
            raise SiapError("variable %r" % var)
        out[cv] = val
    return out


def cycle_warning(data, cycle, year):
    s, e = data.cycle_state(cycle, year)
    w = []
    if not s:
        w.append("start")
    if not e:
        w.append("end")
    return w


def write_csv(rows, path):
    import csv
    if not rows:
        open(path, "w").close()
        return path
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return path


def finite(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x))
