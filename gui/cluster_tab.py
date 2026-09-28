"""Tab 4: groups without field data (k-means)."""

import numpy as np
from qgis.core import QgsApplication
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QSpinBox,
    QPushButton, QLabel, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QSplitter, QPlainTextEdit)

from ..core import cluster
from ..core import rasterio_util as rio
from ..core.i18n import tr
from ..core.task import FunctionTask
from .charts import ProfileChart
from .common import VarList, add_raster, stage_series
from .translatable import Translatable


class ClusterTab(QWidget, Translatable):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.task = None
        self.result = None
        lay = QVBoxLayout(self)
        note = self._lbl("cl.intro")
        note.setWordWrap(True)
        lay.addWidget(note)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        f = QFormLayout()
        self.fw_vars = QgsFileWidget()
        self.fw_vars.setFilter("GeoTIFF (*.tif)")
        self.fw_vars.fileChanged.connect(self._load_names)
        f.addRow(self._lbl("cl.vars"), self.fw_vars)
        self.sp_k = QSpinBox()
        self.sp_k.setRange(2, 12)
        self.sp_k.setValue(6)
        self.sp_n = QSpinBox()
        self.sp_n.setRange(1000, 500000)
        self.sp_n.setSingleStep(10000)
        self.sp_n.setValue(50000)
        self.sp_seed = QSpinBox()
        self.sp_seed.setRange(0, 99999)
        f.addRow(self._lbl("cl.k"), self.sp_k)
        f.addRow(self._lbl("cl.n"), self.sp_n)
        f.addRow(self._lbl("seed"), self.sp_seed)
        ll.addLayout(f)
        ll.addWidget(self._lbl("cl.pick"))
        self.vlist = VarList()
        ll.addWidget(self.vlist, 1)
        row = QHBoxLayout()
        self.btn = QPushButton()
        self._t(self.btn.setText, "cl.run")
        self.btn.clicked.connect(self.run)
        row.addStretch()
        row.addWidget(self.btn)
        ll.addLayout(row)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        self.table = QTableWidget(0, 6)
        self._headers()
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents)
        rl.addWidget(self.table, 1)
        prow = QHBoxLayout()
        self.cb_sensor = QComboBox()
        self.cb_sensor.addItems(["S2", "LS"])
        self.cb_var = QComboBox()
        self.cb_var.addItems(["NDVI", "NDRE", "CIre", "GCVI", "NDMI",
                              "NDTI"])
        for cb in (self.cb_sensor, self.cb_var):
            cb.currentIndexChanged.connect(self._plot)
        prow.addWidget(self._lbl("cl.profile"))
        self.cb_kind = QComboBox()
        self.cb_kind.addItem(tr("kind.rel"), "rel")
        self.cb_kind.addItem(tr("kind.fixed"), "fixed")
        self.cb_kind.currentIndexChanged.connect(self._plot)
        prow.addWidget(self.cb_kind)
        prow.addWidget(self.cb_sensor)
        prow.addWidget(self.cb_var)
        prow.addStretch()
        rl.addLayout(prow)
        self.chart = ProfileChart()
        rl.addWidget(self.chart, 2)
        split.addWidget(right)
        split.setSizes([380, 620])
        lay.addWidget(split, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(90)
        lay.addWidget(self.log)
        self._plot()

    def _lbl(self, key):
        lab = QLabel()
        self._t(lab.setText, key)
        return lab

    def _headers(self):
        self.table.setHorizontalHeaderLabels(
            [tr("cl.col.g"), tr("cl.col.km2"), "NDVImax", tr("cl.col.dur"),
             tr("cl.col.upmax"), tr("cl.col.ref")])

    def _retranslate_extra(self):
        self.cb_kind.setItemText(0, tr("kind.rel"))
        self.cb_kind.setItemText(1, tr("kind.fixed"))
        self._headers()
        self.vlist.retranslate()
        self._plot()

    def set_vars(self, path):
        if path != self.fw_vars.filePath():
            self.fw_vars.setFilePath(path)

    def _load_names(self, *_):
        try:
            ds, names = rio.open_vars(self.fw_vars.filePath())
        except Exception:
            return
        default = [n for n in names if n.startswith("S2_") and
                   (n.endswith("_NDVI") or "_FEN_" in n)] or names
        self.vlist.set_names(names, lambda n: n in default)

    def run(self):
        path = self.fw_vars.filePath()
        sel = self.vlist.checked()
        if not path or not sel:
            QMessageBox.warning(self, "EloteSat", tr("cl.err"))
            return
        k, n, seed = self.sp_k.value(), self.sp_n.value(), self.sp_seed.value()

        def fn(feedback):
            return cluster.run(path, sel, k=k, sample_n=n, seed=seed,
                               feedback=feedback,
                               cancel_check=lambda: self.task and
                               self.task.isCanceled())

        self.task = FunctionTask("EloteSat: grupos", fn)
        self.task.message.connect(self.log.appendPlainText)
        self.task.taskCompleted.connect(self._done)
        self.task.taskTerminated.connect(self._done)
        self.btn.setEnabled(False)
        QgsApplication.taskManager().addTask(self.task)

    def _done(self):
        t = self.task
        self.task = None
        self.btn.setEnabled(True)
        if t.error or not t.result:
            self.log.appendPlainText(tr("error", t.error or tr("cancelled")))
            return
        self.result = r = t.result
        add_raster(r["tif"], "grupos k=%d" % len(r["npx"]))
        names = r["names"]

        def col(name):
            return names.index(name) if name in names else None

        pre = "S2" if any(n.startswith("S2_") for n in names) else "LS"
        c_max, c_dur, c_upm = (col(pre + "_FEN_NDVImax"),
                               col(pre + "_FEN_DUR50"),
                               col(pre + "_FEN_DIASsubemax"))
        self.table.setRowCount(len(r["npx"]))
        for j in range(len(r["npx"])):
            vals = ["G%d" % (j + 1), "%.2f" % r["km2"][j]]
            for c in (c_max, c_dur, c_upm):
                v = r["means"][j][c] if c is not None else np.nan
                vals.append("" if not np.isfinite(v) else "%.2f" % v
                            if c == c_max else "%.0f" % v)
            vals.append(self._ref_text(r.get("ref"), j))
            for i, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if i == 0:
                    it.setBackground(QColor(cluster.CLUSTER_COLORS[
                        j % len(cluster.CLUSTER_COLORS)]))
                    it.setForeground(QColor("white" if j in (4, 5, 7)
                                            else "black"))
                self.table.setItem(j, i, it)
        self.log.appendPlainText(tr("cl.done", r["tif"], r["nodata_px"]))
        self._plot()

    @staticmethod
    def _ref_text(ref, j):
        """Dominant crop-reference code among the group's pixels with a
        curve, with its share. Interpretation only."""
        if ref is None:
            return ""
        row = ref[j]
        with_curve = row[1:].sum()
        if not with_curve:
            return tr("ref.k0")
        k = 1 + int(np.argmax(row[1:]))
        return "%s %.0f %%" % (tr("ref.k%d" % k), 100.0 * row[k] / with_curve)

    def _plot(self, *_):
        r = self.result
        if not r:
            self.chart.set_data([], [], empty_text=tr("cl.empty"))
            return
        pre, var = self.cb_sensor.currentText(), self.cb_var.currentText()
        series, cats = [], []
        for j in range(len(r["npx"])):
            cats, vals = stage_series(r["names"], r["means"][j], pre, var,
                                      self.cb_kind.currentData())
            series.append(("G%d" % (j + 1), cluster.CLUSTER_COLORS[
                j % len(cluster.CLUSTER_COLORS)], vals, None))
        self.chart.set_data(cats, series, title="%s %s" % (pre, var),
                            ylabel=var, empty_text=tr("cl.empty"))
