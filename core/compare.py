"""Mapped area vs SIAP sown area, per municipality, same cycle and regime.

A COHERENCE CHECK, NOT A VALIDATION:
  - SIAP figures are declared (administrative) data, not measured;
  - the map carries its classification errors and mixed pixels on field
    edges;
  - SIAP totals are for the whole municipality: the ratio is only given
    when at least 90 % of it is classified on the map (cobertura_pct);
  - the regime of a pixel is only approximated by the CONAGUA irrigation
    districts (inside = riego, outside = temporal): districts include land
    without irrigation rights and there is irrigation outside them.
SIAP value used: sown area at the last cut of the cycle (not harvested:
failed crops lower the harvested area).
"""

import csv
import os

import numpy as np
from osgeo import gdal

from . import siap
from .samples import CLASSES

CROP_NAME = {"maiz": "Maíz grano", "sorgo": "Sorgo grano"}
MIN_COVER = 0.9  # classified share of the municipality to give a ratio


def mapped_areas(class_tif, zones_tif, block_rows=512):
    """{(cvegeo, regime): {class: ha}} from the class map and zonas.tif
    (band 1 cvegeo, band 2 irrigation district code, 0 = none)."""
    c = gdal.Open(class_tif)
    z = gdal.Open(zones_tif)
    if (c.RasterXSize, c.RasterYSize) != (z.RasterXSize, z.RasterYSize):
        raise ValueError("class map and zonas.tif are on different grids")
    gt = c.GetGeoTransform()
    ha = abs(gt[1] * gt[5]) / 1e4
    out, covered = {}, {}
    w, h = c.RasterXSize, c.RasterYSize
    for r0 in range(0, h, block_rows):
        n = min(block_rows, h - r0)
        cl = c.GetRasterBand(1).ReadAsArray(0, r0, w, n).ravel()
        mu = z.GetRasterBand(1).ReadAsArray(0, r0, w, n).ravel()
        dr = z.GetRasterBand(2).ReadAsArray(0, r0, w, n).ravel()
        cl_ok = (cl > 0) & (mu > 0)
        if cl_ok.any():
            u, cnt = np.unique(mu[cl_ok], return_counts=True)
            for cv, nn in zip(u, cnt):
                k = "%05d" % cv
                covered[k] = covered.get(k, 0.0) + nn * ha
        for k, name in enumerate(CLASSES, start=1):
            m = cl == k
            if not m.any():
                continue
            keys = np.stack([mu[m], (dr[m] > 0).astype(np.int64)], 1)
            u, cnt = np.unique(keys, axis=0, return_counts=True)
            for (cv, riego), nn in zip(u, cnt):
                if cv == 0:
                    continue
                d = out.setdefault(("%05d" % cv,
                                    "riego" if riego else "temporal"), {})
                d[name] = d.get(name, 0.0) + nn * ha
    return out, covered


def municipio_area_ha(gpkg=None):
    from osgeo import ogr
    ds = ogr.Open(gpkg or siap.zones_data())
    return {f["cvegeo"]: f.GetGeometryRef().GetArea() / 1e4
            for f in ds.GetLayer("municipios")}


def siap_sown(rows, cycle, siap_anio):
    """{(cvegeo, regime): {class: ha}} sown at the last cut."""
    last = {}
    for r in rows:
        if r["ciclo"] != cycle or r["anio"] != siap_anio:
            continue
        k = (r["cvegeo"], r["modalidad"], r["cultivo"])
        if k not in last or r["fecha"] > last[k]["fecha"]:
            last[k] = r
    out = {}
    for (cv, mod, cult), r in last.items():
        for cls, name in CROP_NAME.items():
            if cult == name:
                d = out.setdefault((cv, mod), {})
                d[cls] = d.get(cls, 0.0) + r["sembrada"]
    return out, max((r["fecha"] for r in last.values()), default=None)


def compare(class_tif, zones_tif, cycle, siap_anio, rows=None,
            names=None, out_csv=None):
    """Rows per municipality and regime with mapped and SIAP hectares of
    maize, sorghum and both, and the ratio mapped / SIAP."""
    rows = rows if rows is not None else siap.read_avance()
    names = names or siap.municipio_names(siap.zones_data())
    mp, covered = mapped_areas(class_tif, zones_tif)
    area = municipio_area_ha()
    sp, cut = siap_sown(rows, cycle, siap_anio)
    out = []
    for key in sorted(set(mp) | set(sp)):
        cv, mod = key
        a, b = mp.get(key, {}), sp.get(key, {})
        rec = {"cvegeo": cv, "municipio": names.get(cv, ""),
               "modalidad": mod, "ciclo": cycle, "anio_siap": siap_anio,
               "corte_siap": cut.isoformat() if cut else ""}
        for cls in ("maiz", "sorgo"):
            rec["mapa_%s_ha" % cls] = round(a.get(cls, 0.0), 1)
            rec["siap_%s_ha" % cls] = round(b.get(cls, 0.0), 1)
        tm = rec["mapa_maiz_ha"] + rec["mapa_sorgo_ha"]
        ts = rec["siap_maiz_ha"] + rec["siap_sorgo_ha"]
        rec["mapa_total_ha"], rec["siap_total_ha"] = round(tm, 1), round(ts,
                                                                        1)
        cov = covered.get(cv, 0.0) / area[cv] if area.get(cv) else 0.0
        rec["cobertura_pct"] = round(100 * cov, 1)
        # the ratio only makes sense if the map covers the municipality
        rec["cociente"] = round(tm / ts, 3) if ts > 0 and \
            cov >= MIN_COVER else ""
        out.append(rec)
    if out_csv:
        os.makedirs(os.path.dirname(out_csv), exist_ok=True)
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0]) if out else
                               ["cvegeo"])
            w.writeheader()
            w.writerows(out)
    return out
