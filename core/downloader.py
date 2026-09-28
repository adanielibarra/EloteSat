"""Clip Sentinel-2 and Landsat COGs to a study area, without resampling.

Only GDAL/OGR/OSR (bundled with QGIS). Per scene:
  1. Open the mask band (S2 SCL, Landsat QA_PIXEL), move the study area to
     the tile CRS and take an integer pixel window snapped to the sensor
     grid (20 m for S2, 30 m for Landsat) from the tile origin.
  2. Read only that mask window. Inside the polygon (not the rectangle):
       cover = pixels with data / polygon pixels
       clear = clear pixels / pixels with data
     Skip the scene before downloading anything else if cover or clear are
     below the thresholds.
  3. Read the same window of every band (integer srcWin, native CRS: pixels
     are copied, not resampled) and stream it to GeoTIFF stacks:
       S2: 10 m (B02 B03 B04 B08) and 20 m (B05 ... B12, SCL)
       Landsat: 30 m (SR_B* and QA_PIXEL)
"""

import json
import math
import os

from osgeo import gdal, ogr, osr

from .sensors import (S2, BANDS, MASK_BAND, SNAP, CLEAR_SCL,
                      clear_pixels, valid_pixels)
from .i18n import tr

gdal.UseExceptions()

GDAL_REMOTE_OPTIONS = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_MAX_RETRY": "4",
    "GDAL_HTTP_RETRY_DELAY": "3",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "VSI_CACHE": "TRUE",
}
GTIFF_OPTS = ["COMPRESS=DEFLATE", "PREDICTOR=2", "TILED=YES",
              "BIGTIFF=IF_SAFER", "NUM_THREADS=ALL_CPUS"]
LANDSAT_REGION = "us-west-2"


class SceneSkipped(Exception):
    pass


class Cancelled(Exception):
    pass


# ------------------------------------------------------------- remote access
def set_remote_options(scene, creds=None):
    """GDAL options for the scene source (thread-local: safe in QgsTask).

    creds = (aws_key, aws_secret) for the requester-pays Landsat bucket;
    if empty, GDAL falls back to AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
    or ~/.aws/credentials.
    """
    for k, v in GDAL_REMOTE_OPTIONS.items():
        gdal.SetThreadLocalConfigOption(k, v)
    for k in ("AWS_REQUEST_PAYER", "AWS_REGION", "AWS_ACCESS_KEY_ID",
              "AWS_SECRET_ACCESS_KEY", "AWS_NO_SIGN_REQUEST"):
        gdal.SetThreadLocalConfigOption(k, None)
    if scene.auth == "aws-rp":
        gdal.SetThreadLocalConfigOption("AWS_REQUEST_PAYER", "requester")
        gdal.SetThreadLocalConfigOption("AWS_REGION", LANDSAT_REGION)
        gdal.SetThreadLocalConfigOption("AWS_NO_SIGN_REQUEST", "NO")
        if creds and creds[0]:
            gdal.SetThreadLocalConfigOption("AWS_ACCESS_KEY_ID", creds[0])
            gdal.SetThreadLocalConfigOption("AWS_SECRET_ACCESS_KEY",
                                            creds[1])
    else:
        gdal.SetThreadLocalConfigOption("AWS_NO_SIGN_REQUEST", "YES")


def gdal_path(href):
    if href.startswith("s3://"):
        return "/vsis3/" + href[5:]
    if href.startswith("http://") or href.startswith("https://"):
        return "/vsicurl/" + href
    return href  # local file (tests)


def resolve(scene, band, signer=None):
    """GDAL path of a band, signing Planetary Computer URLs."""
    href = scene.assets[band].href
    if scene.auth == "pc" and href.startswith("http"):
        if signer is None:
            raise SceneSkipped(tr("core.nosigner"))
        href = signer.sign(href, scene.collection)
    return gdal_path(href)


# ------------------------------------------------------------- geometry
def _srs_4326():
    s = osr.SpatialReference()
    s.ImportFromEPSG(4326)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


def aoi_to_raster_srs(aoi_wkt_4326, ds):
    geom = ogr.CreateGeometryFromWkt(aoi_wkt_4326)
    dst = osr.SpatialReference()
    dst.ImportFromWkt(ds.GetProjection())
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    geom.Segmentize(0.001)  # ~100 m in degrees, keeps long edges honest
    geom.Transform(osr.CoordinateTransformation(_srs_4326(), dst))
    return geom


def snapped_window(geom, ds, buffer_m, snap):
    """Integer pixel window covering geom + buffer, bounds snapped outward
    to a `snap` metre grid anchored at the raster origin and clamped to the
    raster. Returns (window, bounds); SceneSkipped if outside the tile."""
    gt = ds.GetGeoTransform()
    if abs(gt[2]) > 0 or abs(gt[4]) > 0:
        raise ValueError("Rotated rasters not supported")
    minx, maxx, miny, maxy = geom.GetEnvelope()
    minx -= buffer_m
    maxx += buffer_m
    miny -= buffer_m
    maxy += buffer_m
    ox, oy = gt[0], gt[3]
    minx = ox + math.floor((minx - ox) / snap) * snap
    maxx = ox + math.ceil((maxx - ox) / snap) * snap
    maxy = oy - math.floor((oy - maxy) / snap) * snap
    miny = oy - math.ceil((oy - miny) / snap) * snap
    rx1 = ox + gt[1] * ds.RasterXSize
    ry0 = oy + gt[5] * ds.RasterYSize
    minx, maxx = max(minx, ox), min(maxx, rx1)
    miny, maxy = max(miny, ry0), min(maxy, oy)
    if minx >= maxx or miny >= maxy:
        raise SceneSkipped(tr("core.outside"))
    return window_for(ds, (minx, miny, maxx, maxy)), (minx, miny, maxx, maxy)


def window_for(ds, bounds):
    gt = ds.GetGeoTransform()
    minx, miny, maxx, maxy = bounds
    xoff = int(round((minx - gt[0]) / gt[1]))
    yoff = int(round((maxy - gt[3]) / gt[5]))
    xsize = int(round((maxx - minx) / gt[1]))
    ysize = int(round((miny - maxy) / gt[5]))
    return xoff, yoff, xsize, ysize


def polygon_mask(ds, geom):
    """Boolean array: pixel centres of ds inside geom (touched pixels if
    the polygon is smaller than one pixel centre)."""
    mem = gdal.GetDriverByName("MEM").Create(
        "", ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Byte)
    mem.SetGeoTransform(ds.GetGeoTransform())
    mem.SetProjection(ds.GetProjection())
    src = ogr.GetDriverByName("Memory").CreateDataSource("aoi")
    srs = osr.SpatialReference()
    srs.ImportFromWkt(ds.GetProjection())
    lyr = src.CreateLayer("aoi", srs, ogr.wkbUnknown)
    feat = ogr.Feature(lyr.GetLayerDefn())
    feat.SetGeometry(geom)
    lyr.CreateFeature(feat)
    gdal.RasterizeLayer(mem, [1], lyr, burn_values=[1],
                        options=["ALL_TOUCHED=FALSE"])
    mask = mem.GetRasterBand(1).ReadAsArray().astype(bool)
    if mask.sum() == 0:
        mem.GetRasterBand(1).Fill(0)
        gdal.RasterizeLayer(mem, [1], lyr, burn_values=[1],
                            options=["ALL_TOUCHED=TRUE"])
        mask = mem.GetRasterBand(1).ReadAsArray().astype(bool)
    return mask


def mask_stats(sensor, mask_ds, geom, poly_px=None, scl_classes=CLEAR_SCL):
    """(cover, clear, n_px_in_window, histogram) inside the polygon.
    cover = pixels with data / polygon size in pixels (poly_px, the whole
    polygon even beyond the tile edge; default: pixels in the window);
    clear = clear / with data."""
    arr = mask_ds.GetRasterBand(1).ReadAsArray()
    inside = polygon_mask(mask_ds, geom)
    vals = arr[inside]
    n = int(vals.size)
    if n == 0:
        return 0.0, 0.0, 0, {}
    denom = max(float(poly_px or n), float(n))
    data = valid_pixels(sensor, vals)
    clear = clear_pixels(sensor, vals, scl_classes) & data
    nd = int(data.sum())
    hist = {}
    if sensor == S2:
        for v in set(vals.tolist()):
            hist[int(v)] = int((vals == v).sum())
    else:
        hist = {"data": nd, "clear": int(clear.sum())}
    return (min(nd / denom, 1.0), (clear.sum() / float(nd) if nd else 0.0),
            n, hist)


# ------------------------------------------------------------- writing
def _progress_cb(cancel_check):
    if cancel_check is None:
        return None

    def cb(_pct, _msg, _data):
        return 0 if cancel_check() else 1
    return cb


def _write_stack(path, sources, band_ids, scene, meta_extra,
                 cancel_check=None):
    """sources: list of GDAL paths (VRT windows, one band each)."""
    vrt_path = "/vsimem/stack_%s.vrt" % os.path.basename(path)
    gdal.BuildVRT(vrt_path, sources, separate=True)
    tmp = path + ".part"
    try:
        out = gdal.Translate(tmp, vrt_path, format="GTiff",
                             outputType=gdal.GDT_UInt16,
                             creationOptions=GTIFF_OPTS,
                             callback=_progress_cb(cancel_check))
    except RuntimeError:
        if cancel_check and cancel_check():
            _rm(tmp)
            raise Cancelled()
        _rm(tmp)
        raise
    finally:
        gdal.Unlink(vrt_path)
    if out is None:
        _rm(tmp)
        raise Cancelled()
    for i, b in enumerate(band_ids, start=1):
        band = out.GetRasterBand(i)
        band.SetDescription(b)
        # GeoTIFF keeps ONE nodata per file: 0 for all bands. QA_PIXEL fill
        # pixels are 1 (bit 0) and are handled by the QA logic and by the
        # per-band nodata of the mosaics, not by this tag.
        band.SetNoDataValue(0)
        if b not in ("SCL", "QA_PIXEL"):
            a = scene.assets[b]
            band.SetScale(a.scale)
            if not math.isnan(a.offset):
                band.SetOffset(a.offset)
        band.SetMetadata({"band": b,
                          "long_name": BANDS[scene.sensor][b][2]})
    md = {"scene_id": scene.id, "collection": scene.collection,
          "source": scene.source, "sensor": scene.sensor,
          "datetime": scene.datetime, "tile": scene.tile,
          "platform": scene.platform, "baseline": scene.baseline,
          "reflectance": "DN * scale + offset (per band)"}
    md.update({k: str(v) for k, v in meta_extra.items()})
    out.SetMetadata(md)
    out.FlushCache()
    out = None
    os.replace(tmp, path)


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


def file_tag(scene):
    return "%s_%s_%s_%s" % ("S2" if scene.sensor == S2 else "LS",
                            scene.date.replace("-", ""), scene.tile,
                            scene.short_platform)


def process_scene(scene, aoi_wkt_4326, out_dir, bands, min_clear=0.6,
                  min_cover=0.1, buffer_m=0.0, feedback=None, creds=None,
                  signer=None, cancel_check=None):
    """Download one scene clipped to the study area into out_dir (already
    the stage/sensor folder). Returns a manifest record (without stage).
    Raises SceneSkipped (with the record) when rejected."""
    log = feedback or (lambda m: None)
    sensor = scene.sensor
    mband = MASK_BAND[sensor]
    if mband not in scene.assets:
        raise SceneSkipped(tr("core.nomask", mband))
    set_remote_options(scene, creds)
    tag = file_tag(scene)
    mask_src = gdal.Open(resolve(scene, mband, signer))
    geom = aoi_to_raster_srs(aoi_wkt_4326, mask_src)
    win, bounds = snapped_window(geom, mask_src, buffer_m, SNAP[sensor])
    mask_win = gdal.Translate("/vsimem/mask_%s.tif" % tag, mask_src,
                              srcWin=list(win), format="GTiff")
    # cover is measured against the whole polygon, not only the part that
    # falls inside this tile's window
    gt_m = mask_win.GetGeoTransform()
    poly_px = geom.GetArea() / abs(gt_m[1] * gt_m[5])
    cover, clear, npx, hist = mask_stats(sensor, mask_win, geom, poly_px)
    gdal.Unlink("/vsimem/mask_%s.tif" % tag)
    mask_win = None
    log(tr("core.clear", scene.label, 100 * cover, 100 * clear))
    record = {
        "scene_id": scene.id, "sensor": sensor, "source": scene.source,
        "collection": scene.collection, "date": scene.date,
        "datetime": scene.datetime, "tile": scene.tile,
        "platform": scene.platform, "baseline": scene.baseline,
        "cloud_tile_pct": scene.cloud_tile,
        "cover_aoi_pct": round(100 * cover, 2),
        "clear_aoi_pct": round(100 * clear, 2),
        "aoi_px_mask": npx, "mask_hist": json.dumps(hist, sort_keys=True),
        "crs": osr.SpatialReference(wkt=mask_src.GetProjection())
        .GetAuthorityCode(None) or "",
        "bounds": ",".join("%.1f" % v for v in bounds),
    }
    if cover < min_cover:
        record["status"] = "skipped_cover"
        raise SceneSkipped(tr("core.cover", 100 * cover, 100 * min_cover),
                           record)
    if clear < min_clear:
        record["status"] = "skipped_cloudy"
        raise SceneSkipped(tr("core.cloudy", 100 * clear, 100 * min_clear),
                           record)
    os.makedirs(out_dir, exist_ok=True)
    wanted = [b for b in bands if b in scene.assets]
    if mband not in wanted:
        wanted.append(mband)  # the mask always travels with the data
    by_res = {}
    for b in wanted:
        by_res.setdefault(BANDS[sensor][b][1], []).append(b)
    outputs = {}
    extra = {"cover_aoi_pct": record["cover_aoi_pct"],
             "clear_aoi_pct": record["clear_aoi_pct"]}
    for res in sorted(by_res):
        ids = by_res[res]
        srcs = []
        for b in ids:
            if cancel_check and cancel_check():
                raise Cancelled()
            log("  %s (%d m)" % (b, res))
            ds = mask_src if b == mband else gdal.Open(
                resolve(scene, b, signer))
            w = window_for(ds, bounds)
            p = "/vsimem/win_%s_%s.vrt" % (tag, b)
            gdal.Translate(p, ds, srcWin=list(w), format="VRT")
            srcs.append(p)
            ds = None
        path = os.path.join(out_dir, "%s_%dm.tif" % (tag, res))
        try:
            _write_stack(path, srcs, ids, scene, extra, cancel_check)
        finally:
            for p in srcs:
                gdal.Unlink(p)
        outputs["%dm" % res] = path
    record["status"] = "ok"
    record["files"] = ";".join(os.path.basename(v) for v in outputs.values())
    record["scales"] = json.dumps(
        {b: [scene.assets[b].scale, scene.assets[b].offset]
         for b in wanted if b not in ("SCL", "QA_PIXEL")})
    record["outputs"] = outputs
    return record


# ------------------------------------------------------------- mosaics
def build_mosaics(folder, feedback=None):
    """One VRT per date and resolution when a date has several tiles in the
    same CRS (MOS_<sensor>_<date>_<res>.vrt, relative paths so the folder
    can be moved). Tiles in different CRS are not mosaicked (reported).
    Existing MOS_*.vrt in the folder are rebuilt."""
    log = feedback or (lambda m: None)
    if not os.path.isdir(folder):
        return []
    for n in os.listdir(folder):
        if n.startswith("MOS_") and n.endswith(".vrt"):
            os.remove(os.path.join(folder, n))
    groups = {}
    for n in sorted(os.listdir(folder)):
        if not n.endswith(".tif") or n.startswith("MOS_"):
            continue
        parts = n[:-4].split("_")  # S2_20260301_14RPP_S2A_10m
        if len(parts) < 5:
            continue
        key = (parts[0], parts[1], parts[-1])
        groups.setdefault(key, []).append(n)
    made = []
    cwd = os.getcwd()
    for (sen, date, res), names in groups.items():
        if len(names) < 2:
            continue
        crs = set()
        for n in names:
            ds = gdal.Open(os.path.join(folder, n))
            s = osr.SpatialReference(wkt=ds.GetProjection())
            crs.add(s.GetAuthorityCode(None) or ds.GetProjection())
            ds = None
        if len(crs) > 1:
            log(tr("core.mos.crs", date, ", ".join(sorted(crs))))
            continue
        out = "MOS_%s_%s_%s.vrt" % (sen, date, res)
        try:
            os.chdir(folder)  # relative source paths inside the VRT
            ds = gdal.Open(names[0])
            nd = " ".join("1" if ds.GetRasterBand(i).GetDescription() ==
                          "QA_PIXEL" else "0"
                          for i in range(1, ds.RasterCount + 1))
            ds = None
            # per-band nodata: 0, and 1 (fill) for QA_PIXEL
            gdal.BuildVRT(out, names, srcNodata=nd, VRTNodata=nd)
        finally:
            os.chdir(cwd)
        made.append(os.path.join(folder, out))
        log(tr("core.mos", out, len(names)))
    return made


MANIFEST_FIELDS = ["scene_id", "sensor", "source", "collection", "date",
                   "datetime", "tile", "platform", "baseline", "stage",
                   "cloud_tile_pct", "cover_aoi_pct", "clear_aoi_pct",
                   "aoi_px_mask", "status", "reason", "crs", "bounds",
                   "files", "scales", "mask_hist"]


def append_manifest(folder, records):
    import csv
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "manifest.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS,
                           extrasaction="ignore")
        if new:
            w.writeheader()
        for r in records:
            w.writerow(r)
    return path
