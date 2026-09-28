"""Tab 2: search and download Sentinel-2 and Landsat into stage folders."""

import os

from qgis.core import (
    QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsDistanceArea, QgsGeometry, QgsMapLayerProxyModel, QgsProject,
    QgsRasterLayer, QgsSettings, QgsMultiBandColorRenderer, QgsWkbTypes)
from qgis.gui import QgsMapLayerComboBox, QgsFileWidget
from qgis.PyQt.QtCore import Qt, QDate, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QCheckBox,
    QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QPushButton,
    QTableWidget, QTableWidgetItem, QPlainTextEdit, QLabel, QProgressBar,
    QLineEdit, QMessageBox, QHeaderView, QGridLayout, QApplication,
    QScrollArea)

from ..core import stac_client, phenology
from ..core.sensors import S2, LS, BANDS, DEFAULT_BANDS
from ..core.task import DownloadTask
from ..core.i18n import tr
from .translatable import Translatable

SETTINGS = "EloteSat/"
RGB = {S2: ("B04", "B03", "B02"), LS: ("SR_B4", "SR_B3", "SR_B2")}


class DownloadTab(QWidget, Translatable):
    downloadFinished = pyqtSignal(str)

    def __init__(self, iface, calendar_tab, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.cal_tab = calendar_tab
        self.scenes = []
        self.duplicates = {}
        self.task = None
        self._build()
        self._load_settings()
        self._fill_profiles()
        self._cycle_changed()
        calendar_tab.calendarChanged.connect(self._calendar_changed)
        calendar_tab.profileChanged.connect(self._fill_profiles)
        # a new profile brings its own season: reset the search dates
        calendar_tab.profileChanged.connect(
            lambda *_: QTimer.singleShot(0, self._cycle_changed))
        self.cb_profile.currentIndexChanged.connect(
            lambda: self.cal_tab.set_profile(self.cb_profile.currentData()))

    # ------------------------------------------------------------ UI
    def _build(self):
        # scrollable: on small screens the widgets keep their size
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        lay = QVBoxLayout(inner)

        # study area + cycle side by side
        top = QHBoxLayout()
        g_aoi = QGroupBox()
        self._t(g_aoi.setTitle, "dl.aoi")
        f = QFormLayout(g_aoi)
        self.cb_layer = QgsMapLayerComboBox()
        self.cb_layer.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.chk_selected = QCheckBox()
        self._t(self.chk_selected.setText, "dl.selected")
        self.sp_buffer = QDoubleSpinBox()
        self.sp_buffer.setRange(0, 5000)
        self.sp_buffer.setValue(0)
        self.sp_buffer.setSuffix(" m")
        self._t(self.sp_buffer.setToolTip, "dl.buffer.tip")
        self.lbl_area = QLabel("")
        f.addRow(self._lbl("dl.layer"), self.cb_layer)
        f.addRow("", self.chk_selected)
        f.addRow(self._lbl("dl.buffer"), self.sp_buffer)
        f.addRow("", self.lbl_area)
        top.addWidget(g_aoi, 1)

        g_c = QGroupBox()
        self._t(g_c.setTitle, "dl.cycle.group")
        fc = QFormLayout(g_c)
        self.cb_cycle = QComboBox()
        self.sp_year = QSpinBox()
        self.sp_year.setRange(2013, 2100)
        self.sp_year.setValue(QDate.currentDate().year())
        self.d_from, self.d_to = QDateEdit(), QDateEdit()
        for d in (self.d_from, self.d_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
        dates = QHBoxLayout()
        dates.addWidget(self.d_from)
        dates.addWidget(self._lbl("dl.dates.to"))
        dates.addWidget(self.d_to)
        self.cb_profile = QComboBox()
        self._t(self.cb_profile.setToolTip, "pf.tip")
        fc.addRow(self._lbl("pf.profile"), self.cb_profile)
        arow = QHBoxLayout()
        self.btn_assign = QPushButton()
        self._t(self.btn_assign.setText, "za.assign")
        self._t(self.btn_assign.setToolTip, "za.assign.tip")
        self.btn_assign.clicked.connect(self.assign_profile)
        self.lbl_assign = QLabel("")
        self.lbl_assign.setWordWrap(True)
        arow.addWidget(self.btn_assign)
        arow.addWidget(self.lbl_assign, 1)
        fc.addRow(arow)
        fc.addRow(self._lbl("dl.cycle"), self.cb_cycle)
        yrow = QHBoxLayout()
        yrow.addWidget(self.sp_year)
        self.lbl_siapyear = QLabel("")
        yrow.addWidget(self.lbl_siapyear, 1)
        fc.addRow(self._lbl("dl.year"), yrow)
        fc.addRow(self._lbl("dl.dates"), dates)
        # stage windows, editable here too (same calendar as tab 1)
        self.stage_table = QTableWidget(0, 3)
        self.stage_table.verticalHeader().setVisible(False)
        self.stage_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.stage_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.stage_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._stage_headers()
        fc.addRow(self.stage_table)
        self.lbl_stages = QLabel("")
        self.lbl_stages.setWordWrap(True)
        self._t(self.lbl_stages.setToolTip, "dl.stages.tip")
        fc.addRow(self.lbl_stages)
        top.addWidget(g_c, 1)
        lay.addLayout(top)
        self._fill_cycles()
        self.cb_cycle.currentIndexChanged.connect(self._cycle_changed)
        self.sp_year.valueChanged.connect(self._cycle_changed)

        # sensors and filters
        g_s = QGroupBox()
        self._t(g_s.setTitle, "dl.search.group")
        gs = QGridLayout(g_s)
        self.chk_sensor, self.cb_source = {}, {}
        for r, sensor in enumerate((S2, LS)):
            c = QCheckBox()
            self._t(c.setText, "sensor." + sensor)
            c.setChecked(True)
            cb = QComboBox()
            for k in stac_client.sources_for(sensor):
                cb.addItem(tr(stac_client.SOURCES[k][1]), k)
            cb.currentIndexChanged.connect(self._source_changed)
            self.chk_sensor[sensor], self.cb_source[sensor] = c, cb
            gs.addWidget(c, r, 0)
            gs.addWidget(cb, r, 1, 1, 3)
        self.keys_box = QGroupBox()
        self._t(self.keys_box.setTitle, "dl.keys")
        fk = QFormLayout(self.keys_box)
        self.le_key, self.le_secret = QLineEdit(), QLineEdit()
        self.le_secret.setEchoMode(QLineEdit.Password)
        fk.addRow(self._lbl("dl.key"), self.le_key)
        fk.addRow(self._lbl("dl.secret"), self.le_secret)
        kn = self._lbl("dl.keys.note")
        kn.setWordWrap(True)
        fk.addRow(kn)
        gs.addWidget(self.keys_box, 2, 0, 1, 4)
        self.sp_cloud = self._pct(60, "dl.cloud.tip")
        self.sp_cover = self._pct(10, "dl.cover.tip")
        self.sp_clear = self._pct(60, "dl.clear.tip")
        gs.addWidget(self._lbl("dl.cloud"), 3, 0)
        gs.addWidget(self.sp_cloud, 3, 1)
        gs.addWidget(self._lbl("dl.cover"), 3, 2)
        gs.addWidget(self.sp_cover, 3, 3)
        gs.addWidget(self._lbl("dl.clear"), 4, 0)
        gs.addWidget(self.sp_clear, 4, 1)
        self.btn_search = QPushButton()
        self._t(self.btn_search.setText, "dl.search")
        self.btn_search.clicked.connect(self.search)
        gs.addWidget(self.btn_search, 4, 2, 1, 2)
        lay.addWidget(g_s)
        self._source_changed()

        # results
        self.table = QTableWidget(0, 8)
        self.table.setMinimumHeight(180)
        self._set_headers()
        self.table.horizontalHeader().setSectionResizeMode(
            7, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table, 2)
        sel = QHBoxLayout()
        self.lbl_count = QLabel("")
        self.lbl_count.setWordWrap(True)
        b_all, b_none = QPushButton(), QPushButton()
        self._t(b_all.setText, "dl.check.all")
        self._t(b_none.setText, "dl.check.none")
        b_all.clicked.connect(lambda: self._check_all(True))
        b_none.clicked.connect(lambda: self._check_all(False))
        sel.addWidget(self.lbl_count, 1)
        sel.addWidget(b_all)
        sel.addWidget(b_none)
        lay.addLayout(sel)

        # bands and output
        g_o = QGroupBox()
        self._t(g_o.setTitle, "dl.out.group")
        v = QVBoxLayout(g_o)
        self.band_checks = {S2: {}, LS: {}}
        for sensor in (S2, LS):
            grid = QGridLayout()
            head = QLabel()
            self._t(head.setText, "sensor." + sensor)
            grid.addWidget(head, 0, 0)
            for i, b in enumerate(BANDS[sensor]):
                if b in ("SCL", "QA_PIXEL"):
                    continue  # the mask always goes with the data
                c = QCheckBox("%s" % b)
                c.setToolTip("%s, %d m" % (BANDS[sensor][b][2],
                                           BANDS[sensor][b][1]))
                c.setChecked(b in DEFAULT_BANDS[sensor])
                self.band_checks[sensor][b] = c
                grid.addWidget(c, i // 6, 1 + i % 6)
            v.addLayout(grid)
        opts = QHBoxLayout()
        self.chk_mosaic = QCheckBox()
        self._t(self.chk_mosaic.setText, "dl.mosaic")
        self._t(self.chk_mosaic.setToolTip, "dl.mosaic.tip")
        self.chk_mosaic.setChecked(True)
        self.chk_add = QCheckBox()
        self._t(self.chk_add.setText, "dl.addmap")
        self.chk_add.setChecked(False)
        opts.addWidget(self.chk_mosaic)
        opts.addWidget(self.chk_add)
        opts.addStretch()
        v.addLayout(opts)
        row = QHBoxLayout()
        row.addWidget(self._lbl("dl.outdir"))
        self.fw_out = QgsFileWidget()
        self.fw_out.setStorageMode(QgsFileWidget.GetDirectory)
        row.addWidget(self.fw_out)
        v.addLayout(row)
        lay.addWidget(g_o)

        run = QHBoxLayout()
        self.progress = QProgressBar()
        self.btn_dl, self.btn_cancel = QPushButton(), QPushButton()
        self._t(self.btn_dl.setText, "dl.run")
        self._t(self.btn_cancel.setText, "cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_dl.clicked.connect(self.download)
        self.btn_cancel.clicked.connect(self.cancel)
        run.addWidget(self.progress, 1)
        run.addWidget(self.btn_dl)
        run.addWidget(self.btn_cancel)
        lay.addLayout(run)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.log.setMinimumHeight(100)
        lay.addWidget(self.log, 1)

    def _pct(self, value, tip):
        sp = QSpinBox()
        sp.setRange(0, 100)
        sp.setValue(value)
        sp.setSuffix(" %")
        self._t(sp.setToolTip, tip)
        return sp

    def _lbl(self, key):
        lab = QLabel()
        self._t(lab.setText, key)
        return lab

    def _set_headers(self):
        self.table.setHorizontalHeaderLabels(
            [""] + [tr("dl.col." + k) for k in
                    ("sensor", "date", "tile", "sat", "cloud", "stage",
                     "warn")])

    def _retranslate_extra(self):
        self._set_headers()
        self._stage_headers()
        for sensor, cb in self.cb_source.items():
            for i in range(cb.count()):
                cb.setItemText(i, tr(stac_client.SOURCES[cb.itemData(i)][1]))
        self._cycle_changed(keep_dates=True)
        if self.scenes:
            states = [self.table.item(r, 0).checkState()
                      for r in range(self.table.rowCount())]
            self._fill_table()
            for r, st in enumerate(states):
                self.table.item(r, 0).setCheckState(st)

    def _source_changed(self, *_):
        self.keys_box.setVisible(any(
            cb.currentData() in stac_client.NEEDS_KEYS and
            self.chk_sensor[s].isChecked()
            for s, cb in self.cb_source.items()))

    def _load_settings(self):
        s = QgsSettings()
        self.fw_out.setFilePath(s.value(SETTINGS + "out_dir", ""))
        for key, sp, dflt in (("max_cloud", self.sp_cloud, 60),
                              ("min_cover", self.sp_cover, 10),
                              ("min_clear", self.sp_clear, 60)):
            sp.setValue(int(s.value(SETTINGS + key, dflt)))
        for sensor, cb in self.cb_source.items():
            i = cb.findData(s.value(SETTINGS + "source_" + sensor, ""))
            if i >= 0:
                cb.setCurrentIndex(i)
        for c in self.chk_sensor.values():
            c.toggled.connect(self._source_changed)

    def _save_settings(self):
        s = QgsSettings()
        s.setValue(SETTINGS + "out_dir", self.fw_out.filePath())
        s.setValue(SETTINGS + "max_cloud", self.sp_cloud.value())
        s.setValue(SETTINGS + "min_cover", self.sp_cover.value())
        s.setValue(SETTINGS + "min_clear", self.sp_clear.value())
        for sensor, cb in self.cb_source.items():
            s.setValue(SETTINGS + "source_" + sensor, cb.currentData())

    def _msg(self, text):
        self.log.appendPlainText(text)

    # ------------------------------------------------------------ cycle
    def _fill_cycles(self):
        cur = self.cb_cycle.currentData()
        self.cb_cycle.blockSignals(True)
        self.cb_cycle.clear()
        for c, spec in self.cal_tab.cal.items():
            self.cb_cycle.addItem("%s  %s" % (c, spec.get("label", "")), c)
        i = self.cb_cycle.findData(cur)
        self.cb_cycle.setCurrentIndex(max(i, 0))
        self.cb_cycle.blockSignals(False)

    def assign_profile(self):
        """Pick the SIAP profile from the study area (largest municipality,
        riego if half of the area is in irrigation districts)."""
        from ..core import zones
        try:
            wkt, _, _ = self.aoi()
            res = zones.suggest_profile(wkt, self.cal_tab.profiles)
        except Exception as e:
            QMessageBox.warning(self, "EloteSat", str(e))
            return None
        parts = ["%s %.0f %%" % (n, 100 * f) for n, f in sorted(
            res["shares"].values(), key=lambda x: -x[1])[:4]]
        txt = tr("za.result", ", ".join(parts) or "-",
                 100 * res["dr_share"])
        if res["profile"]:
            self.cal_tab.set_profile(res["profile"])
            txt += " " + tr("za.chosen", res["profile"])
        if res["warnings"]:
            txt += "<br><span style='color:#D55E00'>%s</span>" % \
                "; ".join(res["warnings"])
        self.lbl_assign.setText(txt)
        return res

    def _fill_profiles(self, *_):
        self.cb_profile.blockSignals(True)
        self.cb_profile.clear()
        for n in self.cal_tab.profiles:
            self.cb_profile.addItem(n, n)
        self.cb_profile.setCurrentIndex(self.cb_profile.findData(
            self.cal_tab.profile))
        self.cb_profile.blockSignals(False)

    def _calendar_changed(self):
        self._fill_cycles()
        self._cycle_changed(keep_dates=True)
        if self.scenes:
            self._assign_stages()
            self._fill_table()

    def _cycle_changed(self, *_, keep_dates=False):
        c = self.cb_cycle.currentData()
        if c is None:
            return
        cal = self.cal_tab.cal
        try:
            w = phenology.windows(cal, c, self.sp_year.value())
        except phenology.CalendarError as e:
            self.lbl_stages.setText(tr("cal.invalid", e))
            return
        from ..core import siap
        self.lbl_siapyear.setText(tr("za.siapyear", c, siap.siap_year(
            c, cal, self.sp_year.value())))
        if not keep_dates:
            a, b = w[0][1], w[-1][2]
            self.d_from.setDate(QDate(a.year, a.month, a.day))
            self.d_to.setDate(QDate(b.year, b.month, b.day))
        self._fill_stage_table(w)
        self.lbl_stages.setText(tr("dl.stages.note"))

    def _stage_headers(self):
        self.stage_table.setHorizontalHeaderLabels(
            [tr("cal.col.stage"), tr("dl.stage.start"), tr("dl.stage.end")])

    def _fill_stage_table(self, w):
        names = [n for n, _, _ in w]
        same = names == [self.stage_table.item(r, 0).text()
                         for r in range(self.stage_table.rowCount())
                         if self.stage_table.item(r, 0)]
        if not same:
            self.stage_table.setRowCount(len(w))
        for r, (n, a, b) in enumerate(w):
            if not same:
                self.stage_table.setItem(r, 0, QTableWidgetItem(n))
                for col in (1, 2):
                    de = QDateEdit()
                    de.setCalendarPopup(True)
                    de.setDisplayFormat("yyyy-MM-dd")
                    de.dateChanged.connect(self._stage_edited)
                    self.stage_table.setCellWidget(r, col, de)
            for col, d in ((1, a), (2, b)):
                de = self.stage_table.cellWidget(r, col)
                de.blockSignals(True)
                de.setDate(QDate(d.year, d.month, d.day))
                de.blockSignals(False)
        self.stage_table.resizeColumnsToContents()
        self.stage_table.resizeRowsToContents()
        self.stage_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        h = self.stage_table.horizontalHeader().sizeHint().height() + 4
        h += sum(self.stage_table.rowHeight(r)
                 for r in range(self.stage_table.rowCount()))
        self.stage_table.setFixedHeight(h)

    def _stage_edited(self, *_):
        """A date changed in the stage table: write MM-DD back to the
        calendar (it is the same calendar as tab 1, and it is reused every
        year). Invalid windows are refused and the table goes back."""
        c = self.cb_cycle.currentData()
        new = phenology.copy_calendar(self.cal_tab.cal)
        stages = new[c]["stages"]
        for r in range(min(self.stage_table.rowCount(), len(stages))):
            for col in (1, 2):
                d = self.stage_table.cellWidget(r, col).date()
                stages[r][col] = "%02d-%02d" % (d.month(), d.day())
        try:
            phenology.validate(new)
            # the typed year must fit the cycle year (MM-DD keeps no year)
            w = phenology.windows(new, c, self.sp_year.value())
            for r, (n, a, b) in enumerate(w):
                for col, d in ((1, a), (2, b)):
                    q = self.stage_table.cellWidget(r, col).date()
                    if q.year() != d.year:
                        raise phenology.CalendarError(
                            tr("dl.stage.year", n, d.year))
        except phenology.CalendarError as e:
            self.lbl_stages.setText(
                "<span style='color:#D55E00'>%s</span>" %
                tr("cal.invalid", e))
            QTimer.singleShot(0, self._revert_stage_table)
            return
        # apply after this signal returns (widgets may be refreshed)
        QTimer.singleShot(0, lambda: self.cal_tab.apply_calendar(new))
        QTimer.singleShot(0, lambda: self._cycle_changed())

    def _revert_stage_table(self):
        msg = self.lbl_stages.text()
        self._cycle_changed(keep_dates=True)
        self.lbl_stages.setText(msg)

    def _assign_stages(self):
        c, y, cal = (self.cb_cycle.currentData(), self.sp_year.value(),
                     self.cal_tab.cal)
        for sc in self.scenes:
            sc.stage = phenology.assign(sc.date, cal, c, y)

    # ------------------------------------------------------------ AOI
    def aoi(self):
        """(wkt lon/lat, bbox, area km2) of the union of the polygons."""
        layer = self.cb_layer.currentLayer()
        if layer is None:
            raise ValueError(tr("err.nolayer"))
        feats = (layer.selectedFeatures() if self.chk_selected.isChecked()
                 else list(layer.getFeatures()))
        geoms = [f.geometry() for f in feats
                 if f.hasGeometry() and not f.geometry().isEmpty()]
        if not geoms:
            raise ValueError(tr("err.nogeom"))
        g = QgsGeometry.unaryUnion(geoms)
        if g.type() != QgsWkbTypes.PolygonGeometry:
            raise ValueError(tr("err.notpoly"))
        da = QgsDistanceArea()
        da.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
        da.setEllipsoid(QgsProject.instance().ellipsoid() or "WGS84")
        try:
            from qgis.core import Qgis
            km2_unit = Qgis.AreaUnit.SquareKilometers  # QGIS >= 3.30
        except AttributeError:
            from qgis.core import QgsUnitTypes
            km2_unit = QgsUnitTypes.AreaSquareKilometers
        km2 = da.convertAreaMeasurement(da.measureArea(g), km2_unit)
        xf = QgsCoordinateTransform(
            layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance())
        g.transform(xf)
        return g.asWkt(), g.boundingBox(), km2

    # ------------------------------------------------------------ search
    def search(self):
        try:
            wkt, bb, km2 = self.aoi()
        except ValueError as e:
            QMessageBox.warning(self, "EloteSat", str(e))
            return
        sensors = [s for s, c in self.chk_sensor.items() if c.isChecked()]
        if not sensors:
            QMessageBox.warning(self, "EloteSat", tr("err.nosensor"))
            return
        if self.d_from.date() > self.d_to.date():
            QMessageBox.warning(self, "EloteSat", tr("err.dates"))
            return
        self._wkt, self._km2 = wkt, km2
        self.lbl_area.setText(tr("dl.area", km2))
        bbox = (bb.xMinimum(), bb.yMinimum(), bb.xMaximum(), bb.yMaximum())
        self.scenes = []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for s in sensors:
                src = self.cb_source[s].currentData()
                try:
                    found = stac_client.search(
                        bbox, self.d_from.date().toString("yyyy-MM-dd"),
                        self.d_to.date().toString("yyyy-MM-dd"),
                        source_key=src, max_cloud=self.sp_cloud.value(),
                        post_json=stac_client.qgis_post_json)
                except stac_client.StacError as e:
                    self._msg(tr("dl.msg.searchfail", tr("sensor." + s), e))
                    continue
                self.scenes.extend(found)
                self._msg(tr("dl.msg.found", len(found), tr("sensor." + s),
                             tr(stac_client.SOURCES[src][1])))
        finally:
            QApplication.restoreOverrideCursor()
        self.scenes.sort(key=lambda x: (x.date, x.sensor, x.tile))
        try:
            self.duplicates = stac_client.find_duplicates(self.scenes, wkt)
        except Exception as e:
            self.duplicates = {}
            self._msg(tr("dl.msg.dupfail", e))
        self._assign_stages()
        self._fill_table()

    def _fill_table(self):
        self.table.setRowCount(len(self.scenes))
        for r, sc in enumerate(self.scenes):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            dup = self.duplicates.get(sc.id)
            chk.setCheckState(Qt.Unchecked if dup else Qt.Checked)
            self.table.setItem(r, 0, chk)
            warn = []
            if dup:
                warn.append(tr("dl.warn.dup", dup))
            if sc.missing:
                warn.append(tr("dl.warn.missing", ",".join(sc.missing)))
            if any(a.offset != a.offset for a in sc.assets.values()):
                warn.append(tr("dl.warn.offset"))
            if sc.stage == phenology.OUT_OF_STAGE:
                warn.append(tr("dl.warn.nostage"))
            vals = [tr("sensor." + sc.sensor), sc.date, sc.tile,
                    sc.short_platform, "%.1f" % sc.cloud_tile, sc.stage,
                    "; ".join(warn)]
            for c, v in enumerate(vals, start=1):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(r, c, it)
        self.table.resizeColumnsToContents()
        self._update_count()

    def _update_count(self):
        counts = {}
        for sc in self.scenes:
            counts.setdefault(sc.stage, [0, 0])
            counts[sc.stage][0 if sc.sensor == S2 else 1] += 1
        parts = ["%s: S2 %d, Landsat %d" % (k, v[0], v[1])
                 for k, v in sorted(counts.items())]
        size = ""
        if getattr(self, "_km2", None):
            size = tr("dl.size", self._size_gb())
        self.lbl_count.setText(tr("dl.count", len(self.scenes)) + " " +
                               " · ".join(parts) + size)

    def _size_gb(self):
        """Rough upper bound, uncompressed, all listed scenes."""
        m2 = self._km2 * 1e6
        total = 0.0
        for sc in self.scenes:
            for b, c in self.band_checks[sc.sensor].items():
                if c.isChecked():
                    total += m2 / BANDS[sc.sensor][b][1] ** 2 * 2
            total += m2 / (20 ** 2 if sc.sensor == S2 else 30 ** 2) * 2
        return total / 1e9

    def _check_all(self, state):
        for r in range(self.table.rowCount()):
            self.table.item(r, 0).setCheckState(
                Qt.Checked if state else Qt.Unchecked)

    def _checked_scenes(self):
        return [self.scenes[r] for r in range(self.table.rowCount())
                if self.table.item(r, 0).checkState() == Qt.Checked]

    # ------------------------------------------------------------ download
    def download(self):
        scenes = self._checked_scenes()
        out_dir = self.fw_out.filePath()
        bands = {s: [b for b, c in self.band_checks[s].items()
                     if c.isChecked()] for s in (S2, LS)}
        if not scenes:
            QMessageBox.warning(self, "EloteSat", tr("err.noscenes"))
            return
        if not out_dir:
            QMessageBox.warning(self, "EloteSat", tr("err.nodir"))
            return
        if any(not bands[sc.sensor] for sc in scenes):
            QMessageBox.warning(self, "EloteSat", tr("err.nobands"))
            return
        try:
            wkt, _, _ = self.aoi()
        except ValueError as e:
            QMessageBox.warning(self, "EloteSat", str(e))
            return
        self._save_settings()
        c, y = self.cb_cycle.currentData(), self.sp_year.value()
        self._assign_stages()  # calendar may have changed since the search
        needs_keys = any(sc.source in stac_client.NEEDS_KEYS for sc in scenes)
        params = {
            "profile": self.cal_tab.profile, "cycle": c, "cycle_year": y,
            "date_from": self.d_from.date().toString("yyyy-MM-dd"),
            "date_to": self.d_to.date().toString("yyyy-MM-dd"),
            "sources": ",".join(sorted({sc.source for sc in scenes})),
            "max_cloud_tile_pct": self.sp_cloud.value(),
            "min_cover_aoi_pct": self.sp_cover.value(),
            "min_clear_aoi_pct": self.sp_clear.value(),
            "buffer_m": self.sp_buffer.value(),
            "bands_S2": ",".join(bands[S2]),
            "bands_LANDSAT": ",".join(bands[LS]),
            "study_area_wkt_4326": wkt,
        }
        self.task = DownloadTask(
            scenes, wkt, out_dir, c, y, self.cal_tab.calendar(), bands,
            min_clear=self.sp_clear.value() / 100.0,
            min_cover=self.sp_cover.value() / 100.0,
            buffer_m=self.sp_buffer.value(),
            mosaic=self.chk_mosaic.isChecked(),
            creds=((self.le_key.text().strip(),
                    self.le_secret.text().strip()) if needs_keys else None),
            params=params,
            profile=(self.cal_tab.profile,
                     self.cal_tab.profiles[self.cal_tab.profile]))
        self.task.message.connect(self._msg)
        self.task.progressChanged.connect(
            lambda p: self.progress.setValue(int(p)))
        self.task.taskCompleted.connect(self._done)
        self.task.taskTerminated.connect(self._done)
        self.btn_dl.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self._msg(tr("dl.msg.start", len(scenes), self.task.cycle_dir))
        QgsApplication.taskManager().addTask(self.task)

    def cancel(self):
        if self.task:
            self.task.cancel()

    def _done(self):
        t = self.task
        self.btn_dl.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        st = [str(r.get("status", "")) for r in t.records]
        self._msg(tr("dl.msg.end", st.count("ok"),
                     sum(1 for s in st if s.startswith("skipped")),
                     st.count("error")))
        if t.manifest:
            self._msg(tr("dl.msg.manifest", t.manifest))
        if t.error:
            self._msg(tr("error", t.error))
        if self.chk_add.isChecked() and t.outputs:
            self._add_layers(t)
        self.task = None
        if "ok" in st:
            self.downloadFinished.emit(t.out_dir)

    def _add_layers(self, t):
        root = QgsProject.instance().layerTreeRoot()
        top = root.findGroup("EloteSat") or root.insertGroup(0, "EloteSat")
        cname = "%s_%d" % (t.cycle, t.year)
        cg = top.findGroup(cname) or top.addGroup(cname)
        for rec, o in zip([r for r in t.records if r.get("status") == "ok"],
                          t.outputs):
            p = o.get("10m") or o.get("30m")
            if not p:
                continue
            sg = cg.findGroup(rec["stage"]) or cg.addGroup(rec["stage"])
            lyr = QgsRasterLayer(p, os.path.splitext(os.path.basename(p))[0])
            if not lyr.isValid():
                continue
            descs = [lyr.dataProvider().bandDescription(i)
                     for i in range(1, lyr.bandCount() + 1)]
            rgb = RGB[rec["sensor"]]
            r = lyr.renderer()
            if isinstance(r, QgsMultiBandColorRenderer) and all(
                    b in descs for b in rgb):
                r.setRedBand(descs.index(rgb[0]) + 1)
                r.setGreenBand(descs.index(rgb[1]) + 1)
                r.setBlueBand(descs.index(rgb[2]) + 1)
                lyr.setDefaultContrastEnhancement()
            QgsProject.instance().addMapLayer(lyr, False)
            sg.addLayer(lyr)
