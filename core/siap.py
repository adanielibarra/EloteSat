"""SIAP 'Avance de Siembras y Cosechas' -> calendar profiles.

Input: the table exported from the Avance, by municipality, one row per
monthly cut (fecha_corte = last day of the month). The figures are
CUMULATIVE within the agricultural year (checked on the Tamaulipas
2023-2026 export: 530 of 530 series never decrease).

One profile per municipality and water regime (riego / temporal), WITHOUT
crop: maize and sorghum sown areas are added up. Per cycle (OI, PV):

  sowing:  dates when the cumulative sown area passes 10 %, 50 %, 90 %
           of its final value (linear interpolation between monthly cuts,
           i.e. constant pace within each month: an ASSUMPTION)
  harvest: the same for harvested area (50 %, 90 %)
  years:   median over the agricultural years with a complete series

Stages (every boundary but the sowing and harvest dates is an ASSUMPTION,
editable afterwards; the origin is stored with the profile):
  00_siembra_emergencia      S10 .. S90 + EMERGENCE_DAYS
  03_madurez_senescencia     H50 - MATURITY_DAYS .. H90
  01_vegetativo, 02_floracion_espigamiento: the time in between, split
                             in two equal halves

SIAP year vs EloteSat year: in SIAP, OI 2025 is sown from October 2024 to
March 2025 (year of the END of the cycle); PV 2025 is sown in 2025. In
EloteSat the cycle year is the year of its FIRST stage. See siap_year().
"""

import csv
import datetime as dt
import os
import statistics

from . import phenology

CROPS_DEFAULT = ("Maíz grano", "Sorgo grano")
MIN_HA = 500.0          # below this a cycle is left out of the profile
EMERGENCE_DAYS = 10     # [ASSUMPTION] sowing -> emergence
MATURITY_DAYS = 30      # [ASSUMPTION] start of maturity before H50
JUMP_SHARE = 0.5        # one closing cut adding more than this -> warning
MIN_CYCLE_DAYS = 90     # [ASSUMPTION] S50 -> H50 shorter: not credible
CYCLES = {"Otoño - Invierno": "OI", "Primavera - Verano": "PV"}
MODES = {"Riego": "riego", "Temporal": "temporal"}
STAGES = [s[0] for s in phenology.DEFAULT_CALENDAR["OI"]["stages"]]


class SiapError(Exception):
    pass


# ------------------------------------------------------------ reading
def norm_name(s):
    """Name key for matching SIAP municipality names with the layer:
    no accents, lower case, single spaces ("Soto La Marina" ==
    "Soto la Marina")."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode(
        "ascii", "ignore").decode()
    return " ".join(s.lower().split())


def read_avance(path=None, names=None):
    """Rows as dicts with cvegeo, municipio, anio_agricola (int), ciclo
    (OI/PV), modalidad (riego/temporal), cultivo, fecha (date), sembrada,
    cosechada. Reads the GeoPackage layer 'siap_avance' (default: the
    plugin data) or a CSV. A CSV without cvegeo (as written by the SIAP
    download) is matched by municipality name with `names` {cvegeo:
    name}. Rows with an 'aviso' or an unmatched name are dropped."""
    from .zones import DATA
    path = path or DATA
    if path.lower().endswith(".gpkg"):
        from osgeo import ogr
        ds = ogr.Open(path)
        if ds is None or ds.GetLayerByName("siap_avance") is None:
            raise SiapError("no 'siap_avance' layer in %s" % path)
        lyr = ds.GetLayerByName("siap_avance")
        raw = [{k: f[k] for k in f.keys()} for f in lyr]
    else:
        with open(path, newline="", encoding="utf-8-sig") as f:
            raw = list(csv.DictReader(f))
        if raw and "cvegeo" not in raw[0]:
            if names is None:
                names = municipio_names(DATA)
            by = {norm_name(v): k for k, v in names.items()}
            for r in raw:
                r["cvegeo"] = by.get(norm_name(r.get("municipio")), "")
    rows = []
    for r in raw:
        if (r.get("aviso") or "").strip():
            continue
        c = CYCLES.get(str(r.get("ciclo", "")).strip())
        m = MODES.get(str(r.get("modalidad", "")).strip())
        if not c or not m or not r.get("anio_agricola"):
            continue
        if not str(r.get("cvegeo") or "").strip():
            continue  # municipality name not matched
        try:
            rows.append({
                "cvegeo": str(r["cvegeo"]).strip(),
                "municipio": r.get("municipio", ""),
                "anio": int(float(r["anio_agricola"])),
                "ciclo": c, "modalidad": m,
                "cultivo": str(r["cultivo"]).strip(),
                "fecha": dt.date(*map(int, str(r["fecha_corte"])[:10]
                                      .split("-"))),
                "sembrada": float(r.get("sembrada_ha") or 0),
                "cosechada": float(r.get("cosechada_ha") or 0),
            })
        except (KeyError, ValueError):
            continue
    if not rows:
        raise SiapError("no usable rows")
    return rows


# ------------------------------------------------------------ curves
def series(rows, crops=CROPS_DEFAULT):
    """{(cvegeo, modalidad, ciclo, anio): [(fecha, sembrada, cosechada)]}
    with the chosen crops added up per cut, sorted by date.

    A municipality without a row in a cut that the export does contain
    for that cycle and year (for any municipality) had nothing sown yet:
    those earlier cuts are added as zeros, which anchors the start of the
    curve. Cuts after the last row are NOT filled (the data may simply
    end there)."""
    cuts = {}
    for r in rows:
        cuts.setdefault((r["ciclo"], r["anio"]), set()).add(r["fecha"])
    acc = {}
    for r in rows:
        if r["cultivo"] not in crops:
            continue
        k = (r["cvegeo"], r["modalidad"], r["ciclo"], r["anio"])
        d = acc.setdefault(k, {})
        s, c = d.get(r["fecha"], (0.0, 0.0))
        d[r["fecha"]] = (s + r["sembrada"], c + r["cosechada"])
    out = {}
    for k, d in acc.items():
        pts = sorted((f, s, c) for f, (s, c) in d.items())
        first = pts[0][0]
        allc = sorted(cuts[(k[2], k[3])])
        zeros = [(f, 0.0, 0.0) for f in allc if f < first]
        # if the export reaches the start of the cycle, nothing was sown
        # before its first cut: a zero at the end of the previous month
        if start_covered(k[2], k[3], allc[0]):
            z = allc[0].replace(day=1) - dt.timedelta(days=1)
            zeros = [(z, 0.0, 0.0)] + zeros
        out[k] = zeros + pts
    return out


def start_covered(ciclo, anio, first_cut):
    """Does the export include the start of the cycle? OI Y is sown from
    October of Y-1; PV Y from about June of Y (in Tamaulipas the PV
    cumulative is still near 0 at the end of May)."""
    if ciclo == "OI":
        return first_cut <= dt.date(anio - 1, 10, 31)
    return first_cut <= dt.date(anio, 5, 31)


def _cross(points, p):
    """Date when a cumulative series (dates, fractions 0..1) passes p.
    None if it is already above p at the first cut (start missing) or
    never reaches it."""
    if not points or points[0][1] >= p:
        return None
    for (d0, f0), (d1, f1) in zip(points, points[1:]):
        if f0 < p <= f1:
            w = (p - f0) / (f1 - f0)
            return d0 + dt.timedelta(days=round(w * (d1 - d0).days))
    return None


def cycle_dates(ser):
    """Sowing S10/S50/S90 and harvest H50/H90 for one series, plus
    warnings. Fractions of each series' own final value."""
    warn = []
    tot_s = max(s for _, s, _ in ser)
    tot_c = max(c for _, _, c in ser)
    out = {"sembrada": tot_s, "cosechada": tot_c}
    if tot_s <= 0:
        return out, ["sin siembra"]
    ps = [(f, s / tot_s) for f, s, _ in ser]
    for q, key in ((0.1, "S10"), (0.5, "S50"), (0.9, "S90")):
        out[key] = _cross(ps, q)
    if ps[0][1] > 0.1:
        warn.append("sin datos del arranque (primer corte %s ya al "
                    "%.0f %%)" % (ps[0][0], 100 * ps[0][1]))
    for (d0, f0), (d1, f1) in zip(ps, ps[1:]):
        # a big step that CLOSES the series looks like an administrative
        # catch-up (a big step in the middle is normal under irrigation)
        if f1 - f0 > JUMP_SHARE and f1 >= 0.999:
            warn.append("%.0f %% de la siembra en el corte que cierra la "
                        "serie (%s); puede ser un cierre administrativo"
                        % (100 * (f1 - f0), d1))
    if tot_c > 0:
        pc = [(f, c / tot_c) for f, _, c in ser]
        for q, key in ((0.5, "H50"), (0.9, "H90")):
            out[key] = _cross(pc, q)
        if pc[-1][1] < 0.9:
            warn.append("cosecha sin terminar en el último corte")
    else:
        warn.append("sin cosecha registrada")
    return out, warn


# ------------------------------------------------------------ years
def _ref(ciclo, anio):
    """Origin to average dates of different years: OI from 1 August of
    the year before the SIAP year, PV from 1 January of the SIAP year."""
    return dt.date(anio - 1, 8, 1) if ciclo == "OI" else dt.date(anio, 1, 1)


def median_dates(per_year, ciclo):
    """{key: median offset} from {anio: {key: date}}; returns dates in a
    reference year (for MM-DD) and the years used per key."""
    out, used = {}, {}
    for key in ("S10", "S50", "S90", "H50", "H90"):
        offs, yrs = [], []
        for anio, d in per_year.items():
            if d.get(key):
                offs.append((d[key] - _ref(ciclo, anio)).days)
                yrs.append(anio)
        if offs:
            ref = _ref(ciclo, 2001)
            out[key] = ref + dt.timedelta(days=round(statistics.median(offs)))
            used[key] = sorted(yrs)
    return out, used


def _mmdd(d):
    return "%02d-%02d" % (d.month, d.day)


def stages_from(dates, emergence=EMERGENCE_DAYS, maturity=MATURITY_DAYS):
    """Four stages from S10, S90, H50, H90 (dates in a reference year).
    Returns (stages, origins) or raises SiapError if dates are missing."""
    need = ("S10", "S90", "H50", "H90")
    miss = [k for k in need if k not in dates]
    if miss:
        raise SiapError("faltan %s" % ",".join(miss))
    s10, s90, h50, h90 = (dates[k] for k in need)
    e0 = s90 + dt.timedelta(days=emergence)
    m0 = h50 - dt.timedelta(days=maturity)
    if m0 <= e0 + dt.timedelta(days=2):
        # very short cycle: split the gap in the middle
        mid = e0 + (h50 - e0) / 2
        e0, m0 = mid - dt.timedelta(days=1), mid + dt.timedelta(days=1)
    mid = e0 + (m0 - e0) / 2
    one = dt.timedelta(days=1)
    b = [(s10, e0), (e0 + one, mid), (mid + one, m0 - one), (m0, h90)]
    if h90 <= m0:
        raise SiapError("cosecha antes de la madurez")
    stages = [[n, _mmdd(a), _mmdd(z)] for n, (a, z) in zip(STAGES, b)]
    origins = ["siap: S10 .. S90 + %d d" % emergence,
               "estimada: mitad entre emergencia y madurez",
               "estimada: mitad entre emergencia y madurez",
               "siap: H50 - %d d .. H90" % maturity]
    return stages, origins


# ------------------------------------------------------------ profiles
def build_profiles(rows, names=None, crops=CROPS_DEFAULT, min_ha=MIN_HA,
                   emergence=EMERGENCE_DAYS, maturity=MATURITY_DAYS):
    """{profile_name: profile} and a report list. names: {cvegeo: name}."""
    names = names or {}
    for r in rows:
        names.setdefault(r["cvegeo"], r["municipio"])
    ser = series(rows, crops)
    per_crop = {c: series(rows, (c,)) for c in crops}
    groups = {}
    for (cv, mod, cic, anio), s in ser.items():
        groups.setdefault((cv, mod), {}).setdefault(cic, {})[anio] = s
    profiles, report = {}, []
    for (cv, mod), cycles in sorted(groups.items()):
        cyc_out, siap_meta, warnings = {}, {}, []
        for cic, years in sorted(cycles.items()):
            per_year, areas = {}, []
            for anio, s in sorted(years.items()):
                d, w = cycle_dates(s)
                areas.append(d.get("sembrada", 0))
                warnings += ["%s %d: %s" % (cic, anio, x) for x in w]
                per_year[anio] = d
            area = statistics.median(areas) if areas else 0
            if area < min_ha:
                report.append((cv, mod, cic, "omitido: %.0f ha < %.0f"
                               % (area, min_ha)))
                continue
            med, used = median_dates(per_year, cic)
            if "S50" in med and "H50" in med:
                length = (med["H50"] - med["S50"]).days
                if length < MIN_CYCLE_DAYS:
                    warnings.append(
                        "%s: de siembra al 50 %% a cosecha al 50 %% solo "
                        "%d días; no cuadra con maíz o sorgo de grano. "
                        "Las fechas del Avance pueden reflejar cuándo se "
                        "registró, no cuándo se sembró. REVISAR"
                        % (cic, length))
            try:
                stages, origins = stages_from(med, emergence, maturity)
            except SiapError as e:
                report.append((cv, mod, cic, "omitido: %s" % e))
                continue
            crop_meta = {}
            for c in crops:
                py = {}
                for anio in years:
                    s = per_crop[c].get((cv, mod, cic, anio))
                    if s:
                        py[anio] = cycle_dates(s)[0]
                cm, cu = median_dates(py, cic)
                crop_meta[c] = {k: _mmdd(v) for k, v in cm.items()}
                crop_meta[c]["anios"] = sorted({a for v in cu.values()
                                                for a in v})
            label = "%s %s, SIAP %s" % (
                "Otoño-Invierno" if cic == "OI" else "Primavera-Verano",
                mod, ",".join(map(str, sorted({a for v in used.values()
                                               for a in v}))))
            cyc_out[cic] = {"label": label, "stages": stages,
                            "origin": origins}
            siap_meta[cic] = {"fechas": {k: _mmdd(v) for k, v in
                                         med.items()},
                              "anios": {k: v for k, v in used.items()},
                              "sembrada_mediana_ha": round(area, 1),
                              "por_cultivo": crop_meta}
            report.append((cv, mod, cic, "ok: %.0f ha" % area))
        if not cyc_out:
            continue
        name = "siap_%s_%s_%s" % (cv, _slug(names.get(cv, "")), mod)
        prof = phenology.new_profile(
            cyc_out, note="SIAP Avance de Siembras y Cosechas, %s, %s; "
            "cultivos: %s; emergencia +%d d y madurez -%d d SUPUESTOS"
            % (names.get(cv, cv), mod, " + ".join(crops), emergence,
               maturity))
        prof["siap"] = {"cvegeo": cv, "municipio": names.get(cv, ""),
                        "modalidad": mod, "cultivos": list(crops),
                        "ciclos": siap_meta, "avisos": warnings,
                        "supuestos": {"emergencia_dias": emergence,
                                      "madurez_dias": maturity,
                                      "ritmo": "constante dentro de cada "
                                               "mes (interpolación lineal)"}}
        phenology.validate_profile(prof)
        profiles[name] = prof
    return profiles, report


def _slug(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return "".join(ch if ch.isalnum() else "_" for ch in s).strip("_")


def siap_year(cycle, cal, elotesat_year):
    """SIAP agricultural year of a EloteSat cycle: OI -> year in which the
    cycle ends; PV -> year in which it starts."""
    w = phenology.windows(cal, cycle, elotesat_year)
    return w[-1][2].year if cycle == "OI" else w[0][1].year


def elotesat_year(cycle, cal, siap_anio):
    """Inverse of siap_year: the EloteSat year whose cycle is SIAP's."""
    for y in (siap_anio - 1, siap_anio):
        if siap_year(cycle, cal, y) == siap_anio:
            return y
    return siap_anio


def municipio_names(gpkg):
    from osgeo import ogr
    ds = ogr.Open(gpkg)
    return {f["cvegeo"]: f["municipio"] for f in ds.GetLayer("municipios")}


def import_file(path=None, gpkg_mun=None, extra=None, **kw):
    """Profiles from a SIAP table (default: plugin data) plus, optionally,
    the rows of `extra` files (downloads) that replace or add cuts."""
    rows = read_avance(path)
    if extra is None:
        extra = downloaded_csvs()
    for e in extra or []:
        rows = merge(rows, read_avance(e))
    gpkg_mun = gpkg_mun or zones_data()
    names = municipio_names(gpkg_mun) if os.path.exists(gpkg_mun) else {}
    return build_profiles(rows, names, **kw)


def unmatched_names(path, names=None):
    """SIAP municipality names in a CSV that do not match the layer."""
    from .zones import DATA
    names = names or municipio_names(DATA)
    keys = {norm_name(v) for v in names.values()}
    with open(path, newline="", encoding="utf-8-sig") as f:
        return sorted({r["municipio"] for r in csv.DictReader(f)
                       if r.get("municipio") and
                       norm_name(r["municipio"]) not in keys})


def merge(base, new):
    """Rows of `new` replace rows of `base` with the same municipality,
    agricultural year, cycle, regime, crop and cut."""
    def key(r):
        return (r["cvegeo"], r["anio"], r["ciclo"], r["modalidad"],
                r["cultivo"], r["fecha"])
    d = {key(r): r for r in base}
    for r in new:
        d[key(r)] = r
    return list(d.values())



def zones_data():
    from .zones import DATA
    return DATA


# ------------------------------------------------------------ downloads
def profile_dir():
    """Folder for SIAP downloads in the QGIS profile (survives plugin
    updates; the shipped data are never modified)."""
    try:
        from qgis.core import QgsApplication
        base = QgsApplication.qgisSettingsDirPath()
    except Exception:
        base = ""
    base = base or os.path.join(os.path.expanduser("~"), ".elotesat")
    d = os.path.join(base, "EloteSat", "siap")
    os.makedirs(d, exist_ok=True)
    return d


def downloaded_csvs():
    """CSV downloads in the profile folder, plus those made when the
    plugin was called FenoSat (FenoSat/siap), which are never moved."""
    d = profile_dir()
    old = os.path.join(os.path.dirname(os.path.dirname(d)), "FenoSat",
                       "siap")
    out = []
    # old folder first: a later (newer) file replaces the same cut
    if os.path.isdir(old):
        out += sorted(os.path.join(old, n) for n in os.listdir(old)
                      if n.lower().endswith(".csv"))
    out += sorted(os.path.join(d, n) for n in os.listdir(d)
                  if n.lower().endswith(".csv"))
    return out


def downloaded_rows_raw(names=None):
    """Rows of every downloaded CSV as raw dicts with cvegeo (matched by
    name); rows with an 'aviso' or an unmatched name are dropped."""
    out = []
    names = names
    for p in downloaded_csvs():
        if names is None:
            names = municipio_names(zones_data())
        by = {norm_name(v): k for k, v in names.items()}
        with open(p, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if (r.get("aviso") or "").strip():
                    continue
                r["cvegeo"] = by.get(norm_name(r.get("municipio")), "")
                if r["cvegeo"]:
                    out.append(r)
    return out
