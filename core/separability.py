"""How well do the variables separate two groups of classes?

Jeffries-Matusita distance (JM, 0 to 2) under a Gaussian assumption, per
variable and for small sets chosen by greedy forward selection. And, per
variable, the best single threshold (balanced accuracy on the samples).

Comparisons:
  "c4":  maiz + sorgo  vs  otros   (first step)
  "ms":  maiz          vs  sorgo   (second step)

Caveats written into the report: pixels of one field are not independent,
so JM on pixels looks better than it is; with 'field means' every field
counts once. JM assumes roughly normal classes (it misleads with
bimodal classes, e.g. 'otros' mixing several crops).
"""

import numpy as np

COMPARISONS = {
    "c4": (("maiz", "sorgo"), ("otros",)),
    "ms": (("maiz",), ("sorgo",)),
}


def two_groups(samples, comparison, by_field=False):
    """(A, B, groupsA, groupsB) arrays of the variables for the comparison;
    by_field: one row per field (median of its pixels)."""
    ga, gb = COMPARISONS[comparison]
    ma = np.isin(samples.y, ga)
    mb = np.isin(samples.y, gb)
    A, B = samples.X[ma], samples.X[mb]
    if by_field:
        A = field_medians(A, samples.g[ma])
        B = field_medians(B, samples.g[mb])
    return A, B


def field_medians(X, g):
    out = []
    for v in np.unique(g):
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                out.append(np.nanmedian(X[g == v], axis=0))
    return np.array(out, np.float32).reshape(len(out), X.shape[1])


def jm_1d(a, b):
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 3 or len(b) < 3:
        return np.nan
    m1, m2 = a.mean(), b.mean()
    v1, v2 = a.var(ddof=1), b.var(ddof=1)
    eps = 1e-12 + 1e-9 * max(v1, v2, 1e-12)
    v1, v2 = v1 + eps, v2 + eps
    bh = (m1 - m2) ** 2 / (4 * (v1 + v2)) + 0.5 * np.log(
        (v1 + v2) / (2 * np.sqrt(v1 * v2)))
    return float(2 * (1 - np.exp(-bh)))


def jm_multi(A, B, ridge=1e-6):
    ok_a = np.isfinite(A).all(1)
    ok_b = np.isfinite(B).all(1)
    A, B = A[ok_a], B[ok_b]
    p = A.shape[1]
    if len(A) <= p + 1 or len(B) <= p + 1:
        return np.nan
    m = A.mean(0) - B.mean(0)
    S1 = np.cov(A, rowvar=False).reshape(p, p)
    S2 = np.cov(B, rowvar=False).reshape(p, p)
    scale = np.mean(np.diag(S1) + np.diag(S2)) / 2 or 1.0
    S1 = S1 + np.eye(p) * ridge * scale
    S2 = S2 + np.eye(p) * ridge * scale
    S = (S1 + S2) / 2
    try:
        _, ld = np.linalg.slogdet(S)
        _, l1 = np.linalg.slogdet(S1)
        _, l2 = np.linalg.slogdet(S2)
        bh = m @ np.linalg.solve(S, m) / 8 + 0.5 * (ld - 0.5 * (l1 + l2))
    except np.linalg.LinAlgError:
        return np.nan
    return float(2 * (1 - np.exp(-bh)))


def best_threshold(a, b):
    """Threshold and direction that best split a (positive) from b by
    balanced accuracy. Returns (thr, direction, bal_acc) where direction
    '>' means 'a if value > thr'."""
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) == 0 or len(b) == 0:
        return np.nan, ">", np.nan
    v = np.concatenate([a, b])
    lab = np.concatenate([np.ones(len(a)), np.zeros(len(b))])
    o = np.argsort(v, kind="mergesort")
    v, lab = v[o], lab[o]
    # predicting 'a' for values > v[i]
    a_le = np.cumsum(lab)            # a at or below position i
    b_le = np.cumsum(1 - lab)
    tpr = (len(a) - a_le) / len(a)   # a above threshold
    tnr = b_le / len(b)              # b at or below
    bal_gt = (tpr + tnr) / 2
    bal_lt = ((a_le / len(a)) + (1 - tnr)) / 2
    last = np.r_[v[1:] != v[:-1], True]  # only between distinct values
    bal_gt = np.where(last, bal_gt, -1)
    bal_lt = np.where(last, bal_lt, -1)
    i, j = int(np.argmax(bal_gt)), int(np.argmax(bal_lt))
    nxt = lambda k: v[k + 1] if k + 1 < len(v) else v[k]  # noqa: E731
    if bal_gt[i] >= bal_lt[j]:
        return float((v[i] + nxt(i)) / 2), ">", float(bal_gt[i])
    return float((v[j] + nxt(j)) / 2), "<=", float(bal_lt[j])


def confusion_threshold(a, b, thr, direction):
    """Counts for rule 'class A if value (direction) thr'."""
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if direction == ">":
        pa, pb = a > thr, b > thr
    else:
        pa, pb = a <= thr, b <= thr
    return {"A_as_A": int(pa.sum()), "A_as_B": int((~pa).sum()),
            "B_as_A": int(pb.sum()), "B_as_B": int((~pb).sum())}


def ranking(samples, comparison, by_field=False, var_names=None):
    """[{var, jm, mean_a, mean_b, sd_a, sd_b, thr, dir, bal_acc, n_a, n_b}]
    sorted by JM (NaN last)."""
    A, B = two_groups(samples, comparison, by_field)
    names = samples.names
    out = []
    for j, v in enumerate(names):
        if var_names and v not in var_names:
            continue
        a, b = A[:, j], B[:, j]
        fa, fb = a[np.isfinite(a)], b[np.isfinite(b)]
        thr, d, ba = best_threshold(a, b)
        out.append({"var": v, "jm": jm_1d(a, b),
                    "mean_a": float(fa.mean()) if len(fa) else np.nan,
                    "mean_b": float(fb.mean()) if len(fb) else np.nan,
                    "sd_a": float(fa.std()) if len(fa) > 1 else np.nan,
                    "sd_b": float(fb.std()) if len(fb) > 1 else np.nan,
                    "thr": thr, "dir": d, "bal_acc": ba,
                    "n_a": int(len(fa)), "n_b": int(len(fb))})
    out.sort(key=lambda r: -r["jm"] if np.isfinite(r["jm"]) else 9)
    return out


def forward_selection(samples, comparison, k=5, by_field=False,
                      candidates=None, max_corr=0.95):
    """Greedy: add the variable that most raises multivariate JM; skip
    candidates correlated > max_corr with one already chosen. Returns
    [(var, jm_after)]."""
    A, B = two_groups(samples, comparison, by_field)
    names = samples.names
    cand = [names.index(v) for v in (candidates or names)]
    X = np.vstack([A, B])
    chosen, path = [], []
    for _ in range(k):
        best = (None, -1.0)
        for j in cand:
            if j in chosen:
                continue
            if chosen and _max_abs_corr(X, j, chosen) > max_corr:
                continue
            jm = jm_multi(A[:, chosen + [j]], B[:, chosen + [j]])
            if np.isfinite(jm) and jm > best[1]:
                best = (j, jm)
        if best[0] is None:
            break
        chosen.append(best[0])
        path.append((names[best[0]], best[1]))
        if best[1] >= 1.9999:
            break
    return path


def _max_abs_corr(X, j, chosen):
    ok = np.isfinite(X[:, [j] + chosen]).all(1)
    if ok.sum() < 3:
        return 0.0
    Z = X[ok][:, [j] + chosen]
    sd = Z.std(0)
    if sd[0] == 0:
        return 1.0
    r = [abs(np.corrcoef(Z[:, 0], Z[:, i])[0, 1]) if sd[i] > 0 else 0
         for i in range(1, Z.shape[1])]
    return max(r) if r else 0.0


def apply_rule(vpath, var, thr, direction, out_path, block_px=200000):
    """Raster: 1 where the rule holds, 0 where not, 255 without data."""
    from . import rasterio_util as rio
    ds, names = rio.open_vars(vpath)
    b = names.index(var) + 1
    out = rio.create_like(out_path, ds, 1, rio.gdal.GDT_Byte, 255,
                          ["%s %s %g" % (var, direction, thr)])
    w = ds.RasterXSize
    n_yes = 0
    for row0, n in rio.blocks(ds, block_px):
        a = ds.GetRasterBand(b).ReadAsArray(0, row0, w, n)
        r = np.full(a.shape, 255, np.uint8)
        ok = np.isfinite(a)
        hit = (a > thr) if direction == ">" else (a <= thr)
        r[ok] = hit[ok].astype(np.uint8)
        n_yes += int((r == 1).sum())
        out.GetRasterBand(1).WriteArray(r, 0, row0)
    out.FlushCache()
    out = None
    rio.write_qml(out_path, [(0, "no", "#BBBBBB"),
                             (1, "%s %s %.4g" % (var, direction, thr),
                              "#C28400")])
    return n_yes * rio.pixel_area_km2(ds)
