"""Minimal STAC API client (search + pagination + signing), no extra deps.

Sources (catalogue, collection, how the files are read):

  es-s2  Earth Search (Element 84, AWS), sentinel-2-c1-l2a, anonymous COG
  pc-s2  Planetary Computer (Microsoft), sentinel-2-l2a, COG + SAS token
  pc-ls  Planetary Computer, landsat-c2-l2 (8/9 only), COG + SAS token
  es-ls  Earth Search, landsat-c2-l2, s3://usgs-landsat (requester pays:
         needs AWS keys, the downloader pays the transfer)

The HTTP transport is injectable: in QGIS QgsBlockingNetworkRequest (proxy
settings apply), in tests plain urllib or a fake.
"""

import json
import re
import time
import urllib.request
from dataclasses import dataclass, field

from .sensors import S2, LS, BANDS, find_asset, LS_SCALE, LS_OFFSET
from .i18n import tr

EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1"
PC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
PC_TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/"

# key: (sensor, i18n label, stac url, collection, auth)
SOURCES = {
    "es-s2": (S2, "src.es.s2", EARTH_SEARCH_URL, "sentinel-2-c1-l2a", None),
    "pc-s2": (S2, "src.pc.s2", PC_URL, "sentinel-2-l2a", "pc"),
    "pc-ls": (LS, "src.pc.ls", PC_URL, "landsat-c2-l2", "pc"),
    "es-ls": (LS, "src.es.ls", EARTH_SEARCH_URL, "landsat-c2-l2", "aws-rp"),
}
NEEDS_KEYS = {"es-ls"}
LANDSAT_PLATFORMS = ("landsat-8", "landsat-9")
MAX_ITEMS = 2000


class StacError(Exception):
    pass


def sources_for(sensor):
    return [k for k, v in SOURCES.items() if v[0] == sensor]


# ---------------------------------------------------------------- transport
def urllib_post_json(url, payload, timeout=60):
    """POST payload as JSON, or GET if payload is None."""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="GET" if payload is None else "POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/geo+json, application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def qgis_post_json(url, payload, timeout=60):
    """Same with the QGIS network stack (user proxy/SSL settings)."""
    from qgis.core import QgsBlockingNetworkRequest
    from qgis.PyQt.QtCore import QUrl, QByteArray
    from qgis.PyQt.QtNetwork import QNetworkRequest

    req = QNetworkRequest(QUrl(url))
    req.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
    req.setRawHeader(b"Accept", b"application/geo+json, application/json")
    blocking = QgsBlockingNetworkRequest()
    if payload is None:
        err = blocking.get(req)
    else:
        err = blocking.post(
            req, QByteArray(json.dumps(payload).encode("utf-8")))
    if err != QgsBlockingNetworkRequest.NoError:
        raise StacError(tr("stac.net", blocking.errorMessage()))
    content = bytes(blocking.reply().content())
    try:
        return json.loads(content.decode("utf-8"))
    except ValueError as e:
        raise StacError(tr("stac.json", e))


# ---------------------------------------------------------------- PC token
class PcSigner:
    """Anonymous SAS tokens from Planetary Computer, cached per collection
    and renewed 5 minutes before they expire."""

    def __init__(self, get_json=None, now=time.time):
        self.get_json = get_json or (lambda u: urllib_post_json(u, None))
        self.now = now
        self.cache = {}  # collection -> (token, expiry epoch)

    def token(self, collection):
        tok = self.cache.get(collection)
        if tok and tok[1] - self.now() > 300:
            return tok[0]
        try:
            js = self.get_json(PC_TOKEN_URL + collection)
        except Exception as e:
            raise StacError(tr("stac.token", e))
        if "token" not in js:
            raise StacError(tr("stac.token", str(js)[:200]))
        exp = _parse_iso(js.get("msft:expiry")) or (self.now() + 1800)
        self.cache[collection] = (js["token"], exp)
        return js["token"]

    def sign(self, href, collection):
        if "?" in href and "sig=" in href:
            return href  # already signed
        return href + ("&" if "?" in href else "?") + self.token(collection)


def _parse_iso(s):
    if not s:
        return None
    import calendar
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})", s)
    if not m:
        return None
    return calendar.timegm(tuple(int(x) for x in m.groups()) + (0, 0, 0))


# ---------------------------------------------------------------- items
@dataclass
class BandAsset:
    band: str
    key: str
    href: str
    scale: float
    offset: float


@dataclass
class Scene:
    id: str
    sensor: str
    source: str
    collection: str
    datetime: str
    date: str
    tile: str          # MGRS tile (S2) or WRS-2 path/row PPPRRR (Landsat)
    cloud_tile: float
    baseline: str
    platform: str
    auth: str = None
    assets: dict = field(default_factory=dict)
    missing: list = field(default_factory=list)
    footprint: dict = None
    datatake: str = ""
    stage: str = ""    # filled by the phenology calendar

    @property
    def short_platform(self):
        p = self.platform.lower()
        if p.startswith("sentinel-2"):
            return "S2" + p[-1].upper()
        if p.startswith("landsat-"):
            return "L" + p.split("-")[1]
        return p or "?"

    @property
    def label(self):
        return "%s  %s  %s" % (self.date, self.tile, self.short_platform)


def _s2_tile(props, item_id):
    if props.get("s2:mgrs_tile"):
        return props["s2:mgrs_tile"]
    zone = props.get("mgrs:utm_zone")
    if zone is not None:
        return "%s%s%s" % (zone, props.get("mgrs:latitude_band", ""),
                           props.get("mgrs:grid_square", ""))
    code = props.get("grid:code", "")
    if code.startswith("MGRS-"):
        return code[5:]
    m = re.search(r"_T(\d{2}[A-Z]{3})(_|$)", item_id)
    if m:
        return m.group(1)
    parts = item_id.split("_")
    return parts[1] if len(parts) > 1 else "?"


def _ls_pathrow(props, item_id):
    p, r = props.get("landsat:wrs_path"), props.get("landsat:wrs_row")
    if p is not None and r is not None:
        return "%03d%03d" % (int(p), int(r))
    m = re.search(r"_(\d{6})_\d{8}_", item_id)  # LC09_L2SP_026042_2026...
    return m.group(1) if m else "?"


def _datatake(sensor, props, item_id, sc):
    if sensor == S2:
        if props.get("s2:datatake_id"):
            return str(props["s2:datatake_id"])
        parts = item_id.split("_")
        if len(parts) > 2 and "T" in parts[2] and len(parts[2]) == 15:
            return "%s_%s" % (parts[0], parts[2])
        return "%s_%s" % (sc.platform, sc.date)
    # Landsat: consecutive rows of one path on one day are one pass
    return "%s_%s_%s" % (sc.platform, sc.date, sc.tile[:3])


def _scale_offset(sensor, asset, band, baseline):
    """Reflectance = DN * scale + offset, from STAC raster:bands if present.
    Fallbacks: S2 ESA convention (offset -0.1 from baseline 04.00), Landsat
    C2 L2 constants. Masks are categorical (1, 0)."""
    if band in ("SCL", "QA_PIXEL"):
        return 1.0, 0.0
    rb = asset.get("raster:bands") or []
    if rb and ("scale" in rb[0] or "offset" in rb[0]):
        return float(rb[0].get("scale", 1.0)), float(rb[0].get("offset", 0.0))
    if sensor == LS:
        return LS_SCALE, LS_OFFSET
    try:
        ge4 = float(baseline) >= 4.0
    except (TypeError, ValueError):
        return 0.0001, float("nan")  # unknown: say so, do not guess
    return 0.0001, (-0.1 if ge4 else 0.0)


def _href(asset, auth):
    href = asset["href"]
    alts = asset.get("alternate") or {}
    if auth == "aws-rp":
        # requester-pays bucket: read with S3 credentials
        if href.startswith("s3://"):
            return href
        s3 = (alts.get("s3") or {}).get("href")
        return s3 or href
    https = (alts.get("https") or {}).get("href")
    if href.startswith("s3://") and https:
        return https
    return href


def parse_item(item, source_key, bands=None):
    sensor, _, _, _, auth = SOURCES[source_key]
    bands = bands or list(BANDS[sensor])
    props = item.get("properties", {})
    dt = props.get("datetime") or ""
    baseline = str(props.get("s2:processing_baseline",
                             props.get("processing:version", "")) or "")
    if sensor == S2 and not baseline:
        m = re.search(r"_N(\d{2})(\d{2})_", item["id"])
        if m:
            baseline = "%s.%s" % m.groups()
    if sensor == LS:
        baseline = str(props.get("landsat:collection_category", "") or "")
    sc = Scene(
        id=item["id"], sensor=sensor, source=source_key,
        collection=item.get("collection", SOURCES[source_key][3]),
        datetime=dt, date=dt[:10],
        tile=_s2_tile(props, item["id"]) if sensor == S2
        else _ls_pathrow(props, item["id"]),
        cloud_tile=float(props.get("eo:cloud_cover", float("nan"))),
        baseline=baseline, platform=str(props.get("platform", "")),
        auth=auth)
    sc.footprint = item.get("geometry")
    sc.datatake = _datatake(sensor, props, item["id"], sc)
    for b in bands:
        key, asset = find_asset(item.get("assets", {}), sensor, b)
        if asset is None:
            sc.missing.append(b)
            continue
        scale, offset = _scale_offset(sensor, asset, b, baseline)
        sc.assets[b] = BandAsset(b, key, _href(asset, auth), scale, offset)
    return sc


def search(bbox_4326, date_from, date_to, source_key="es-s2", max_cloud=60,
           bands=None, post_json=None, max_items=MAX_ITEMS):
    """Search scenes in bbox (lon/lat). Returns Scenes sorted by date."""
    post_json = post_json or urllib_post_json
    sensor, _, url, coll, _ = SOURCES[source_key]
    payload = {
        "collections": [coll],
        "bbox": list(bbox_4326),
        "datetime": "%sT00:00:00Z/%sT23:59:59Z" % (date_from, date_to),
        "limit": 100,
        "query": {"eo:cloud_cover": {"lte": max_cloud}},
    }
    if sensor == LS:
        payload["query"]["platform"] = {"in": list(LANDSAT_PLATFORMS)}
    endpoint = url.rstrip("/") + "/search"
    scenes, seen, pages = [], set(), 0
    while True:
        try:
            fc = post_json(endpoint, payload)
        except StacError:
            raise
        except Exception as e:
            raise StacError(tr("stac.fail", e))
        if "features" not in fc:
            raise StacError(tr("stac.unexpected", str(fc)[:300]))
        for item in fc["features"]:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            props = item.get("properties") or {}
            cc = props.get("eo:cloud_cover")
            if cc is not None and float(cc) > max_cloud:
                continue  # client-side too, in case the query is ignored
            if sensor == LS and props.get("platform") not in \
                    LANDSAT_PLATFORMS:
                continue  # no Landsat 7 (SLC-off stripes) or older
            scenes.append(parse_item(item, source_key, bands))
        pages += 1
        nxt = [lk for lk in fc.get("links", []) if lk.get("rel") == "next"]
        if not nxt or len(scenes) >= max_items or pages > 80:
            break
        lk = nxt[0]
        if lk.get("method", "GET").upper() == "POST" and lk.get("body"):
            body = dict(payload)
            if lk.get("merge"):
                body.update(lk["body"])
            else:
                body = lk["body"]
            endpoint, payload = lk["href"], body
        else:
            endpoint, payload = lk["href"], None
    scenes.sort(key=lambda s: (s.datetime, s.tile))
    return scenes


def find_duplicates(scenes, aoi_wkt_4326):
    """Tiles of one pass that repeat another tile which alone contains the
    whole AOI: {scene_id: kept_tile}. If no single tile contains the AOI
    (usual with a large study area), nothing is marked."""
    from osgeo import ogr
    aoi = ogr.CreateGeometryFromWkt(aoi_wkt_4326)
    groups = {}
    for sc in scenes:
        groups.setdefault((sc.sensor, sc.datatake), []).append(sc)
    dup = {}
    for group in groups.values():
        if len(group) < 2:
            continue
        keeper = None
        for sc in sorted(group, key=lambda s: s.tile):
            if not sc.footprint:
                continue
            fp = ogr.CreateGeometryFromJson(json.dumps(sc.footprint))
            if fp is not None and fp.Contains(aoi):
                keeper = sc
                break
        if keeper is None:
            continue
        for sc in group:
            if sc is not keeper:
                dup[sc.id] = keeper.tile
    return dup
