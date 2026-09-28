"""Tab 3: variables per stage and phenology metrics on a common grid."""

import json
import os

from qgis.core import QgsApplication, QgsProject, QgsRasterLayer
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QCheckBox,
    QComboBox, QPushButton, QLabel, QPlainTextEdit, QLineEdit, QMessageBox,
    QProgressBar, QGridLayout, QSpinBox)

from ..core import features, phenology
from ..core.sensors import S2, LS
from ..core.i18n import tr
from ..core.task import FunctionTask
from .translatable import Translatable


class FeaturesTab(QWidget, Translatable):
    featuresReady = pyqtSignal(str)   # path of variables.tif

    def __init__(self, parent=None, get_profile=None):
        super().__init__(parent)
        self.task = None
        self.get_profile = get_profile  # () -> (name, references)
        lay = QVBoxLayout(self)
        intro = self._lbl("ft.intro")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        g = QGroupBox()
        self._t(g.setTitle, "ft.input")
        f = QFormLayout(g)
        self.fw_cycle = QgsFileWidget()
        self.fw_cycle.setStorageMode(QgsFileWidget.GetDirectory)
        self._t(self.fw_cycle.setToolTip, "ft.cycle.tip")
        self.fw_cycle.fileChanged.connect(self._inspect)
        f.addRow(self._lbl("ft.cycle"), self.fw_cycle)
        self.lbl_info = QLabel("")
        self.lbl_info.setWordWrap(True)
        f.addRow(self.lbl_info)
        lay.addWidget(g)

        g2 = QGroupBox()
        self._t(g2.setTitle, "ft.opts")
        grid = QGridLayout(g2)
        self.cb_res = QComboBox()
        for r in (10, 20, 30):
            self.cb_res.addItem("%d m" % r, r)
        self.cb_res.setCurrentIndex(1)
        self._t(self.cb_res.setToolTip, "ft.res.tip")
        grid.addWidget(self._lbl("ft.res"), 0, 0)
        grid.addWidget(self.cb_res, 0, 1)
        self.chk_s2, self.chk_ls = QCheckBox(), QCheckBox()
        self._t(self.chk_s2.setText, "sensor.S2")
        self._t(self.chk_ls.setText, "sensor.LANDSAT")
        for c in (self.chk_s2, self.chk_ls):
            c.setChecked(True)
        grid.addWidget(self._lbl("ft.sensors"), 1, 0)
        grid.addWidget(self.chk_s2, 1, 1)
        grid.addWidget(self.chk_ls, 1, 2)
        self.chk_bands = QCheckBox()
        self._t(self.chk_bands.setText, "ft.bands")
        self.chk_bands.setChecked(True)
        self.chk_phen = QCheckBox()
        self._t(self.chk_phen.setText, "ft.phen")
        self._t(self.chk_phen.setToolTip, "ft.phen.tip")
        self.chk_phen.setChecked(True)
        self.chk_abs = QCheckBox()
        self._t(self.chk_abs.setText, "ft.abs")
        self._t(self.chk_abs.setToolTip, "ft.abs.tip")
        grid.addWidget(self.chk_bands, 2, 1)
        grid.addWidget(self.chk_phen, 2, 2, 1, 2)
        grid.addWidget(self.chk_abs, 2, 4, 1, 2)
        grid.addWidget(self._lbl("ft.indices"), 3, 0)
        self.idx_checks = {}
        for i, (name, (formula, _, sens)) in enumerate(
                features.INDICES.items()):
            c = QCheckBox(name)
            c.setChecked(True)
            c.setToolTip("%s  (%s)" % (formula, ", ".join(
                "S2" if s == S2 else "Landsat" for s in sens)))
            self.idx_checks[name] = c
            grid.addWidget(c, 3 + i // 4, 1 + i % 4)
        self.le_scl = QLineEdit(",".join(map(str,
                                             features.DEFAULT_S2_CLEAR)))
        self._t(self.le_scl.setToolTip, "ft.scl.tip")
        grid.addWidget(self._lbl("ft.scl"), 5, 0)
        grid.addWidget(self.le_scl, 5, 1)
        # windows relative to each pixel's curve
        self.chk_rel = QCheckBox()
        self._t(self.chk_rel.setText, "ft.rel")
        self._t(self.chk_rel.setToolTip, "ft.rel.tip")
        self.chk_rel.setChecked(True)
        grid.addWidget(self.chk_rel, 6, 0, 1, 2)
        self.rel_spins = []
        rg = QGridLayout()
        for i, (name, anchor, a, b) in enumerate(features.REL_WINDOWS):
            lab = QLabel("%s  (%s %s)" % (name, tr("ft.rel.anchor"),
                                          anchor))
            s0, s1 = QSpinBox(), QSpinBox()
            for sp, v in ((s0, a), (s1, b)):
                sp.setRange(-120, 200)
                sp.setValue(v)
                sp.setSuffix(" d")
            self.rel_spins.append((name, anchor, s0, s1, lab))
            rg.addWidget(lab, i, 0)
            rg.addWidget(s0, i, 1)
            rg.addWidget(s1, i, 2)
        grid.addLayout(rg, 7, 1, 1, 5)
        self.chk_rel.toggled.connect(
            lambda on: [w.setEnabled(on) for r in self.rel_spins
                        for w in r[2:]])
        # fixed stage folders, off by default
        self.chk_fixed = QCheckBox()
        self._t(self.chk_fixed.setText, "ft.fixed")
        self._t(self.chk_fixed.setToolTip, "ft.fixed.tip")
        grid.addWidget(self.chk_fixed, 8, 0, 1, 2)
        self.stage_box = QHBoxLayout()
        grid.addLayout(self.stage_box, 9, 1, 1, 5)
        self.stage_checks = {}
        self.chk_fixed.toggled.connect(
            lambda on: [c.setEnabled(on) for c in
                        self.stage_checks.values()])
        # crop references (interpretation only)
        self.chk_ref = QCheckBox()
        self._t(self.chk_ref.setText, "ft.ref")
        self._t(self.chk_ref.setToolTip, "ft.ref.tip")
        self.chk_ref.setChecked(True)
        self.lbl_ref = QLabel("")
        self.lbl_ref.setWordWrap(True)
        grid.addWidget(self.chk_ref, 10, 0, 1, 2)
        grid.addWidget(self.lbl_ref, 10, 2, 1, 4)
        lay.addWidget(g2)

        row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.btn = QPushButton()
        self._t(self.btn.setText, "ft.run")
        self.btn.clicked.connect(self.run)
        self.btn_cancel = QPushButton()
        self._t(self.btn_cancel.setText, "cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(lambda: self.task and
                                        self.task.cancel())
        self.chk_add = QCheckBox()
        self._t(self.chk_add.setText, "dl.addmap")
        row.addWidget(self.progress, 1)
        row.addWidget(self.chk_add)
        row.addWidget(self.btn)
        row.addWidget(self.btn_cancel)
        lay.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        lay.addWidget(self.log, 1)

    def _lbl(self, key):
        lab = QLabel()
        self._t(lab.setText, key)
        return lab

    def set_cycle_dir(self, path):
        if path and path != self.fw_cycle.filePath():
            self.fw_cycle.setFilePath(path)

    def _inspect(self, *_):
        cdir = self.fw_cycle.filePath()
        for c in self.stage_checks.values():
            c.setParent(None)
        self.stage_checks = {}
        try:
            obs = features.observations(cdir)
            cycle, year = features.parse_cycle_dir(cdir)
        except Exception as e:
            self.lbl_info.setText(tr("ft.noinfo", e))
            return
        stages = sorted({o[1] for s in obs for o in obs[s]})
        parts = []
        for s in (S2, LS):
            per = {}
            for _, st, _ in obs.get(s, []):
                per[st] = per.get(st, 0) + 1
            parts.append("%s: %s" % (tr("sensor." + s), ", ".join(
                "%s %d" % (k, v) for k, v in sorted(per.items())) or "0"))
        self.lbl_info.setText(tr("ft.info", cycle, year) + "<br>" +
                              "<br>".join(parts))
        for st in stages:
            c = QCheckBox(st)
            c.setChecked(st != phenology.OUT_OF_STAGE)
            c.setEnabled(self.chk_fixed.isChecked())
            self.stage_checks[st] = c
            self.stage_box.addWidget(c)
        self._show_ref_source()

    # crop references: the profile saved with the download, if any
    def _references(self):
        """(profile name, references dict, source) or (None, None, '')."""
        cdir = self.fw_cycle.filePath()
        p = os.path.join(cdir, "perfil.json") if cdir else ""
        if p and os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    js = json.load(f)
                return js.get("name", "?"), js.get("references"), "cycle"
            except Exception:
                pass
        if self.get_profile:
            name, refs = self.get_profile()
            return name, refs, "current"
        return None, None, ""

    def _show_ref_source(self):
        name, refs, src = self._references()
        filled = any(a for spec in (refs or {}).values()
                     for pair in spec.values() for a in pair)
        if not filled:
            self.lbl_ref.setText(tr("ft.ref.none", name or "-"))
        else:
            self.lbl_ref.setText(tr("ft.ref.src." + src, name))

    def run(self):
        cdir = self.fw_cycle.filePath()
        if not cdir or not os.path.exists(os.path.join(cdir,
                                                       "manifest.csv")):
            QMessageBox.warning(self, "EloteSat", tr("ft.err.cycle"))
            return
        sensors = [s for s, c in ((S2, self.chk_s2), (LS, self.chk_ls))
                   if c.isChecked()]
        idx = [k for k, c in self.idx_checks.items() if c.isChecked()]
        stages = [k for k, c in self.stage_checks.items() if c.isChecked()]
        try:
            scl = tuple(int(v) for v in self.le_scl.text().split(",") if
                        v.strip())
        except ValueError:
            QMessageBox.warning(self, "EloteSat", tr("ft.err.scl"))
            return
        if not sensors or (self.chk_fixed.isChecked() and not stages):
            QMessageBox.warning(self, "EloteSat", tr("ft.err.empty"))
            return
        rel_w = []
        for name, anchor, s0, s1, _ in self.rel_spins:
            if s1.value() < s0.value():
                QMessageBox.warning(self, "EloteSat", tr("ft.err.rel", name))
                return
            rel_w.append((name, anchor, s0.value(), s1.value()))
        rel, fixed = self.chk_rel.isChecked(), self.chk_fixed.isChecked()
        if not (rel or fixed or self.chk_phen.isChecked() or
                self.chk_abs.isChecked()):
            QMessageBox.warning(self, "EloteSat", tr("ft.err.empty"))
            return
        refdays = None
        if self.chk_ref.isChecked():
            _, refs, _ = self._references()
            try:
                cycle, year = features.parse_cycle_dir(cdir)
                calp = os.path.join(cdir, "calendario.json")
                cal = phenology.load_calendar(calp) \
                    if os.path.exists(calp) else phenology.copy_calendar()
                refdays = phenology.reference_days(refs or {}, cal, cycle,
                                                   year) or None
            except Exception as e:
                self.log.appendPlainText(tr("error", e))
        kw = dict(res=float(self.cb_res.currentData()), sensors=sensors,
                  stages=stages, indices=idx,
                  bands=self.chk_bands.isChecked(),
                  phen=self.chk_phen.isChecked(),
                  abs_dates=self.chk_abs.isChecked(), rel=rel,
                  rel_windows=tuple(rel_w), fixed=fixed,
                  references=refdays, scl_clear=scl)

        def fn(feedback):
            return features.build(cdir, feedback=feedback,
                                  cancel_check=lambda: self.task and
                                  self.task.isCanceled(), **kw)

        self.task = FunctionTask("EloteSat: variables", fn)
        self.task.message.connect(self.log.appendPlainText)
        self.task.taskCompleted.connect(self._done)
        self.task.taskTerminated.connect(self._done)
        self.btn.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.progress.setVisible(True)
        QgsApplication.taskManager().addTask(self.task)

    def _done(self):
        t = self.task
        self.task = None
        self.btn.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setVisible(False)
        if t.error:
            self.log.appendPlainText(tr("error", t.error))
            return
        if not t.result:
            self.log.appendPlainText(tr("cancelled"))
            return
        path = t.result["path"]
        self.log.appendPlainText(tr("ft.done", len(t.result["vars"]), path))
        rc = t.result.get("reference_counts")
        if rc:
            self.log.appendPlainText(tr("ft.ref.done", *rc[1:6]))
            if self.chk_add.isChecked():
                from .common import add_raster
                add_raster(t.result["reference"], tr("ft.ref.layer"))
        if self.chk_add.isChecked():
            lyr = QgsRasterLayer(path, "variables")
            if lyr.isValid():
                QgsProject.instance().addMapLayer(lyr)
        self.featuresReady.emit(path)
