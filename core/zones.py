"""Municipality and irrigation-district rasters on the variables grid.

Data shipped with the plugin (data/tamaulipas_elotesat.gpkg):
  municipios       43 municipalities of Tamaulipas, Who's On First
                   (geometry from Quattroshapes, CC-BY), INEGI key in
                   `cvegeo`, simplified to 30 m as a coverage (no gaps or
                   overlaps). Same geometry as VaquerosGIS 0.2.1.
  distritos_riego  7 irrigation districts, CONAGUA via SEMARNAT INFOTECA
                   (agricultural year 2016-2017), unclipped, simplified.

A pixel belongs to the polygon that contains its centre. Outside every
polygon: 0. The irrigation-district band is only a proxy for "riego":
the district perimeter includes land without irrigation rights, and there
is irrigated land outside the districts (unidades de riego).
"""

import csv
import os

import numpy as np
from osgeo import gdal, ogr, osr

gdal.UseExceptions()

DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data",
                    "tamaulipas_elotesat.gpkg")
ATTRIBUTION = ("Municipios: Who's On First "
               "(https://whosonfirst.org/docs/licenses/), geometría de "
               "Quattroshapes (CC-BY). Distritos de riego: CONAGUA, vía "
               "INFOTECA de SEMARNAT, año agrícola 2016-2017.")


def _burn(ds_like, layer, codes, field):
    mem = gdal.GetDriverByName("MEM").Create(
        "", ds_like.RasterXSize, ds_like.RasterYSize, 1, gdal.GDT_Int32)
    mem.SetGeoTransform(ds_like.GetGeoTransform())
    mem.SetProjection(ds_like.GetProjection())
    # temporary layer with an integer code per feature, in the grid CRS
    dst = osr.SpatialReference(wkt=ds_like.GetProjection())
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    src = layer.GetSpatialRef().Clone()
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    xf = None if src.IsSame(dst) else osr.CoordinateTransformation(src, dst)
    tmp = ogr.GetDriverByName("Memory").CreateDataSource("z")
    tl = tmp.CreateLayer("z", dst, ogr.wkbMultiPolygon)
    tl.CreateField(ogr.FieldDefn("code", ogr.OFTInteger))
    layer.ResetReading()
    for f in layer:
        g = f.GetGeometryRef().Clone()
        if xf:
            g.Transform(xf)
        nf = ogr.Feature(tl.GetLayerDefn())
        nf["code"] = codes[f[field]]
        nf.SetGeometry(g)
        tl.CreateFeature(nf)
    gdal.RasterizeLayer(mem, [1], tl, options=["ATTRIBUTE=code",
                                               "ALL_TOUCHED=FALSE"])
    return mem.GetRasterBand(1).ReadAsArray()


def build_zones(vpath, gpkg=DATA, out_dir=None):
    """Write zonas.tif (band 1 municipality = integer cvegeo, band 2
    irrigation district = code 1..7) and zonas.csv (lookup) next to the
    variables raster. Returns a dict with paths and pixel counts."""
    if not os.path.exists(gpkg):
        raise FileNotFoundError(gpkg)
    ref = gdal.Open(vpath)
    out_dir = out_dir or os.path.dirname(vpath)
    src = ogr.Open(gpkg)
    lm = src.GetLayer("municipios")
    mcodes, mnames = {}, {}
    for f in lm:
        mcodes[f["cvegeo"]] = int(f["cvegeo"])
        mnames[int(f["cvegeo"])] = f["municipio"]
    mun = _burn(ref, lm, mcodes, "cvegeo")
    ld = src.GetLayer("distritos_riego")
    dcodes, dnames = {}, {}
    for i, f in enumerate(sorted(ld, key=lambda f: f["id_dr"]), start=1):
        dcodes[f["id_dr"]] = i
        dnames[i] = (f["id_dr"], f["nom_dr"])
    dr = _burn(ref, ld, dcodes, "id_dr")
    tif = os.path.join(out_dir, "zonas.tif")
    drv = gdal.GetDriverByName("GTiff")
    out = drv.Create(tif, ref.RasterXSize, ref.RasterYSize, 2, gdal.GDT_Int32,
                     ["COMPRESS=DEFLATE", "TILED=YES"])
    out.SetGeoTransform(ref.GetGeoTransform())
    out.SetProjection(ref.GetProjection())
    for b, (arr, name) in enumerate(((mun, "cvegeo"),
                                     (dr, "distrito_riego")), start=1):
        band = out.GetRasterBand(b)
        band.WriteArray(arr)
        band.SetDescription(name)
        band.SetNoDataValue(0)
    out.SetMetadata({"attribution": ATTRIBUTION})
    out = None
    csvp = os.path.join(out_dir, "zonas.csv")
    mc = {int(k): int(v) for k, v in zip(*np.unique(mun, return_counts=True))}
    dc = {int(k): int(v) for k, v in zip(*np.unique(dr, return_counts=True))}
    with open(csvp, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["banda", "codigo", "clave", "nombre", "pixeles"])
        for c in sorted(mnames):
            if c in mc:
                w.writerow(["cvegeo", c, "%05d" % c, mnames[c], mc[c]])
        for c in sorted(dnames):
            if c in dc:
                w.writerow(["distrito_riego", c, dnames[c][0], dnames[c][1],
                            dc[c]])
    return {"tif": tif, "csv": csvp, "mun_px": mc, "dr_px": dc,
            "municipios": {c: mnames[c] for c in mc if c},
            "distritos": {c: dnames[c] for c in dc if c}}


def zone_shares(aoi_wkt_4326, gpkg=DATA):
    """Shares of the study area by municipality and inside irrigation
    districts: ({cvegeo: (name, share)}, dr_share, outside_share)."""
    src = ogr.Open(gpkg)
    lm = src.GetLayer("municipios")
    dst = lm.GetSpatialRef().Clone()
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    s4326 = osr.SpatialReference()
    s4326.ImportFromEPSG(4326)
    s4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    aoi = ogr.CreateGeometryFromWkt(aoi_wkt_4326)
    aoi.Transform(osr.CoordinateTransformation(s4326, dst))
    total = aoi.GetArea()
    if total <= 0:
        raise ValueError("empty study area")
    shares, inside = {}, 0.0
    for f in lm:
        g = f.GetGeometryRef()
        if g.Intersects(aoi):
            a = g.Intersection(aoi).GetArea()
            if a > 0:
                shares[f["cvegeo"]] = (f["municipio"], a / total)
                inside += a
    ld = src.GetLayer("distritos_riego")
    dr = None
    for f in ld:
        g = f.GetGeometryRef()
        if g.Intersects(aoi):
            part = g.Intersection(aoi)
            dr = part if dr is None else dr.Union(part)
    dr_share = dr.GetArea() / total if dr is not None else 0.0
    return shares, dr_share, 1.0 - inside / total


def suggest_profile(aoi_wkt_4326, profiles, gpkg=DATA):
    """Pick the SIAP profile of the municipality with the largest share
    of the study area; regime 'riego' if at least half of the area lies in
    irrigation districts, else 'temporal'. Returns a dict with the choice,
    the shares and warnings (several municipalities, mixed regime, no
    profile, outside Tamaulipas)."""
    shares, dr_share, outside = zone_shares(aoi_wkt_4326, gpkg)
    warn = []
    if not shares:
        return {"profile": None, "shares": {}, "dr_share": dr_share,
                "outside": outside, "warnings": ["fuera de Tamaulipas"]}
    cv, (name, share) = max(shares.items(), key=lambda kv: kv[1][1])
    mod = "riego" if dr_share >= 0.5 else "temporal"
    if len([s for s in shares.values() if s[1] >= 0.1]) > 1:
        warn.append("la zona pilla varios municipios")
    if 0.2 < dr_share < 0.8:
        warn.append("la zona mezcla distrito de riego (%.0f %%) y fuera"
                    % (100 * dr_share))
    if outside > 0.05:
        warn.append("%.0f %% de la zona cae fuera de Tamaulipas"
                    % (100 * outside))
    pick = None
    for pname, p in profiles.items():
        meta = p.get("siap") or {}
        if meta.get("cvegeo") == cv and meta.get("modalidad") == mod:
            pick = pname
            break
    if pick is None:
        warn.append("no hay perfil del SIAP para %s (%s)" % (name, mod))
    return {"profile": pick, "cvegeo": cv, "municipio": name,
            "modalidad": mod, "shares": shares, "dr_share": dr_share,
            "outside": outside, "warnings": warn}
