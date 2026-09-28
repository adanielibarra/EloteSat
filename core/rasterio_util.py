"""Block reading/writing helpers for the variables raster (GDAL + numpy)."""

import os

import numpy as np
from osgeo import gdal

gdal.UseExceptions()


def open_vars(path):
    ds = gdal.Open(path)
    names = [ds.GetRasterBand(i).GetDescription()
             for i in range(1, ds.RasterCount + 1)]
    return ds, names


def blocks(ds, block_px=200000):
    rows = max(1, int(block_px // max(ds.RasterXSize, 1)))
    for row0 in range(0, ds.RasterYSize, rows):
        yield row0, min(rows, ds.RasterYSize - row0)


def read_block(ds, bands, row0, n):
    """(n*w, len(bands)) float32 for 1-based band numbers."""
    w = ds.RasterXSize
    X = np.empty((n * w, len(bands)), np.float32)
    for j, b in enumerate(bands):
        X[:, j] = ds.GetRasterBand(b).ReadAsArray(0, row0, w, n).ravel()
    return X


def create_like(path, ds, nbands, dtype, nodata=None, names=None):
    drv = gdal.GetDriverByName("GTiff")
    out = drv.Create(path, ds.RasterXSize, ds.RasterYSize, nbands, dtype,
                     ["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=IF_SAFER"])
    out.SetGeoTransform(ds.GetGeoTransform())
    out.SetProjection(ds.GetProjection())
    for i in range(1, nbands + 1):
        b = out.GetRasterBand(i)
        if nodata is not None:
            b.SetNoDataValue(nodata)
        if names:
            b.SetDescription(names[i - 1])
    return out


def pixel_area_km2(ds):
    gt = ds.GetGeoTransform()
    return abs(gt[1] * gt[5]) / 1e6


def write_qml(tif_path, classes):
    """Paletted style next to the raster (QGIS loads it automatically).
    classes: [(value, label, '#rrggbb')]."""
    items = "\n".join(
        '        <paletteEntry value="%d" label="%s" color="%s" alpha="255"/>'
        % (v, _xml(lbl), col) for v, lbl, col in classes)
    qml = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.28">
  <pipe>
    <rasterrenderer type="paletted" opacity="1" band="1" alphaBand="-1">
      <colorPalette>
%s
      </colorPalette>
    </rasterrenderer>
  </pipe>
</qgis>
""" % items
    with open(os.path.splitext(tif_path)[0] + ".qml", "w",
              encoding="utf-8") as f:
        f.write(qml)


def _xml(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace('"', "&quot;"))


def majority3(cls, nodata=0):
    """3x3 majority filter on a class array (ties keep the centre),
    nodata stays nodata and does not vote."""
    vals = [v for v in np.unique(cls) if v != nodata]
    if not vals:
        return cls
    h, w = cls.shape
    counts = []
    for v in vals:
        m = np.pad((cls == v).astype(np.int16), 1)
        s = sum(m[i:i + h, j:j + w] for i in range(3) for j in range(3))
        counts.append(s)
    counts = np.stack(counts)
    best = np.array(vals)[np.argmax(counts, axis=0)]
    top = counts.max(0)
    centre_count = np.zeros_like(top)
    for k, v in enumerate(vals):
        centre_count[cls == v] = counts[k][cls == v]
    out = np.where(centre_count >= top, cls, best)
    out[cls == nodata] = nodata
    return out.astype(cls.dtype)
