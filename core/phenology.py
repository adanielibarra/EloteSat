"""Crop calendar: stages as date windows per cycle, and the stage folders.

A cycle (OI = otoño-invierno, PV = primavera-verano) is a list of stages
(folder name, start MM-DD, end MM-DD), in order. For a cycle year Y the
first stage starts in Y; any later date whose MM-DD is earlier than that
start falls in Y+1, so a cycle can cross New Year.

The default windows are a STARTING POINT written from general knowledge of
the Tamaulipas calendar (OI irrigated in the north, PV rain-fed in the
centre/south). They are not taken from a verified source: check them
against SIAP/SADER or the irrigation district calendar and edit them.
"""

import csv
import datetime as dt
import json
import os
import re
import shutil

OUT_OF_STAGE = "fuera_de_etapa"

DEFAULT_CALENDAR = {
    "OI": {
        "label": "Otoño-Invierno (riego, norte) [VERIFICAR]",
        "stages": [
            ["00_siembra_emergencia", "01-15", "02-28"],
            ["01_vegetativo", "03-01", "04-10"],
            ["02_floracion_espigamiento", "04-11", "05-15"],
            ["03_madurez_senescencia", "05-16", "07-15"],
        ],
    },
    "PV": {
        "label": "Primavera-Verano (temporal, centro-sur) [VERIFICAR]",
        "stages": [
            ["00_siembra_emergencia", "06-15", "07-31"],
            ["01_vegetativo", "08-01", "09-10"],
            ["02_floracion_espigamiento", "09-11", "10-15"],
            ["03_madurez_senescencia", "10-16", "12-15"],
        ],
    },
}

_NAME_OK = re.compile(r"^[A-Za-z0-9_\-]+$")


class CalendarError(ValueError):
    pass


def copy_calendar(cal=None):
    return json.loads(json.dumps(cal or DEFAULT_CALENDAR))


def _mmdd(s):
    m = re.match(r"^(\d{2})-(\d{2})$", str(s).strip())
    if not m:
        raise CalendarError("MM-DD: %r" % s)
    mo, d = int(m.group(1)), int(m.group(2))
    try:
        dt.date(2001, mo, d)  # non-leap year: 02-29 not allowed
    except ValueError:
        raise CalendarError("MM-DD: %r" % s)
    return mo, d


def windows(cal, cycle, year):
    """[(stage, date_start, date_end)] for cycle year `year`."""
    stages = cal[cycle]["stages"]
    if not stages:
        raise CalendarError("empty cycle %s" % cycle)
    first = _mmdd(stages[0][1])
    out = []
    for name, s, e in stages:
        ms, me = _mmdd(s), _mmdd(e)
        ys = year + (1 if ms < first else 0)
        ye = year + (1 if me < first else 0)
        ds, de = dt.date(ys, *ms), dt.date(ye, *me)
        if de < ds:
            ye += 1
            de = dt.date(ye, *me)
        out.append((name, ds, de))
    return out


def validate(cal):
    """Raise CalendarError if names are not folder-safe, windows are empty,
    out of order or overlap. Gaps are allowed (dates go to OUT_OF_STAGE)."""
    for cycle, spec in cal.items():
        if not _NAME_OK.match(cycle):
            raise CalendarError("cycle name %r" % cycle)
        names = [s[0] for s in spec.get("stages", [])]
        if len(set(names)) != len(names):
            raise CalendarError("%s: repeated stage names" % cycle)
        for n in names:
            if not _NAME_OK.match(n) or n == OUT_OF_STAGE:
                raise CalendarError("%s: stage name %r" % (cycle, n))
        w = windows(cal, cycle, 2001)
        for i, (n, ds, de) in enumerate(w):
            if i and ds <= w[i - 1][2]:
                raise CalendarError("%s: %s overlaps or goes before %s"
                                    % (cycle, n, w[i - 1][0]))
        if w[-1][2] - w[0][1] > dt.timedelta(days=366):
            raise CalendarError("%s: longer than one year" % cycle)
    return True


def span(cal, cycle, year):
    w = windows(cal, cycle, year)
    return w[0][1], w[-1][2]


def assign(date, cal, cycle, year):
    """Stage name for a date (datetime.date or 'YYYY-MM-DD')."""
    if isinstance(date, str):
        date = dt.date(*map(int, date[:10].split("-")))
    for name, ds, de in windows(cal, cycle, year):
        if ds <= date <= de:
            return name
    return OUT_OF_STAGE


def cycle_dir(out_dir, cycle, year):
    return os.path.join(out_dir, "%s_%d" % (cycle, year))


def stage_dir(out_dir, cycle, year, stage, sensor):
    return os.path.join(cycle_dir(out_dir, cycle, year), stage, sensor)


def save_calendar(cal, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cal, f, ensure_ascii=False, indent=2)


def load_calendar(path):
    with open(path, encoding="utf-8") as f:
        cal = json.load(f)
    validate(cal)
    return cal


def reorganize(out_dir, cal, cycle, year, feedback=None):
    """Move the files listed in the cycle manifest to the stage folders of
    `cal` (after editing the windows). Never overwrites: a file whose
    destination exists is left where it is and reported. Rewrites the
    manifest with the new stage and paths. Returns (moved, kept, problems).
    """
    log = feedback or (lambda m: None)
    cdir = cycle_dir(out_dir, cycle, year)
    man = os.path.join(cdir, "manifest.csv")
    if not os.path.exists(man):
        raise FileNotFoundError(man)
    with open(man, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        fields = rd.fieldnames
        rows = list(rd)
    moved = kept = 0
    problems = []
    touched = set()
    for r in rows:
        if r.get("status") != "ok" or not r.get("files"):
            continue
        new_stage = assign(r["date"], cal, cycle, year)
        if new_stage == r.get("stage"):
            kept += 1
            continue
        src_dir = stage_dir(out_dir, cycle, year, r["stage"], r["sensor"])
        dst_dir = stage_dir(out_dir, cycle, year, new_stage, r["sensor"])
        names = r["files"].split(";")
        clash = [n for n in names if os.path.exists(os.path.join(dst_dir, n))]
        missing = [n for n in names
                   if not os.path.exists(os.path.join(src_dir, n))]
        if clash or missing:
            problems.append("%s: %s" % (r["scene_id"],
                                        "exists " + ",".join(clash) if clash
                                        else "missing " + ",".join(missing)))
            continue
        os.makedirs(dst_dir, exist_ok=True)
        for n in names:
            shutil.move(os.path.join(src_dir, n), os.path.join(dst_dir, n))
        touched.update((src_dir, dst_dir))
        log("%s: %s -> %s" % (r["date"], r["stage"], new_stage))
        r["stage"] = new_stage
        moved += 1
    tmp = man + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, man)
    save_calendar(cal, os.path.join(cdir, "calendario.json"))
    if touched:
        from .downloader import build_mosaics
        for d in touched:
            build_mosaics(d, feedback)
    # drop stage folders left empty
    for root, dirs, files in sorted(os.walk(cdir), reverse=True):
        if root != cdir and not os.listdir(root):
            os.rmdir(root)
    return moved, kept, problems


# ------------------------------------------------------------ profiles
# A profile = one region's calendar (both cycles) plus, optionally, the
# expected green-up and peak windows of maize and sorghum. The reference
# windows are for INTERPRETATION only (does a pixel's curve fit what we
# expect of maize or sorghum?); they are never used to file images nor as
# model variables. They ship EMPTY: fill them from field data or from a
# verified source.
CROPS = ("maiz", "sorgo")
REF_KEYS = ("arranque", "maximo")
DEFAULT_PROFILE = "generico_VERIFICAR"


def empty_references():
    return {c: {k: ["", ""] for k in REF_KEYS} for c in CROPS}


def new_profile(cycles=None, note="", references=None):
    return {"note": note, "cycles": copy_calendar(cycles),
            "references": json.loads(json.dumps(references or
                                                empty_references()))}


def default_profiles():
    return {DEFAULT_PROFILE: new_profile(
        note="Calendario de partida sin verificar. Duplícalo para cada "
             "región (p. ej. norte_riego, centro_sur_temporal) y ajusta "
             "las fechas.")}


def refs_for_cycle(refs, cycle):
    """References may be flat ({crop: ...}, same for every cycle, as in
    0.3.0) or per cycle ({"OI": {crop: ...}, "PV": ...})."""
    refs = refs or {}
    if any(k in CROPS for k in refs):
        return refs
    return refs.get(cycle) or {}


def _check_refs(refs, where=""):
    for crop, spec in refs.items():
        if crop not in CROPS:
            raise CalendarError("unknown crop %r%s" % (crop, where))
        for k, pair in spec.items():
            if k not in REF_KEYS:
                raise CalendarError("unknown reference %r" % k)
            a, b = (list(pair) + ["", ""])[:2]
            if bool(a) != bool(b):
                raise CalendarError("%s %s: give both dates or none"
                                    % (crop, k))
            if a:
                _mmdd(a)
                _mmdd(b)


def _check_offsets(offs):
    for cycle, crops in (offs or {}).items():
        for crop, spec in crops.items():
            if crop not in CROPS:
                raise CalendarError("unknown crop %r" % crop)
            for k, pair in spec.items():
                if k not in REF_KEYS:
                    raise CalendarError("unknown offset %r" % k)
                a, b = (list(pair) + ["", ""])[:2]
                if (a in ("", None)) != (b in ("", None)):
                    raise CalendarError("%s %s: give both offsets or none"
                                        % (crop, k))
                if a not in ("", None) and int(b) < int(a):
                    raise CalendarError("%s %s: max < min" % (crop, k))


def validate_profile(p):
    validate(p["cycles"])
    refs = p.get("references") or {}
    if any(k in CROPS for k in refs):
        _check_refs(refs)
    else:
        for cycle, r in refs.items():
            _check_refs(r or {}, " in %s" % cycle)
    _check_offsets(p.get("offsets"))
    return True


def references_from_siap(profile, cycle, offsets):
    """Crop references of one cycle from the SIAP sowing window of each
    crop and the sowing->green-up / sowing->peak offsets (days, ASSUMED):
        arranque = [S10 + min, S90 + max], maximo = [S10 + min, S90 + max]
    Returns ({crop: {"arranque": [mmdd, mmdd], "maximo": [...]}}, notes).
    Crops or offsets missing are left empty and reported."""
    meta = ((profile.get("siap") or {}).get("ciclos") or {}).get(cycle)
    if not meta:
        raise CalendarError("the profile has no SIAP data for %s" % cycle)
    out, notes = {}, []
    for crop in CROPS:
        name = {"maiz": "Maíz grano", "sorgo": "Sorgo grano"}[crop]
        pc = (meta.get("por_cultivo") or {}).get(name) or {}
        spec = {k: ["", ""] for k in REF_KEYS}
        if "S10" not in pc or "S90" not in pc:
            notes.append("%s: sin ventana de siembra del SIAP" % crop)
            out[crop] = spec
            continue
        ref = dt.date(2001, *_mmdd(pc["S10"]))
        s90 = dt.date(2001, *_mmdd(pc["S90"]))
        if s90 < ref:
            s90 = dt.date(2002, *_mmdd(pc["S90"]))
        for k in REF_KEYS:
            lo, hi = ((offsets.get(crop) or {}).get(k) or ["", ""])[:2]
            if lo in ("", None):
                notes.append("%s %s: sin desfase" % (crop, k))
                continue
            a = ref + dt.timedelta(days=int(lo))
            b = s90 + dt.timedelta(days=int(hi))
            spec[k] = ["%02d-%02d" % (a.month, a.day),
                       "%02d-%02d" % (b.month, b.day)]
        out[crop] = spec
    return out, notes


def validate_profiles(profiles):
    if not profiles:
        raise CalendarError("no profiles")
    for name, p in profiles.items():
        if not str(name).strip():
            raise CalendarError("empty profile name")
        validate_profile(p)
    return True


def _day_in_cycle(mmdd, cal, cycle, year, day0):
    first = _mmdd(cal[cycle]["stages"][0][1])
    mo, d = _mmdd(mmdd)
    y = year + (1 if (mo, d) < first else 0)
    return (dt.date(y, mo, d) - day0).days


def reference_days(references, cal, cycle, year):
    """{crop: {"arranque": (d0, d1) | None, "maximo": ...}} in days from
    the start of the cycle (same origin as the curve metrics). Crops with
    no window at all are left out."""
    day0 = windows(cal, cycle, year)[0][1]
    out = {}
    for crop, spec in refs_for_cycle(references, cycle).items():
        w = {}
        for k in REF_KEYS:
            a, b = (spec.get(k) or ["", ""])[:2]
            if not a:
                w[k] = None
                continue
            d0 = _day_in_cycle(a, cal, cycle, year, day0)
            d1 = _day_in_cycle(b, cal, cycle, year, day0)
            if d1 < d0:
                d1 += 365
            w[k] = (d0, d1)
        if any(w.values()):
            out[crop] = w
    return out


def mark_manual(old_cal, new_cal):
    """Keep the origin of each stage (SIAP, estimated...) and set it to
    'manual' for the stages whose name or dates changed."""
    for c, spec in new_cal.items():
        old = (old_cal or {}).get(c) or {}
        orig = list(old.get("origin") or [])
        if not orig:
            continue
        ost = old.get("stages") or []
        out = []
        for i, st in enumerate(spec.get("stages") or []):
            same = i < len(ost) and list(ost[i]) == list(st)
            out.append(orig[i] if same and i < len(orig) else "manual")
        spec["origin"] = out
    return new_cal

