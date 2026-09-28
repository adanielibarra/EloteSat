"""Shipped municipios / irrigation-district data and zonas.tif.

    python elotesat/tests/test_zones.py
"""
import csv
import os
import shutil
import sys
import tempfile

from osgeo import gdal, ogr, osr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
gdal.UseExceptions()
from elotesat.core import zones  # noqa: E402

FAIL = []
TMP = tempfile.mkdtemp(prefix="elotesat_z_")


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        FAIL.append(m)


ds = ogr.Open(zones.DATA)
lm = ds.GetLayer("municipios")
cv = [f["cvegeo"] for f in lm]
check(len(cv) == 43 and len(set(cv)) == 43 and
      all(c.startswith("28") and len(c) == 5 for c in cv),
      "43 municipios, cvegeo unique 28xxx")
check(all(f["municipio"] for f in lm), "every municipio has a name")
# coverage: no overlaps (sum of areas == area of the union)
geoms = [f.GetGeometryRef().Clone() for f in lm]
union = geoms[0]
for g in geoms[1:]:
    union = union.Union(g)
tot = sum(g.GetArea() for g in geoms)
check(abs(tot - union.GetArea()) / tot < 1e-4, "no overlaps between "
      "municipios (%.5f %%)" % (100 * (tot - union.GetArea()) / tot))
check(78000 < tot / 1e6 < 82000, "state area %.0f km2" % (tot / 1e6))
ld = ds.GetLayer("distritos_riego")
check(sorted(f["id_dr"] for f in ld) ==
      ["002", "025", "026", "029", "050", "086", "092A"],
      "7 irrigation districts")


def grid(path, epsg, x0, y0, res, n):
    s = osr.SpatialReference()
    s.ImportFromEPSG(epsg)
    d = gdal.GetDriverByName("GTiff").Create(path, n, n, 1,
                                            gdal.GDT_Float32)
    d.SetGeoTransform((x0, res, 0, y0, 0, -res))
    d.SetProjection(s.ExportToWkt())
    d = None


def utm(lon, lat):
    a, b = osr.SpatialReference(), osr.SpatialReference()
    a.ImportFromEPSG(4326)
    b.ImportFromEPSG(32614)
    for s in (a, b):
        s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    x, y, _ = osr.CoordinateTransformation(a, b).TransformPoint(lon, lat)
    return x, y


# around Río Bravo city (inside DR 025), 4 km x 4 km at 20 m
x, y = utm(-98.09, 25.99)
p = os.path.join(TMP, "v1.tif")
grid(p, 32614, x - 2000, y + 2000, 20, 200)
z = zones.build_zones(p)
a = gdal.Open(z["tif"]).ReadAsArray()
check(a.shape == (2, 200, 200), "zonas.tif: 2 bands on the grid")
check(28033 in z["mun_px"] and z["mun_px"][28033] > 0.5 * 200 * 200,
      "Río Bravo city falls mostly in cvegeo 28033 (%s)" % z["mun_px"])
check({v[0] for v in z["distritos"].values()} == {"025", "026"} and
      z["dr_px"].get(0, 0) > 0.3 * 200 * 200,
      "Río Bravo city: between DR 025 and 026, urban core outside both")
# farmland north-east of Valle Hermoso: DR 025
x2, y2 = utm(-97.70, 25.75)
os.makedirs(os.path.join(TMP, "c"))
p3 = os.path.join(TMP, "c", "v3.tif")
grid(p3, 32614, x2 - 2000, y2 + 2000, 20, 200)
z3 = zones.build_zones(p3)
check({v[0] for v in z3["distritos"].values()} == {"025"} and
      z3["dr_px"].get(2, 0) > 0.8 * 200 * 200,
      "farmland in DR 025 (%s)" % z3["dr_px"])
rows = list(csv.DictReader(open(z["csv"], encoding="utf-8")))
check(any(r["banda"] == "cvegeo" and r["clave"] == "28033" and
          r["nombre"] == "Río Bravo" for r in rows), "zonas.csv lookup")
# a grid in lon/lat is reprojected, and the sea gives 0
p2 = os.path.join(TMP, "v2.tif")
os.makedirs(os.path.join(TMP, "b"))
p2 = os.path.join(TMP, "b", "v2.tif")
grid(p2, 4326, -98.0, 24.2, 0.002, 200)   # coast of Soto la Marina + sea
z2 = zones.build_zones(p2)
check(z2["mun_px"].get(0, 0) > 0 and
      set(z2["municipios"].values()) == {"Soto la Marina"},
      "lon/lat grid: land gets a municipio, sea gets 0 (%s)" %
      z2["municipios"])
check("Quattroshapes" in gdal.Open(z["tif"]).GetMetadataItem("attribution"),
      "attribution in the raster metadata")

print("\n%d failures" % len(FAIL))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
