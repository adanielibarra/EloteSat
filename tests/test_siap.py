"""SIAP: import to profiles (real Tamaulipas export shipped in data/),
references from sowing windows, profile assignment by area, download
module (offline, with a SYNTHETIC response built to the parser's
expected structure: it checks the code path, not the real server's HTML)
and mapped vs SIAP area comparison.

    python elotesat/tests/test_siap.py
"""
import csv
import datetime as dt
import os
import shutil
import sys
import tempfile

import numpy as np
from osgeo import gdal, osr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
gdal.UseExceptions()
from elotesat.core import (siap, siap_download, phenology, zones,  # noqa
                          compare)

FAIL = []
TMP = tempfile.mkdtemp(prefix="elotesat_siap_")


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        FAIL.append(m)


# ------------------------------------------------------------ real data
rows = siap.read_avance()
check(len(rows) == 4478 and len({r["cvegeo"] for r in rows}) == 38,
      "shipped SIAP table: 4478 rows, 38 municipios")
ser = siap.series(rows)
mono = all(all(b[1] >= a[1] - 1e-6 and b[2] >= a[2] - 1e-6
               for a, b in zip(s, s[1:])) for s in ser.values())
check(mono, "all %d series are cumulative (never decrease)" % len(ser))

profiles, report = siap.import_file()
check(len(profiles) >= 30, "%d profiles created" % len(profiles))
check(all(n.startswith("siap_28") and n.endswith(("_riego", "_temporal"))
          and "maiz" not in n.lower() and "sorgo" not in n.lower()
          for n in profiles), "profile names: municipality + regime, "
      "no crop")
for n, p in profiles.items():
    phenology.validate_profile(p)
check(True, "every profile validates")
rb = profiles["siap_28033_Rio_Bravo_riego"]
oi = rb["cycles"]["OI"]
f = rb["siap"]["ciclos"]["OI"]["fechas"]
check(f["S50"].startswith("02-") and oi["stages"][0][1] == f["S10"] and
      oi["stages"][3][2] == f["H90"], "Río Bravo riego OI: S50 in "
      "February, stage 00 starts at S10, 03 ends at H90 (%s)" % f)
check([o.split(":")[0] for o in oi["origin"]] ==
      ["siap", "estimada", "estimada", "siap"], "stage origins recorded")
check(rb["siap"]["supuestos"]["emergencia_dias"] == 10,
      "assumptions stored with the profile")
mante = profiles.get("siap_28021_El_Mante_riego")
check(mante and any("REVISAR" in a for a in mante["siap"]["avisos"]),
      "El Mante riego OI: 64-day cycle flagged REVISAR")
# name matching of the CSV (no cvegeo) gives the same rows
E = os.path.join(TMP, "t.csv")
with open(E, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh)
    w.writerow(["anio_agricola", "ciclo", "modalidad", "cultivo",
                "fecha_corte", "municipio", "sembrada_ha", "cosechada_ha",
                "aviso"])
    w.writerow([2025, "Otoño - Invierno", "Riego", "Sorgo grano",
                "2025-02-28", "SOTO LA MARINA", 10, 0, ""])
    w.writerow([2025, "Otoño - Invierno", "Riego", "Sorgo grano",
                "2025-02-28", "Villa Inventada", 10, 0, ""])
r2 = siap.read_avance(E)
check(len(r2) == 1 and r2[0]["cvegeo"] == "28037" and
      siap.unmatched_names(E) == ["Villa Inventada"],
      "CSV without cvegeo matched by name (accents/case), unmatched listed")
merged = siap.merge(rows, [dict(rows[0], sembrada=-1.0)])
check(len(merged) == len(rows) and
      sum(1 for r in merged if r["sembrada"] == -1.0) == 1,
      "merge replaces the same cut")

# ------------------------------------------------------------ units
D = dt.date


def mk(cut_vals, anio=2025, ciclo="OI", cv="28001"):
    return [{"cvegeo": cv, "municipio": "x", "anio": anio, "ciclo": ciclo,
             "modalidad": "riego", "cultivo": "Sorgo grano", "fecha": d,
             "sembrada": s, "cosechada": c} for d, s, c in cut_vals]


# start covered (October cut in the export) -> zero anchor at 30 Sep
base = mk([(D(2024, 10, 31), 0, 0), (D(2024, 11, 30), 50, 0)], cv="28002")
own = mk([(D(2025, 1, 31), 20, 0), (D(2025, 2, 28), 90, 0),
          (D(2025, 3, 31), 100, 0), (D(2025, 6, 30), 100, 90),
          (D(2025, 7, 31), 100, 100)])
s = siap.series(base + own)[("28001", "riego", "OI", 2025)]
check(s[0][0] == D(2024, 9, 30) and s[0][1] == 0 and len(s) == 8,
      "zero anchor + zero cuts (Oct, Nov) before the first row")
d, w = siap.cycle_dates(s)
# 10 % halfway between 30 Nov (0) and 31 Jan (20 %); 90 % on 28 Feb
check(d["S10"] == D(2024, 12, 31) and d["S90"] == D(2025, 2, 28),
      "S10/S90 interpolated (%s, %s)" % (d["S10"], d["S90"]))
check(not any("cierre" in x for x in w),
      "70 % in a middle cut is not flagged")
s2 = siap.series(mk([(D(2025, 1, 31), 20, 0), (D(2025, 2, 28), 100, 0)],
                    anio=2023))[("28001", "riego", "OI", 2023)]
d2, w2 = siap.cycle_dates(s2)
check(d2["S10"] is None and any("arranque" in x for x in w2) and
      any("cierre" in x for x in w2),
      "no start in export -> S10 empty; closing jump flagged")
cal = profiles["siap_28033_Rio_Bravo_riego"]["cycles"]
check(siap.siap_year("OI", cal, 2025) == 2025 and
      siap.elotesat_year("OI", cal, 2025) == 2025, "OI starting in "
      "January: EloteSat year = SIAP year")
xcal = {"OI": {"label": "", "stages": [
    ["00_siembra_emergencia", "10-15", "12-31"],
    ["01_vegetativo", "01-01", "02-15"],
    ["02_floracion_espigamiento", "02-16", "03-31"],
    ["03_madurez_senescencia", "04-01", "06-15"]]}}
check(siap.siap_year("OI", xcal, 2024) == 2025 and
      siap.elotesat_year("OI", xcal, 2025) == 2024, "OI starting in "
      "October: SIAP 2025 = EloteSat 2024")

# references from the SIAP sowing window + assumed offsets
refs, notes = phenology.references_from_siap(rb, "OI", {})
check(all(v == ["", ""] for c in refs.values() for v in c.values()) and
      notes, "no offsets -> references stay empty (no invented values)")
off = {"maiz": {"arranque": [20, 35], "maximo": [55, 75]},
       "sorgo": {"arranque": [20, 35], "maximo": [50, 70]}}
refs, notes = phenology.references_from_siap(rb, "OI", off)
pc = rb["siap"]["ciclos"]["OI"]["por_cultivo"]["Sorgo grano"]
s10 = D(2001, *map(int, pc["S10"].split("-")))
exp = s10 + dt.timedelta(days=20)
check(refs["sorgo"]["arranque"][0] == "%02d-%02d" % (exp.month, exp.day),
      "sorghum green-up window starts at S10 + 20 d")
p2 = dict(rb, references={"OI": refs}, offsets={"OI": off})
phenology.validate_profile(p2)
rd = phenology.reference_days(p2["references"], rb["cycles"], "OI", 2025)
check(set(rd) == {"maiz", "sorgo"} and rd["sorgo"]["maximo"],
      "per-cycle references convert to cycle days")

# ------------------------------------------------------------ assignment
a, b = osr.SpatialReference(), osr.SpatialReference()
a.ImportFromEPSG(4326)
b.ImportFromEPSG(32614)
for sr in (a, b):
    sr.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)


def square(lon, lat, d=0.02):
    return ("POLYGON((%f %f,%f %f,%f %f,%f %f,%f %f))" % (
        lon - d, lat - d, lon + d, lat - d, lon + d, lat + d, lon - d,
        lat + d, lon - d, lat - d))


res = zones.suggest_profile(square(-97.70, 25.75), profiles)
check(res["modalidad"] == "riego" and res["cvegeo"] == "28022" and
      res["profile"] == "siap_28022_Matamoros_riego",
      "farmland in DR 025 -> %s" % res["profile"])
res = zones.suggest_profile(square(-97.95, 24.0), profiles)
check(res["modalidad"] == "temporal" and res["cvegeo"] == "28037",
      "Soto la Marina outside districts -> temporal (%s)" % res["profile"])
res = zones.suggest_profile(square(-95.0, 25.0), profiles)
check(res["profile"] is None and "fuera de Tamaulipas" in res["warnings"],
      "sea -> no profile")

# ------------------------------------------------------------ download
plan = siap_download.plan([2025])
check((2024, 1, 10) in plan and (2025, 1, 12) in plan and
      (2025, 2, 4) in plan and (2026, 2, 3) in plan and
      (2025, 2, 1) not in plan, "request plan covers OI and PV 2025")

XML = """<?xml version="1.0" encoding="iso-8859-1"?><xjx><cmd><![CDATA[
<div class="titulosTabla">Año agrícola: {an} Ciclo: {ciclo} Modalidad:
{mod} Cultivo: {cult} Entidad: Tamaulipas Situación al 28 de febrero de
{an}</div><table><tr><th>#</th><th>Entidad</th><th>Municipio</th></tr>
<tr><td>1</td><td>Tamaulipas</td><td>Río Bravo</td>
<td class="tdNum">1,234.50</td><td class="tdNum">0.00</td>
<td class="tdNum">0.00</td><td class="tdNum">0.00</td>
<td class="tdNum">0.00</td></tr></table>]]></cmd></xjx>"""


class FakeResp:
    def __init__(self, b):
        self.b = b

    def read(self):
        return self.b


class FakeOpener:
    def __init__(self):
        self.n = 0

    def open(self, req, timeout=0):
        self.n += 1
        return FakeResp(XML.format(an=2025, ciclo="Otoño - Invierno",
                                   mod="Riego", cult="Sorgo grano")
                        .encode("utf-8"))


fo = FakeOpener()
out = os.path.join(TMP, "dl", "s.csv")
os.makedirs(os.path.dirname(out))
n, req, err = siap_download.download([2025], out, pause=0, opener=fo,
                                     ciclos=(1,), today=D(2025, 3, 15))
check(req == 4 * len([p for p in siap_download.plan([2025], (1,))
                      if D(p[0], p[2], 1) <= D(2025, 3, 15)]) and
      fo.n == req and not err, "future months skipped, 4 requests per "
      "month (2 regimes x 2 crops): %d" % req)
got = list(csv.DictReader(open(out, encoding="utf-8-sig")))
check(got[0]["municipio"] == "Río Bravo" and
      float(got[0]["sembrada_ha"]) == 1234.5 and
      got[0]["fecha_corte"] == "2025-02-28",
      "synthetic response parsed (name, thousands separator, cut date)")
check(any("modalidad recibida" in r["aviso"] for r in got),
      "header differing from the request is flagged (Temporal asked, "
      "Riego answered)")
raw = os.path.join(os.path.dirname(out), "siap_crudos")
check(len(os.listdir(raw)) == req, "every raw response saved")
out2 = os.path.join(TMP, "dl", "s2.csv")
check(siap_download.parse_raw_dir(raw, out2) == len(got),
      "CSV rebuilt from the raw responses")
check(siap.read_avance(out)[0]["cvegeo"] == "28033",
      "downloaded CSV joins by name")

# ------------------------------------------------------------ comparison
x0, y0, _ = osr.CoordinateTransformation(a, b).TransformPoint(-97.70,
                                                                25.75)
gt = (x0 - 1000, 20, 0, y0 + 1000, 0, -20)
s32614 = b.ExportToWkt()
vd = os.path.join(TMP, "OI_2025", "variables")
os.makedirs(vd)
vt = os.path.join(vd, "variables.tif")
ds = gdal.GetDriverByName("GTiff").Create(vt, 100, 100, 1,
                                          gdal.GDT_Float32)
ds.SetGeoTransform(gt)
ds.SetProjection(s32614)
ds = None
z = zones.build_zones(vt)
ct = os.path.join(TMP, "c.tif")
ds = gdal.GetDriverByName("GTiff").Create(ct, 100, 100, 1, gdal.GDT_Byte)
ds.SetGeoTransform(gt)
ds.SetProjection(s32614)
cls = np.full((100, 100), 3, np.uint8)
cls[:50] = 2          # sorghum
cls[50:60] = 1        # maize
ds.GetRasterBand(1).WriteArray(cls)
ds = None
mp, cov = compare.mapped_areas(ct, z["tif"])
zz = gdal.Open(z["tif"]).ReadAsArray()
exp_sorgo = ((cls == 2) & (zz[0] == 28022) & (zz[1] > 0)).sum() * 0.04
check(abs(mp[("28022", "riego")]["sorgo"] - exp_sorgo) < 1e-6,
      "mapped sorghum ha inside DR (%.1f)" % exp_sorgo)
rowsc = compare.compare(ct, z["tif"], "OI", 2025,
                        out_csv=os.path.join(TMP, "cmp.csv"))
r = [x for x in rowsc if x["cvegeo"] == "28022" and
     x["modalidad"] == "riego"][0]
check(r["siap_sorgo_ha"] > 1000 and r["cobertura_pct"] < 5 and
      r["cociente"] == "", "SIAP sown read; tiny coverage -> no ratio "
      "(%.2f %%)" % r["cobertura_pct"])
check(os.path.exists(os.path.join(TMP, "cmp.csv")), "comparison CSV")

print("\n%d failures" % len(FAIL))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
