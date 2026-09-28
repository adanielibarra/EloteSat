"""Offline tests for EloteSat phase 1 (synthetic COGs, fake STAC).

Run with the Python that ships with QGIS, from the plugin's parent folder:
    python elotesat/tests/test_core.py
"""
import csv
import datetime as dt
import json
import os
import shutil
import sys
import tempfile

import numpy as np
from osgeo import gdal, osr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
gdal.UseExceptions()

from elotesat.core import stac_client, downloader, phenology, i18n  # noqa
from elotesat.core.sensors import S2, LS, BANDS  # noqa

i18n.set_lang("es")
TMP = tempfile.mkdtemp(prefix="elotesat_")
EPSG = 32614
FAIL = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


# ------------------------------------------------------------------ helpers
def make_cog(path, ox, oy, res, arr, dtype=gdal.GDT_UInt16):
    h, w = arr.shape
    mem = gdal.GetDriverByName("MEM").Create("", w, h, 1, dtype)
    mem.SetGeoTransform((ox, res, 0, oy, 0, -res))
    s = osr.SpatialReference()
    s.ImportFromEPSG(EPSG)
    mem.SetProjection(s.ExportToWkt())
    mem.GetRasterBand(1).WriteArray(arr)
    gdal.Translate(path, mem, format="COG")


def s2_tile(name, ox, oy, size_m=12000, cloud_rows=None):
    """Band values encode the global column: v = 1 + col (so we can check
    the clip is not shifted). SCL 4 everywhere; cloud_rows (in 20 m px)
    get SCL 9."""
    d = os.path.join(TMP, name)
    os.makedirs(d)
    assets = {}
    for b, (keys, res, _) in BANDS[S2].items():
        n = int(size_m / res)
        rows, cols = np.mgrid[0:n, 0:n]
        if b == "SCL":
            arr = np.full((n, n), 4, np.uint8)
            if cloud_rows:
                arr[cloud_rows[0]:cloud_rows[1], :] = 9
            dtype = gdal.GDT_Byte
        else:
            arr = (1 + cols + int(round((ox - 400000) / res))).astype(
                np.uint16)
            dtype = gdal.GDT_UInt16
        p = os.path.join(d, "%s.tif" % keys[0])
        make_cog(p, ox, oy, res, arr, dtype)
        a = {"href": p}
        if b != "SCL":
            a["raster:bands"] = [{"scale": 0.0001, "offset": -0.1}]
        assets[keys[0]] = a
    return assets


def ls_tile(name, ox, oy, size_m=12000, qa_fn=None):
    d = os.path.join(TMP, name)
    os.makedirs(d)
    assets = {}
    n = int(size_m / 30)
    rows, cols = np.mgrid[0:n, 0:n]
    for b, (keys, res, _) in BANDS[LS].items():
        if b == "QA_PIXEL":
            arr = np.full((n, n), 21824, np.uint16)  # typical clear land
            if qa_fn:
                qa_fn(arr)
        else:
            arr = (7273 + cols).astype(np.uint16)
        p = os.path.join(d, "%s.tif" % keys[0])
        make_cog(p, ox, oy, 30, arr)
        assets[keys[0]] = {"href": p}
    return assets


def aoi_wkt(minx, miny, maxx, maxy):
    """Rectangle in UTM 14N -> WKT lon/lat."""
    from osgeo import ogr
    ring = "POLYGON((%f %f,%f %f,%f %f,%f %f,%f %f))" % (
        minx, miny, maxx, miny, maxx, maxy, minx, maxy, minx, miny)
    g = ogr.CreateGeometryFromWkt(ring)
    src = osr.SpatialReference()
    src.ImportFromEPSG(EPSG)
    dst = osr.SpatialReference()
    dst.ImportFromEPSG(4326)
    for s in (src, dst):
        s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    g.Transform(osr.CoordinateTransformation(src, dst))
    return g.ExportToWkt()


def s2_item(iid, date, assets, tile="14RPP", cloud=10.0):
    return {"id": iid, "collection": "sentinel-2-c1-l2a", "assets": assets,
            "geometry": None,
            "properties": {"datetime": date + "T17:00:00Z",
                           "eo:cloud_cover": cloud, "platform": "sentinel-2a",
                           "s2:mgrs_tile": tile,
                           "s2:processing_baseline": "05.11"}}


# ================================================================== 1 calendar
cal = phenology.copy_calendar()
phenology.validate(cal)
check(True, "default calendar valid")
w = phenology.windows(cal, "OI", 2026)
check(w[0][1] == dt.date(2026, 1, 15) and w[-1][2] == dt.date(2026, 7, 15),
      "OI 2026 span 2026-01-15 .. 2026-07-15")
check(phenology.assign("2026-04-20", cal, "OI", 2026) ==
      "02_floracion_espigamiento", "2026-04-20 -> floración (OI)")
check(phenology.assign("2026-02-28", cal, "OI", 2026) ==
      "00_siembra_emergencia", "last day of a window is inside")
check(phenology.assign("2026-08-01", cal, "OI", 2026) ==
      phenology.OUT_OF_STAGE, "date after the cycle -> fuera_de_etapa")
x = {"X": {"label": "", "stages": [["a", "11-01", "12-15"],
                                   ["b", "12-16", "01-31"],
                                   ["c", "02-01", "03-31"]]}}
phenology.validate(x)
wx = phenology.windows(x, "X", 2025)
check(wx[1][1] == dt.date(2025, 12, 16) and wx[1][2] == dt.date(2026, 1, 31)
      and wx[2][1] == dt.date(2026, 2, 1), "cycle crossing New Year")
check(phenology.assign("2026-01-10", x, "X", 2025) == "b",
      "2026-01-10 in cycle X 2025 -> b")
for bad, why in (
        ({"X": {"stages": [["a", "01-01", "02-10"],
                           ["b", "02-05", "03-01"]]}}, "overlap"),
        ({"X": {"stages": [["a b", "01-01", "02-10"]]}}, "space in name"),
        ({"X": {"stages": [["a", "02-30", "03-01"]]}}, "bad day"),
        ({"X": {"stages": [["a", "01-01", "02-01"],
                           ["a", "03-01", "04-01"]]}}, "repeated name")):
    try:
        phenology.validate(bad)
        check(False, "rejects " + why)
    except phenology.CalendarError:
        check(True, "rejects " + why)

# ================================================================== 2 STAC
pc_s2 = {"id": "S2A_MSIL2A_20260310T170901_R069_T14RPP_20260310T220000",
         "collection": "sentinel-2-l2a", "geometry": None,
         "assets": {b: {"href": "https://sentinel2l2a01.blob.core.windows"
                        ".net/x/%s.tif" % b}
                    for b in ("B02", "B03", "B04", "B08", "B05", "B06",
                              "B07", "B8A", "B11", "B12", "SCL")},
         "properties": {"datetime": "2026-03-10T17:09:01Z",
                        "eo:cloud_cover": 3.2, "platform": "Sentinel-2A",
                        "s2:mgrs_tile": "14RPP",
                        "s2:processing_baseline": "05.11"}}
sc = stac_client.parse_item(pc_s2, "pc-s2")
check(not sc.missing and sc.assets["B04"].key == "B04",
      "PC S2: B04-style asset keys found")
check(sc.assets["B04"].offset == -0.1 and sc.assets["B04"].scale == 1e-4,
      "PC S2: no raster:bands -> ESA offset -0.1 (baseline 05.11)")
check(sc.short_platform == "S2A" and sc.auth == "pc", "PC S2 platform/auth")

ls_assets = {k: {"href": "https://landsateuwest.blob.core.windows.net/x/"
                 "%s.TIF" % k,
                 "raster:bands": [{"scale": 2.75e-05, "offset": -0.2}]}
             for k in ("coastal", "blue", "green", "red", "nir08", "swir16",
                       "swir22")}
ls_assets["qa_pixel"] = {"href": "https://landsateuwest.blob.core.windows"
                         ".net/x/QA_PIXEL.TIF"}
pc_ls = {"id": "LC09_L2SP_026042_20260312_02_T1", "collection":
         "landsat-c2-l2", "assets": ls_assets, "geometry": None,
         "properties": {"datetime": "2026-03-12T16:55:00Z",
                        "eo:cloud_cover": 12.0, "platform": "landsat-9",
                        "landsat:wrs_path": "026", "landsat:wrs_row": "042",
                        "landsat:collection_category": "T1"}}
sl = stac_client.parse_item(pc_ls, "pc-ls")
check(sl.tile == "026042" and sl.short_platform == "L9",
      "PC Landsat: path/row 026042, L9")
check(sl.assets["SR_B4"].key == "red" and "QA_PIXEL" in sl.assets,
      "PC Landsat: red and qa_pixel found")
check(abs(sl.assets["SR_B5"].scale - 2.75e-05) < 1e-12 and
      sl.assets["SR_B5"].offset == -0.2, "PC Landsat: scale/offset read")

es_ls = json.loads(json.dumps(pc_ls))
for k, a in es_ls["assets"].items():
    a["href"] = "https://landsatlook.usgs.gov/data/x/%s.TIF" % k
    a["alternate"] = {"s3": {"href": "s3://usgs-landsat/x/%s.TIF" % k}}
    a.pop("raster:bands", None)
se = stac_client.parse_item(es_ls, "es-ls")
check(se.assets["SR_B4"].href.startswith("s3://usgs-landsat/"),
      "Earth Search Landsat: requester-pays s3 href chosen")
check(se.assets["SR_B4"].scale == 2.75e-05 and se.assets["SR_B4"].offset
      == -0.2, "Landsat fallback scale/offset")
check(downloader.gdal_path(se.assets["SR_B4"].href).startswith(
    "/vsis3/usgs-landsat/"), "s3 -> /vsis3/")

# search: pagination, Landsat 7 dropped, client-side cloud filter
pages = []


def fake_post(url, payload):
    pages.append((url, payload))
    l7 = json.loads(json.dumps(pc_ls))
    l7["id"], l7["properties"]["platform"] = "LE07_x", "landsat-7"
    cloudy = json.loads(json.dumps(pc_ls))
    cloudy["id"], cloudy["properties"]["eo:cloud_cover"] = "LC08_c", 95
    if len(pages) == 1:
        return {"features": [pc_ls, l7],
                "links": [{"rel": "next", "method": "POST", "merge": True,
                           "href": url, "body": {"token": "p2"}}]}
    return {"features": [cloudy, pc_ls], "links": []}


found = stac_client.search((-98, 25, -97.8, 25.2), "2026-01-15",
                           "2026-07-15", "pc-ls", max_cloud=60,
                           post_json=fake_post)
check(len(found) == 1 and found[0].id == pc_ls["id"],
      "search: L7 dropped, cloudy dropped, duplicate across pages once")
check(pages[0][1]["query"]["platform"]["in"] == ["landsat-8", "landsat-9"]
      and pages[0][1]["collections"] == ["landsat-c2-l2"],
      "search payload: collection and platform filter")
check(pages[1][1].get("token") == "p2", "pagination POST body merged")

# PC signer
calls = []
clock = [1000000.0]


def fake_token(url):
    calls.append(url)
    exp = dt.datetime.fromtimestamp(clock[0] + 3600,
                                    dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    return {"token": "st=a&sig=XYZ%d" % len(calls), "msft:expiry": exp}


sg = stac_client.PcSigner(get_json=fake_token, now=lambda: clock[0])
h1 = sg.sign("https://a/b.tif", "sentinel-2-l2a")
h2 = sg.sign("https://a/c.tif", "sentinel-2-l2a")
check(h1 == "https://a/b.tif?st=a&sig=XYZ1" and len(calls) == 1 and
      h2.endswith("XYZ1"), "PC token requested once and cached")
check(calls[0].endswith("/token/sentinel-2-l2a"), "token URL per collection")
clock[0] += 3400  # 200 s left: renew
sg.sign("https://a/d.tif", "sentinel-2-l2a")
check(len(calls) == 2, "token renewed when < 5 min left")
check(downloader.resolve(sc, "B04", sg).startswith(
    "/vsicurl/https://sentinel2l2a01") and "sig=" in
    downloader.resolve(sc, "B04", sg), "resolve() signs PC hrefs")

# ================================================================== 3 S2 clip
# tile A: x 400000..412000, y 2800000..2788000 ; tile B to the east
A = s2_tile("s2A", 400000, 2800000, cloud_rows=(0, 150))  # north 3 km
B = s2_tile("s2B", 412000, 2800000)
it_a = s2_item("S2A_T14RPP_20260320T170000_L2A", "2026-03-20", A, "14RPP")
it_b = s2_item("S2A_T14RQP_20260320T170000_L2A", "2026-03-20", B, "14RQP")
sa = stac_client.parse_item(it_a, "es-s2")
sb = stac_client.parse_item(it_b, "es-s2")
# study area straddles both tiles, 9.99..14.01 km east, 3.5..8.5 km south
wkt = aoi_wkt(409990, 2791500, 414010, 2796500)
out = os.path.join(TMP, "out")
cal = phenology.copy_calendar()
stage = phenology.assign(sa.date, cal, "OI", 2026)
check(stage == "01_vegetativo", "2026-03-20 -> 01_vegetativo")
folder = phenology.stage_dir(out, "OI", 2026, stage, S2)
recs = []
for s in (sa, sb):
    s.stage = stage
    r = downloader.process_scene(s, wkt, folder, list(BANDS[S2]),
                                 min_clear=0.6, min_cover=0.1)
    r.pop("outputs")
    r["stage"] = stage
    recs.append(r)
check(os.path.isdir(os.path.join(out, "OI_2026", "01_vegetativo", "S2")),
      "stage folder OI_2026/01_vegetativo/S2 created")
p10 = os.path.join(folder, "S2_20260320_14RPP_S2A_10m.tif")
p20 = os.path.join(folder, "S2_20260320_14RPP_S2A_20m.tif")
ds10, ds20 = gdal.Open(p10), gdal.Open(p20)
gt10, gt20 = ds10.GetGeoTransform(), ds20.GetGeoTransform()
check([ds10.GetRasterBand(i).GetDescription() for i in range(1, 5)] ==
      ["B02", "B03", "B04", "B08"], "10 m stack band order")
check(ds20.GetRasterBand(7).GetDescription() == "SCL", "SCL in 20 m stack")
check(gt10[0] == gt20[0] and gt10[3] == gt20[3] and gt10[0] % 20 == 0,
      "10 and 20 m stacks share origin on the 20 m grid")
col0 = int((gt10[0] - 400000) / 10)
check(int(ds10.GetRasterBand(3).ReadAsArray()[0, 0]) == 1 + col0,
      "no shift: first pixel value = global column")
check(ds10.GetRasterBand(3).GetScale() == 1e-4 and
      ds10.GetRasterBand(3).GetOffset() == -0.1, "scale/offset in band")
check(gt10[0] + gt10[1] * ds10.RasterXSize == 412000,
      "tile A clip clamped to its east edge")
check(abs(recs[0]["cover_aoi_pct"] - 50) < 3 and
      recs[0]["clear_aoi_pct"] == 100.0,
      "tile A: ~50 %% cover, 100 %% clear (%.1f)" % recs[0]["cover_aoi_pct"])
ds10 = ds20 = None

# cloudy scene: whole AOI under cloud in tile A
C = s2_tile("s2C", 400000, 2800000, cloud_rows=(0, 600))
scc = stac_client.parse_item(s2_item("S2B_T14RPP_20260325T170000_L2A",
                                     "2026-03-25", C), "es-s2")
scc.stage = stage
try:
    downloader.process_scene(scc, wkt, folder, list(BANDS[S2]))
    check(False, "cloudy scene skipped")
except downloader.SceneSkipped as e:
    check(e.args[1]["status"] == "skipped_cloudy" and not any(
        "20260325" in n for n in os.listdir(folder)),
        "cloudy scene skipped, nothing written")
# sliver: AOI only 1 % in tile
try:
    downloader.process_scene(sa, aoi_wkt(411900, 2791500, 421900, 2796500),
                             os.path.join(TMP, "sliver"), ["B04"],
                             min_cover=0.1)
    check(False, "sliver skipped")
except downloader.SceneSkipped as e:
    check(e.args[1]["status"] == "skipped_cover", "sliver skipped by cover")

# mosaic
made = downloader.build_mosaics(folder)
names = sorted(os.path.basename(m) for m in made)
check(names == ["MOS_S2_20260320_10m.vrt", "MOS_S2_20260320_20m.vrt"],
      "two mosaics (10 and 20 m)")
vrt_txt = open(os.path.join(folder, "MOS_S2_20260320_10m.vrt")).read()
check('relativeToVRT="1"' in vrt_txt, "mosaic uses relative paths")
m = gdal.Open(os.path.join(folder, "MOS_S2_20260320_10m.vrt"))
arr = m.GetRasterBand(3).ReadAsArray()
mgt = m.GetGeoTransform()
exp = 1 + np.arange(m.RasterXSize) + int((mgt[0] - 400000) / 10)
check(np.array_equal(arr[0], exp), "mosaic continuous across tiles")
m = None

# ================================================================== 4 Landsat
def qa(arr):
    arr[0:40, :] = 21824 | (1 << 3) | (1 << 1)   # cloud + dilated
    arr[40:60, :] = 21824 | (1 << 4)             # shadow


L = ls_tile("ls", 399990, 2800020, qa_fn=qa)
ls_item = json.loads(json.dumps(pc_ls))
ls_item["assets"] = {k: dict(v, **{"raster:bands": [
    {"scale": 2.75e-05, "offset": -0.2}]}) if k != "qa_pixel" else v
    for k, v in L.items()}
sll = stac_client.parse_item(ls_item, "pc-ls")
sll.auth = None  # local files, no signing
sll.stage = stage
lfold = phenology.stage_dir(out, "OI", 2026, stage, LS)
# AOI rows: y 2800020-1200 .. -2400 -> QA rows 40..80 (half shadow)
r = downloader.process_scene(sll, aoi_wkt(401000, 2797620, 404000, 2798820),
                             lfold, ["SR_B4", "SR_B5"], min_clear=0.3)
r.pop("outputs")
r["stage"] = stage
recs.append(r)
check(abs(r["clear_aoi_pct"] - 50) < 5,
      "Landsat QA: shadow half -> ~50 %% clear (%.1f)" % r["clear_aoi_pct"])
lp = os.path.join(lfold, "LS_20260312_026042_L9_30m.tif")
ld = gdal.Open(lp)
lgt = ld.GetGeoTransform()
check([ld.GetRasterBand(i).GetDescription() for i in (1, 2, 3)] ==
      ["SR_B4", "SR_B5", "QA_PIXEL"], "Landsat stack: bands + QA added")
check((lgt[0] - 399990) % 30 == 0 and (2800020 - lgt[3]) % 30 == 0,
      "Landsat window on the 30 m grid")
check(ld.GetRasterBand(1).GetNoDataValue() == 0 and
      ld.GetRasterBand(1).GetOffset() == -0.2, "SR nodata 0 and offset")
check(int(ld.GetRasterBand(1).ReadAsArray()[0, 0]) ==
      7273 + int((lgt[0] - 399990) / 30), "Landsat no shift")
ld = None
try:
    downloader.process_scene(sll, aoi_wkt(401000, 2798820, 404000, 2799600),
                             os.path.join(TMP, "lc"), ["SR_B4"])
    check(False, "Landsat cloudy skipped")
except downloader.SceneSkipped as e:
    check(e.args[1]["status"] == "skipped_cloudy",
          "Landsat cloud/dilated rows -> skipped")

# Landsat mosaic: second row overlaps with fill (QA 1, SR 0) on top
def fill_top(arr):
    arr[:, :] = 21824
    arr[0:100, :] = 1


L2 = ls_tile("ls2", 399990, 2800020 - 9000, qa_fn=fill_top)
for k in ("red", "nir08"):
    ds = gdal.Open(L2[k]["href"])
    a = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    a[0:100, :] = 0
    make_cog(L2[k]["href"], 399990, 2800020 - 9000, 30, a)
it2 = json.loads(json.dumps(ls_item))
it2["id"] = "LC09_L2SP_026043_20260312_02_T1"
it2["properties"]["landsat:wrs_row"] = "043"
it2["assets"] = {k: dict(v) for k, v in L2.items()}
sl2 = stac_client.parse_item(it2, "pc-ls")
sl2.auth = None
downloader.process_scene(sl2, aoi_wkt(401000, 2791000, 404000, 2798820),
                         lfold, ["SR_B4", "SR_B5"], min_clear=0.0,
                         min_cover=0.0)
downloader.process_scene(sll, aoi_wkt(401000, 2791000, 404000, 2798820),
                         lfold + "_tmp", ["SR_B4", "SR_B5"], min_clear=0.0,
                         min_cover=0.0)
lm = downloader.build_mosaics(lfold)
check(len(lm) == 1, "Landsat mosaic built")
mv = gdal.Open(lm[0])
check(mv.GetRasterBand(3).GetNoDataValue() == 1 and
      mv.GetRasterBand(1).GetNoDataValue() == 0,
      "Landsat mosaic: nodata 0 for SR, 1 for QA")
mv = None
os.remove(lm[0])
os.remove(os.path.join(lfold, "LS_20260312_026043_L9_30m.tif"))
shutil.rmtree(lfold + "_tmp")

# ================================================================== 5 reorganize
cdir = phenology.cycle_dir(out, "OI", 2026)
downloader.append_manifest(cdir, recs)
cal2 = phenology.copy_calendar()
cal2["OI"]["stages"][1][2] = "03-15"       # vegetativo ends earlier
cal2["OI"]["stages"][2][1] = "03-16"       # floración starts 03-16
moved, kept, probs = phenology.reorganize(out, cal2, "OI", 2026)
check(moved == 2 and kept == 1 and not probs,
      "reorganize: 2 S2 scenes (03-20) moved, Landsat (03-12) kept")
nf = os.path.join(cdir, "02_floracion_espigamiento", "S2")
check(os.path.exists(os.path.join(nf, "S2_20260320_14RPP_S2A_10m.tif"))
      and os.path.exists(os.path.join(nf, "MOS_S2_20260320_10m.vrt")),
      "files and rebuilt mosaic in the new folder")
check(not os.path.exists(os.path.join(cdir, "01_vegetativo", "S2")),
      "empty old folder removed")
check(gdal.Open(os.path.join(nf, "MOS_S2_20260320_10m.vrt")) is not None,
      "moved mosaic opens")
with open(os.path.join(cdir, "manifest.csv"), encoding="utf-8") as f:
    st = [row["stage"] for row in csv.DictReader(f)]
check(st.count("02_floracion_espigamiento") == 2, "manifest stages updated")
check(json.load(open(os.path.join(cdir, "calendario.json")))["OI"]
      ["stages"][2][1] == "03-16", "calendario.json updated")
# clash: put a file with the same name at the destination, move back
os.makedirs(os.path.join(cdir, "01_vegetativo", "S2"))
shutil.copy(os.path.join(nf, "S2_20260320_14RPP_S2A_10m.tif"),
            os.path.join(cdir, "01_vegetativo", "S2"))
moved, kept, probs = phenology.reorganize(out, cal, "OI", 2026)
check(len(probs) == 1 and moved == 1,
      "clash: one scene left in place and reported, never overwritten")

print("\n%d failures" % len(FAIL))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
