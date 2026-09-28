"""Phase 2 tabs in a real (headless) QGIS with the real task manager.

    QT_QPA_PLATFORM=offscreen python elotesat/tests/test_gui2.py [shots_dir]
"""
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (QgsApplication, QgsVectorLayer, QgsFeature,  # noqa
                       QgsGeometry, QgsProject, QgsSettings, QgsField)
from qgis.PyQt.QtCore import QVariant  # noqa: E402

app = QgsApplication([], True)
app.initQgis()
QgsSettings().remove("EloteSat")
QgsSettings().setValue("EloteSat/lang", "es")

import synth  # noqa: E402
from elotesat.gui.main_dialog import EloteSatDialog  # noqa: E402

FAIL = []
TMP = tempfile.mkdtemp(prefix="elotesat_g2_")
SHOTS = sys.argv[1] if len(sys.argv) > 1 else None


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        FAIL.append(m)


def wait(tab, secs=300):
    t0 = time.time()
    while tab.task is not None and time.time() - t0 < secs:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()


def shot(dlg, tab, name):
    if SHOTS:
        dlg.tabs.setCurrentWidget(tab)
        app.processEvents()
        dlg.grab().save(os.path.join(SHOTS, name))


synth.HARD = True
cdir, C, F, cls = synth.build(TMP)
dlg = EloteSatDialog(None)
dlg.resize(1150, 900)
dlg.show()
d = dlg.download
d.fw_out.setFilePath(TMP)
d.cb_cycle.setCurrentIndex(d.cb_cycle.findData("OI"))
d.sp_year.setValue(2026)
ft = dlg.features
check(os.path.normpath(ft.fw_cycle.filePath()) == os.path.normpath(cdir),
      "tab 3 gets the cycle folder from tab 2")
check(len(ft.stage_checks) == 4 and "S2" in ft.lbl_info.text() or
      "Sentinel" in ft.lbl_info.text(), "tab 3 lists stages and dates")
check(all(not cb.isEnabled() for cb in ft.stage_checks.values()) and
      ft.chk_rel.isChecked() and not ft.chk_fixed.isChecked() and
      not ft.chk_abs.isChecked(), "defaults: relative windows, no fixed "
      "stages, no absolute dates")
# crop references in the current profile (tab 1) -> referencia.tif
cal = dlg.calendar
for col, v in enumerate(("02-10", "04-10")):
    cal.ref_table.item(0, col).setText(v)          # maize green-up
for col, v in enumerate(("03-20", "05-10")):
    cal.ref_table.item(1, 2 + col).setText(v)      # sorghum peak
app.processEvents()
check("generico_VERIFICAR" in ft.lbl_ref.text(),
      "tab 3 says which profile's references it uses")
ft.run()
wait(ft)
check(os.path.exists(os.path.join(cdir, "variables", "referencia.tif")),
      "referencia.tif written")
vpath = os.path.join(cdir, "variables", "variables.tif")
check(os.path.exists(vpath), "variables computed from the tab")
check(dlg.samples.fw_vars.filePath() == vpath and
      dlg.classify.fw_vars.filePath() == vpath and
      dlg.cluster.fw_vars.filePath() == vpath,
      "variables path passed to tabs 4-6")
shot(dlg, ft, "t3.png")

# groups
cl = dlg.cluster
cl.sp_k.setValue(4)
cl.sp_n.setValue(20000)
cl.run()
wait(cl)
check(cl.result is not None and cl.table.rowCount() == 4,
      "groups tab: 4 groups in the table")
refcol = [cl.table.item(r, 5).text() for r in range(4)]
check(all(refcol) and any("%" in t for t in refcol),
      "reference column per group: %s" % refcol)
shot(dlg, cl, "t4.png")

# field layer (one field in three), names as a user would type them
lyr = QgsVectorLayer("Polygon?crs=EPSG:32614", "campo", "memory")
pr = lyr.dataProvider()
pr.addAttributes([QgsField("cultivo", QVariant.String),
                  QgsField("parcela", QVariant.Int)])
lyr.updateFields()
names = {"maiz": "Maíz", "sorgo": "Sorgo", "otros": "Pasto"}
feats = []
for wkt, c, gid in synth.field_polygons(cls, set(range(0, 400, 3))):
    f = QgsFeature(lyr.fields())
    f.setGeometry(QgsGeometry.fromWkt(wkt))
    f["cultivo"], f["parcela"] = names[c], gid
    feats.append(f)
pr.addFeatures(feats)
QgsProject.instance().addMapLayer(lyr)
sm = dlg.samples
sm.cb_layer.setLayer(lyr)
sm.cb_field.setField("cultivo")
sm.cb_gid.setField("parcela")
app.processEvents()
mp = sm._mapping()
check(mp == {"Maíz": "maiz", "Sorgo": "sorgo", "Pasto": "otros"},
      "class values guessed: %s" % mp)
sm.sp_buf.setValue(0)
sm.extract()
check(sm.samples is not None and len(set(sm.samples.g)) == 134,
      "samples extracted, 134 fields")
check(os.path.exists(os.path.join(cdir, "muestras", "muestras.csv")),
      "muestras.csv saved")
sm.cb_comp.setCurrentIndex(sm.cb_comp.findData("ms"))
check(sm.rank_table.rowCount() == len(sm.samples.names),
      "ranking table filled")
top = sm.rank_table.item(0, 0).text()
check(any(k in top for k in ("CIre", "NDRE", "B05")),
      "step 2 ranking led by red-edge in the tab (%s)" % top)
check("maíz" in sm.lbl_conf.text(), "threshold explorer text")
before = sm.lbl_conf.text()
sm.sp_thr.setValue(sm.sp_thr.value() + 0.5)
check(sm.lbl_conf.text() != before, "moving the threshold updates counts")
sm._rule_map()
check(os.path.isdir(os.path.join(cdir, "reglas")), "rule map written")
sm.sp_k.setValue(3)
sm._forward()
check(len(sm._fwd) >= 1, "best combination found: %s" % sm._fwd)
sm.btn_use.click()
check(set(dlg.classify.vlist.checked()) == set(sm._fwd),
      "combination sent to tab 6")
shot(dlg, sm, "t5.png")

# classification with the selected variables (fast)
cf = dlg.classify
cf.chk_flat.setChecked(False)
cf.sp_trees.setValue(40)
cf.sp_k.setValue(3)
cf.sp_cap.setValue(600)
cf.run()
wait(cf)
html = cf.report.toPlainText()
check("OA" in html and "Paso 2" in html, "report shown")
check(os.path.exists(os.path.join(cdir, "clasificacion",
                                  "jerarquica_clases.tif")),
      "class map written")
check(cf.imp_table.rowCount() > 0, "importance table filled")
check(os.path.exists(os.path.join(cdir, "variables", "zonas.tif")),
      "zonas.tif written with the variables")
check(os.path.exists(os.path.join(cdir, "clasificacion",
                                  "jerarquica_superficies_siap.csv")),
      "mapped vs SIAP areas CSV written")
shot(dlg, cf, "t6.png")

dlg.home.cb_lang.setCurrentIndex(dlg.home.cb_lang.findData("en"))
check(dlg.tabs.tabText(6) == "6 · Classification" and
      cf.btn.text() == "Validate and classify", "English")
dlg.close()
print("\n%d failures" % len(FAIL))
shutil.rmtree(TMP, ignore_errors=True)
QgsSettings().remove("EloteSat")
app.exitQgis()
sys.exit(1 if FAIL else 0)
