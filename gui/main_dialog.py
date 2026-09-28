"""Single EloteSat window with all tabs."""

import os

from qgis.PyQt.QtWidgets import QDialog, QTabWidget, QVBoxLayout

from ..core import i18n
from ..core.i18n import tr
from .home_tab import HomeTab
from .calendar_tab import CalendarTab
from .download_tab import DownloadTab
from .features_tab import FeaturesTab
from .cluster_tab import ClusterTab
from .samples_tab import SamplesTab
from .classify_tab import ClassifyTab
from .siap_map_tab import SiapMapTab
from .help_tab import HelpTab
from ..core import phenology

TAB_KEYS = ("tab.home", "tab.calendar", "tab.download", "tab.features",
            "tab.cluster", "tab.samples", "tab.classify", "tab.siap",
            "tab.help")


class EloteSatDialog(QDialog):
    def __init__(self, iface, parent=None):
        from ..core.migrate import migrate_settings
        migrate_settings()  # settings of FenoSat, the former name
        i18n.set_lang(i18n.default_lang())
        super().__init__(parent)
        self.resize(1040, 900)
        self.tabs = QTabWidget()
        self.home = HomeTab(self)
        self.calendar = CalendarTab(self)
        self.download = DownloadTab(iface, self.calendar, self)
        self.features = FeaturesTab(
            self, get_profile=lambda: (self.calendar.profile,
                                       self.calendar.references()))
        self.cluster = ClusterTab(self)
        self.samples = SamplesTab(self)
        self.classify = ClassifyTab(self.samples, self)
        self.siapmap = SiapMapTab(self)
        self.help = HelpTab(self)
        self.pages = (self.home, self.calendar, self.download,
                      self.features, self.cluster, self.samples,
                      self.classify, self.siapmap, self.help)
        for w in self.pages:
            self.tabs.addTab(w, "")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.tabs)
        self._titles()
        # the reorganize box points at the download folder
        self.calendar.fw_dir.setFilePath(self.download.fw_out.filePath())
        self.download.fw_out.fileChanged.connect(
            self.calendar.fw_dir.setFilePath)
        # same cycle and year in both tabs
        self.download.cb_cycle.currentIndexChanged.connect(self._sync_cycle)
        self.download.sp_year.valueChanged.connect(
            self.calendar.sp_year.setValue)
        self.calendar.sp_year.setValue(self.download.sp_year.value())
        self.home.languageChanged.connect(self._retranslate)
        # the cycle folder of tab 2 feeds tab 3; variables feed tabs 4-6
        for sig in (self.download.fw_out.fileChanged,
                    self.download.cb_cycle.currentIndexChanged,
                    self.download.sp_year.valueChanged):
            sig.connect(self._cycle_folder)
        self.download.downloadFinished.connect(self._cycle_folder)
        self.features.featuresReady.connect(self._variables)
        self.features.fw_cycle.fileChanged.connect(self._existing_vars)
        self.calendar.siapUpdated.connect(self.siapmap.reload)
        self.calendar.profileChanged.connect(self.features._show_ref_source)
        self.calendar.referencesChanged.connect(
            self.features._show_ref_source)
        self._cycle_folder()

    def _cycle_folder(self, *_):
        out = self.download.fw_out.filePath()
        c = self.download.cb_cycle.currentData()
        if out and c:
            self.features.set_cycle_dir(phenology.cycle_dir(
                out, c, self.download.sp_year.value()))

    def _existing_vars(self, cdir):
        p = os.path.join(cdir, "variables", "variables.tif")
        if os.path.exists(p):
            self._variables(p)

    def _variables(self, path):
        for t in (self.cluster, self.samples, self.classify):
            t.set_vars(path)

    def _sync_cycle(self, *_):
        c = self.download.cb_cycle.currentData()
        i = self.calendar.cb_cycle.findData(c)
        if i >= 0:
            self.calendar.cb_cycle.setCurrentIndex(i)

    def _titles(self):
        self.setWindowTitle(tr("win.title"))
        for n, key in enumerate(TAB_KEYS):
            self.tabs.setTabText(n, tr(key))

    def _retranslate(self, _code=None):
        self._titles()
        for w in self.pages:
            w.retranslate()
