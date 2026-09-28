import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu

NAME = "EloteSat Tamaulipas"
# (translation key, tab index) for the direct entries of the menu
ENTRIES = (("tab.home", 0), ("tab.calendar", 1), ("tab.download", 2),
           ("tab.features", 3), ("tab.cluster", 4), ("tab.samples", 5),
           ("tab.classify", 6), ("tab.siap", 7), ("tab.help", 8))


class EloteSatPlugin:
    """Own menu in the QGIS menu bar (before Help), own toolbar, and the
    classic entry in Raster so it is found in any of the three places."""

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.menu = None
        self.toolbar = None
        self.tab_actions = []
        self.dialog = None

    def initGui(self):  # noqa: N802
        from .core import i18n
        i18n.set_lang(i18n.default_lang())
        mw = self.iface.mainWindow()
        icon = QIcon(os.path.join(os.path.dirname(__file__), "icon.png"))
        self.action = QAction(icon, NAME, mw)
        self.action.setObjectName("EloteSatOpen")
        self.action.triggered.connect(lambda: self.run(0))

        # own menu in the menu bar, one entry per tab
        self.menu = QMenu("EloteSat", mw)
        self.menu.setObjectName("mEloteSatMenu")
        self.menu.addAction(self.action)
        self.menu.addSeparator()
        for key, idx in ENTRIES[1:]:
            a = QAction(i18n.tr(key), mw)
            a.triggered.connect(lambda _=False, i=idx: self.run(i))
            self.menu.addAction(a)
            self.tab_actions.append(a)
        bar = mw.menuBar()
        help_menu = self.iface.firstRightStandardMenu()
        if help_menu is not None:
            bar.insertMenu(help_menu.menuAction(), self.menu)
        else:
            bar.addMenu(self.menu)

        # own toolbar (the Raster one is often hidden)
        self.toolbar = self.iface.addToolBar(NAME)
        self.toolbar.setObjectName("EloteSatToolbar")
        self.toolbar.addAction(self.action)

        self.iface.addPluginToRasterMenu(NAME, self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginRasterMenu(NAME, self.action)
        if self.toolbar:
            self.toolbar.deleteLater()
            self.toolbar = None
        if self.menu:
            self.iface.mainWindow().menuBar().removeAction(
                self.menu.menuAction())
            self.menu.deleteLater()
            self.menu = None
        self.tab_actions = []
        if self.dialog:
            for t in (self.dialog.download.task, self.dialog.calendar.task,
                      self.dialog.features.task, self.dialog.cluster.task,
                      self.dialog.classify.task):
                if t:
                    t.cancel()
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None

    def run(self, tab=0):
        from .gui.main_dialog import EloteSatDialog
        if self.dialog is None:
            self.dialog = EloteSatDialog(self.iface, self.iface.mainWindow())
        self.dialog.tabs.setCurrentIndex(tab or 0)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
