"""Phase 2 offline tests: variables, groups, samples, separability and
classification, on the synthetic cycle of synth.py.

    python elotesat/tests/test_analysis.py
"""
import csv
import json
import os
import shutil
import sys
import tempfile

import numpy as np
from osgeo import gdal, osr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
gdal.UseExceptions()

import synth  # noqa: E402
from elotesat.core import (features, samples, separability, classify,  # noqa
                          cluster, rasterio_util as rio)
from elotesat.core.rf_numpy import RandomForest  # noqa: E402

FAIL = []
TMP = tempfile.mkdtemp(prefix="elotesat_an_")


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        FAIL.append(m)


# ================================================================ units
# NDVI curve metrics on a known curve
t = np.arange(0, 181, 5, dtype=float)
true = synth.dlogistic(t, 50, 125, 0.2, 0.85)
V = np.tile(true[:, None], (1, 4)).astype(np.float32)
V[10, 1] = 0.1          # spike (undetected cloud) in pixel 1
V[::2, 2] = np.nan      # half of the dates missing in pixel 2
V[3:, 3] = np.nan       # pixel 3: only 3 dates
m = features.ndvi_metrics(t, V)
check(abs(m["DIAsube50"][0] - 50) <= 5 and abs(m["DIAbaja50"][0] - 125) <= 5,
      "curve: green-up ~50, senescence ~125 (%s, %s)" % (
          m["DIAsube50"][0], m["DIAbaja50"][0]))
check(abs(m["NDVImax"][0] - true.max()) < 0.03, "curve: max NDVI")
check(abs(m["DIAsube50"][1] - m["DIAsube50"][0]) <= 5 and
      abs(m["NDVImax"][1] - m["NDVImax"][0]) < 0.03,
      "curve: spike removed, same result")
check(abs(m["DIAsube50"][2] - 50) <= 10, "curve: works with half the dates")
check(np.isnan(m["NDVImax"][3]), "curve: < 4 dates -> no metrics")

# shape metrics: max slope of the double logistic ~ amp * k1 / 4
check(abs(m["AMPLITUD"][0] - (m["NDVImax"][0] - 0.2)) < 0.05,
      "shape: amplitude ~ max - base")
check(0.7 * 0.65 * 0.12 / 4 < m["VELsube"][0] < 1.3 * 0.65 * 0.12 / 4,
      "shape: steepest rise %.4f NDVI/day" % m["VELsube"][0])
check(m["VELbaja"][0] > 0 and
      abs(m["DIASsubemax"][0] - (m["DIAmax"][0] - m["DIAsube50"][0])) < 1e-6,
      "shape: fall speed > 0, green-up->peak days")
shifted = features.ndvi_metrics(t, np.tile(synth.dlogistic(
    t, 80, 155, 0.2, 0.85)[:, None], (1, 1)).astype(np.float32))
check(abs(shifted["VELsube"][0] - m["VELsube"][0]) < 0.002 and
      abs(shifted["DUR50"][0] - m["DUR50"][0]) <= 5 and
      abs(shifted["DIAsube50"][0] - m["DIAsube50"][0] - 30) <= 5,
      "shape metrics unchanged by a 30-day later sowing, dates move 30")

# crop references (interpretation only)
from elotesat.core import phenology  # noqa: E402
cal0 = phenology.copy_calendar()
refs = phenology.empty_references()
refs["maiz"]["arranque"] = ["02-20", "03-31"]
refs["sorgo"]["maximo"] = ["03-01", "04-15"]
rd = phenology.reference_days(refs, cal0, "OI", 2026)
check(rd["maiz"]["arranque"] == (36, 75) and rd["maiz"]["maximo"] is None
      and rd["sorgo"]["maximo"] == (45, 90), "reference windows in cycle "
      "days (%s)" % rd)
xcal = {"X": {"label": "", "stages": [["a", "11-01", "12-31"],
                                      ["b", "01-01", "03-31"]]}}
xr = {"maiz": {"arranque": ["12-15", "01-15"], "maximo": ["", ""]}}
check(phenology.reference_days(xr, xcal, "X", 2025)["maiz"]["arranque"]
      == (44, 75), "reference window crossing New Year")
code = features.coherence(np.array([40, 40, 10, np.nan, np.nan, np.nan]),
                          np.array([60, 100, 30, 50, 30, np.nan]), rd)
# 4th: no green-up but its peak fits sorghum -> 2; 5th: fits nothing and
# the maize green-up cannot be checked -> 5 (incomplete)
check(code.tolist() == [3, 1, 4, 2, 5, 0], "coherence codes %s" % code)
bad = phenology.new_profile(references={"maiz": {"arranque": ["02-01", ""],
                                                 "maximo": ["", ""]}})
try:
    phenology.validate_profile(bad)
    check(False, "half-filled reference rejected")
except phenology.CalendarError:
    check(True, "half-filled reference rejected")

# JM and thresholds
rng = np.random.default_rng(0)
a, b = rng.normal(0, 1, 2000), rng.normal(0, 1, 2000)
check(separability.jm_1d(a, b) < 0.01, "JM ~0 for identical classes")
check(separability.jm_1d(a, b + 10) > 1.99, "JM ~2 for far classes")
jm2 = separability.jm_1d(a, b + 2)
# Bhattacharyya for equal variances = d^2/8 -> JM = 2(1-exp(-0.5))
check(abs(jm2 - 2 * (1 - np.exp(-0.5))) < 0.05, "JM matches formula")
thr, d, ba = separability.best_threshold(a + 3, b)
check(d == ">" and 1.0 < thr < 2.0 and ba > 0.9, "best threshold '>'")
thr, d, ba = separability.best_threshold(b, a + 3)
check(d == "<=" and 1.0 < thr < 2.0, "best threshold '<='")
A = np.c_[a, rng.normal(0, 1, 2000)]
B = np.c_[b + 1, rng.normal(0, 1, 2000) + 1]
check(separability.jm_multi(A, B) > separability.jm_1d(A[:, 0], B[:, 0]),
      "multivariate JM > single variable")

# grouped folds: no field in two folds, each class in each fold
y = np.array(["maiz"] * 60 + ["sorgo"] * 60 + ["otros"] * 60, object)
g = np.array(["f%d" % (i // 10) for i in range(180)], object)
f, k, w = classify.group_folds(y, g, 5)
leak = any(len(set(f[g == gi])) > 1 for gi in set(g))
check(not leak, "folds: every field in one fold only")
check(k == 5 and all(set(y[f == j]) == {"maiz", "sorgo", "otros"}
                     for j in range(k)), "folds: 3 classes in every fold")
f, k, w = classify.group_folds(y[:130], g[:130], 5)
check(k == 1 or f is None or (w and k < 5),
      "folds: k reduced / refused with few fields (%s)" % w)

# majority filter
c = np.ones((5, 5), np.uint8)
c[2, 2] = 2
c[0, :] = 0
mf = rio.majority3(c)
check(mf[2, 2] == 1 and (mf[0] == 0).all(), "3x3 filter: lone pixel "
      "removed, nodata kept")

# numpy forest
X = rng.normal(0, 1, (600, 5))
yy = np.where(X[:, 0] + X[:, 1] > 0, "a", "b")
rf = RandomForest(n_estimators=30, random_state=1).fit(X[:400], yy[:400])
check((rf.predict(X[400:]) == yy[400:]).mean() > 0.85,
      "numpy forest learns a simple rule")

_orig = classify.sklearn_available
classify.sklearn_available = lambda: False
check(classify.make_rf("auto", 5, 0)[1] == "numpy",
      "auto engine falls back to numpy without scikit-learn")
classify.sklearn_available = _orig

# ================================================================ pipeline
synth.HARD = True   # maize and sorghum share the NDVI curve
synth.SHIFT_SD = 20  # staggered sowing: fixed windows mix phases
cdir, C, F, cls = synth.build(TMP)
# relative vs fixed windows on the same data (S2 only, per field)
rfx = features.build(cdir, res=20, sensors=("S2",), fixed=True,
                     references=rd)
check(os.path.exists(rfx["reference"]) and
      os.path.exists(rfx["reference"][:-4] + ".qml") and
      sum(rfx["reference_counts"]) == 300 * 300, "referencia.tif + style")
s_ = osr.SpatialReference()
s_.ImportFromEPSG(32614)
_fe = [(w, s_.ExportToWkt(), c, g)
       for w, c, g in synth.field_polygons(cls, set(range(0, 400, 3)))]
Sfx, _ = samples.extract(rfx["path"], _fe, inner_buffer=0)
rk_fx = separability.ranking(Sfx, "ms", by_field=True)
best_rel = max(x["jm"] for x in rk_fx if "_REL" in x["var"] and
               x["var"].endswith("CIre"))
best_fix = max(x["jm"] for x in rk_fx if "_REL" not in x["var"] and
               x["var"].endswith("CIre") and "_FEN_" not in x["var"])
check(best_rel > best_fix + 0.5,
      "staggered sowing: CIre JM relative %.2f vs fixed %.2f" % (
          best_rel, best_fix))
r = features.build(cdir, res=20)
vpath = r["path"]
cat = features.read_catalog(os.path.dirname(vpath))
names = [c["name"] for c in cat]
check(len(names) == len(set(names)) and names[0].startswith("S2_REL1_"),
      "variables: unique names, relative windows first")
check(not any(n.startswith("S2_0") for n in names) and
      "S2_FEN_VELsube" in names and "S2_FEN_DIAmax" not in names,
      "defaults: no fixed stages, shape metrics, no absolute dates")
check(any(n.startswith("LS_") for n in names) and
      not any("LS_" in n and ("NDRE" in n or "CIre" in n) for n in names),
      "Landsat kept apart, no red-edge indices for Landsat")
nobs = gdal.Open(r["nobs"])
check(nobs.RasterCount == 8, "nobs: 4 relative windows x 2 sensors")
ds = gdal.Open(vpath)
check(abs(ds.GetGeoTransform()[1] - 20) < 1e-9 and ds.RasterXSize == 300,
      "grid 20 m, 300 px")
params = json.load(open(os.path.join(os.path.dirname(vpath),
                                     "parametros.txt")))
check(params["day0"] == "2026-01-15" and params["s2_clear_scl"] == [4, 5],
      "parametros.txt")

# samples: one field in three
s = osr.SpatialReference()
s.ImportFromEPSG(32614)
srs = s.ExportToWkt()
polys = synth.field_polygons(cls, set(range(0, 400, 3)))
feats = [(w, srs, c, gid) for w, c, gid in polys]
feats.append((polys[0][0], srs, "arroz", "x"))   # ignored class
S, rep = samples.extract(vpath, feats, inner_buffer=0)
check(rep["ignored_class"] == 1 and rep["outside"] == 0,
      "samples: unknown class ignored")
# 240 m fields on a 20 m grid: 12 or 13 pixel centres per side
per = np.unique(S.g, return_counts=True)[1]
check(len(per) == 134 and per.min() >= 144 and per.max() <= 169,
      "samples: 12-13 px per side in every field (%d-%d)" % (per.min(),
                                                            per.max()))
S2, _ = samples.extract(vpath, feats, inner_buffer=30)
per2 = np.unique(S2.g, return_counts=True)[1]
check(per2.min() >= 81 and per2.max() <= 100,
      "inner buffer 30 m -> 9-10 px per side (%d-%d)" % (per2.min(),
                                                         per2.max()))
csvp = os.path.join(TMP, "m.csv")
S.save_csv(csvp)
L = samples.Samples.load_csv(csvp)
check(len(L) == len(S) and np.allclose(np.nan_to_num(L.X),
                                       np.nan_to_num(S.X), atol=1e-4),
      "samples CSV round trip")
# points
pts = []
for w, c, gid in polys[:5]:
    from osgeo import ogr
    ctr = ogr.CreateGeometryFromWkt(w).Centroid()
    pts.append((ctr.ExportToWkt(), srs, c, gid))
SP, _ = samples.extract(vpath, pts, point_radius=0)
check(len(SP) == 5, "points: one pixel each")

# separability, step 2 on the hard case: red-edge must lead
rk = separability.ranking(S, "ms")
check(any(k in rk[0]["var"] for k in ("CIre", "NDRE", "B05")),
      "step 2 ranking led by red-edge (%s)" % rk[0]["var"])
rk1 = separability.ranking(S, "c4")
check(rk1[0]["jm"] > 1.9, "step 1: some variable separates C4 from other")
rkf = separability.ranking(S, "ms", by_field=True)
check(rkf[0]["n_a"] < 60, "per-field ranking uses one value per field")
path = separability.forward_selection(S, "ms", k=3)
check(len(path) >= 1 and path[-1][1] >= path[0][1],
      "forward selection increases JM")
rule = os.path.join(TMP, "rule.tif")
km2 = separability.apply_rule(vpath, rk[0]["var"], rk[0]["thr"],
                              rk[0]["dir"], rule)
check(km2 > 0 and os.path.exists(rule[:-4] + ".qml"), "rule map + style")

# classification
for eng in ("sklearn", "numpy"):
    if eng == "sklearn" and not classify.sklearn_available():
        print("SKIP sklearn not installed")
        continue
    cv = classify.cross_validate(S, names, "hier", k=4, engine=eng,
                                 n_trees=60 if eng == "sklearn" else 25,
                                 max_per_class=600,
                                 importance=(eng == "sklearn"))
    check(cv["engine"] == eng, "%s engine used" % eng)
    check(cv["step1"]["oa"] > 0.95 and cv["step2"]["oa"] > 0.9,
          "%s hierarchical CV: step1 %.3f, step2 %.3f" % (
              eng, cv["step1"]["oa"], cv["step2"]["oa"]))
    check(cv["field"]["n"] == 134, "%s: field-level metrics over 134 fields"
          % eng)
    if "importance" in cv:
        top2 = max(cv["importance"], key=lambda x: x["step2"])["var"]
        check(any(k in top2 for k in ("CIre", "NDRE", "B05")),
              "importance step 2 -> red-edge (%s)" % top2)
cvf = classify.cross_validate(S, names, "flat", k=4, n_trees=60,
                              max_per_class=600, importance=False)
check(cvf["pixel"]["oa"] > 0.9, "flat CV %.3f" % cvf["pixel"]["oa"])

model = classify.fit_final(S, names, "hier", n_trees=60, max_per_class=800)
out = os.path.join(cdir, "clasificacion")
mp = classify.predict_map(model, vpath, names, out, "jerarquica",
                          majority=True)
cm = gdal.Open(mp["classes"]).ReadAsArray()
truth = C[::2, ::2] + 1
cl_ok = cm > 0
check(cl_ok.mean() > 0.97, "map: %.1f %% of pixels classified" %
      (100 * cl_ok.mean()))
acc = (cm[cl_ok] == truth[cl_ok]).mean()
check(acc > 0.95, "map vs synthetic truth %.3f" % acc)
unseen = ~np.isin(synth.field_map(1)[1][::2, ::2],
                  list(range(0, 400, 3))) & cl_ok
check((cm[unseen] == truth[unseen]).mean() > 0.9,
      "map on fields not used for training %.3f" %
      (cm[unseen] == truth[unseen]).mean())
pr = gdal.Open(mp["prob"]).ReadAsArray().astype(int)
check(np.all(np.abs(pr[:, cl_ok].sum(0) - 100) <= 2) and
      np.all(pr[:, ~cl_ok] == 255), "probabilities add to 100, 255 if none")
check(os.path.exists(mp["classes"][:-4] + ".qml"), "class style written")
js = classify.write_report(out, "jerarquica", cv, mp, {"mode": "hier"})
check(os.path.exists(js) and os.path.exists(os.path.join(
    out, "jerarquica_confusion.csv")), "report files")
# min_valid: a variables file with holes -> nodata
hole = os.path.join(TMP, "hole.tif")
gdal.Translate(hole, vpath)
hd = gdal.Open(hole, gdal.GA_Update)
for b in range(1, hd.RasterCount + 1):
    a = hd.GetRasterBand(b).ReadAsArray()
    a[:10, :10] = np.nan
    hd.GetRasterBand(b).WriteArray(a)
hd = None
mp2 = classify.predict_map(model, hole, names, os.path.join(TMP, "h"),
                           "x")
check(mp2["nodata_px"] == mp["nodata_px"] + int(cl_ok[:10, :10].sum()),
      "pixels without data -> no class")

# groups
cl = cluster.run(vpath, [n for n in names if n.startswith("S2_") and
                         (n.endswith("_NDVI") or "_FEN_" in n)], k=3,
                 sample_n=20000)
gm = gdal.Open(cl["tif"]).ReadAsArray()
pur = [np.bincount(truth[gm == k], minlength=4)[1:].max() /
       max((gm == k).sum(), 1) for k in (1, 2, 3)]
check(len(cl["npx"]) == 3 and os.path.exists(cl["csv"]),
      "groups: map and table")
check(max(pur) > 0.9, "groups: 'other' comes out as a clean group "
      "(purities %s)" % [round(p, 2) for p in pur])
with open(cl["csv"], encoding="utf-8") as fh:
    rows = list(csv.reader(fh))
check(len(rows) == 4 and rows[0][:3] == ["grupo", "pixeles", "km2"],
      "groups CSV")

print("\n%d failures" % len(FAIL))
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
