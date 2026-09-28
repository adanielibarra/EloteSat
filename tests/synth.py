"""Synthetic downloaded cycle (same layout the download tab writes) with
three crops on square fields: maize, sorghum and 'other'.

This is a PLUMBING test bed, not a model of real crops: the curves and
spectra are invented so that the classes differ in a known way (maize
peaks later and higher, with more red-edge chlorophyll; sorghum reddens
at heading; 'other' is an early short crop or bare soil). Accuracy on
these data says nothing about accuracy on real Tamaulipas fields.
"""
import datetime as dt
import os

import numpy as np
from osgeo import gdal, osr

from elotesat.core import phenology, downloader
from elotesat.core.sensors import S2, LS

EPSG = 32614
OX, OY = 500000.0, 2760000.0
SIZE_M = 6000
FIELD_M = 300
CLASSES = ("maiz", "sorgo", "otros")


def _srs():
    s = osr.SpatialReference()
    s.ImportFromEPSG(EPSG)
    return s.ExportToWkt()


def field_map(seed=1):
    """Class (0 maize, 1 sorghum, 2 other) and field id per 10 m pixel,
    plus per-field sowing shift in days."""
    rng = np.random.default_rng(seed)
    nf = SIZE_M // FIELD_M
    cls = rng.choice(3, size=(nf, nf), p=[0.3, 0.3, 0.4])
    shift = rng.normal(0, SHIFT_SD, size=(nf, nf))
    n = SIZE_M // 10
    k = FIELD_M // 10
    C = np.kron(cls, np.ones((k, k), int))
    ids = np.arange(nf * nf).reshape(nf, nf)
    F = np.kron(ids, np.ones((k, k), int))
    Sh = np.kron(shift, np.ones((k, k)))
    return C[:n, :n], F[:n, :n], Sh[:n, :n], cls


def dlogistic(t, up, down, vmin, vmax, k1=0.12, k2=0.10):
    return vmin + (vmax - vmin) * (1 / (1 + np.exp(-k1 * (t - up))) -
                                   1 / (1 + np.exp(-k2 * (t - down))))


HARD = False  # True: maize and sorghum share the NDVI curve
SHIFT_SD = 8  # days: spread of sowing dates between fields


def fraction(day, C, Sh, rng):
    t = day - Sh
    f = np.zeros(C.shape)
    f[C == 0] = dlogistic(t[C == 0], 50, 125, 0.0, 1.0)
    if HARD:
        f[C == 1] = dlogistic(t[C == 1], 50, 125, 0.0, 1.0)
    else:
        f[C == 1] = dlogistic(t[C == 1], 45, 110, 0.0, 0.92)
    oth = C == 2
    f[oth] = dlogistic(t[oth], 15, 65, 0.0, 0.6)
    f += rng.normal(0, 0.03, f.shape)
    return np.clip(f, 0, 1)


def reflectances(day, C, Sh, f, rng):
    t = day - Sh
    heading = (C == 1) & (t > 80) & (t < 110)  # sorghum panicles
    if HARD:
        heading = heading & False  # only the red-edge differs
    R = {}
    R["blue"] = 0.06 - 0.03 * f
    R["green"] = 0.09 - 0.02 * f
    R["red"] = 0.13 - 0.10 * f + 0.03 * heading
    R["nir"] = 0.22 + 0.28 * f
    chl = np.where(C == 0, 1.0, 0.8)  # more red-edge contrast for maize
    R["re1"] = 0.14 - 0.06 * f * chl
    R["re2"] = 0.18 + 0.15 * f
    R["re3"] = 0.21 + 0.25 * f
    R["nir8a"] = R["nir"] + 0.01
    R["swir1"] = 0.30 - 0.12 * f + 0.02 * heading
    R["swir2"] = 0.25 - 0.13 * f
    for k in R:
        R[k] = np.clip(R[k] + rng.normal(0, 0.004, f.shape), 0.001, 0.9)
    return R


def _write(path, arrs, names, res, scale, offset, nodata_bands=()):
    n = arrs[0].shape
    ds = gdal.GetDriverByName("GTiff").Create(
        path, n[1], n[0], len(arrs), gdal.GDT_UInt16,
        ["COMPRESS=DEFLATE", "TILED=YES"])
    ds.SetGeoTransform((OX, res, 0, OY, 0, -res))
    ds.SetProjection(_srs())
    for i, (a, nm) in enumerate(zip(arrs, names), start=1):
        b = ds.GetRasterBand(i)
        b.WriteArray(a)
        b.SetDescription(nm)
        b.SetNoDataValue(0)
        if nm not in ("SCL", "QA_PIXEL"):
            b.SetScale(scale)
            b.SetOffset(offset)
    ds = None


def _agg(a, k):
    h, w = a.shape[0] // k, a.shape[1] // k
    return a[:h * k, :w * k].reshape(h, k, w, k).mean(axis=(1, 3))


def build(out_root, cycle="OI", year=2026, seed=1, s2_step=5, ls_step=16,
          cloud_frac=0.15):
    rng = np.random.default_rng(seed)
    C, F, Sh, cls = field_map(seed)
    cal = phenology.copy_calendar()
    w = phenology.windows(cal, cycle, year)
    day0, end = w[0][1], w[-1][2]
    cdir = phenology.cycle_dir(out_root, cycle, year)
    os.makedirs(cdir, exist_ok=True)
    phenology.save_calendar(cal, os.path.join(cdir, "calendario.json"))
    recs = []
    days = [(s, d) for s, step in ((S2, s2_step), (LS, ls_step))
            for d in range(0, (end - day0).days + 1, step)]
    for sensor, day in days:
        date = day0 + dt.timedelta(days=day)
        stage = phenology.assign(date, cal, cycle, year)
        folder = phenology.stage_dir(out_root, cycle, year, stage, sensor)
        os.makedirs(folder, exist_ok=True)
        f = fraction(day, C, Sh, rng)
        R = reflectances(day, C, Sh, f, rng)
        # cloud: a random horizontal band
        cloud = np.zeros(C.shape, bool)
        if rng.random() < 0.5:
            h0 = rng.integers(0, C.shape[0])
            cloud[h0:h0 + int(cloud_frac * C.shape[0])] = True
        ds = date.strftime("%Y%m%d")
        if sensor == S2:
            dn = {k: np.round((v + 0.1) / 1e-4).astype(np.uint16)
                  for k, v in R.items()}
            tile, plat = "14RPQ", "S2A"
            n10 = ["B02", "B03", "B04", "B08"]
            r10 = ["blue", "green", "red", "nir"]
            p10 = "S2_%s_%s_%s_10m.tif" % (ds, tile, plat)
            _write(os.path.join(folder, p10), [dn[r] for r in r10], n10, 10,
                   1e-4, -0.1)
            n20 = ["B05", "B06", "B07", "B8A", "B11", "B12", "SCL"]
            r20 = ["re1", "re2", "re3", "nir8a", "swir1", "swir2"]
            a20 = [np.round(_agg(dn[r].astype(float), 2)).astype(np.uint16)
                   for r in r20]
            scl = np.where(_agg(cloud.astype(float), 2) > 0.5, 9, 4)
            a20.append(scl.astype(np.uint16))
            p20 = "S2_%s_%s_%s_20m.tif" % (ds, tile, plat)
            _write(os.path.join(folder, p20), a20, n20, 20, 1e-4, -0.1)
            files = [p10, p20]
        else:
            roles = ["blue", "green", "red", "nir", "swir1", "swir2"]
            names = ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"]
            arrs = [np.round((_agg(R[r], 3) + 0.2) / 2.75e-5).astype(
                np.uint16) for r in roles]
            qa = np.where(_agg(cloud.astype(float), 3) > 0.5,
                          21824 | 8, 21824).astype(np.uint16)
            p30 = "LS_%s_026043_L9_30m.tif" % ds
            _write(os.path.join(folder, p30), arrs + [qa],
                   names + ["QA_PIXEL"], 30, 2.75e-5, -0.2)
            files = [p30]
        recs.append({"scene_id": "%s_%s" % (sensor, ds), "sensor": sensor,
                     "date": date.isoformat(), "stage": stage,
                     "status": "ok", "files": ";".join(files),
                     "tile": "x", "platform": "x"})
    downloader.append_manifest(cdir, recs)
    return cdir, C, F, cls


def field_polygons(cls, which=None):
    """[(wkt, class_name, field_id)] with a 30 m inner margin already
    applied; which = subset of field ids."""
    nf = cls.shape[0]
    out = []
    for i in range(nf):
        for j in range(nf):
            fid = i * nf + j
            if which is not None and fid not in which:
                continue
            x0 = OX + j * FIELD_M + 30
            y1 = OY - i * FIELD_M - 30
            x1, y0 = x0 + FIELD_M - 60, y1 - FIELD_M + 60
            wkt = "POLYGON((%f %f,%f %f,%f %f,%f %f,%f %f))" % (
                x0, y0, x1, y0, x1, y1, x0, y1, x0, y0)
            out.append((wkt, CLASSES[cls[i, j]], fid))
    return out
