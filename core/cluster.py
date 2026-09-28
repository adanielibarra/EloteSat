"""Unsupervised grouping (k-means, numpy) to explore without field data.

The groups are NOT crops. They gather pixels with similar variables
(e.g. similar NDVI curves); naming them needs field checks or photo
interpretation. Useful to see how many distinct crop calendars there are
and to choose where to go and sample.
"""

import csv
import json
import os

import numpy as np

from . import rasterio_util as rio
from .downloader import Cancelled


def kmeans(X, k, seed=0, n_init=4, max_iter=100, tol=1e-4):
    """Plain k-means with k-means++ init. Returns (centers, labels,
    inertia) of the best of n_init runs."""
    rng = np.random.default_rng(seed)
    best = None
    n = len(X)
    k = min(k, n)
    for _ in range(n_init):
        c = [X[rng.integers(n)]]
        d2 = ((X - c[0]) ** 2).sum(1)
        for _j in range(1, k):
            p = d2 / d2.sum() if d2.sum() > 0 else None
            c.append(X[rng.choice(n, p=p)])
            d2 = np.minimum(d2, ((X - c[-1]) ** 2).sum(1))
        C = np.array(c, float)
        for _it in range(max_iter):
            lab = assign(X, C)
            newC = np.array([X[lab == j].mean(0) if (lab == j).any()
                             else X[rng.integers(n)] for j in range(k)])
            shift = np.abs(newC - C).max()
            C = newC
            if shift < tol:
                break
        lab = assign(X, C)
        inertia = float(((X - C[lab]) ** 2).sum())
        if best is None or inertia < best[2]:
            best = (C, lab, inertia)
    return best


def assign(X, C):
    d = (X ** 2).sum(1)[:, None] - 2 * X @ C.T + (C ** 2).sum(1)[None]
    return np.argmin(d, axis=1)


def run(vpath, var_names, k=8, sample_n=50000, seed=0, block_px=200000,
        out_dir=None, feedback=None, cancel_check=None):
    log = feedback or (lambda m: None)
    ds, names = rio.open_vars(vpath)
    missing = [v for v in var_names if v not in names]
    if missing:
        raise ValueError("unknown variables: %s" % ", ".join(missing))
    sel = [names.index(v) + 1 for v in var_names]
    allb = list(range(1, len(names) + 1))
    # 1) sample complete pixels
    rng = np.random.default_rng(seed)
    total = ds.RasterXSize * ds.RasterYSize
    keep_p = min(1.0, 3.0 * sample_n / max(total, 1))
    parts = []
    for row0, n in rio.blocks(ds, block_px):
        X = rio.read_block(ds, sel, row0, n)
        ok = np.isfinite(X).all(1) & (rng.random(len(X)) < keep_p)
        parts.append(X[ok])
    S = np.concatenate(parts) if parts else np.empty((0, len(sel)))
    if len(S) < k * 10:
        raise ValueError("too few complete pixels (%d)" % len(S))
    if len(S) > sample_n:
        S = S[rng.choice(len(S), sample_n, replace=False)]
    mu, sd = S.mean(0), S.std(0)
    sd[sd == 0] = 1
    log("k-means: %d pixels, %d variables, k=%d" % (len(S), len(sel), k))
    C, lab, _ = kmeans((S - mu) / sd, k, seed)
    # order groups by size in the sample (1 = largest)
    order = np.argsort(-np.bincount(lab, minlength=len(C)))
    C = C[order]
    # 2) assign every pixel, accumulate means of ALL variables per group
    out_dir = out_dir or os.path.join(os.path.dirname(vpath), "..",
                                      "grupos")
    out_dir = os.path.normpath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    tif = os.path.join(out_dir, "grupos_k%d.tif" % k)
    out = rio.create_like(tif + ".part", ds, 1, rio.gdal.GDT_Byte, 0,
                          ["grupo"])
    kk = len(C)
    # crop-reference coherence (interpretation only), if computed
    rpath = os.path.join(os.path.dirname(vpath), "referencia.tif")
    rds = rio.gdal.Open(rpath) if os.path.exists(rpath) else None
    if rds is not None and (rds.RasterXSize != ds.RasterXSize or
                            rds.RasterYSize != ds.RasterYSize):
        rds = None
    refc = np.zeros((kk, 6), np.int64)
    sums = np.zeros((kk, len(allb)))
    cnts = np.zeros((kk, len(allb)))
    npx = np.zeros(kk, int)
    nodata_px = 0
    w = ds.RasterXSize
    for row0, n in rio.blocks(ds, block_px):
        if cancel_check and cancel_check():
            out = None
            os.remove(tif + ".part")
            raise Cancelled()
        XA = rio.read_block(ds, allb, row0, n)
        X = XA[:, [b - 1 for b in sel]]
        ok = np.isfinite(X).all(1)
        g = np.zeros(len(X), np.uint8)
        if ok.any():
            lab = assign((X[ok] - mu) / sd, C)
            g[ok] = lab + 1
            if rds is not None:
                rc = rds.GetRasterBand(1).ReadAsArray(0, row0, w,
                                                      n).ravel()[ok]
                np.add.at(refc, (lab, np.minimum(rc, 5)), 1)
            for j in range(kk):
                m = lab == j
                if not m.any():
                    continue
                sub = XA[ok][m]
                fin = np.isfinite(sub)
                sums[j] += np.where(fin, sub, 0).sum(0)
                cnts[j] += fin.sum(0)
                npx[j] += m.sum()
        nodata_px += int((~ok).sum())
        out.GetRasterBand(1).WriteArray(g.reshape(n, w), 0, row0)
    out.FlushCache()
    out = None
    os.replace(tif + ".part", tif)
    means = np.where(cnts > 0, sums / np.maximum(cnts, 1), np.nan)
    colors = CLUSTER_COLORS
    rio.write_qml(tif, [(j + 1, "G%d" % (j + 1), colors[j % len(colors)])
                        for j in range(kk)])
    km2 = rio.pixel_area_km2(ds)
    csvp = os.path.join(out_dir, "grupos_k%d.csv" % k)
    with open(csvp, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        rhead = ["ref_" + REF_KEYS[k] for k in range(6)] \
            if rds is not None else []
        wr.writerow(["grupo", "pixeles", "km2"] + rhead + names)
        for j in range(kk):
            wr.writerow(["G%d" % (j + 1), int(npx[j]),
                         round(npx[j] * km2, 3)] +
                        ([int(v) for v in refc[j]] if rds is not None
                         else []) +
                        ["" if np.isnan(v) else round(float(v), 5)
                         for v in means[j]])
    with open(os.path.join(out_dir, "grupos_k%d_parametros.txt" % k), "w",
              encoding="utf-8") as f:
        json.dump({"variables": var_names, "k": k, "sample_n": int(len(S)),
                   "seed": seed, "standardized": "z (sample mean/sd)",
                   "pixels_without_group": nodata_px}, f, indent=2)
    log("-> %s (%d px without all variables)" % (tif, nodata_px))
    return {"tif": tif, "csv": csvp, "names": names, "means": means,
            "npx": npx, "km2": npx * km2, "nodata_px": nodata_px,
            "ref": refc if rds is not None else None}


# short keys of the reference codes (features.REF_LABELS)
REF_KEYS = ("sin_curva", "maiz", "sorgo", "ambos", "ninguno", "incompleta")


# Okabe-Ito order, then two greys; the legend always carries G1..Gk
CLUSTER_COLORS = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2",
                  "#D55E00", "#CC79A7", "#000000", "#999999", "#666666",
                  "#BBBBBB", "#444444"]
