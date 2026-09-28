"""Tab 5: labelled samples, separability and a threshold explorer."""

import html
import os

import numpy as np
from qgis.core import (QgsMapLayerProxyModel, QgsWkbTypes)
from qgis.gui import QgsFileWidget, QgsMapLayerComboBox, QgsFieldComboBox
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QSpinBox,
    QDoubleSpinBox, QPushButton, QLabel, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QSplitter, QFileDialog,
    QAbstractItemView)

from ..core import samples as smp
from ..core import separability as sep
from ..core.classify import CLASS_COLORS
from ..core.i18n import tr
from .charts import HistChart, ProfileChart
from .common import add_raster, stage_series
from .translatable import Translatable

CLASS_KEYS = ("maiz", "sorgo", "otros", "")


def guess_class(value):
    v = str(value).lower()
    if v.startswith("ma") or "corn" in v or "maize" in v:
        return "maiz"
    if v.startswith("sorg"):
        return "sorgo"
    return "otros"


class SamplesTab(QWidget, Translatable):
    samplesReady = pyqtSignal()
    useVariables = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = None
        self.rank = []
        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)

        # ---------------- left: samples + ranking
        left = QWidget()
        ll = QVBoxLayout(left)
        g = QGroupBox()
        self._t(g.setTitle, "sm.group")
        f = QFormLayout(g)
        self.fw_vars = QgsFileWidget()
        self.fw_vars.setFilter("GeoTIFF (*.tif)")
        f.addRow(self._lbl("cl.vars"), self.fw_vars)
        self.cb_layer = QgsMapLayerComboBox()
        self.cb_layer.setFilters(QgsMapLayerProxyModel.PolygonLayer |
                                 QgsMapLayerProxyModel.PointLayer)
        self.cb_field = QgsFieldComboBox()
        self.cb_gid = QgsFieldComboBox()
        self.cb_gid.setAllowEmptyFieldName(True)
        self._t(self.cb_gid.setToolTip, "sm.gid.tip")
        self.cb_layer.layerChanged.connect(self.cb_field.setLayer)
        self.cb_layer.layerChanged.connect(self.cb_gid.setLayer)
        self.cb_field.setLayer(self.cb_layer.currentLayer())
        self.cb_gid.setLayer(self.cb_layer.currentLayer())
        self.cb_field.fieldChanged.connect(self._fill_mapping)
        # the field box picks its first field silently when the layer
        # changes: refresh the mapping after it (connected last)
        self.cb_layer.layerChanged.connect(self._fill_mapping)
        f.addRow(self._lbl("sm.layer"), self.cb_layer)
        f.addRow(self._lbl("sm.field"), self.cb_field)
        f.addRow(self._lbl("sm.gid"), self.cb_gid)
        self.map_table = QTableWidget(0, 2)
        self.map_table.verticalHeader().setVisible(False)
        self.map_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.map_table.setMaximumHeight(130)
        f.addRow(self.map_table)
        opts = QHBoxLayout()
        self.sp_buf = QDoubleSpinBox()
        self.sp_buf.setRange(0, 200)
        self.sp_buf.setValue(10)
        self.sp_buf.setSuffix(" m")
        self._t(self.sp_buf.setToolTip, "sm.buf.tip")
        self.sp_rad = QDoubleSpinBox()
        self.sp_rad.setRange(0, 200)
        self.sp_rad.setValue(0)
        self.sp_rad.setSuffix(" m")
        self._t(self.sp_rad.setToolTip, "sm.rad.tip")
        self.sp_max = QSpinBox()
        self.sp_max.setRange(0, 100000)
        self.sp_max.setValue(0)
        self._t(self.sp_max.setToolTip, "sm.max.tip")
        opts.addWidget(self._lbl("sm.buf"))
        opts.addWidget(self.sp_buf)
        opts.addWidget(self._lbl("sm.rad"))
        opts.addWidget(self.sp_rad)
        opts.addWidget(self._lbl("sm.max"))
        opts.addWidget(self.sp_max)
        f.addRow(opts)
        brow = QHBoxLayout()
        self.btn_ext = QPushButton()
        self._t(self.btn_ext.setText, "sm.extract")
        self.btn_ext.clicked.connect(self.extract)
        self.btn_load = QPushButton()
        self._t(self.btn_load.setText, "sm.load")
        self.btn_load.clicked.connect(self._load_csv)
        brow.addWidget(self.btn_ext)
        brow.addWidget(self.btn_load)
        f.addRow(brow)
        self.lbl_sum = QLabel("")
        self.lbl_sum.setWordWrap(True)
        f.addRow(self.lbl_sum)
        ll.addWidget(g)

        g2 = QGroupBox()
        self._t(g2.setTitle, "sm.sep")
        v2 = QVBoxLayout(g2)
        r2 = QHBoxLayout()
        self.cb_comp = QComboBox()
        self.cb_unit = QComboBox()
        self._fill_combos()
        self.cb_comp.currentIndexChanged.connect(self.update_ranking)
        self.cb_unit.currentIndexChanged.connect(self.update_ranking)
        r2.addWidget(self.cb_comp, 2)
        r2.addWidget(self.cb_unit, 1)
        v2.addLayout(r2)
        self.rank_table = QTableWidget(0, 6)
        self.rank_table.verticalHeader().setVisible(False)
        self.rank_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.rank_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.rank_table.itemSelectionChanged.connect(self._var_selected)
        self._rank_headers()
        v2.addWidget(self.rank_table, 1)
        r3 = QHBoxLayout()
        self.sp_k = QSpinBox()
        self.sp_k.setRange(1, 15)
        self.sp_k.setValue(5)
        self.btn_fwd = QPushButton()
        self._t(self.btn_fwd.setText, "sm.fwd")
        self.btn_fwd.clicked.connect(self._forward)
        self.btn_use = QPushButton()
        self._t(self.btn_use.setText, "sm.use")
        self._t(self.btn_use.setToolTip, "sm.use.tip")
        self.btn_use.clicked.connect(
            lambda: self.useVariables.emit(list(getattr(self, "_fwd",
                                                        []))))
        r3.addWidget(self._lbl("sm.k"))
        r3.addWidget(self.sp_k)
        r3.addWidget(self.btn_fwd)
        r3.addWidget(self.btn_use)
        v2.addLayout(r3)
        self.lbl_fwd = QLabel("")
        self.lbl_fwd.setWordWrap(True)
        self.lbl_fwd.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v2.addWidget(self.lbl_fwd)
        ll.addWidget(g2, 1)
        split.addWidget(left)

        # ---------------- right: charts and threshold
        right = QWidget()
        rl = QVBoxLayout(right)
        self.hist = HistChart()
        rl.addWidget(self.hist, 2)
        tr_row = QHBoxLayout()
        self.cb_dir = QComboBox()
        self.cb_dir.addItems([">", "<="])
        self.sp_thr = QDoubleSpinBox()
        self.sp_thr.setDecimals(4)
        self.sp_thr.setRange(-1e9, 1e9)
        self.sp_thr.setSingleStep(0.01)
        self.sp_thr.valueChanged.connect(self._thr_changed)
        self.cb_dir.currentIndexChanged.connect(self._thr_changed)
        self.btn_rule = QPushButton()
        self._t(self.btn_rule.setText, "sm.rule")
        self.btn_rule.clicked.connect(self._rule_map)
        tr_row.addWidget(self._lbl("sm.thr"))
        tr_row.addWidget(self.cb_dir)
        tr_row.addWidget(self.sp_thr)
        tr_row.addWidget(self.btn_rule)
        rl.addLayout(tr_row)
        self.lbl_conf = QLabel("")
        self.lbl_conf.setWordWrap(True)
        self.lbl_conf.setTextFormat(Qt.RichText)
        rl.addWidget(self.lbl_conf)
        prow = QHBoxLayout()
        self.cb_psens = QComboBox()
        self.cb_psens.addItems(["S2", "LS"])
        self.cb_pvar = QComboBox()
        self.cb_pvar.addItems(["NDVI", "NDRE", "CIre", "GCVI", "NDMI",
                               "NDTI", "B04", "B05", "B8A", "B11"])
        self.cb_pvar.setEditable(True)
        for cb in (self.cb_psens, self.cb_pvar):
            cb.currentIndexChanged.connect(self._profile)
        prow.addWidget(self._lbl("cl.profile"))
        self.cb_kind = QComboBox()
        self.cb_kind.addItem(tr("kind.rel"), "rel")
        self.cb_kind.addItem(tr("kind.fixed"), "fixed")
        self.cb_kind.currentIndexChanged.connect(self._profile)
        prow.addWidget(self.cb_kind)
        prow.addWidget(self.cb_psens)
        prow.addWidget(self.cb_pvar)
        prow.addStretch()
        rl.addLayout(prow)
        self.prof = ProfileChart()
        rl.addWidget(self.prof, 2)
        split.addWidget(right)
        split.setSizes([480, 560])
        lay.addWidget(split, 1)
        self._var_selected()
        self._profile()

    # ------------------------------------------------------------ helpers
    def _lbl(self, key):
        lab = QLabel()
        self._t(lab.setText, key)
        return lab

    def _fill_combos(self):
        ci, ui = self.cb_comp.currentIndex(), self.cb_unit.currentIndex()
        self.cb_comp.blockSignals(True)
        self.cb_unit.blockSignals(True)
        self.cb_comp.clear()
        self.cb_comp.addItem(tr("sm.comp.c4"), "c4")
        self.cb_comp.addItem(tr("sm.comp.ms"), "ms")
        self.cb_unit.clear()
        self.cb_unit.addItem(tr("sm.unit.px"), False)
        self.cb_unit.addItem(tr("sm.unit.field"), True)
        self.cb_comp.setCurrentIndex(max(ci, 0))
        self.cb_unit.setCurrentIndex(max(ui, 0))
        self.cb_comp.blockSignals(False)
        self.cb_unit.blockSignals(False)

    def _rank_headers(self):
        c = self.cb_comp.currentData()
        a, b = (tr("sm.a.c4"), tr("sm.b.c4")) if c == "c4" else \
            (tr("cls.maiz"), tr("cls.sorgo"))
        self.rank_table.setHorizontalHeaderLabels(
            [tr("sm.col.var"), "JM", a, b, tr("sm.col.rule"),
             tr("sm.col.bal")])

    def _retranslate_extra(self):
        self.cb_kind.setItemText(0, tr("kind.rel"))
        self.cb_kind.setItemText(1, tr("kind.fixed"))
        self._fill_combos()
        self._rank_headers()
        self._fill_mapping()
        self._var_selected()
        self._profile()

    def set_vars(self, path):
        if path != self.fw_vars.filePath():
            self.fw_vars.setFilePath(path)

    def _fill_mapping(self, *_):
        self.map_table.setHorizontalHeaderLabels([tr("sm.value"),
                                                  tr("sm.class")])
        lyr = self.cb_layer.currentLayer()
        fld = self.cb_field.currentField()
        self.map_table.setRowCount(0)
        if lyr is None or not fld:
            return
        idx = lyr.fields().indexOf(fld)
        vals = sorted({str(v) for v in lyr.uniqueValues(idx)
                       if v is not None})[:200]
        self.map_table.setRowCount(len(vals))
        for r, v in enumerate(vals):
            self.map_table.setItem(r, 0, QTableWidgetItem(v))
            cb = QComboBox()
            for k in CLASS_KEYS:
                cb.addItem(tr("cls." + (k or "ignore")), k)
            cb.setCurrentIndex(cb.findData(guess_class(v)))
            self.map_table.setCellWidget(r, 1, cb)

    def _mapping(self):
        return {self.map_table.item(r, 0).text():
                self.map_table.cellWidget(r, 1).currentData()
                for r in range(self.map_table.rowCount())}

    # ------------------------------------------------------------ samples
    def extract(self):
        vpath = self.fw_vars.filePath()
        lyr = self.cb_layer.currentLayer()
        fld = self.cb_field.currentField()
        if not vpath or lyr is None or not fld:
            QMessageBox.warning(self, "EloteSat", tr("sm.err.input"))
            return
        mapping = self._mapping()
        gid = self.cb_gid.currentField()
        srs = lyr.crs().toWkt()
        feats = []
        for ft in lyr.getFeatures():
            if not ft.hasGeometry():
                continue
            label = mapping.get(str(ft[fld]), "")
            gval = ft[gid] if gid else ft.id()
            feats.append((ft.geometry().asWkt(), srs, label,
                          "%s" % gval))
        pts = QgsWkbTypes.geometryType(lyr.wkbType()) == \
            QgsWkbTypes.PointGeometry
        try:
            s, rep = smp.extract(vpath, feats,
                                 inner_buffer=0 if pts else
                                 self.sp_buf.value(),
                                 point_radius=self.sp_rad.value(),
                                 max_per_group=self.sp_max.value() or None)
        except Exception as e:
            QMessageBox.warning(self, "EloteSat", str(e))
            return
        out = os.path.join(os.path.dirname(os.path.dirname(vpath)),
                           "muestras", "muestras.csv")
        s.save_csv(out)
        self._set_samples(s, rep, out)

    def _load_csv(self):
        p, _ = QFileDialog.getOpenFileName(self, "EloteSat", "",
                                           "CSV (*.csv)")
        if not p:
            return
        try:
            s = smp.Samples.load_csv(p)
        except Exception as e:
            QMessageBox.warning(self, "EloteSat", str(e))
            return
        self._set_samples(s, None, p)

    def _set_samples(self, s, rep, path):
        self.samples = s
        summ = s.summary()
        txt = tr("sm.summary", *[v for c in smp.CLASSES for v in summ[c]])
        if rep:
            txt += " " + tr("sm.rep", rep["ignored_class"],
                            rep["empty_after_buffer"], rep["outside"])
        few = [c for c in smp.CLASSES if summ[c][1] < 10]
        if few:
            txt += "<br><span style='color:#D55E00'>%s</span>" % tr(
                "sm.few", ", ".join(tr("cls." + c) for c in few))
        self.lbl_sum.setText(txt + "<br>" + path)
        self.update_ranking()
        self._profile()
        self.samplesReady.emit()

    # ------------------------------------------------------------ ranking
    def update_ranking(self, *_):
        self._rank_headers()
        s = self.samples
        self.rank_table.setRowCount(0)
        if s is None:
            return
        self.rank = sep.ranking(s, self.cb_comp.currentData(),
                                by_field=self.cb_unit.currentData())
        self.rank_table.setRowCount(len(self.rank))
        for r, row in enumerate(self.rank):
            vals = [row["var"], "%.3f" % row["jm"],
                    "%.4g ± %.2g" % (row["mean_a"], row["sd_a"]),
                    "%.4g ± %.2g" % (row["mean_b"], row["sd_b"]),
                    "%s %.4g" % (row["dir"], row["thr"]),
                    "%.3f" % row["bal_acc"]]
            for c, v in enumerate(vals):
                self.rank_table.setItem(r, c, QTableWidgetItem(v))
        self.rank_table.resizeColumnsToContents()
        if self.rank:
            self.rank_table.selectRow(0)

    def _forward(self):
        s = self.samples
        if s is None:
            return
        path = sep.forward_selection(s, self.cb_comp.currentData(),
                                     k=self.sp_k.value(),
                                     by_field=self.cb_unit.currentData())
        self._fwd = [p[0] for p in path]
        self.lbl_fwd.setText(tr("sm.fwd.res") + "<br>" + "<br>".join(
            "%d. %s  (JM %.3f)" % (i + 1, v, jm)
            for i, (v, jm) in enumerate(path)))

    # ------------------------------------------------------------ charts
    def _current_var(self):
        rows = self.rank_table.selectionModel().selectedRows() \
            if self.rank_table.selectionModel() else []
        if not rows or not self.rank:
            return None
        return self.rank[rows[0].row()]

    def _var_selected(self):
        row = self._current_var()
        if row is None or self.samples is None:
            self.hist.set_data([], empty_text=tr("sm.empty"))
            self.lbl_conf.setText("")
            return
        s = self.samples
        j = s.names.index(row["var"])
        by_field = self.cb_unit.currentData()
        groups = []
        for c in smp.CLASSES:
            m = s.y == c
            v = s.X[m, j]
            if by_field and m.any():
                v = sep.field_medians(s.X[m][:, [j]], s.g[m])[:, 0]
            groups.append((tr("cls." + c), CLASS_COLORS[c], v))
        self.hist.set_data(groups, title=row["var"], threshold=row["thr"],
                           empty_text=tr("sm.empty"))
        self.sp_thr.blockSignals(True)
        self.cb_dir.blockSignals(True)
        self.sp_thr.setValue(row["thr"] if np.isfinite(row["thr"]) else 0)
        self.cb_dir.setCurrentText(row["dir"])
        self.sp_thr.blockSignals(False)
        self.cb_dir.blockSignals(False)
        self._thr_changed()

    def _thr_changed(self, *_):
        row = self._current_var()
        if row is None or self.samples is None:
            return
        thr, d = self.sp_thr.value(), self.cb_dir.currentText()
        self.hist.set_threshold(thr)
        s = self.samples
        comp = self.cb_comp.currentData()
        A, B = sep.two_groups(s, comp, self.cb_unit.currentData())
        j = s.names.index(row["var"])
        c = sep.confusion_threshold(A[:, j], B[:, j], thr, d)
        na = c["A_as_A"] + c["A_as_B"]
        nb = c["B_as_A"] + c["B_as_B"]
        a_lbl = tr("sm.a.c4") if comp == "c4" else tr("cls.maiz")
        b_lbl = tr("sm.b.c4") if comp == "c4" else tr("cls.sorgo")
        self.lbl_conf.setText(html.escape(tr(
            "sm.conf", a_lbl, row["var"], d, thr, a_lbl,
            c["A_as_A"], na, 100.0 * c["A_as_A"] / max(na, 1), b_lbl,
            c["B_as_A"], nb, 100.0 * c["B_as_A"] / max(nb, 1))))

    def _profile(self, *_):
        s = self.samples
        if s is None:
            self.prof.set_data([], [], empty_text=tr("sm.empty"))
            return
        pre, var = self.cb_psens.currentText(), self.cb_pvar.currentText()
        series, cats = [], []
        for c in smp.CLASSES:
            m = s.y == c
            if not m.any():
                continue
            with np.errstate(all="ignore"):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)
                    mean = np.nanmean(s.X[m], axis=0)
                    sd = np.nanstd(s.X[m], axis=0)
            kind = self.cb_kind.currentData()
            cats, mv = stage_series(s.names, mean, pre, var, kind)
            _, sv = stage_series(s.names, sd, pre, var, kind)
            series.append((tr("cls." + c), CLASS_COLORS[c], mv, sv))
        self.prof.set_data(cats, series, title="%s %s (± 1 sd)" % (pre, var),
                           ylabel=var, empty_text=tr("sm.empty"))

    def _rule_map(self):
        row = self._current_var()
        vpath = self.fw_vars.filePath()
        if row is None or not vpath:
            return
        thr, d = self.sp_thr.value(), self.cb_dir.currentText()
        out = os.path.join(os.path.dirname(os.path.dirname(vpath)),
                           "reglas", "regla_%s_%s_%g.tif" % (
                               row["var"], "gt" if d == ">" else "le", thr))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        km2 = sep.apply_rule(vpath, row["var"], thr, d, out)
        add_raster(out, os.path.basename(out)[:-4])
        self.lbl_conf.setText(self.lbl_conf.text() + "<br>" +
                              tr("sm.rule.done", km2))
