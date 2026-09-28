"""Tab 7 (SIAP maps, from the Claudia/Daniel 0.4.0 variant) on the real
shipped data, and SIAP downloads kept in the QGIS profile folder.

    QT_QPA_PLATFORM=offscreen python elotesat/tests/test_maps.py
"""
import csv
import datetime as dt
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication, QgsProject, QgsSettings  # noqa: E402

app = QgsApplication([], True)
app.initQgis()
QgsSettings().remove("EloteSat")
QgsSettings().setValue("EloteSat/lang", "es")
from qgis.PyQt.QtWidgets import QMessageBox  # noqa: E402
for n in ("question", "warning", "information"):
    setattr(QMessageBox, n, staticmethod(lambda *a, **k: QMessageBox.Yes))

from elotesat.core import siap, siap_maps  # noqa: E402
from elotesat.gui.main_dialog import EloteSatDialog  # noqa: E402

FAIL = []
TMP = tempfile.mkdtemp(prefix="elotesat_maps_")


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        FAIL.append(m)


# keep any real downloads of this machine out of the way
pdir = siap.profile_dir()
backup = os.path.join(TMP, "backup")
shutil.copytree(pdir, backup)
for n in os.listdir(pdir):
    p = os.path.join(pdir, n)
    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

try:
    d = siap_maps.Data()
    check(len(siap_maps.municipalities()) == 43 and len(d.names) == 38,
          "43 municipalities, 38 with SIAP data")
    check(d.complete_years("OI") == [2024, 2025] and
          d.complete_years("PV") == [2023, 2024],
          "complete cycles: OI 2024-2025, PV 2023-2024")
    s = d.series("OI", 2025, ("riego",), ("sorgo",))
    vals = [v["sembrada_ha"] for _, v in s]
    check(abs(vals[-1] - 172511) < 2, "OI 2025 irrigated sorghum closes at "
          "172 511 ha (%.0f)" % vals[-1])
    tot = sum(siap_maps.summary(d, "OI", 2025, ("riego",), ("sorgo",),
                                "sembrada_ha").values())
    check(abs(tot - vals[-1]) < 2, "summary per municipality adds up")
    y = siap_maps.summary(d, "OI", 2025, ("riego",), ("sorgo",),
                          "rendimiento")
    check(all(v is None or 0 < v < 15 for v in y.values()),
          "yields plausible (t/ha)")

    # a download in the profile folder is read and replaces the same cut
    csvp = os.path.join(pdir, "siap_prueba.csv")
    with open(csvp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["anio_consulta", "anio_agricola", "ciclo", "modalidad",
                    "cultivo", "mes_consulta", "fecha_corte", "municipio",
                    "sembrada_ha", "cosechada_ha", "siniestrada_ha",
                    "produccion", "rendimiento", "aviso"])
        w.writerow([2025, 2025, "Otoño - Invierno", "Riego", "Sorgo grano",
                    3, "2025-03-31", "Valle Hermoso", 1.0, 0, 0, 0, 0, ""])
    d2 = siap_maps.Data()
    vh = [r for r in d2.rows if r["cvegeo"] == "28040" and
          r["fecha"] == dt.date(2025, 3, 31) and r["modalidad"] == "Riego"
          and r["anio_agricola"] == 2025
          and r["cultivo"] == "Sorgo grano"]
    check(len(vh) == 1 and vh[0]["sembrada_ha"] == 1.0,
          "download in the profile folder replaces the shipped cut")
    check(siap.downloaded_csvs() == [csvp] and
          any(r["cvegeo"] == "28040" for r in siap.downloaded_rows_raw()),
          "profile-folder CSV listed and matched by name")
    os.remove(csvp)

    # the tab
    dlg = EloteSatDialog(None)
    dlg.resize(1150, 950)
    dlg.show()
    m = dlg.siapmap
    check(dlg.tabs.count() == 9 and dlg.tabs.tabText(7) == "7 · Mapas SIAP",
          "9 tabs, SIAP maps before Ayuda")
    check(m.cb_year.currentData() == 2025, "maps start on the latest "
          "complete OI (2025)")
    for v in ("sembrada_ha", "rendimiento", "pct_siniestrada",
              "p50_siembra", "p50_cosecha"):
        m.cb_var.setCurrentIndex(m.cb_var.findData(v))
        lyr = m.make_map()
        check(lyr is not None and lyr.featureCount() == 43,
              "map of %s: 43 municipalities" % v)
    m.cb_var.setCurrentIndex(m.cb_var.findData("sembrada_ha"))
    m.cb_reg.setCurrentIndex(m.cb_reg.findData("riego"))
    m.cb_crop.setCurrentIndex(m.cb_crop.findData("sorgo"))
    lyr = m.make_map()
    tot_m = sum(ft["valor"] or 0 for ft in lyr.getFeatures())
    check(abs(tot_m - 172511) < 2, "map total = SIAP state total (%.0f)"
          % tot_m)
    m.cb_cut.setCurrentIndex(m.cb_cut.findData("2025-02-28"))
    lyr_f = m.make_map()
    check(sum(ft["valor"] or 0 for ft in lyr_f.getFeatures()) < tot_m,
          "February cut shows less sown area")
    png = os.path.join(TMP, "layout.png")
    lo = m.make_layout(png)
    check(lo is not None and os.path.exists(png) and
          os.path.getsize(png) > 50000, "print layout exported")
    names = [it.__class__.__name__ for it in lo.items()]
    check(all(k in names for k in ("QgsLayoutItemMap", "QgsLayoutItemLegend",
                                   "QgsLayoutItemScaleBar",
                                   "QgsLayoutItemPicture")),
          "layout: map, legend, scale bar, logo")
    m.cb_cycle.setCurrentIndex(m.cb_cycle.findData("PV"))
    check(m.cb_year.currentData() == 2024, "PV maps start on 2024")
    if len(sys.argv) > 1:
        dlg.tabs.setCurrentWidget(m)
        app.processEvents()
        dlg.grab().save(os.path.join(sys.argv[1], "t7.png"))
        shutil.copy(png, os.path.join(sys.argv[1], "t7_layout.png"))
    dlg.home.cb_lang.setCurrentIndex(dlg.home.cb_lang.findData("en"))
    app.processEvents()
    check(dlg.tabs.tabText(7) == "7 · SIAP maps", "English")
    dlg.close()
    del lo, lyr, lyr_f
    QgsProject.instance().clear()
finally:
    for n in os.listdir(pdir):
        p = os.path.join(pdir, n)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    for n in os.listdir(backup):
        s = os.path.join(backup, n)
        (shutil.copytree if os.path.isdir(s) else shutil.copy)(
            s, os.path.join(pdir, n))

print("\n%d failures" % len(FAIL))
shutil.rmtree(TMP, ignore_errors=True)
QgsSettings().remove("EloteSat")
app.exitQgis()
sys.exit(1 if FAIL else 0)
