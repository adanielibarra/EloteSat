"""Tab 1: crop calendar (stages as date windows) and folder reorganizing."""

import json
import os

from qgis.core import QgsApplication, QgsSettings
from qgis.gui import QgsFileWidget
from qgis.PyQt.QtCore import Qt, QDate, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QComboBox,
    QSpinBox, QPushButton, QTableWidget, QTableWidgetItem, QLabel,
    QLineEdit, QMessageBox, QHeaderView, QFileDialog, QPlainTextEdit,
    QTextBrowser, QInputDialog, QScrollArea)

from ..core import phenology
from ..core.i18n import tr
from ..core.task import FunctionTask
from .translatable import Translatable

SETTINGS = "EloteSat/"


class CalendarTab(QWidget, Translatable):
    calendarChanged = pyqtSignal()
    profileChanged = pyqtSignal(str)
    referencesChanged = pyqtSignal()
    siapUpdated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cal = self._load_saved()
        self.task = None
        self._loading = False
        # scrollable: widgets keep their size on small screens
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        lay = QVBoxLayout(inner)

        intro = QLabel()
        intro.setWordWrap(True)
        self._t(intro.setText, "cal.intro")
        lay.addWidget(intro)

        prow = QHBoxLayout()
        self.cb_profile = QComboBox()
        self.cb_profile.setMinimumContentsLength(18)
        self._t(self.cb_profile.setToolTip, "pf.tip")
        prow.addWidget(self._lbl("pf.profile"))
        prow.addWidget(self.cb_profile, 1)
        for key, fn in (("pf.dup", self._dup_profile),
                        ("pf.rename", self._rename_profile),
                        ("pf.del", self._del_profile)):
            b = QPushButton()
            self._t(b.setText, key)
            b.clicked.connect(fn)
            prow.addWidget(b)
        lay.addLayout(prow)
        self.le_note = QLineEdit()
        self._t(self.le_note.setPlaceholderText, "pf.note")
        self.le_note.editingFinished.connect(self._note_edited)
        lay.addWidget(self.le_note)

        top = QHBoxLayout()
        self.cb_cycle = QComboBox()
        for c in self.cal:
            self.cb_cycle.addItem(c, c)
        self.le_label = QLineEdit()
        self.sp_year = QSpinBox()
        self.sp_year.setRange(2013, 2100)
        self.sp_year.setValue(QDate.currentDate().year())
        top.addWidget(self._lbl("cal.cycle"))
        top.addWidget(self.cb_cycle)
        top.addWidget(self.le_label, 1)
        top.addWidget(self._lbl("cal.year"))
        top.addWidget(self.sp_year)
        lay.addLayout(top)

        self.table = QTableWidget(0, 4)
        self._set_headers()
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(170)
        lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        for key, fn in (("cal.add", self._add_row), ("cal.del", self._del_row),
                        ("cal.reset", self._reset),
                        ("cal.import", self._import),
                        ("cal.export", self._export)):
            b = QPushButton()
            self._t(b.setText, key)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)

        self.lbl_preview = QLabel()
        self.lbl_preview.setWordWrap(True)
        self.lbl_preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.lbl_preview)

        gr = QGroupBox()
        self._t(gr.setTitle, "pf.refs")
        vr = QVBoxLayout(gr)
        self.ref_table = QTableWidget(len(phenology.CROPS), 4)
        self._ref_headers()
        self.ref_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        two_rows = (self.ref_table.horizontalHeader().sizeHint().height() +
                    2 * self.ref_table.verticalHeader()
                    .defaultSectionSize() + 6)
        self.ref_table.setFixedHeight(two_rows)
        self.ref_table.itemChanged.connect(self._refs_edited)
        vr.addWidget(self.ref_table)
        self.lbl_refs = QLabel()
        self.lbl_refs.setWordWrap(True)
        self._t(self.lbl_refs.setText, "pf.refs.note")
        vr.addWidget(self.lbl_refs)
        # offsets sowing -> green-up / peak (ASSUMED), per cycle and crop
        go = QHBoxLayout()
        self.off_table = QTableWidget(len(phenology.CROPS), 4)
        self._off_headers()
        self.off_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.off_table.setFixedHeight(two_rows)
        self.off_table.itemChanged.connect(self._offsets_edited)
        go.addWidget(self.off_table, 1)
        self.btn_fill = QPushButton()
        self._t(self.btn_fill.setText, "sp.fill")
        self._t(self.btn_fill.setToolTip, "sp.fill.tip")
        self.btn_fill.clicked.connect(self._fill_refs_from_siap)
        go.addWidget(self.btn_fill)
        vr.addLayout(go)
        self.lbl_off = QLabel()
        self.lbl_off.setWordWrap(True)
        self._t(self.lbl_off.setText, "sp.off.note")
        vr.addWidget(self.lbl_off)
        lay.addWidget(gr)

        # SIAP
        gs = QGroupBox()
        self._t(gs.setTitle, "sp.group")
        vs = QVBoxLayout(gs)
        rs = QHBoxLayout()
        self.btn_siap = QPushButton()
        self._t(self.btn_siap.setText, "sp.import")
        self._t(self.btn_siap.setToolTip, "sp.import.tip")
        self.btn_siap.clicked.connect(self._import_siap)
        self.btn_upd = QPushButton()
        self._t(self.btn_upd.setText, "sp.update")
        self._t(self.btn_upd.setToolTip, "sp.update.tip")
        self.btn_upd.clicked.connect(self._update_siap)
        rs.addWidget(self.btn_siap)
        rs.addWidget(self.btn_upd)
        rs.addStretch()
        vs.addLayout(rs)
        self.siap_info = QTextBrowser()
        self.siap_info.setMinimumHeight(110)
        self.siap_info.setMaximumHeight(160)
        vs.addWidget(self.siap_info)
        lay.addWidget(gs)

        g = QGroupBox()
        self._t(g.setTitle, "cal.reorg.group")
        f = QFormLayout(g)
        note = self._lbl("cal.reorg.note")
        note.setWordWrap(True)
        f.addRow(note)
        self.fw_dir = QgsFileWidget()
        self.fw_dir.setStorageMode(QgsFileWidget.GetDirectory)
        f.addRow(self._lbl("cal.reorg.dir"), self.fw_dir)
        self.btn_reorg = QPushButton()
        self._t(self.btn_reorg.setText, "cal.reorg.run")
        self.btn_reorg.clicked.connect(self._reorganize)
        f.addRow(self.btn_reorg)
        lay.addWidget(g)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(80)
        self.log.setMaximumHeight(120)
        lay.addWidget(self.log)

        self.cb_profile.currentIndexChanged.connect(
            lambda: self.set_profile(self.cb_profile.currentData()))
        self.cb_cycle.currentIndexChanged.connect(self._show_cycle)
        self.sp_year.valueChanged.connect(self._preview)
        self.table.itemChanged.connect(self._edited)
        self.le_label.editingFinished.connect(self._edited)
        self._refresh_profile_widgets()

    # ---------- helpers
    def _lbl(self, key):
        lab = QLabel()
        self._t(lab.setText, key)
        return lab

    def _set_headers(self):
        self.table.setHorizontalHeaderLabels(
            [tr("cal.col.stage"), tr("cal.col.start"), tr("cal.col.end"),
             tr("cal.col.origin")])

    def _ref_headers(self):
        self.ref_table.setHorizontalHeaderLabels(
            [tr("pf.col.up0"), tr("pf.col.up1"), tr("pf.col.pk0"),
             tr("pf.col.pk1")])
        self.ref_table.setVerticalHeaderLabels(
            [tr("cls." + c) for c in phenology.CROPS])

    def _off_headers(self):
        self.off_table.setHorizontalHeaderLabels(
            [tr("sp.off.up0"), tr("sp.off.up1"), tr("sp.off.pk0"),
             tr("sp.off.pk1")])
        self.off_table.setVerticalHeaderLabels(
            [tr("cls." + c) for c in phenology.CROPS])

    def _retranslate_extra(self):
        self._set_headers()
        self._ref_headers()
        self._off_headers()
        self._show_siap_info()
        self._preview()

    def _load_saved(self):
        """Profiles from the settings. A calendar saved by 0.1/0.2 (one
        calendar, no profiles) becomes the profile 'mi_calendario'."""
        st = QgsSettings()
        profiles = None
        raw = st.value(SETTINGS + "profiles", "")
        if raw:
            try:
                profiles = json.loads(raw)
                phenology.validate_profiles(profiles)
            except Exception:
                profiles = None
        if profiles is None:
            profiles = phenology.default_profiles()
            old = st.value(SETTINGS + "calendar", "")
            if old:
                try:
                    cal = json.loads(old)
                    phenology.validate(cal)
                    profiles["mi_calendario"] = phenology.new_profile(cal)
                except Exception:
                    pass
        self.profiles = profiles
        cur = st.value(SETTINGS + "profile", "")
        self.profile = cur if cur in profiles else next(iter(profiles))
        return self.profiles[self.profile]["cycles"]

    def _save(self):
        self.profiles[self.profile]["cycles"] = phenology.copy_calendar(
            self.cal)
        st = QgsSettings()
        st.setValue(SETTINGS + "profiles",
                    json.dumps(self.profiles, ensure_ascii=False))
        st.setValue(SETTINGS + "profile", self.profile)

    def references(self):
        return json.loads(json.dumps(
            self.profiles[self.profile].get("references") or
            phenology.empty_references()))

    def set_profile(self, name):
        if name not in self.profiles or name == self.profile:
            return
        self.profile = name
        self.cal = phenology.copy_calendar(self.profiles[name]["cycles"])
        self._refresh_profile_widgets()
        self._save()
        self.profileChanged.emit(name)
        self.calendarChanged.emit()

    def _refresh_profile_widgets(self):
        self.cb_profile.blockSignals(True)
        self.cb_profile.clear()
        for n in self.profiles:
            self.cb_profile.addItem(n, n)
        self.cb_profile.setCurrentIndex(self.cb_profile.findData(
            self.profile))
        self.cb_profile.blockSignals(False)
        self._loading = True
        self.le_note.setText(self.profiles[self.profile].get("note", ""))
        self._loading = False
        cur = self.cycle()
        self.cb_cycle.blockSignals(True)
        self.cb_cycle.clear()
        for c in self.cal:
            self.cb_cycle.addItem(c, c)
        i = self.cb_cycle.findData(cur)
        self.cb_cycle.setCurrentIndex(max(i, 0))
        self.cb_cycle.blockSignals(False)
        self._show_cycle()
        self._show_refs()

    # ---------- profile buttons
    def _ask_name(self, key, default=""):
        from qgis.PyQt.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "EloteSat", tr(key),
                                        text=default)
        name = (name or "").strip()
        if not ok or not name:
            return None
        if name in self.profiles:
            QMessageBox.warning(self, "EloteSat", tr("pf.exists", name))
            return None
        return name

    def _dup_profile(self):
        name = self._ask_name("pf.new.ask", self.profile + "_copia")
        if name:
            self.profiles[name] = json.loads(json.dumps(
                self.profiles[self.profile]))
            self.set_profile(name)

    def _rename_profile(self):
        name = self._ask_name("pf.rename.ask", self.profile)
        if not name:
            return
        items = [(name if k == self.profile else k, v)
                 for k, v in self.profiles.items()]
        self.profiles = dict(items)
        self.profile = name
        self._save()
        self._refresh_profile_widgets()
        self.profileChanged.emit(name)

    def _del_profile(self):
        if len(self.profiles) < 2:
            QMessageBox.warning(self, "EloteSat", tr("pf.last"))
            return
        if QMessageBox.question(self, "EloteSat", tr(
                "pf.del.ask", self.profile)) != QMessageBox.Yes:
            return
        del self.profiles[self.profile]
        self.profile = next(iter(self.profiles))
        self.cal = phenology.copy_calendar(
            self.profiles[self.profile]["cycles"])
        self._save()
        self._refresh_profile_widgets()
        self.profileChanged.emit(self.profile)
        self.calendarChanged.emit()

    def _note_edited(self):
        if self._loading:
            return
        self.profiles[self.profile]["note"] = self.le_note.text().strip()
        self._save()

    # ---------- crop references (interpretation only)
    def _show_refs(self):
        self._loading = True
        refs = phenology.refs_for_cycle(self.references(), self.cycle())
        for r, crop in enumerate(phenology.CROPS):
            vals = (refs.get(crop, {}).get("arranque", ["", ""]) +
                    refs.get(crop, {}).get("maximo", ["", ""]))
            for c, v in enumerate(vals):
                self.ref_table.setItem(r, c, QTableWidgetItem(v))
        self._loading = False
        self._show_offsets()
        self._show_siap_info()

    def _refs_edited(self, *_):
        if self._loading:
            return
        refs = {}
        for r, crop in enumerate(phenology.CROPS):
            v = [(self.ref_table.item(r, c).text().strip()
                  if self.ref_table.item(r, c) else "") for c in range(4)]
            refs[crop] = {"arranque": v[:2], "maximo": v[2:]}
        # references are kept per cycle (0.3.0 stored one set for all)
        allr = self.references()
        if not allr or any(k in phenology.CROPS for k in allr):
            allr = {c: json.loads(json.dumps(allr)) for c in self.cal}
        allr[self.cycle()] = refs
        refs = allr
        prof = dict(self.profiles[self.profile], references=refs)
        try:
            phenology.validate_profile(prof)
        except phenology.CalendarError as e:
            self.lbl_refs.setText("<span style='color:#D55E00'>%s</span>"
                                  % tr("cal.invalid", e))
            return
        self.profiles[self.profile]["references"] = refs
        self._save()
        self.lbl_refs.setText(tr("pf.refs.note"))
        self.referencesChanged.emit()

    # ---------- offsets and SIAP
    def _offsets(self):
        return json.loads(json.dumps(
            (self.profiles[self.profile].get("offsets") or {}).get(
                self.cycle()) or {}))

    def _show_offsets(self):
        if not hasattr(self, "off_table"):
            return
        self._loading = True
        off = self._offsets()
        for r, crop in enumerate(phenology.CROPS):
            v = ((off.get(crop) or {}).get("arranque") or ["", ""]) + \
                ((off.get(crop) or {}).get("maximo") or ["", ""])
            for c, x in enumerate(v):
                self.off_table.setItem(r, c, QTableWidgetItem(str(x)))
        self._loading = False
        self.btn_fill.setEnabled(bool(self.profiles[self.profile].get(
            "siap")))

    def _offsets_edited(self, *_):
        if self._loading:
            return
        off = {}
        try:
            for r, crop in enumerate(phenology.CROPS):
                v = []
                for c in range(4):
                    it = self.off_table.item(r, c)
                    t = it.text().strip() if it else ""
                    v.append(int(t) if t else "")
                off[crop] = {"arranque": v[:2], "maximo": v[2:]}
            allo = dict(self.profiles[self.profile].get("offsets") or {})
            allo[self.cycle()] = off
            prof = dict(self.profiles[self.profile], offsets=allo)
            phenology.validate_profile(prof)
        except (ValueError, phenology.CalendarError) as e:
            self.lbl_off.setText("<span style='color:#D55E00'>%s</span>"
                                 % tr("cal.invalid", e))
            return
        self.profiles[self.profile]["offsets"] = allo
        self._save()
        self.lbl_off.setText(tr("sp.off.note"))

    def _fill_refs_from_siap(self):
        prof = self.profiles[self.profile]
        try:
            refs, notes = phenology.references_from_siap(
                prof, self.cycle(), self._offsets())
        except phenology.CalendarError as e:
            QMessageBox.warning(self, "EloteSat", str(e))
            return
        allr = self.references()
        if not allr or any(k in phenology.CROPS for k in allr):
            allr = {c: json.loads(json.dumps(allr)) for c in self.cal}
        allr[self.cycle()] = refs
        prof["references"] = allr
        orig = prof.setdefault("references_origin", {})
        orig[self.cycle()] = tr("sp.fill.origin", json.dumps(
            self._offsets(), ensure_ascii=False))
        phenology.validate_profile(prof)
        self._save()
        self._show_refs()
        self.lbl_refs.setText(tr("sp.fill.done", "; ".join(notes) or "-"))
        self.referencesChanged.emit()

    def _show_siap_info(self):
        if not hasattr(self, "siap_info"):
            return
        meta = self.profiles[self.profile].get("siap")
        if not meta:
            self.siap_info.setHtml(tr("sp.noinfo"))
            return
        c = self.cycle()
        cm = (meta.get("ciclos") or {}).get(c)
        h = ["<b>%s</b> (%s), %s. %s" % (meta.get("municipio"),
                                        meta.get("cvegeo"),
                                        meta.get("modalidad"),
                                        " + ".join(meta.get("cultivos")))]
        if cm:
            f = cm["fechas"]
            h.append(tr("sp.info.dates", c, *[f.get(k, "-") for k in (
                "S10", "S50", "S90", "H50", "H90")]) +
                " " + tr("sp.info.years", ", ".join(
                    "%s: %s" % (k, "/".join(map(str, v)))
                    for k, v in cm["anios"].items())) +
                " " + tr("sp.info.area", cm["sembrada_mediana_ha"]))
            for crop, d in (cm.get("por_cultivo") or {}).items():
                h.append("%s: %s" % (crop, ", ".join(
                    "%s %s" % (k, v) for k, v in d.items()
                    if k != "anios")))
        else:
            h.append(tr("sp.info.nocycle", c))
        sup = meta.get("supuestos") or {}
        h.append(tr("sp.info.assumed", sup.get("emergencia_dias"),
                    sup.get("madurez_dias")))
        av = [a for a in meta.get("avisos") or [] if a.startswith(c)]
        if av:
            h.append("<span style='color:#D55E00'>%s</span>" %
                     "<br>".join(av))
        self.siap_info.setHtml("<br>".join(h))

    def _install_siap_profiles(self, profiles, report, extra_note=""):
        existing = [n for n in self.profiles if n.startswith("siap_")]
        if existing and QMessageBox.question(
                self, "EloteSat", tr("sp.replace", len(existing))) != \
                QMessageBox.Yes:
            return
        for n in existing:
            self.profiles.pop(n, None)
        if not self.profiles:
            self.profiles.update(phenology.default_profiles())
        self.profiles.update(profiles)
        if self.profile not in self.profiles:
            self.profile = next(iter(self.profiles))
            self.cal = phenology.copy_calendar(
                self.profiles[self.profile]["cycles"])
        self._save()
        self._refresh_profile_widgets()
        self.profileChanged.emit(self.profile)
        ok = sum(1 for r in report if r[3].startswith("ok"))
        self.log.appendPlainText(tr("sp.done", len(profiles), ok,
                                    len(report) - ok) + extra_note)
        for r in report:
            if not r[3].startswith("ok"):
                self.log.appendPlainText("  %s %s %s: %s" % r)

    def _import_siap(self):
        from ..core import siap
        extra = siap.downloaded_csvs()
        try:
            profiles, report = siap.import_file(None, siap.zones_data(),
                                                extra=extra)
        except Exception as e:
            QMessageBox.warning(self, "EloteSat", str(e))
            return
        self._install_siap_profiles(
            profiles, report, (" " + tr("sp.extra", len(extra)))
            if extra else "")

    def _update_siap(self):
        from ..core import siap, siap_download
        txt, ok = QInputDialog.getText(
            self, "EloteSat", tr("sp.years.ask"),
            text=str(QDate.currentDate().year()))
        if not ok:
            return
        try:
            years = sorted({int(t) for t in txt.replace(",", " ").split()})
        except ValueError:
            QMessageBox.warning(self, "EloteSat", tr("sp.years.bad"))
            return
        folder = siap.profile_dir()
        if QMessageBox.question(self, "EloteSat", tr(
                "sp.vpn", len(siap_download.plan(years)) * 4)) != \
                QMessageBox.Yes:
            return
        import time
        out = os.path.join(folder, "siap_%s_%s.csv" % (
            "_".join(map(str, years)), time.strftime("%Y%m%d_%H%M%S")))

        def fn(feedback):
            n, req, err = siap_download.download(
                years, out, raw_dir=os.path.join(folder, "siap_crudos"),
                feedback=feedback,
                cancel_check=lambda: self.task and self.task.isCanceled())
            bad = siap.unmatched_names(out)
            return n, req, err, bad

        self.task = FunctionTask("EloteSat: SIAP", fn)
        self.task.message.connect(self.log.appendPlainText)
        self.task.taskCompleted.connect(lambda: self._siap_done(out))
        self.task.taskTerminated.connect(lambda: self._siap_done(out))
        self.btn_upd.setEnabled(False)
        QgsApplication.taskManager().addTask(self.task)

    def _siap_done(self, out):
        t = self.task
        self.task = None
        self.btn_upd.setEnabled(True)
        if t.error or not t.result:
            self.log.appendPlainText(tr("error", t.error or tr("cancelled")))
            return
        n, req, err, bad = t.result
        self.log.appendPlainText(tr("sp.dl.done", n, req, len(err), out))
        for e in err[:10]:
            self.log.appendPlainText("  " + e)
        if bad:
            self.log.appendPlainText(tr("sp.unmatched", ", ".join(bad)))
        if n:
            self._import_siap()
            self.siapUpdated.emit()
        elif os.path.exists(out):
            os.remove(out)  # nothing downloaded: do not keep an empty CSV

    def cycle(self):
        return self.cb_cycle.currentData()

    def calendar(self):
        return phenology.copy_calendar(self.cal)

    # ---------- table <-> calendar
    def _show_cycle(self, *_):
        c = self.cycle()
        if c is None:
            return
        self._loading = True
        spec = self.cal[c]
        self.le_label.setText(spec.get("label", ""))
        self.table.setRowCount(len(spec["stages"]))
        orig = spec.get("origin") or []
        for r, st in enumerate(spec["stages"]):
            for col, v in enumerate(st):
                self.table.setItem(r, col, QTableWidgetItem(v))
            it = QTableWidgetItem(orig[r] if r < len(orig) else "")
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(r, 3, it)
        self._loading = False
        self._preview()
        self._show_refs()

    def _read_table(self):
        stages = []
        for r in range(self.table.rowCount()):
            vals = []
            for col in range(3):
                it = self.table.item(r, col)
                vals.append(it.text().strip() if it else "")
            if any(vals):
                stages.append(vals)
        return stages

    def _edited(self, *_):
        if self._loading:
            return
        c = self.cycle()
        new = phenology.copy_calendar(self.cal)
        new[c] = dict(new[c], label=self.le_label.text().strip(),
                      stages=self._read_table())
        phenology.mark_manual(self.cal, new)
        try:
            phenology.validate(new)
        except phenology.CalendarError as e:
            self.lbl_preview.setText(
                "<span style='color:#D55E00'>%s</span>" % tr("cal.invalid",
                                                             e))
            return
        self.cal = new
        self._save()
        self._show_cycle()
        self.calendarChanged.emit()

    def _preview(self, *_):
        c = self.cycle()
        if c is None:
            return
        try:
            w = phenology.windows(self.cal, c, self.sp_year.value())
        except phenology.CalendarError as e:
            self.lbl_preview.setText(tr("cal.invalid", e))
            return
        lines = ["%s: %s → %s" % (n, a.isoformat(), b.isoformat())
                 for n, a, b in w]
        self.lbl_preview.setText(tr("cal.preview", c, self.sp_year.value())
                                 + "<br>" + "<br>".join(lines))

    def apply_calendar(self, cal):
        """Take a validated calendar edited elsewhere (tab 2)."""
        phenology.validate(cal)
        self.cal = phenology.mark_manual(self.cal,
                                         phenology.copy_calendar(cal))
        self._save()
        self._show_cycle()
        self.calendarChanged.emit()

    def _add_row(self):
        self._loading = True
        r = self.table.rowCount()
        self.table.insertRow(r)
        for col, v in enumerate(("%02d_etapa" % r, "", "")):
            self.table.setItem(r, col, QTableWidgetItem(v))
        self._loading = False

    def _del_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            self._edited()

    def _reset(self):
        if QMessageBox.question(self, "EloteSat", tr("cal.reset.ask")) != \
                QMessageBox.Yes:
            return
        self.cal = phenology.copy_calendar()
        self._save()
        self._refresh_profile_widgets()
        self.calendarChanged.emit()

    def _import(self):
        """A profile file (from Export) or a plain calendar.json of a
        downloaded cycle: either becomes a new profile."""
        import os
        p, _ = QFileDialog.getOpenFileName(self, "EloteSat", "",
                                           "JSON (*.json)")
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as f:
                js = json.load(f)
            if "cycles" in js:
                prof = phenology.new_profile(js["cycles"], js.get("note", ""),
                                             js.get("references"))
                name = js.get("name") or os.path.splitext(
                    os.path.basename(p))[0]
            else:
                prof = phenology.new_profile(js)
                name = os.path.splitext(os.path.basename(p))[0]
            phenology.validate_profile(prof)
        except Exception as e:
            QMessageBox.warning(self, "EloteSat", tr("cal.invalid", e))
            return
        base, k = name, 2
        while name in self.profiles:
            name = "%s_%d" % (base, k)
            k += 1
        self.profiles[name] = prof
        self.set_profile(name)

    def _export(self):
        p, _ = QFileDialog.getSaveFileName(
            self, "EloteSat", "perfil_%s.json" % self.profile, "JSON (*.json)")
        if p:
            js = dict(self.profiles[self.profile], name=self.profile)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(js, f, ensure_ascii=False, indent=2)

    # ---------- reorganize
    def _reorganize(self):
        out = self.fw_dir.filePath()
        c, y = self.cycle(), self.sp_year.value()
        if not out:
            QMessageBox.warning(self, "EloteSat", tr("err.nodir"))
            return
        cal = self.calendar()

        def fn(feedback):
            return phenology.reorganize(out, cal, c, y, feedback)

        self.task = FunctionTask("EloteSat: reorganizar", fn)
        self.task.message.connect(self.log.appendPlainText)
        self.task.taskCompleted.connect(self._reorg_done)
        self.task.taskTerminated.connect(self._reorg_done)
        self.btn_reorg.setEnabled(False)
        QgsApplication.taskManager().addTask(self.task)

    def _reorg_done(self):
        t = self.task
        self.btn_reorg.setEnabled(True)
        if t.error:
            self.log.appendPlainText(tr("error", t.error))
        elif t.result:
            moved, kept, problems = t.result
            self.log.appendPlainText(tr("cal.reorg.done", moved, kept,
                                        len(problems)))
            for p in problems:
                self.log.appendPlainText("  " + p)
        self.task = None
