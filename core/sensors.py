"""Band definitions for Sentinel-2 L2A and Landsat 8/9 Collection 2 L2.

Each band has a list of candidate asset keys: Earth Search / USGS use common
names (red, nir08...), Planetary Computer uses B04... for Sentinel-2 and
common names for Landsat. The eo:bands name is a last fallback.
"""

from collections import OrderedDict

S2 = "S2"
LS = "LANDSAT"
SENSORS = (S2, LS)

# band id -> (candidate asset keys, native resolution m, description)
S2_BANDS = OrderedDict([
    ("B02", (["blue", "B02", "B02_10m"], 10, "Blue 490 nm")),
    ("B03", (["green", "B03", "B03_10m"], 10, "Green 560 nm")),
    ("B04", (["red", "B04", "B04_10m"], 10, "Red 665 nm")),
    ("B08", (["nir", "B08", "B08_10m"], 10, "NIR 842 nm")),
    ("B05", (["rededge1", "B05", "B05_20m"], 20, "Red edge 705 nm")),
    ("B06", (["rededge2", "B06", "B06_20m"], 20, "Red edge 740 nm")),
    ("B07", (["rededge3", "B07", "B07_20m"], 20, "Red edge 783 nm")),
    ("B8A", (["nir08", "B8A", "B8A_20m"], 20, "Narrow NIR 865 nm")),
    ("B11", (["swir16", "B11", "B11_20m"], 20, "SWIR 1610 nm")),
    ("B12", (["swir22", "B12", "B12_20m"], 20, "SWIR 2190 nm")),
    ("SCL", (["scl", "SCL", "SCL_20m"], 20, "Scene classification")),
])

# Landsat 8/9 OLI surface reflectance. Band ids keep the USGS numbering.
LS_BANDS = OrderedDict([
    ("SR_B1", (["coastal", "SR_B1"], 30, "Coastal/aerosol 443 nm")),
    ("SR_B2", (["blue", "SR_B2"], 30, "Blue 482 nm")),
    ("SR_B3", (["green", "SR_B3"], 30, "Green 561 nm")),
    ("SR_B4", (["red", "SR_B4"], 30, "Red 655 nm")),
    ("SR_B5", (["nir08", "SR_B5"], 30, "NIR 865 nm")),
    ("SR_B6", (["swir16", "SR_B6"], 30, "SWIR 1609 nm")),
    ("SR_B7", (["swir22", "SR_B7"], 30, "SWIR 2201 nm")),
    ("QA_PIXEL", (["qa_pixel", "QA_PIXEL"], 30, "Pixel quality bits")),
])

BANDS = {S2: S2_BANDS, LS: LS_BANDS}
MASK_BAND = {S2: "SCL", LS: "QA_PIXEL"}
DEFAULT_BANDS = {S2: list(S2_BANDS), LS: [b for b in LS_BANDS
                                          if b != "SR_B1"]}
# window snapping grid (m): common multiple of the native pixel sizes
SNAP = {S2: 20.0, LS: 30.0}

# ---- Sentinel-2 SCL classes counted as clear
# 4 vegetation, 5 not vegetated, 6 water, 7 unclassified
CLEAR_SCL = (4, 5, 6, 7)
SCL_NAMES = {
    0: "no data", 1: "saturated/defective", 2: "dark/topographic shadow",
    3: "cloud shadow", 4: "vegetation", 5: "not vegetated", 6: "water",
    7: "unclassified", 8: "cloud medium prob.", 9: "cloud high prob.",
    10: "thin cirrus", 11: "snow/ice",
}

# ---- Landsat C2 QA_PIXEL bits (USGS Landsat 8-9 C2 L2 Science Product
# Guide; bit numbers written from memory, VERIFY against the guide):
# 0 fill, 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow, 5 snow,
# 6 clear, 7 water. A pixel is clear here when none of 0-5 is set.
QA_BAD_BITS = (0, 1, 2, 3, 4, 5)
QA_BAD_MASK = sum(1 << b for b in QA_BAD_BITS)
QA_FILL_BIT = 0

# ---- Landsat C2 L2 surface reflectance scale/offset (fallback when the
# catalogue does not declare raster:bands). USGS: 0.0000275 and -0.2.
LS_SCALE, LS_OFFSET = 0.0000275, -0.2


def native_res(sensor, band_id):
    return BANDS[sensor][band_id][1]


def find_asset(assets, sensor, band_id):
    """Return (asset_key, asset_dict) for a band id, or (None, None)."""
    candidates = BANDS[sensor][band_id][0]
    for key in candidates:
        if key in assets:
            return key, assets[key]
    for key, asset in assets.items():
        for b in asset.get("eo:bands", []) or []:
            name = (b.get("name") or "").upper()
            if name == band_id or name == band_id.replace("B0", "B"):
                if "jp2" not in key.lower():
                    return key, asset
    return None, None


def clear_pixels(sensor, arr, scl_classes=CLEAR_SCL):
    """Boolean array of clear pixels for the mask band of each sensor."""
    import numpy as np
    if sensor == S2:
        return np.isin(arr, scl_classes)
    a = arr.astype(np.uint32)
    return (a & QA_BAD_MASK) == 0


def valid_pixels(sensor, arr):
    """Pixels with data (inside the swath)."""
    import numpy as np
    if sensor == S2:
        return arr != 0
    return (arr.astype(np.uint32) & (1 << QA_FILL_BIT)) == 0
