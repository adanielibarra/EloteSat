"""EloteSat in a real (headless) QGIS: plugin load, dialog, calendar edits,
search with a fake catalogue and download with the real task manager.

    QT_QPA_PLATFORM=offscreen python elotesat/tests/test_gui.py
"""
import csv
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (QgsApplication, QgsVectorLayer, QgsFeature,  # noqa
                       QgsGeometry, QgsProject, QgsSettings)
from qgis.PyQt.QtCore import Qt  # noqa

app = QgsApplication([], True)
app.initQgis()
QgsSettings().remove("EloteSat")

from osgeo import gdal, osr  # noqa: E402

import elotesat  # noqa: E402
from elotesat.core import stac_client  # noqa: E402
from elotesat.core.sensors import BANDS, S2  # noqa: E402

FAIL = []
TMP = tempfile.mkdtemp(prefix="elotesat_gui_")


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        FAIL.append(m)


class FakeIface:
    def __init__(self):
        from qgis.PyQt.QtWidgets import QMainWindow
        self.w = QMainWindow()

    def mainWindow(self):  # noqa: N802
        return self.w

    def addRasterToolBarIcon(self, a):  # noqa: N802
        pass

    def addPluginToRasterMenu(self, n, a):  # noqa: N802
        pass

    def removePluginRasterMenu(self, n, a):  # noqa: N802
        pass

    def removeRasterToolBarIcon(self, a):  # noqa: N802
        pass

    def firstRightStandardMenu(self):  # noqa: N802
        return None

    def addToolBar(self, name):  # noqa: N802
        return self.w.addToolBar(name)


iface = FakeIface()
plugin = elotesat.classFactory(iface)
plugin.initGui()
plugin.run()
dlg = plugin.dialog
check(dlg is not None and dlg.tabs.count() == 9, "dialog with 9 tabs")

# study area in EPSG:32614
lyr = QgsVectorLayer("Polygon?crs=EPSG:32614", "zona", "memory")
f = QgsFeature()
f.setGeometry(QgsGeometry.fromWkt(
    "POLYGON((402000 2792000,408000 2792000,408000 2798000,"
    "402000 2798000,402000 2792000))"))
lyr.dataProvider().addFeatures([f])
QgsProject.instance().addMapLayer(lyr)
d = dlg.download
d.cb_layer.setLayer(lyr)

# cycle OI 2026 -> dates from the calendar
d.cb_cycle.setCurrentIndex(d.cb_cycle.findData("OI"))
d.sp_year.setValue(2026)
check(d.d_from.date().toString("yyyy-MM-dd") == "2026-01-15" and
      d.d_to.date().toString("yyyy-MM-dd") == "2026-07-15",
      "search dates filled from OI 2026")
check(dlg.calendar.sp_year.value() == 2026, "year synced to calendar tab")

# stage dates editable from the download tab
from qgis.PyQt.QtCore import QDate  # noqa: E402


def settle():
    for _ in range(5):
        app.processEvents()


check(d.stage_table.rowCount() == 4, "stage table in download tab")
d.stage_table.cellWidget(3, 2).setDate(QDate(2026, 7, 31))  # last end
settle()
check(dlg.calendar.cal["OI"]["stages"][3][2] == "07-31",
      "end date edited in tab 2 -> calendar updated")
check(dlg.calendar.table.item(3, 2).text() == "07-31",
      "calendar tab table shows the edit")
check(d.d_to.date().toString("yyyy-MM-dd") == "2026-07-31",
      "search end follows the last stage")
d.stage_table.cellWidget(1, 2).setDate(QDate(2026, 4, 20))  # overlap
settle()
check(dlg.calendar.cal["OI"]["stages"][1][2] == "04-10" and
      d.stage_table.cellWidget(1, 2).date() == QDate(2026, 4, 10) and
      ("no válido" in d.lbl_stages.text() or
       "Invalid" in d.lbl_stages.text()),
      "overlapping edit refused and reverted")
d.stage_table.cellWidget(3, 2).setDate(QDate(2026, 7, 15))  # restore
settle()
check(dlg.calendar.cal["OI"]["stages"][3][2] == "07-15", "restored")

# ---- region profiles
c = dlg.calendar
check(c.profile == "generico_VERIFICAR" and
      d.cb_profile.currentData() == c.profile, "default profile in both tabs")
c._ask_name = lambda key, default="": "norte_riego"
c._dup_profile()
settle()
check(c.profile == "norte_riego" and d.cb_profile.currentData() ==
      "norte_riego", "duplicated profile selected everywhere")
d.stage_table.cellWidget(0, 1).setDate(QDate(2026, 1, 20))
settle()
check(c.profiles["norte_riego"]["cycles"]["OI"]["stages"][0][1] == "01-20"
      and c.profiles["generico_VERIFICAR"]["cycles"]["OI"]["stages"][0][1]
      == "01-15", "edits go to the current profile only")
d.cb_profile.setCurrentIndex(d.cb_profile.findData("generico_VERIFICAR"))
settle()
check(c.profile == "generico_VERIFICAR" and
      d.d_from.date().toString("yyyy-MM-dd") == "2026-01-15",
      "switching profile from tab 2 changes calendar and dates")
saved = json.loads(QgsSettings().value("EloteSat/profiles"))
check(set(saved) == {"generico_VERIFICAR", "norte_riego"},
      "profiles saved in settings")
# references: half-filled is refused, complete is saved
c.ref_table.item(0, 0).setText("02-01")
check(c.profiles[c.profile]["references"]["maiz"]["arranque"] == ["", ""]
      and ("no válido" in c.lbl_refs.text() or
           "Invalid" in c.lbl_refs.text()), "half reference refused")
c.ref_table.item(0, 1).setText("03-15")
check(c.profiles[c.profile]["references"][c.cycle()]["maiz"]["arranque"]
      == ["02-01", "03-15"], "reference saved in the profile, per cycle")
c.ref_table.item(0, 0).setText("")
c.ref_table.item(0, 1).setText("")
# rename and delete
c._ask_name = lambda key, default="": "norte_riego_2026"
d.cb_profile.setCurrentIndex(d.cb_profile.findData("norte_riego"))
settle()
c._rename_profile()
check("norte_riego_2026" in c.profiles and "norte_riego" not in c.profiles
      and d.cb_profile.findData("norte_riego_2026") >= 0, "rename")
from qgis.PyQt.QtWidgets import QMessageBox  # noqa: E402
_q = QMessageBox.question
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
c._del_profile()
QMessageBox.question = _q
check(list(c.profiles) == ["generico_VERIFICAR"] and
      d.cb_profile.count() == 1, "delete")
# settings from 0.1/0.2 (one calendar, no profiles) are kept
from elotesat.gui.calendar_tab import CalendarTab  # noqa: E402
st = QgsSettings()
st.remove("EloteSat/profiles")
oldcal = json.loads(json.dumps(c.cal))
oldcal["OI"]["stages"][0][1] = "01-10"
st.setValue("EloteSat/calendar", json.dumps(oldcal))
c2 = CalendarTab()
check("mi_calendario" in c2.profiles and
      c2.profiles["mi_calendario"]["cycles"]["OI"]["stages"][0][1] ==
      "01-10", "old calendar migrated to profile 'mi_calendario'")
st.remove("EloteSat/calendar")
c._save()

# ---- SIAP profiles, offsets, references and assignment by area
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
c._import_siap()
settle()
check(sum(1 for n in c.profiles if n.startswith("siap_")) >= 30 and
      "generico_VERIFICAR" in c.profiles, "SIAP profiles imported")
lyr0 = QgsVectorLayer("Polygon?crs=EPSG:32614", "zona_vh", "memory")
fz = QgsFeature()
fz.setGeometry(QgsGeometry.fromWkt(
    "POLYGON((628000 2846000,632000 2846000,632000 2850000,"
    "628000 2850000,628000 2846000))"))
lyr0.dataProvider().addFeatures([fz])
QgsProject.instance().addMapLayer(lyr0)
d.cb_layer.setLayer(lyr0)
res = d.assign_profile()
settle()
check(res and res["profile"] == c.profile == d.cb_profile.currentData()
      and c.profile.endswith("_riego"),
      "assign by area -> %s" % (res and res["profile"]))
check("SIAP" in d.lbl_siapyear.text() or "del SIAP" in
      d.lbl_siapyear.text(), "SIAP year shown next to the year")
c.cb_cycle.setCurrentIndex(c.cb_cycle.findData("OI"))
settle()
check("S" in c.siap_info.toPlainText() and "SUPUESTOS" in
      c.siap_info.toPlainText() or "ASSUMPTIONS" in
      c.siap_info.toPlainText(), "SIAP info with assumptions shown")
check(c.table.item(0, 3).text().startswith("siap"), "origin column")
c.table.item(1, 2).setText(c.table.item(1, 2).text())  # no change
old_end = c.table.item(1, 2).text()
mm, dd = map(int, old_end.split("-"))
import datetime as _dt  # noqa: E402
nd = _dt.date(2001, mm, dd) - _dt.timedelta(days=1)
c.table.item(1, 2).setText("%02d-%02d" % (nd.month, nd.day))
settle()
check(c.table.item(1, 3).text() == "manual" and
      c.table.item(0, 3).text().startswith("siap"),
      "edited stage -> origin 'manual', others kept")
for col, v in enumerate(("20", "35", "55", "75")):
    c.off_table.item(1, col).setText(v)    # sorghum
settle()
c._fill_refs_from_siap()
settle()
check(c.ref_table.item(1, 0).text() != "" and
      c.ref_table.item(0, 0).text() == "",
      "references filled for sorghum only (maize without offsets)")
lyr_back = lyr

# synthetic tile and fake catalogue
d.cb_layer.setLayer(lyr_back)
d.cb_profile.setCurrentIndex(d.cb_profile.findData("generico_VERIFICAR"))
settle()
s = osr.SpatialReference()
s.ImportFromEPSG(32614)
assets = {}
for b, (keys, res, _) in BANDS[S2].items():
    n = int(12000 / res)
    mem = gdal.GetDriverByName("MEM").Create(
        "", n, n, 1, gdal.GDT_Byte if b == "SCL" else gdal.GDT_UInt16)
    mem.SetGeoTransform((400000, res, 0, 2800000, 0, -res))
    mem.SetProjection(s.ExportToWkt())
    mem.GetRasterBand(1).Fill(4 if b == "SCL" else 1500)
    p = os.path.join(TMP, "%s.tif" % keys[0])
    gdal.Translate(p, mem, format="COG")
    assets[keys[0]] = {"href": p,
                       "raster:bands": [{"scale": 1e-4, "offset": -0.1}]}


def item(date):
    return {"id": "S2A_T14RPP_%sT170000_L2A" % date.replace("-", ""),
            "collection": "sentinel-2-c1-l2a", "assets": assets,
            "geometry": None,
            "properties": {"datetime": date + "T17:00:00Z",
                           "eo:cloud_cover": 5, "platform": "sentinel-2a",
                           "s2:mgrs_tile": "14RPP"}}


def fake_post(url, payload):
    return {"features": [item("2026-02-10"), item("2026-04-20"),
                         item("2026-07-30")], "links": []}


stac_client.qgis_post_json = fake_post
d.chk_sensor["LANDSAT"].setChecked(False)
d.cb_source[S2].setCurrentIndex(d.cb_source[S2].findData("es-s2"))
d.search()
stages = [d.table.item(r, 6).text() for r in range(d.table.rowCount())]
check(stages == ["00_siembra_emergencia", "02_floracion_espigamiento",
                 "fuera_de_etapa"], "stages in the table: %s" % stages)
check(abs(d._km2 - 36.0) < 0.5, "area 36 km² (%.2f)" % d._km2)
check("GB" in d.lbl_count.text(), "size estimate shown")

# edit the calendar: 02-10 now vegetativo -> table follows
c = dlg.calendar
c.cb_cycle.setCurrentIndex(c.cb_cycle.findData("OI"))
c.table.item(0, 2).setText("02-05")
c.table.item(1, 1).setText("02-06")
check(c.cal["OI"]["stages"][1][1] == "02-06", "calendar edit accepted")
check(d.table.item(0, 6).text() == "01_vegetativo",
      "download table re-staged after calendar edit")
c.table.item(1, 1).setText("02-01")  # overlap -> refused
check(c.cal["OI"]["stages"][1][1] == "02-06" and
      ("no válido" in c.lbl_preview.text() or "Invalid" in c.lbl_preview.text()), "overlapping edit refused")
c.table.item(1, 1).setText("02-06")

# download with the real task manager
out = os.path.join(TMP, "out")
d.fw_out.setFilePath(out)
d.table.item(2, 0).setCheckState(Qt.Unchecked)
d.download()
t0 = time.time()
while d.task is not None and time.time() - t0 < 60:
    app.processEvents()
    time.sleep(0.05)
cdir = os.path.join(out, "OI_2026")
check(os.path.exists(os.path.join(cdir, "01_vegetativo", "S2",
                                  "S2_20260210_14RPP_S2A_10m.tif")),
      "02-10 saved in 01_vegetativo/S2")
check(os.path.exists(os.path.join(cdir, "02_floracion_espigamiento", "S2",
                                  "S2_20260420_14RPP_S2A_20m.tif")),
      "04-20 saved in 02_floracion_espigamiento/S2")
rows = list(csv.DictReader(open(os.path.join(cdir, "manifest.csv"))))
check(len(rows) == 2 and all(r["status"] == "ok" for r in rows),
      "manifest: 2 ok")
check(json.load(open(os.path.join(cdir, "calendario.json")))["OI"]
      ["stages"][1][1] == "02-06", "calendario.json = edited calendar")
check(json.load(open(os.path.join(cdir, "perfil.json")))["name"] ==
      "generico_VERIFICAR", "perfil.json saved with the download")
check("min_clear_aoi_pct = 60" in open(os.path.join(cdir,
                                                    "parametros.txt")).read(),
      "parametros.txt written")

# reorganize from the calendar tab
c.table.item(2, 1).setText("04-26")  # floración later (gap is fine)
c.table.item(1, 2).setText("04-25")  # vegetativo longer
check(c.cal["OI"]["stages"][1][2] == "04-25", "calendar extended")
c.fw_dir.setFilePath(out)
c._reorganize()
t0 = time.time()
while c.task is not None and time.time() - t0 < 30:
    app.processEvents()
    time.sleep(0.05)
check(os.path.exists(os.path.join(cdir, "01_vegetativo", "S2",
                                  "S2_20260420_14RPP_S2A_10m.tif")),
      "reorganize from the tab moved 04-20 into 01_vegetativo")

# language switch
dlg.home.cb_lang.setCurrentIndex(dlg.home.cb_lang.findData("en"))
check(dlg.tabs.tabText(1) == "1 · Calendar" and
      d.btn_search.text() == "Search scenes", "switch to English")

plugin.unload()
check(plugin.dialog is None, "unload")
print("\n%d failures" % len(FAIL))
shutil.rmtree(TMP, ignore_errors=True)
QgsSettings().remove("EloteSat")
app.exitQgis()
sys.exit(1 if FAIL else 0)
