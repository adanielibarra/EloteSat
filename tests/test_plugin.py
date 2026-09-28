"""Plugin entry points: own menu in the menu bar, own toolbar, Raster menu,
and a clean unload.

    QT_QPA_PLATFORM=offscreen python elotesat/tests/test_plugin.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from qgis.core import QgsApplication, QgsSettings  # noqa: E402
from qgis.PyQt.QtWidgets import QMainWindow, QToolBar  # noqa: E402

app = QgsApplication([], True)
app.initQgis()
QgsSettings().remove("EloteSat/lang")
QgsSettings().setValue("locale/userLocale", "en_US")
from qgis.PyQt.QtWidgets import QMessageBox  # noqa: E402
for _n in ("question", "warning", "information"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.Yes))
from elotesat.plugin import EloteSatPlugin  # noqa: E402
from elotesat.core import i18n  # noqa: E402

FAIL = []


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        FAIL.append(m)


class FakeIface:
    def __init__(self):
        self.mw = QMainWindow()
        bar = self.mw.menuBar()
        bar.addMenu("Proyecto")
        self.help = bar.addMenu("Ayuda")
        self.raster = {}

    def mainWindow(self):  # noqa: N802
        return self.mw

    def firstRightStandardMenu(self):  # noqa: N802
        return self.help

    def addToolBar(self, name):  # noqa: N802
        return self.mw.addToolBar(name)

    def addPluginToRasterMenu(self, name, a):  # noqa: N802
        self.raster.setdefault(name, []).append(a)

    def removePluginRasterMenu(self, name, a):  # noqa: N802
        self.raster.get(name, []).remove(a)


check(i18n.default_lang() == "es", "Spanish by default, QGIS in English")
QgsSettings().setValue("EloteSat/lang", "en")
check(i18n.default_lang() == "en", "English only when chosen")
QgsSettings().remove("EloteSat/lang")

iface = FakeIface()
p = EloteSatPlugin(iface)
p.initGui()
titles = [a.text() for a in iface.mw.menuBar().actions()]
check(titles == ["Proyecto", "EloteSat", "Ayuda"],
      "own menu in the menu bar, before Help (%s)" % titles)
items = [a.text() for a in p.menu.actions() if not a.isSeparator()]
check(len(items) == 9 and items[0] == "EloteSat Tamaulipas" and
      items[-2] == "7 · Mapas SIAP" and items[-1] == "Ayuda",
      "menu: open + 7 tabs + Ayuda")
tbs = [t.windowTitle() for t in iface.mw.findChildren(QToolBar)]
check("EloteSat Tamaulipas" in tbs, "own toolbar")
check(iface.raster.get("EloteSat Tamaulipas") == [p.action],
      "still in the Raster menu")
p.tab_actions[5].trigger()  # 6 · Clasificación
check(p.dialog is not None and p.dialog.tabs.currentIndex() == 6,
      "menu entry opens its tab")
p.tab_actions[-1].trigger()
check(p.dialog.tabs.currentIndex() == 8 and
      p.dialog.tabs.tabText(8) == "Ayuda", "Ayuda is the last tab")
p.action.trigger()
check(p.dialog.tabs.currentIndex() == 0, "main entry opens Home")
import tempfile  # noqa: E402
h = p.dialog.help
out = os.path.join(tempfile.mkdtemp(), "manual")
saved = h.save_manual(out)
from elotesat.gui.help_tab import manual_path  # noqa: E402
check(saved == out + ".pdf" and os.path.getsize(saved) ==
      os.path.getsize(manual_path()) and
      open(saved, "rb").read(5) == b"%PDF-", "manual saved as a PDF copy")
check(h.bt_open.isEnabled() and "0.4.3" in h.lb_version.text(),
      "help shows plugin version (%s)" % h.lb_version.text())
p.unload()
app.processEvents()
titles = [a.text() for a in iface.mw.menuBar().actions()]
check(titles == ["Proyecto", "Ayuda"] and
      not iface.raster.get("EloteSat Tamaulipas"), "unload removes all")

print("\n%d failures" % len(FAIL))
QgsSettings().remove("locale/userLocale")
app.exitQgis()
sys.exit(1 if FAIL else 0)
