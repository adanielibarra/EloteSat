"""Random Forest classification of maize / sorghum / other, two ways:

  flat          one model with the three classes
  hierarchical  step 1: (maize + sorghum) vs other
                step 2: maize vs sorghum, trained only on maize/sorghum
                P(maize) = P1(maize+sorghum) * P2(maize), etc.

Validation holds out whole FIELDS (the group id of each sample), never
loose pixels of a field that is also in training: grouped, stratified
k-fold. Metrics per pixel and per field (majority of its pixels).
Permutation importance on the held-out folds, separately for step 1
(maize+sorghum vs other) and step 2 (maize vs sorghum).

Uses scikit-learn's RandomForestClassifier when installed, otherwise the
small numpy forest in rf_numpy.
"""

import csv
import json
import os

import numpy as np

from . import rasterio_util as rio
from .downloader import Cancelled
from .samples import CLASSES

CLASS_COLORS = {"maiz": "#C28400", "sorgo": "#1F86C8", "otros": "#009E73"}
MISSING = -9999.0
C4 = ("maiz", "sorgo")


def sklearn_available():
    try:
        import sklearn  # noqa: F401
        return True
    except Exception:
        return False


def make_rf(engine, n_trees, seed, min_leaf=1):
    if engine == "auto":
        engine = "sklearn" if sklearn_available() else "numpy"
    if engine == "sklearn":
        from sklearn.ensemble import RandomForestClassifier
        # n_jobs uses threads for forests: safe inside QGIS
        return RandomForestClassifier(
            n_estimators=n_trees, class_weight="balanced", n_jobs=-1,
            min_samples_leaf=min_leaf, random_state=seed), "sklearn"
    from .rf_numpy import RandomForest
    return RandomForest(n_estimators=n_trees, min_samples_leaf=min_leaf,
                        random_state=seed), "numpy"


class Model:
    def __init__(self, mode, engine="auto", n_trees=200, seed=0):
        self.mode, self.engine, self.n_trees, self.seed = (mode, engine,
                                                          n_trees, seed)

    def _rf(self):
        m, used = make_rf(self.engine, self.n_trees, self.seed)
        self.engine_used = used
        return m

    def fit(self, X, y):
        # missing values -> a constant far below any real value, so the
        # trees can split "no value" apart: with curve windows a missing
        # value carries information (e.g. no green-up inside the season)
        self.med = np.full(X.shape[1], MISSING)
        Xi = self.impute(X)
        y = np.asarray(y, object)
        if self.mode == "flat":
            self.m = self._rf().fit(Xi, y.astype(str))
        else:
            y1 = np.where(np.isin(y, C4), "c4", "otros")
            self.m1 = self._rf().fit(Xi, y1)
            mc4 = np.isin(y, C4)
            self.m2 = None
            if len(set(y[mc4].tolist())) == 2:
                self.m2 = self._rf().fit(Xi[mc4], y[mc4].astype(str))
            else:
                self.only_c4 = y[mc4][0] if mc4.any() else "maiz"
        return self

    def impute(self, X):
        X = np.array(X, np.float64, copy=True)
        bad = ~np.isfinite(X)
        if bad.any():
            X[bad] = np.take(self.med, np.nonzero(bad)[1])
        return X

    @staticmethod
    def _col(model, P, cls):
        cl = list(model.classes_)
        return P[:, cl.index(cls)] if cls in cl else np.zeros(len(P))

    def proba(self, X, imputed=False):
        """(n, 3) probabilities in CLASSES order."""
        Xi = X if imputed else self.impute(X)
        if self.mode == "flat":
            P = self.m.predict_proba(Xi)
            return np.stack([self._col(self.m, P, c) for c in CLASSES], 1)
        P1 = self.m1.predict_proba(Xi)
        pc4 = self._col(self.m1, P1, "c4")
        if self.m2 is not None:
            P2 = self.m2.predict_proba(Xi)
            pm = self._col(self.m2, P2, "maiz")
            ps = self._col(self.m2, P2, "sorgo")
        else:
            pm = np.ones(len(Xi)) * (self.only_c4 == "maiz")
            ps = 1 - pm
        return np.stack([pc4 * pm, pc4 * ps, 1 - pc4], 1)

    def predict(self, X, imputed=False):
        return np.array(CLASSES, object)[np.argmax(self.proba(X, imputed),
                                                   1)]

    # step-wise predictions for importance
    def predict_step1(self, Xi):
        if self.mode == "flat":
            p = self.predict(Xi, imputed=True)
            return np.where(np.isin(p, C4), "c4", "otros")
        return np.asarray(self.m1.predict(Xi), object)

    def predict_step2(self, Xi):
        if self.mode == "flat":
            P = self.proba(Xi, imputed=True)
            return np.where(P[:, 0] >= P[:, 1], "maiz", "sorgo")
        if self.m2 is None:
            return np.array([self.only_c4] * len(Xi), object)
        return np.asarray(self.m2.predict(Xi), object)


# ------------------------------------------------------------ folds
def group_folds(y, g, k, seed=0):
    """Stratified grouped folds: each field goes whole to one fold; fields
    of each class are spread so every fold gets some of each class.
    Returns (fold index per sample, k actually used, warnings)."""
    rng = np.random.default_rng(seed)
    warn = []
    groups = {}
    for gi, yi in zip(g, y):
        groups.setdefault(gi, []).append(yi)
    gcls = {gi: max(set(v), key=v.count) for gi, v in groups.items()}
    gsize = {gi: len(v) for gi, v in groups.items()}
    per_class = {c: [gi for gi in gcls if gcls[gi] == c] for c in CLASSES}
    nmin = min((len(v) for v in per_class.values() if v), default=0)
    if nmin < 2:
        return None, 0, ["not enough fields per class for validation"]
    if nmin < k:
        warn.append("k reduced from %d to %d (fields per class)" % (k, nmin))
        k = nmin
    fold_of = {}
    load = np.zeros(k)
    for c, gl in per_class.items():
        gl = list(gl)
        rng.shuffle(gl)
        gl.sort(key=lambda x: -gsize[x])
        cl = np.zeros(k)
        for gi in gl:
            f = int(np.lexsort((load, cl))[0])  # fewest of this class
            fold_of[gi] = f
            cl[f] += gsize[gi]
            load[f] += gsize[gi]
    return np.array([fold_of[gi] for gi in g]), k, warn


# ------------------------------------------------------------ metrics
def confusion(y_true, y_pred, labels=CLASSES):
    M = np.zeros((len(labels), len(labels)), int)
    li = {c: i for i, c in enumerate(labels)}
    for t, p in zip(y_true, y_pred):
        if t in li and p in li:
            M[li[t], li[p]] += 1
    return M


def scores(M, labels=CLASSES):
    tot = M.sum()
    oa = np.trace(M) / tot if tot else np.nan
    out = {"oa": float(oa), "n": int(tot), "classes": {}}
    for i, c in enumerate(labels):
        pa = M[i, i] / M[i].sum() if M[i].sum() else np.nan
        ua = M[i, i] / M[:, i].sum() if M[:, i].sum() else np.nan
        f1 = 2 * pa * ua / (pa + ua) if (pa + ua) else np.nan
        out["classes"][c] = {"producer": float(pa), "user": float(ua),
                             "f1": float(f1), "n": int(M[i].sum())}
    rec = [v["producer"] for v in out["classes"].values()
           if np.isfinite(v["producer"])]
    out["balanced"] = float(np.mean(rec)) if rec else np.nan
    return out


def _bal_acc(t, p):
    labs = sorted(set(np.asarray(t).tolist()))
    r = [np.mean(np.asarray(p)[np.asarray(t) == c] == c) for c in labs]
    return float(np.mean(r)) if r else np.nan


def field_vote(y, pred, g):
    yt, yp = [], []
    for gi in np.unique(g):
        m = g == gi
        vals, cnt = np.unique(pred[m], return_counts=True)
        yp.append(vals[np.argmax(cnt)])
        tv, tc = np.unique(y[m], return_counts=True)
        yt.append(tv[np.argmax(tc)])
    return np.array(yt, object), np.array(yp, object)


def _cap(y, max_per_class, rng):
    if not max_per_class:
        return np.arange(len(y))
    keep = []
    for c in np.unique(y):
        idx = np.nonzero(y == c)[0]
        if len(idx) > max_per_class:
            idx = rng.choice(idx, max_per_class, replace=False)
        keep.append(idx)
    return np.sort(np.concatenate(keep))


# ------------------------------------------------------------ validation
def cross_validate(samples, var_names, mode, k=5, engine="auto",
                   n_trees=200, max_per_class=5000, importance=True,
                   seed=0, feedback=None, cancel_check=None):
    log = feedback or (lambda m: None)
    X = samples.cols_of(var_names)
    y, g = samples.y, samples.g
    folds, k, warn = group_folds(y, g, k, seed)
    for w in warn:
        log(w)
    if folds is None:
        return {"error": warn[0]}
    rng = np.random.default_rng(seed)
    pred = np.empty(len(y), object)
    imp1 = np.zeros(len(var_names))
    imp2 = np.zeros(len(var_names))
    nimp = 0
    engine_used = None
    for f in range(k):
        if cancel_check and cancel_check():
            raise Cancelled()
        tr = np.nonzero(folds != f)[0]
        te = np.nonzero(folds == f)[0]
        tr = tr[_cap(y[tr], max_per_class, rng)]
        m = Model(mode, engine, n_trees, seed + f).fit(X[tr], y[tr])
        engine_used = getattr(m, "engine_used", engine)
        Xi = m.impute(X[te])
        pred[te] = m.predict(Xi, imputed=True)
        log("fold %d/%d: %d train px, %d test px" % (f + 1, k, len(tr),
                                                     len(te)))
        if importance:
            yt1 = np.where(np.isin(y[te], C4), "c4", "otros")
            base1 = _bal_acc(yt1, m.predict_step1(Xi))
            c4 = np.isin(y[te], C4)
            base2 = _bal_acc(y[te][c4], m.predict_step2(Xi[c4])) \
                if c4.sum() and len(set(y[te][c4].tolist())) == 2 else None
            for j in range(len(var_names)):
                if cancel_check and cancel_check():
                    raise Cancelled()
                Xp = Xi.copy()
                Xp[:, j] = Xp[rng.permutation(len(Xp)), j]
                imp1[j] += base1 - _bal_acc(yt1, m.predict_step1(Xp))
                if base2 is not None:
                    imp2[j] += base2 - _bal_acc(
                        y[te][c4], m.predict_step2(Xp[c4]))
            nimp += 1
    M = confusion(y, pred)
    yt_f, yp_f = field_vote(y, pred, g)
    Mf = confusion(yt_f, yp_f)
    res = {"mode": mode, "k": k, "engine": engine_used, "warnings": warn,
           "pixel": {"confusion": M.tolist(), **scores(M)},
           "field": {"confusion": Mf.tolist(), **scores(Mf)},
           "step1": _two(M, "c4"), "step2": _two(M, "ms")}
    if importance and nimp:
        res["importance"] = [
            {"var": v, "step1": float(imp1[j] / nimp),
             "step2": float(imp2[j] / nimp)}
            for j, v in enumerate(var_names)]
    return res


def _two(M, which):
    """2x2 from the 3x3 pixel confusion. c4: (maiz+sorgo) vs otros over
    all samples. ms: maiz vs sorgo among true maize/sorghum samples
    predicted as maize or sorghum (step 2 on its own)."""
    if which == "c4":
        a = M[:2, :2].sum()
        b = M[:2, 2].sum()
        c = M[2, :2].sum()
        d = M[2, 2]
        M2 = np.array([[a, b], [c, d]])
        return {"labels": ["maiz+sorgo", "otros"], "confusion": M2.tolist(),
                **scores(M2, ("maiz+sorgo", "otros"))}
    M2 = M[:2, :2]
    return {"labels": ["maiz", "sorgo"], "confusion": M2.tolist(),
            **scores(M2, ("maiz", "sorgo"))}


# ------------------------------------------------------------ map
def fit_final(samples, var_names, mode, engine="auto", n_trees=200,
              max_per_class=5000, seed=0):
    X = samples.cols_of(var_names)
    idx = _cap(samples.y, max_per_class, np.random.default_rng(seed))
    return Model(mode, engine, n_trees, seed).fit(X[idx], samples.y[idx])


def predict_map(model, vpath, var_names, out_dir, tag, min_valid=0.5,
                majority=False, block_px=100000, feedback=None,
                cancel_check=None):
    log = feedback or (lambda m: None)
    ds, names = rio.open_vars(vpath)
    sel = [names.index(v) + 1 for v in var_names]
    os.makedirs(out_dir, exist_ok=True)
    ctif = os.path.join(out_dir, "%s_clases.tif" % tag)
    ptif = os.path.join(out_dir, "%s_prob.tif" % tag)
    co = rio.create_like(ctif + ".part", ds, 1, rio.gdal.GDT_Byte, 0,
                         ["clase"])
    po = rio.create_like(ptif + ".part", ds, 3, rio.gdal.GDT_Byte, 255,
                         ["p_%s" % c for c in CLASSES])
    w = ds.RasterXSize
    counts = np.zeros(4, int)
    for row0, n in rio.blocks(ds, block_px):
        if cancel_check and cancel_check():
            co = po = None
            for p in (ctif, ptif):
                os.remove(p + ".part")
            raise Cancelled()
        X = rio.read_block(ds, sel, row0, n)
        ok = np.isfinite(X).mean(1) >= min_valid
        cls = np.zeros(len(X), np.uint8)
        prob = np.full((len(X), 3), 255, np.uint8)
        if ok.any():
            P = model.proba(X[ok])
            cls[ok] = np.argmax(P, 1) + 1
            prob[ok] = np.round(P * 100).astype(np.uint8)
        co.GetRasterBand(1).WriteArray(cls.reshape(n, w), 0, row0)
        for b in range(3):
            po.GetRasterBand(b + 1).WriteArray(prob[:, b].reshape(n, w), 0,
                                               row0)
        log("map rows %d-%d / %d" % (row0, row0 + n, ds.RasterYSize))
    co.FlushCache()
    po.FlushCache()
    co = po = None
    os.replace(ctif + ".part", ctif)
    os.replace(ptif + ".part", ptif)
    if majority:
        _majority_pass(ctif, block_px)
    # counts after filtering
    cds = rio.gdal.Open(ctif)
    for row0, n in rio.blocks(cds, block_px):
        a = cds.GetRasterBand(1).ReadAsArray(0, row0, w, n)
        counts += np.bincount(a.ravel(), minlength=4)[:4]
    km2 = rio.pixel_area_km2(ds)
    cds = None
    rio.write_qml(ctif, [(i + 1, c, CLASS_COLORS[c])
                         for i, c in enumerate(CLASSES)])
    return {"classes": ctif, "prob": ptif,
            "px": {c: int(counts[i + 1]) for i, c in enumerate(CLASSES)},
            "km2": {c: float(counts[i + 1] * km2)
                    for i, c in enumerate(CLASSES)},
            "nodata_px": int(counts[0])}


def _majority_pass(ctif, block_px):
    ds = rio.gdal.Open(ctif, rio.gdal.GA_Update)
    b = ds.GetRasterBand(1)
    h, w = ds.RasterYSize, ds.RasterXSize
    rows = max(1, int(block_px // max(w, 1)))
    out = {}
    for row0 in range(0, h, rows):
        n = min(rows, h - row0)
        r0, r1 = max(0, row0 - 1), min(h, row0 + n + 1)
        a = b.ReadAsArray(0, r0, w, r1 - r0)
        f = rio.majority3(a)
        out[row0] = f[row0 - r0: row0 - r0 + n]
        # write the previous block (its halo rows are no longer needed)
        prev = row0 - rows
        if prev in out:
            b.WriteArray(out.pop(prev), 0, prev)
    for row0, arr in out.items():
        b.WriteArray(arr, 0, row0)
    ds.FlushCache()
    ds = None


def write_report(out_dir, tag, cv, mapres, params):
    os.makedirs(out_dir, exist_ok=True)
    js = os.path.join(out_dir, "%s_informe.json" % tag)
    with open(js, "w", encoding="utf-8") as f:
        json.dump({"params": params, "validation": cv, "map": mapres}, f,
                  indent=2, ensure_ascii=False, default=float)
    if cv and "importance" in cv:
        with open(os.path.join(out_dir, "%s_importancia.csv" % tag), "w",
                  newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["variable", "paso1_maizsorgo_vs_otros",
                        "paso2_maiz_vs_sorgo"])
            for r in sorted(cv["importance"], key=lambda r: -r["step1"]):
                w.writerow([r["var"], "%.4f" % r["step1"],
                            "%.4f" % r["step2"]])
    if cv and "pixel" in cv:
        with open(os.path.join(out_dir, "%s_confusion.csv" % tag), "w",
                  newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for level in ("pixel", "field"):
                w.writerow(["%s: real \\ predicho" % level] + list(CLASSES))
                for c, row in zip(CLASSES, cv[level]["confusion"]):
                    w.writerow([c] + row)
                w.writerow([])
    return js
