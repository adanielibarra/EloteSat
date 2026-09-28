"""Training/validation samples: pixels of the variables raster under
labelled polygons or points. Every sample keeps the id of its polygon
(group), so validation can hold out whole fields, not loose pixels.
"""

import csv
import os

import numpy as np
from osgeo import gdal, ogr, osr

from . import rasterio_util as rio

CLASSES = ("maiz", "sorgo", "otros")
IGNORE = ""


class Samples:
    def __init__(self, X, y, g, names, rows=None, cols=None):
        self.X = np.asarray(X, np.float32)
        self.y = np.asarray(y, object)
        self.g = np.asarray(g, object)
        self.names = list(names)
        self.rows, self.cols = rows, cols

    def __len__(self):
        return len(self.y)

    def summary(self):
        out = {}
        for c in CLASSES:
            m = self.y == c
            out[c] = (int(m.sum()), len(set(self.g[m].tolist())))
        return out

    def subset(self, mask):
        return Samples(self.X[mask], self.y[mask], self.g[mask], self.names,
                       None if self.rows is None else self.rows[mask],
                       None if self.cols is None else self.cols[mask])

    def cols_of(self, var_names):
        idx = [self.names.index(v) for v in var_names]
        return self.X[:, idx]

    def save_csv(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["grupo", "clase", "fila", "col"] + self.names)
            for i in range(len(self)):
                w.writerow([self.g[i], self.y[i],
                            "" if self.rows is None else int(self.rows[i]),
                            "" if self.cols is None else int(self.cols[i])]
                           + ["" if not np.isfinite(v) else "%.6g" % v
                              for v in self.X[i]])

    @classmethod
    def load_csv(cls, path):
        with open(path, newline="", encoding="utf-8") as f:
            r = csv.reader(f)
            head = next(r)
            rows = list(r)
        names = head[4:]
        X = np.array([[float(v) if v != "" else np.nan for v in row[4:]]
                      for row in rows], np.float32).reshape(len(rows),
                                                            len(names))
        return cls(X, [row[1] for row in rows], [row[0] for row in rows],
                   names,
                   np.array([int(row[2]) if row[2] else -1 for row in rows]),
                   np.array([int(row[3]) if row[3] else -1 for row in rows]))


def extract(vpath, features, inner_buffer=10.0, point_radius=0.0,
            max_per_group=None, seed=0, feedback=None):
    """features: [(wkt, srs_wkt, class_name, group_id)]; class_name in
    CLASSES (others are ignored). Polygons shrink by inner_buffer (m);
    points take the pixels within point_radius (0: the pixel under the
    point). Returns Samples and a report dict."""
    log = feedback or (lambda m: None)
    ds, names = rio.open_vars(vpath)
    dst = osr.SpatialReference(wkt=ds.GetProjection())
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    gt = ds.GetGeoTransform()
    res = abs(gt[1])
    drv = ogr.GetDriverByName("Memory")
    src_ds = drv.CreateDataSource("s")
    lyr = src_ds.CreateLayer("s", dst, ogr.wkbUnknown)
    lyr.CreateField(ogr.FieldDefn("gid", ogr.OFTInteger))
    groups, labels = [], []
    rep = {"features": 0, "ignored_class": 0, "empty_after_buffer": 0,
           "outside": 0}
    for wkt, srs_wkt, label, gid in features:
        rep["features"] += 1
        if label not in CLASSES:
            rep["ignored_class"] += 1
            continue
        g = ogr.CreateGeometryFromWkt(wkt)
        if g is None:
            continue
        s = osr.SpatialReference(wkt=srs_wkt)
        s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        if not s.IsSame(dst):
            g.Transform(osr.CoordinateTransformation(s, dst))
        gtype = ogr.GT_Flatten(g.GetGeometryType())
        if gtype in (ogr.wkbPoint, ogr.wkbMultiPoint):
            g = g.Buffer(max(point_radius, res * 0.01))
        elif inner_buffer:
            g = g.Buffer(-inner_buffer)
        if g is None or g.IsEmpty():
            rep["empty_after_buffer"] += 1
            continue
        f = ogr.Feature(lyr.GetLayerDefn())
        f.SetField("gid", len(groups) + 1)
        f.SetGeometry(g)
        lyr.CreateFeature(f)
        groups.append(str(gid))
        labels.append(label)
    if not groups:
        raise ValueError("no usable features")
    mem = gdal.GetDriverByName("MEM").Create("", ds.RasterXSize,
                                             ds.RasterYSize, 1,
                                             gdal.GDT_Int32)
    mem.SetGeoTransform(gt)
    mem.SetProjection(ds.GetProjection())
    gdal.RasterizeLayer(mem, [1], lyr, options=["ATTRIBUTE=gid",
                                                "ALL_TOUCHED=FALSE"])
    ids = mem.GetRasterBand(1).ReadAsArray()
    # points / tiny polygons that hit no pixel centre: take touched pixels
    hit = set(np.unique(ids).tolist()) - {0}
    missing = [i + 1 for i in range(len(groups)) if i + 1 not in hit]
    if missing:
        lyr.SetAttributeFilter("gid IN (%s)" % ",".join(map(str, missing)))
        mem2 = gdal.GetDriverByName("MEM").Create(
            "", ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Int32)
        mem2.SetGeoTransform(gt)
        mem2.SetProjection(ds.GetProjection())
        gdal.RasterizeLayer(mem2, [1], lyr, options=["ATTRIBUTE=gid",
                                                     "ALL_TOUCHED=TRUE"])
        a2 = mem2.GetRasterBand(1).ReadAsArray()
        fill = (ids == 0) & (a2 > 0)
        ids[fill] = a2[fill]
        hit = set(np.unique(ids).tolist()) - {0}
    rep["outside"] = len(groups) - len(hit)
    rr, cc = np.nonzero(ids)
    gi = ids[rr, cc]
    rng = np.random.default_rng(seed)
    if max_per_group:
        keep = np.zeros(len(gi), bool)
        for v in np.unique(gi):
            idx = np.nonzero(gi == v)[0]
            if len(idx) > max_per_group:
                idx = rng.choice(idx, max_per_group, replace=False)
            keep[idx] = True
        rr, cc, gi = rr[keep], cc[keep], gi[keep]
    X = np.full((len(rr), len(names)), np.nan, np.float32)
    for b in range(1, len(names) + 1):
        band = ds.GetRasterBand(b)
        # read only the rows that hold samples
        r0, r1 = (rr.min(), rr.max() + 1) if len(rr) else (0, 0)
        if r1 > r0:
            a = band.ReadAsArray(0, int(r0), ds.RasterXSize, int(r1 - r0))
            X[:, b - 1] = a[rr - r0, cc]
    y = np.array([labels[i - 1] for i in gi], object)
    g = np.array([groups[i - 1] for i in gi], object)
    s = Samples(X, y, g, names, rr, cc)
    rep["pixels"] = len(s)
    rep["by_class"] = s.summary()
    log("samples: %d px; %s" % (len(s), rep["by_class"]))
    return s, rep
