"""Tab 6: Random Forest (hierarchical and/or flat), grouped validation,
map and report."""

import os

import numpy as np
from qgis.core import QgsApplication
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QSpinBox,
    QPushButton, QLabel, QComboBox, QCheckBox, QMessageBox, QSplitter,
    QTextBrowser, QTableWidget, QTableWidgetItem, QHeaderView,
    QPlainTextEdit)

from ..core import classify as clf
from ..core import rasterio_util as rio
from ..core.samples import CLASSES
from ..core.i18n import tr
from ..core.task import FunctionTask
from .common import VarList, add_raster
from .translatable import Translatable


class ClassifyTab(QWidget, Translatable):
    def __init__(self, samples_tab, parent=None):
        super().__init__(parent)
        self.stab = samples_tab
        self.task = None
        lay = QVBoxLayout(self)
        note = self._lbl("cf.intro")
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
        self.lbl_samples = QLabel("")
        self.lbl_samples.setWordWrap(True)
        f.addRow(self._lbl("cf.samples"), self.lbl_samples)
        modes = QHBoxLayout()
        self.chk_hier, self.chk_flat = QCheckBox(), QCheckBox()
        self._t(self.chk_hier.setText, "cf.hier")
        self._t(self.chk_flat.setText, "cf.flat")
        self._t(self.chk_hier.setToolTip, "cf.hier.tip")
        for c in (self.chk_hier, self.chk_flat):
            c.setChecked(True)
            modes.addWidget(c)
        f.addRow(self._lbl("cf.modes"), modes)
        self.cb_engine = QComboBox()
        self._fill_engine()
        f.addRow(self._lbl("cf.engine"), self.cb_engine)
        grid = QHBoxLayout()
        self.sp_trees = self._spin(10, 2000, 200)
        self.sp_k = self._spin(2, 10, 5)
        self.sp_cap = self._spin(0, 1000000, 5000)
        self._t(self.sp_cap.setToolTip, "cf.cap.tip")
        grid.addWidget(self._lbl("cf.trees"))
        grid.addWidget(self.sp_trees)
        grid.addWidget(self._lbl("cf.k"))
        grid.addWidget(self.sp_k)
        grid.addWidget(self._lbl("cf.cap"))
        grid.addWidget(self.sp_cap)
        f.addRow(grid)
        g2 = QHBoxLayout()
        self.chk_imp = QCheckBox()
        self._t(self.chk_imp.setText, "cf.imp")
        self._t(self.chk_imp.setToolTip, "cf.imp.tip")
        self.chk_imp.setChecked(True)
        self.chk_maj = QCheckBox()
        self._t(self.chk_maj.setText, "cf.maj")
        self.sp_valid = self._spin(10, 100, 50)
        self.sp_valid.setSuffix(" %")
        self._t(self.sp_valid.setToolTip, "cf.valid.tip")
        g2.addWidget(self.chk_imp)
        g2.addWidget(self.chk_maj)
        g2.addWidget(self._lbl("cf.valid"))
        g2.addWidget(self.sp_valid)
        f.addRow(g2)
        self.sp_seed = self._spin(0, 99999, 0)
        f.addRow(self._lbl("seed"), self.sp_seed)
        ll.addLayout(f)
        ll.addWidget(self._lbl("cf.pick"))
        self.vlist = VarList()
        ll.addWidget(self.vlist, 1)
        row = QHBoxLayout()
        self.btn = QPushButton()
        self._t(self.btn.setText, "cf.run")
        self.btn.clicked.connect(self.run)
        self.btn_cancel = QPushButton()
        self._t(self.btn_cancel.setText, "cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(lambda: self.task and
                                        self.task.cancel())
        row.addStretch()
        row.addWidget(self.btn)
        row.addWidget(self.btn_cancel)
        ll.addLayout(row)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        self.report = QTextBrowser()
        rl.addWidget(self.report, 3)
        self.imp_table = QTableWidget(0, 3)
        self.imp_table.verticalHeader().setVisible(False)
        self.imp_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self._imp_headers()
        rl.addWidget(self.imp_table, 2)
        split.addWidget(right)
        split.setSizes([430, 610])
        lay.addWidget(split, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(90)
        lay.addWidget(self.log)
        samples_tab.samplesReady.connect(self._samples_changed)
        samples_tab.useVariables.connect(self._use_vars)
        self._samples_changed()

    def _lbl(self, key):
        lab = QLabel()
        self._t(lab.setText, key)
        return lab

    def _spin(self, lo, hi, v):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(v)
        return s

    def _fill_engine(self):
        i = max(self.cb_engine.currentIndex(), 0)
        self.cb_engine.clear()
        ok = clf.sklearn_available()
        self.cb_engine.addItem(tr("cf.eng.auto", "scikit-learn" if ok
                                  else "numpy"), "auto")
        self.cb_engine.addItem("scikit-learn" + ("" if ok else
                                                 tr("cf.eng.missing")),
                               "sklearn")
        self.cb_engine.addItem(tr("cf.eng.numpy"), "numpy")
        if not ok:
            self.cb_engine.model().item(1).setEnabled(False)
        self.cb_engine.setCurrentIndex(i)

    def _imp_headers(self):
        self.imp_table.setHorizontalHeaderLabels(
            [tr("sm.col.var"), tr("cf.imp1"), tr("cf.imp2")])

    def _retranslate_extra(self):
        self._fill_engine()
        self._imp_headers()
        self.vlist.retranslate()
        self._samples_changed()

    def set_vars(self, path):
        if path != self.fw_vars.filePath():
            self.fw_vars.setFilePath(path)

    def _load_names(self, *_):
        try:
            _, names = rio.open_vars(self.fw_vars.filePath())
        except Exception:
            return
        self.vlist.set_names(names)

    def _use_vars(self, names):
        if names:
            self.vlist.set_checked(names)

    def _samples_changed(self):
        s = self.stab.samples
        if s is None:
            self.lbl_samples.setText(tr("cf.nosamples"))
            return
        summ = s.summary()
        self.lbl_samples.setText(tr("sm.summary", *[
            v for c in CLASSES for v in summ[c]]))

    # ------------------------------------------------------------ run
    def run(self):
        s = self.stab.samples
        vpath = self.fw_vars.filePath()
        names = self.vlist.checked()
        modes = [m for m, c in (("hier", self.chk_hier),
                                ("flat", self.chk_flat)) if c.isChecked()]
        if s is None or not vpath or not names or not modes:
            QMessageBox.warning(self, "EloteSat", tr("cf.err"))
            return
        missing = [n for n in names if n not in s.names]
        if missing:
            QMessageBox.warning(self, "EloteSat", tr("cf.err.vars",
                                                    ", ".join(missing[:5])))
            return
        opts = dict(engine=self.cb_engine.currentData(),
                    n_trees=self.sp_trees.value(),
                    max_per_class=self.sp_cap.value() or None,
                    seed=self.sp_seed.value())
        k, imp = self.sp_k.value(), self.chk_imp.isChecked()
        maj, minv = self.chk_maj.isChecked(), self.sp_valid.value() / 100.0
        out_dir = os.path.join(os.path.dirname(os.path.dirname(vpath)),
                               "clasificacion")

        def fn(feedback):
            cancel = lambda: self.task and self.task.isCanceled()  # noqa
            res = {}
            for mode in modes:
                tag = "jerarquica" if mode == "hier" else "plana"
                feedback("== %s ==" % tag)
                cv = clf.cross_validate(s, names, mode, k=k,
                                        importance=imp, feedback=feedback,
                                        cancel_check=cancel, **opts)
                model = clf.fit_final(s, names, mode, **opts)
                mp = clf.predict_map(model, vpath, names, out_dir, tag,
                                     min_valid=minv, majority=maj,
                                     feedback=feedback, cancel_check=cancel)
                params = dict(opts, mode=mode, k=k, variables=names,
                              min_valid=minv, majority3x3=maj,
                              engine_used=getattr(model, "engine_used", ""),
                              samples=s.summary())
                mp["siap"] = self._compare_siap(vpath, mp["classes"],
                                                out_dir, tag, feedback)
                clf.write_report(out_dir, tag, cv, mp, params)
                res[mode] = (cv, mp)
            return res

        self.task = FunctionTask("EloteSat: clasificación", fn)
        self.task.message.connect(self.log.appendPlainText)
        self.task.taskCompleted.connect(self._done)
        self.task.taskTerminated.connect(self._done)
        self.btn.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        QgsApplication.taskManager().addTask(self.task)

    @staticmethod
    def _compare_siap(vpath, class_tif, out_dir, tag, feedback):
        """Mapped vs SIAP sown area (coherence check). None if the grid
        has no zonas.tif or the cycle has no SIAP data."""
        import json
        from ..core import compare, features, phenology, siap
        ztif = os.path.join(os.path.dirname(vpath), "zonas.tif")
        if not os.path.exists(ztif):
            return None
        try:
            cdir = os.path.dirname(os.path.dirname(vpath))
            cycle, year = features.parse_cycle_dir(cdir)
            calp = os.path.join(cdir, "calendario.json")
            cal = phenology.load_calendar(calp) if os.path.exists(calp) \
                else phenology.copy_calendar()
            sy = siap.siap_year(cycle, cal, year)
            rows = compare.compare(
                class_tif, ztif, cycle, sy,
                out_csv=os.path.join(out_dir, "%s_superficies_siap.csv"
                                     % tag))
            rows = [r for r in rows if r["mapa_total_ha"] > 0 or
                    r["siap_total_ha"] > 0]
            feedback(tr("cf.siap.log", cycle, sy, len(rows)))
            return {"cycle": cycle, "siap_year": sy, "rows": json.loads(
                json.dumps(rows))}
        except Exception as e:
            feedback(tr("cf.siap.fail", e))
            return None

    def _done(self):
        t = self.task
        self.task = None
        self.btn.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if t.error or not t.result:
            self.log.appendPlainText(tr("error", t.error or tr("cancelled")))
            return
        html = []
        for mode, (cv, mp) in t.result.items():
            name = tr("cf.hier") if mode == "hier" else tr("cf.flat")
            add_raster(mp["classes"], "%s: %s" % (tr("cf.map"), name))
            html.append(self._html(name, cv, mp))
        self.report.setHtml("".join(html))
        first = next(iter(t.result.values()))[0]
        self._fill_importance(first)

    def _html(self, name, cv, mp):
        h = ["<h3>%s</h3>" % name]
        if "error" in cv:
            h.append("<p><b>%s</b></p>" % tr("cf.nocv", cv["error"]))
        else:
            h.append("<p>%s</p>" % tr("cf.cvinfo", cv["k"], cv["engine"]))
            for w in cv.get("warnings", []):
                h.append("<p style='color:#D55E00'>%s</p>" % w)
            for level in ("pixel", "field"):
                sc = cv[level]
                h.append("<p><b>%s</b>: OA %.3f, %s %.3f (n = %d)</p>" % (
                    tr("cf.level." + level), sc["oa"], tr("cf.balanced"),
                    sc["balanced"], sc["n"]))
                h.append(self._table(sc["confusion"], CLASSES,
                                     sc["classes"]))
            for step in ("step1", "step2"):
                sc = cv[step]
                h.append("<p><b>%s</b>: OA %.3f</p>" % (
                    tr("cf." + step), sc["oa"]))
                h.append(self._table(sc["confusion"], sc["labels"],
                                     sc["classes"]))
        h.append("<p><b>%s</b> %s</p>" % (tr("cf.area"), ", ".join(
            "%s %.2f km²" % (tr("cls." + c), mp["km2"][c])
            for c in CLASSES)))
        h.append("<p><i>%s</i></p>" % tr("cf.caveat"))
        sp = mp.get("siap")
        if sp and sp.get("rows"):
            h.append("<p><b>%s</b></p>" % tr("cf.siap.title", sp["cycle"],
                                              sp["siap_year"]))
            head = "".join("<th>%s</th>" % tr(k) for k in (
                "cf.siap.mun", "cf.siap.mod", "cf.siap.cov",
                "cf.siap.map", "cf.siap.siap", "cf.siap.ratio"))
            body = []
            for r in sp["rows"][:40]:
                body.append(
                    "<tr><td>%s</td><td>%s</td><td align=right>%.0f %%</td>"
                    "<td align=right>%.0f</td><td align=right>%.0f</td>"
                    "<td align=right>%s</td></tr>" % (
                        r["municipio"], r["modalidad"], r["cobertura_pct"],
                        r["mapa_total_ha"], r["siap_total_ha"],
                        r["cociente"] if r["cociente"] != "" else "-"))
            h.append("<table border=1 cellspacing=0 cellpadding=3><tr>%s"
                     "</tr>%s</table>" % (head, "".join(body)))
            h.append("<p><i>%s</i></p>" % tr("cf.siap.caveat"))
        return "".join(h)

    @staticmethod
    def _table(M, labels, per_class):
        head = "".join("<th>%s</th>" % tr("cls." + c) if c in CLASSES
                       else "<th>%s</th>" % c for c in labels)
        rows = []
        for lab, row in zip(labels, M):
            pc = per_class.get(lab, {})
            rows.append("<tr><th>%s</th>%s<td>%.2f</td><td>%.2f</td></tr>" % (
                tr("cls." + lab) if lab in CLASSES else lab,
                "".join("<td align=right>%d</td>" % v for v in row),
                pc.get("producer", np.nan), pc.get("user", np.nan)))
        return ("<table border=1 cellspacing=0 cellpadding=3><tr>"
                "<th>%s</th>%s<th>%s</th><th>%s</th></tr>%s</table>" % (
                    tr("cf.real"), head, tr("cf.pa"), tr("cf.ua"),
                    "".join(rows)))

    def _fill_importance(self, cv):
        imp = cv.get("importance") or []
        imp = sorted(imp, key=lambda r: -(r["step1"] + r["step2"]))[:40]
        self.imp_table.setRowCount(len(imp))
        for r, row in enumerate(imp):
            for c, v in enumerate((row["var"], "%.4f" % row["step1"],
                                   "%.4f" % row["step2"])):
                self.imp_table.setItem(r, c, QTableWidgetItem(v))
