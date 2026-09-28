"""Per-pixel variables from one downloaded cycle, on a common grid.

For each sensor (kept apart, never mixed) and each stage folder:
  median of the clear observations of every band (reflectance) and index.
For each sensor, over the whole cycle: metrics of the NDVI curve (peak,
day of peak, green-up and senescence days at 50 % of the amplitude,
duration, mean NDVI above the base). Days are counted from the start of
the first stage of the cycle.

Processing is done in row blocks, so a large study area does not need to
fit in memory. Output in <cycle>/variables/:
  variables.tif   Float32, one band per variable, nodata NaN
  variables.csv   band number, name, sensor, stage, variable
  nobs.tif        Int16, clear observations per sensor and stage
  parametros.txt
"""

import csv
import datetime as dt
import json
import os
import warnings
from collections import OrderedDict

import numpy as np
from osgeo import gdal, osr

from . import phenology
from .sensors import S2, LS, QA_BAD_MASK
from .downloader import Cancelled

gdal.UseExceptions()

# common band names -> band id per sensor
ROLES = {
    S2: OrderedDict([("blue", "B02"), ("green", "B03"), ("red", "B04"),
                     ("nir", "B08"), ("re1", "B05"), ("re2", "B06"),
                     ("re3", "B07"), ("nir8a", "B8A"), ("swir1", "B11"),
                     ("swir2", "B12")]),
    LS: OrderedDict([("blue", "SR_B2"), ("green", "SR_B3"),
                     ("red", "SR_B4"), ("nir", "SR_B5"),
                     ("swir1", "SR_B6"), ("swir2", "SR_B7")]),
}

# index -> (formula text, roles needed, sensors)
INDICES = OrderedDict([
    ("NDVI", ("(nir - red) / (nir + red)", ("nir", "red"), (S2, LS))),
    ("GCVI", ("nir / green - 1", ("nir", "green"), (S2, LS))),
    ("NDMI", ("(nir - swir1) / (nir + swir1); S2: B8A", ("nir", "swir1"),
              (S2, LS))),
    ("NDTI", ("(swir1 - swir2) / (swir1 + swir2)", ("swir1", "swir2"),
              (S2, LS))),
    ("NDRE", ("(B8A - B05) / (B8A + B05)", ("nir8a", "re1"), (S2,))),
    ("CIre", ("B07 / B05 - 1", ("re3", "re1"), (S2,))),
])

# curve metrics that do not depend on the sowing date (shape) ...
PHEN_SHAPE = ("NDVImax", "AMPLITUD", "VELsube", "VELbaja", "DIASsubemax",
              "DUR50", "NDVImedio")
# ... and absolute dates (days from the cycle start), optional as variables
PHEN_ABS = ("DIAsube50", "DIAmax", "DIAbaja50")
PHEN = PHEN_SHAPE + PHEN_ABS

LS_EXTRA_DAYS = 8  # Landsat windows are widened by this on each side
# windows relative to each pixel's own curve: (name, anchor, from, to) days
REL_WINDOWS = (
    ("REL1_arranque", "DIAsube50", -10, 10),
    ("REL2_maximo", "DIAmax", -10, 10),
    ("REL3_postmax", "DIAmax", 20, 40),
    ("REL4_bajada", "DIAbaja50", -10, 10),
)
DEFAULT_S2_CLEAR = (4, 5)  # vegetation, bare soil
SPIKE_DROP = 0.10          # NDVI drop vs both neighbours -> residual cloud
STEP_DAYS = 5              # regular grid for the NDVI curve
MIN_OBS_PHEN = 4


class FeatureError(Exception):
    pass


def _ratio(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        r = a / b
    r[~np.isfinite(r)] = np.nan
    return r


def compute_index(name, sensor, R):
    """R: role -> reflectance array. Returns array or None."""
    if name == "NDVI":
        return _ratio(R["nir"] - R["red"], R["nir"] + R["red"])
    if name == "GCVI":
        return _ratio(R["nir"], R["green"]) - 1
    if name == "NDMI":
        nir = R["nir8a"] if sensor == S2 else R["nir"]
        return _ratio(nir - R["swir1"], nir + R["swir1"])
    if name == "NDTI":
        return _ratio(R["swir1"] - R["swir2"], R["swir1"] + R["swir2"])
    if name == "NDRE":
        return _ratio(R["nir8a"] - R["re1"], R["nir8a"] + R["re1"])
    if name == "CIre":
        return _ratio(R["re3"], R["re1"]) - 1
    return None


def roles_needed(sensor, indices, bands):
    need = set(ROLES[sensor]) if bands else set()
    for ix in indices:
        if sensor in INDICES[ix][2]:
            need.update(INDICES[ix][1])
            if ix == "NDMI" and sensor == S2:
                need.add("nir8a")
    need.update(("nir", "red"))  # NDVI curve
    return [r for r in ROLES[sensor] if r in need]


# ------------------------------------------------------------ inventory
def read_manifest(cycle_dir):
    man = os.path.join(cycle_dir, "manifest.csv")
    if not os.path.exists(man):
        raise FeatureError("manifest.csv not found in %s" % cycle_dir)
    with open(man, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r.get("status") == "ok"]


def parse_cycle_dir(cycle_dir):
    name = os.path.basename(os.path.normpath(cycle_dir))
    cycle, _, year = name.rpartition("_")
    return cycle, int(year)


def observations(cycle_dir, out_root=None):
    """{sensor: [(date, stage, [file paths])]} grouped by (sensor, date):
    several tiles of one date are one observation."""
    out_root = out_root or os.path.dirname(os.path.normpath(cycle_dir))
    cycle, year = parse_cycle_dir(cycle_dir)
    groups = OrderedDict()
    for r in read_manifest(cycle_dir):
        folder = phenology.stage_dir(out_root, cycle, year, r["stage"],
                                     r["sensor"])
        paths = [os.path.join(folder, n) for n in r["files"].split(";") if n]
        key = (r["sensor"], r["date"])
        g = groups.setdefault(key, {"stage": r["stage"], "tiles": []})
        g["tiles"].append(paths)
    obs = {S2: [], LS: []}
    for (sensor, date), g in sorted(groups.items(), key=lambda kv: kv[0][1]):
        obs.setdefault(sensor, []).append((date, g["stage"], g["tiles"]))
    return obs


def _crs_code(ds):
    s = osr.SpatialReference(wkt=ds.GetProjection())
    return s.GetAuthorityCode(None), ds.GetProjection()


def define_grid(obs, res):
    """Common grid: CRS of most files, union extent snapped to res."""
    counts, wkts, boxes = {}, {}, []
    for sensor, items in obs.items():
        for _, _, tiles in items:
            for paths in tiles:
                ds = gdal.Open(paths[0])
                code, wkt = _crs_code(ds)
                counts[code] = counts.get(code, 0) + 1
                wkts[code] = wkt
                gt = ds.GetGeoTransform()
                boxes.append((code, gt[0], gt[3] + gt[5] * ds.RasterYSize,
                              gt[0] + gt[1] * ds.RasterXSize, gt[3]))
                ds = None
    if not counts:
        raise FeatureError("no downloaded scenes")
    code = max(counts, key=counts.get)
    wkt = wkts[code]
    minx = min(b[1] for b in boxes if b[0] == code)
    miny = min(b[2] for b in boxes if b[0] == code)
    maxx = max(b[3] for b in boxes if b[0] == code)
    maxy = max(b[4] for b in boxes if b[0] == code)
    minx, miny = np.floor(minx / res) * res, np.floor(miny / res) * res
    maxx, maxy = np.ceil(maxx / res) * res, np.ceil(maxy / res) * res
    w, h = int(round((maxx - minx) / res)), int(round((maxy - miny) / res))
    return {"wkt": wkt, "epsg": code, "res": float(res),
            "gt": (minx, res, 0.0, maxy, 0.0, -res), "w": w, "h": h,
            "other_crs": sorted(c for c in counts if c != code)}


# ------------------------------------------------------------ warped reading
class WarpedTile:
    """One downloaded tile (its 1-2 stacks) warped to the grid as VRTs."""

    _n = 0

    def __init__(self, sensor, paths, grid, roles):
        WarpedTile._n += 1
        self.sensor, self.vrts, self.band = sensor, [], {}
        bounds = (grid["gt"][0], grid["gt"][3] + grid["gt"][5] * grid["h"],
                  grid["gt"][0] + grid["gt"][1] * grid["w"], grid["gt"][3])
        need = {ROLES[sensor][r]: r for r in roles}
        mask_id = "SCL" if sensor == S2 else "QA_PIXEL"
        for p in paths:
            ds = gdal.Open(p)
            res = ds.GetGeoTransform()[1]
            descs = [ds.GetRasterBand(i).GetDescription()
                     for i in range(1, ds.RasterCount + 1)]
            for i, d in enumerate(descs, start=1):
                if d not in need and d != mask_id:
                    continue
                if d == mask_id:
                    alg = "mode" if res < grid["res"] else "near"
                elif res < grid["res"]:
                    alg = "average"
                elif res > grid["res"]:
                    alg = "bilinear"
                else:
                    alg = "near"
                src = "/vsimem/fs_src_%d_%s.vrt" % (WarpedTile._n, d)
                dst = "/vsimem/fs_dst_%d_%s.vrt" % (WarpedTile._n, d)
                gdal.Translate(src, ds, bandList=[i], format="VRT")
                gdal.Warp(dst, src, format="VRT", outputBounds=bounds,
                          xRes=grid["res"], yRes=grid["res"],
                          dstSRS=grid["wkt"], resampleAlg=alg,
                          srcNodata=None if d == "QA_PIXEL" else 0,
                          dstNodata=1 if d == "QA_PIXEL" else 0,
                          outputType=gdal.GDT_Float32 if d != mask_id
                          else gdal.GDT_UInt16)
                b = ds.GetRasterBand(i)
                scale = b.GetScale() or 1.0
                off = b.GetOffset() or 0.0
                self.band[d] = (gdal.Open(dst), scale, off)
                self.vrts += [src, dst]
            ds = None

    def read(self, row0, nrows, scl_clear):
        """(role -> reflectance with NaN where not clear) for a row block."""
        mask_id = "SCL" if self.sensor == S2 else "QA_PIXEL"
        if mask_id not in self.band:
            return None
        mds = self.band[mask_id][0]
        m = mds.GetRasterBand(1).ReadAsArray(0, row0, mds.RasterXSize,
                                             nrows)
        if self.sensor == S2:
            clear = np.isin(m, scl_clear)
        else:
            mi = m.astype(np.uint32)
            clear = ((mi & QA_BAD_MASK) == 0) & (mi != 0)
        out = {}
        for bid, (ds, scale, off) in self.band.items():
            if bid == mask_id:
                continue
            a = ds.GetRasterBand(1).ReadAsArray(0, row0, ds.RasterXSize,
                                                nrows).astype(np.float32)
            valid = (a != 0) & clear
            refl = a * scale + off
            refl[~valid] = np.nan
            out[self._role(bid)] = refl
        return out

    def _role(self, bid):
        for r, b in ROLES[self.sensor].items():
            if b == bid:
                return r
        return bid

    def close(self):
        self.band = {}
        for v in self.vrts:
            gdal.Unlink(v)


# ------------------------------------------------------------ NDVI curve
def ndvi_metrics(t, V, spike=SPIKE_DROP, step=STEP_DAYS,
                 min_obs=MIN_OBS_PHEN):
    """t: (T,) day numbers sorted; V: (T, N) NDVI with NaN.
    Returns dict of (N,) arrays for PHEN metrics."""
    T, N = V.shape
    V = V.copy()
    out = {k: np.full(N, np.nan, np.float32) for k in PHEN}
    if T < 3:
        return out
    ar = np.arange(T)[:, None]
    valid = np.isfinite(V)
    # neighbours (previous / next valid) for the spike filter
    fidx = np.where(valid, ar, -1)
    fidx = np.maximum.accumulate(fidx, axis=0)
    bidx = np.where(valid, ar, T)
    bidx = np.minimum.accumulate(bidx[::-1], axis=0)[::-1]
    prev_i = np.vstack([np.full((1, N), -1), fidx[:-1]])
    next_i = np.vstack([bidx[1:], np.full((1, N), T)])
    Vp = np.take_along_axis(V, np.clip(prev_i, 0, T - 1), 0)
    Vn = np.take_along_axis(V, np.clip(next_i, 0, T - 1), 0)
    has_both = (prev_i >= 0) & (next_i < T) & valid
    spikes = has_both & (V < np.minimum(Vp, Vn) - spike)
    V[spikes] = np.nan
    valid = np.isfinite(V)
    nvalid = valid.sum(0)
    # interpolate on a regular grid (no extrapolation)
    fidx = np.maximum.accumulate(np.where(valid, ar, -1), axis=0)
    bidx = np.minimum.accumulate(np.where(valid, ar, T)[::-1], axis=0)[::-1]
    grid_t = np.arange(t[0], t[-1] + 1e-9, step)
    G = np.full((len(grid_t), N), np.nan, np.float32)
    for k, tk in enumerate(grid_t):
        j = np.searchsorted(t, tk, side="right") - 1
        p = fidx[j]
        # next valid obs after position j
        n = bidx[j + 1] if j + 1 < T else np.full(N, T)
        exact = valid[j] & (t[j] == tk)
        ok = (p >= 0) & ((n < T) | exact)
        pc, nc = np.clip(p, 0, T - 1), np.clip(n, 0, T - 1)
        vp = np.take_along_axis(V, pc[None], 0)[0]
        vn = np.take_along_axis(V, nc[None], 0)[0]
        tp, tn = t[pc], t[nc]
        with np.errstate(divide="ignore", invalid="ignore"):
            w = np.where(tn > tp, (tk - tp) / (tn - tp), 0.0)
        val = np.where(n < T, vp + (vn - vp) * w, vp)
        G[k] = np.where(ok, val, np.nan)
    # light smoothing: mean of 3 grid steps where available
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        S = G.copy()
        S[1:-1] = np.nanmean(np.stack([G[:-2], G[1:-1], G[2:]]), axis=0)
        S[np.isnan(G)] = np.nan
        good = (nvalid >= min_obs) & np.isfinite(S).any(0)
        if not good.any():
            return out
        Sg = S[:, good]
        kmax = np.nanargmax(np.where(np.isfinite(Sg), Sg, -np.inf), axis=0)
        vmax = Sg[kmax, np.arange(Sg.shape[1])]
        big = np.where(np.isfinite(Sg), Sg, np.inf)
        idx = np.arange(Sg.shape[0])[:, None]
        pre = np.where(idx <= kmax[None], big, np.inf)
        post = np.where(idx >= kmax[None], big, np.inf)
        base_up, base_dn = pre.min(0), post.min(0)
        thr_up = base_up + 0.5 * (vmax - base_up)
        thr_dn = base_dn + 0.5 * (vmax - base_dn)
        fin = np.isfinite(Sg)
        up_hit = fin & (idx <= kmax[None]) & (Sg >= thr_up[None])
        kup = np.argmax(up_hit, axis=0)
        dn_hit = fin & (idx > kmax[None]) & (Sg < thr_dn[None])
        has_dn = dn_hit.any(0)
        kdn = np.argmax(dn_hit, axis=0)
        mean = np.nanmean(Sg, axis=0)
        # steepest rise before the peak and steepest fall after it
        D = np.diff(Sg, axis=0) / float(step)
        di = np.arange(D.shape[0])[:, None]
        vup = np.nanmax(np.where(di < kmax[None], D, np.nan), axis=0)
        vdn = -np.nanmin(np.where(di >= kmax[None], D, np.nan), axis=0)
    o = {}
    o["NDVImax"] = vmax
    o["DIAmax"] = grid_t[kmax]
    # green-up only meaningful if the curve actually rose before the peak
    rose = (vmax - base_up) >= 0.1
    o["DIAsube50"] = np.where(rose, grid_t[kup], np.nan)
    o["DIAbaja50"] = np.where(has_dn & ((vmax - base_dn) >= 0.1),
                              grid_t[kdn], np.nan)
    o["DUR50"] = o["DIAbaja50"] - o["DIAsube50"]
    o["NDVImedio"] = mean
    o["AMPLITUD"] = vmax - base_up
    o["VELsube"] = vup
    o["VELbaja"] = vdn
    o["DIASsubemax"] = o["DIAmax"] - o["DIAsube50"]
    for k in PHEN:
        out[k][good] = o[k]
    return out


# ------------------------------------------------------------ main
def build(cycle_dir, res=20.0, sensors=(S2, LS), stages=None,
          indices=tuple(INDICES), bands=True, phen=True,
          rel=True, rel_windows=REL_WINDOWS, fixed=False, abs_dates=False,
          ls_extra=LS_EXTRA_DAYS,
          references=None, scl_clear=DEFAULT_S2_CLEAR, block_px=None,
          feedback=None, cancel_check=None, out_root=None):
    """Variables of one cycle.

    rel:        medians in windows relative to each pixel's own NDVI curve
                (rel_windows: (name, anchor metric, from, to) in days).
    fixed:      medians per fixed stage folder (the calendar windows).
    phen:       shape metrics of the NDVI curve (PHEN_SHAPE).
    abs_dates:  also the absolute curve dates (PHEN_ABS) as variables.
    references: {crop: {"arranque": (d0, d1), "maximo": (d0, d1)}} in days
                from the cycle start (see phenology.reference_days); writes
                referencia.tif (interpretation only, never a variable).
    """
    log = feedback or (lambda m: None)
    cycle, year = parse_cycle_dir(cycle_dir)
    calpath = os.path.join(cycle_dir, "calendario.json")
    cal = phenology.load_calendar(calpath) if os.path.exists(calpath) \
        else phenology.copy_calendar()
    day0 = phenology.windows(cal, cycle, year)[0][1]
    obs = observations(cycle_dir, out_root)
    obs = {s: v for s, v in obs.items() if s in sensors and v}
    if not obs:
        raise FeatureError("no scenes for the chosen sensors")
    all_stages = [w[0] for w in phenology.windows(cal, cycle, year)]
    stages = [s for s in (stages or all_stages)]
    if not (rel or fixed or phen or abs_dates):
        raise FeatureError("nothing to compute")
    grid = define_grid(obs, res)
    if grid["other_crs"]:
        log("CRS %s ignored (grid in EPSG:%s)" % (
            ",".join(map(str, grid["other_crs"])), grid["epsg"]))
    log("grid %d x %d px, %.0f m, EPSG:%s" % (grid["w"], grid["h"], res,
                                              grid["epsg"]))
    roles = {s: roles_needed(s, [i for i in indices if s in INDICES[i][2]],
                             bands) for s in obs}
    tiles = {s: [(date, st, [WarpedTile(s, p, grid, roles[s])
                             for p in tl]) for date, st, tl in obs[s]]
             for s in obs}
    avail = {}
    for s in obs:
        ids = set()
        for _, _, wts in tiles[s]:
            for wt in wts:
                ids.update(wt.band)
        avail[s] = {r for r, b in ROLES[s].items() if b in ids}
        if not {"nir", "red"} <= avail[s]:
            raise FeatureError("%s: red/NIR not downloaded" % s)

    # ---- variable list
    vars_, nobs_ = [], []   # (name, sensor, stage, var) / (name, s, stage)
    use_idx, use_roles = {}, {}
    for s in obs:
        use_idx[s] = [i for i in indices if s in INDICES[i][2] and
                      set(INDICES[i][1]) <= avail[s] and
                      not (i == "NDMI" and s == S2 and
                           "nir8a" not in avail[s])]
        use_roles[s] = [r for r in ROLES[s] if r in avail[s]] if bands \
            else []
        vlist = [_vname(s, r) for r in use_roles[s]] + use_idx[s]
        if rel:
            for wname, _, _, _ in rel_windows:
                for v in vlist:
                    vars_.append(("%s_%s_%s" % (_pfx(s), wname, v), s,
                                  wname, v))
                nobs_.append(("%s_%s_nobs" % (_pfx(s), wname), s, wname))
        if fixed:
            for st in stages:
                if not any(o[1] == st for o in obs[s]):
                    continue
                for v in vlist:
                    vars_.append(("%s_%s_%s" % (_pfx(s), st, v), s, st, v))
                nobs_.append(("%s_%s_nobs" % (_pfx(s), st), s, st))
        mets = (PHEN_SHAPE if phen else ()) + (PHEN_ABS if abs_dates
                                               else ())
        for m in mets:
            vars_.append(("%s_FEN_%s" % (_pfx(s), m), s, "FEN", m))
    if not vars_:
        raise FeatureError("no variables to compute")
    ref_sensor = S2 if S2 in obs else LS
    refs = {c: w for c, w in (references or {}).items() if w}

    vdir = os.path.join(cycle_dir, "variables")
    os.makedirs(vdir, exist_ok=True)
    fpath = os.path.join(vdir, "variables.tif")
    npath = os.path.join(vdir, "nobs.tif")
    rpath = os.path.join(vdir, "referencia.tif")
    drv = gdal.GetDriverByName("GTiff")
    opts = ["COMPRESS=DEFLATE", "PREDICTOR=3", "TILED=YES",
            "BIGTIFF=IF_SAFER"]
    fds = drv.Create(fpath + ".part", grid["w"], grid["h"], len(vars_),
                     gdal.GDT_Float32, opts)
    nds = drv.Create(npath + ".part", grid["w"], grid["h"],
                     max(len(nobs_), 1), gdal.GDT_Int16,
                     ["COMPRESS=DEFLATE", "TILED=YES"])
    rds = None
    if refs:
        rds = drv.Create(rpath + ".part", grid["w"], grid["h"], 1,
                         gdal.GDT_Byte, ["COMPRESS=DEFLATE", "TILED=YES"])
    for d in (fds, nds, rds):
        if d is not None:
            d.SetGeoTransform(grid["gt"])
            d.SetProjection(grid["wkt"])
    for i, v in enumerate(vars_, start=1):
        b = fds.GetRasterBand(i)
        b.SetDescription(v[0])
        b.SetNoDataValue(float("nan"))
    for i, v in enumerate(nobs_, start=1):
        nds.GetRasterBand(i).SetDescription(v[0])
    vindex = {v[0]: i for i, v in enumerate(vars_, start=1)}
    nindex = {v[0]: i for i, v in enumerate(nobs_, start=1)}
    days = {s: np.array([(dt.date(*map(int, d.split("-"))) - day0).days
                         for d, _, _ in obs[s]], float) for s in obs}
    # all dates of a block are held at once when windows are relative
    if block_px is None:
        block_px = 60000 if rel else 200000
    rows = max(1, int(block_px // max(grid["w"], 1)))
    W = grid["w"]
    ref_counts = np.zeros(6, np.int64)

    def put(name, arr, row0, n):
        fds.GetRasterBand(vindex[name]).WriteArray(
            arr.reshape(n, W).astype(np.float32), 0, row0)

    try:
        for row0 in range(0, grid["h"], rows):
            if cancel_check and cancel_check():
                raise Cancelled()
            n = min(rows, grid["h"] - row0)
            log("rows %d-%d / %d" % (row0, row0 + n, grid["h"]))
            npx = n * W
            for s in obs:
                vlist = [_vname(s, r) for r in use_roles[s]] + use_idx[s]
                series = {v: [] for v in vlist}   # var -> [T x (npx,)]
                ndvi_series, stage_of = [], []
                for date, st, wts in tiles[s]:
                    R = None
                    for wt in wts:  # tiles of one date: first valid wins
                        r = wt.read(row0, n, scl_clear)
                        if r is None:
                            continue
                        if R is None:
                            R = r
                        else:
                            for k in R:
                                if k in r:
                                    hole = np.isnan(R[k])
                                    R[k][hole] = r[k][hole]
                    stage_of.append(st)
                    if R is None:
                        empty = np.full(npx, np.nan, np.float32)
                        ndvi_series.append(empty)
                        for v in vlist:
                            series[v].append(empty)
                        continue
                    ndvi = compute_index("NDVI", s, R).ravel()
                    ndvi_series.append(ndvi)
                    for role in use_roles[s]:
                        series[_vname(s, role)].append(R[role].ravel())
                    for ix in use_idx[s]:
                        series[ix].append(ndvi if ix == "NDVI" else
                                          compute_index(ix, s, R).ravel())
                V = np.stack(ndvi_series)
                met = ndvi_metrics(days[s], V)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    if rel:
                        # Landsat revisits every 8-16 days: wider windows
                        ext = ls_extra if s == LS else 0
                        for wname, anchor, a, b in rel_windows:
                            a, b = a - ext, b + ext
                            dtm = days[s][:, None] - met[anchor][None, :]
                            inwin = (dtm >= a) & (dtm <= b)
                            for v in vlist:
                                X = np.stack(series[v])
                                X = np.where(inwin, X, np.nan)
                                put("%s_%s_%s" % (_pfx(s), wname, v),
                                    np.nanmedian(X, axis=0), row0, n)
                            cnt = (inwin & np.isfinite(V)).sum(0)
                            nds.GetRasterBand(nindex["%s_%s_nobs" % (
                                _pfx(s), wname)]).WriteArray(
                                cnt.reshape(n, W).astype(np.int16), 0, row0)
                    if fixed:
                        so = np.array(stage_of)
                        for st in stages:
                            m = so == st
                            if not m.any():
                                continue
                            for v in vlist:
                                X = np.stack(series[v])[m]
                                put("%s_%s_%s" % (_pfx(s), st, v),
                                    np.nanmedian(X, axis=0), row0, n)
                            cnt = np.isfinite(V[m]).sum(0)
                            nds.GetRasterBand(nindex["%s_%s_nobs" % (
                                _pfx(s), st)]).WriteArray(
                                cnt.reshape(n, W).astype(np.int16), 0, row0)
                mets = (PHEN_SHAPE if phen else ()) + (
                    PHEN_ABS if abs_dates else ())
                for m in mets:
                    put("%s_FEN_%s" % (_pfx(s), m), met[m], row0, n)
                if rds is not None and s == ref_sensor:
                    code = coherence(met["DIAsube50"], met["DIAmax"], refs)
                    ref_counts += np.bincount(code, minlength=6)[:6]
                    rds.GetRasterBand(1).WriteArray(
                        code.reshape(n, W).astype(np.uint8), 0, row0)
    finally:
        for s in tiles:
            for _, _, wts in tiles[s]:
                for wt in wts:
                    wt.close()
    for d in (fds, nds, rds):
        if d is not None:
            d.FlushCache()
    fds = nds = rds = None
    os.replace(fpath + ".part", fpath)
    os.replace(npath + ".part", npath)
    if refs:
        os.replace(rpath + ".part", rpath)
        from . import rasterio_util as rio
        rio.write_qml(rpath, [(k, REF_LABELS[k], REF_COLORS[k])
                              for k in range(1, 6)])
    elif os.path.exists(rpath):
        os.remove(rpath)  # stale file from another run
    with open(os.path.join(vdir, "variables.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["band", "name", "sensor", "stage", "variable"])
        for i, v in enumerate(vars_, start=1):
            w.writerow([i] + list(v))
    with open(os.path.join(vdir, "parametros.txt"), "w",
              encoding="utf-8") as f:
        p = {"cycle": cycle, "year": year, "day0": day0.isoformat(),
             "res_m": res, "epsg": grid["epsg"], "sensors": list(obs),
             "relative_windows": [list(x) for x in rel_windows] if rel
             else None,
             "landsat_extra_days": ls_extra if rel else None,
             "fixed_stages": stages if fixed else None,
             "indices": list(indices), "bands": bands,
             "shape_metrics": list(PHEN_SHAPE) if phen else None,
             "absolute_dates_as_variables": abs_dates,
             "crop_references_days": refs or None,
             "reference_sensor": ref_sensor if refs else None,
             "reference_pixels": {REF_LABELS[k]: int(ref_counts[k])
                                  for k in range(6)} if refs else None,
             "s2_clear_scl": list(scl_clear),
             "landsat_bad_qa_bits": "0-5", "spike_drop_ndvi": SPIKE_DROP,
             "curve_step_days": STEP_DAYS, "min_obs_curve": MIN_OBS_PHEN,
             "resampling": "finer->coarser average (mask: mode); "
                           "coarser->finer bilinear (mask: near)",
             "index_formulas": {k: v[0] for k, v in INDICES.items()}}
        json.dump(p, f, ensure_ascii=False, indent=2)
    log("%d variables -> %s" % (len(vars_), fpath))
    zones = None
    try:
        from . import zones as zmod
        zones = zmod.build_zones(fpath)
        log("zonas: %d municipios, %d distritos de riego -> %s" % (
            len(zones["municipios"]), len(zones["distritos"]),
            zones["tif"]))
    except Exception as e:  # never lose the variables for this
        log("zonas: %s" % e)
    return {"zones": zones, "path": fpath, "nobs": npath, "vars": vars_, "grid": grid,
            "reference": rpath if refs else None,
            "reference_counts": ref_counts.tolist() if refs else None}


# ------------------------------------------------------------ references
REF_LABELS = {0: "sin curva", 1: "encaja con maiz", 2: "encaja con sorgo",
              3: "encaja con los dos", 4: "no encaja con ninguno",
              5: "curva incompleta"}
REF_COLORS = {1: "#C28400", 2: "#1F86C8", 3: "#7F7F7F", 4: "#D55E00",
              5: "#BBBBBB"}


def coherence(sube, dmax, refs):
    """Per pixel: does its curve fit the expected windows of each crop?
    refs: {"maiz"|"sorgo": {"arranque": (d0, d1) or None,
                            "maximo": (d0, d1) or None}} in cycle days.
    Codes: 0 no curve, 1 maize only, 2 sorghum only, 3 both, 4 neither,
    5 curve without green-up date (and a green-up window is defined).
    For interpretation only: it never enters a model."""
    code = np.zeros(len(sube), np.uint8)
    has = np.isfinite(dmax)
    fits = {}
    incomplete = np.zeros(len(sube), bool)
    for crop in ("maiz", "sorgo"):
        w = refs.get(crop)
        if not w:
            continue
        ok = has.copy()
        if w.get("arranque"):
            a, b = w["arranque"]
            incomplete |= has & ~np.isfinite(sube)
            with np.errstate(invalid="ignore"):
                ok &= (sube >= a) & (sube <= b)
        if w.get("maximo"):
            a, b = w["maximo"]
            with np.errstate(invalid="ignore"):
                ok &= (dmax >= a) & (dmax <= b)
        fits[crop] = ok
    m = fits.get("maiz", np.zeros(len(sube), bool))
    s = fits.get("sorgo", np.zeros(len(sube), bool))
    code[has] = 4
    code[m & ~s] = 1
    code[s & ~m] = 2
    code[m & s] = 3
    code[has & incomplete & ~m & ~s] = 5
    return code


def _vname(sensor, role_or_index):
    if role_or_index in ROLES[sensor]:
        return ROLES[sensor][role_or_index]
    return role_or_index


def read_catalog(vdir):
    with open(os.path.join(vdir, "variables.csv"), newline="",
              encoding="utf-8") as f:
        return [dict(r, band=int(r["band"])) for r in csv.DictReader(f)]


def _pfx(sensor):
    return "S2" if sensor == S2 else "LS"
