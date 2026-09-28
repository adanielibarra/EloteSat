"""Last tab: the user manual (PDF shipped in docs/), to save or open."""

import glob
import os
import re
import shutil

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QPushButton,
    QFileDialog, QMessageBox)

from ..core.i18n import tr

DOCS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")


def manual_path():
    """The newest Manual_*.pdf in docs/ (None if there is none)."""
    found = sorted(glob.glob(os.path.join(DOCS, "Manual_*.pdf")))
    return found[-1] if found else None


def plugin_version():
    meta = os.path.join(os.path.dirname(DOCS), "metadata.txt")
    try:
        with open(meta, encoding="utf-8") as f:
            m = re.search(r"^version=(.+)$", f.read(), re.M)
        return m.group(1).strip() if m else "?"
    except OSError:
        return "?"


class HelpTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        self.box = QGroupBox()
        b = QVBoxLayout(self.box)
        self.lb_text = QLabel()
        self.lb_text.setWordWrap(True)
        b.addWidget(self.lb_text)
        row = QHBoxLayout()
        self.bt_save = QPushButton()
        self.bt_open = QPushButton()
        self.bt_save.clicked.connect(self.save_manual)
        self.bt_open.clicked.connect(self.open_manual)
        row.addWidget(self.bt_save)
        row.addWidget(self.bt_open)
        row.addStretch(1)
        b.addLayout(row)
        self.lb_version = QLabel()
        self.lb_version.setStyleSheet("color: gray")
        b.addWidget(self.lb_version)
        lay.addWidget(self.box)
        lay.addStretch(1)
        self.retranslate()

    def retranslate(self):
        self.box.setTitle(tr("help.title"))
        self.lb_text.setText(tr("help.text"))
        self.bt_save.setText(tr("help.download"))
        self.bt_open.setText(tr("help.open"))
        m = manual_path()
        self.lb_version.setText(tr("help.version", plugin_version(),
                                   os.path.basename(m) if m else "—"))
        self.bt_save.setEnabled(bool(m))
        self.bt_open.setEnabled(bool(m))

    def _manual(self):
        m = manual_path()
        if not m:
            QMessageBox.warning(self, tr("tab.help"),
                                tr("help.missing", DOCS))
        return m

    def save_manual(self, target=None):
        """Copy the manual to a path chosen by the user; returns it."""
        m = self._manual()
        if not m:
            return None
        if not target:
            start = os.path.join(os.path.expanduser("~"), os.path.basename(m))
            target, _ = QFileDialog.getSaveFileName(
                self, tr("help.download"), start, "PDF (*.pdf)")
        if not target:
            return None
        if not target.lower().endswith(".pdf"):
            target += ".pdf"
        try:
            shutil.copyfile(m, target)
        except OSError as e:
            QMessageBox.warning(self, tr("tab.help"), tr("help.error", e))
            return None
        QMessageBox.information(self, tr("tab.help"),
                                tr("help.saved", target))
        return target

    def open_manual(self):
        m = self._manual()
        if m:
            QDesktopServices.openUrl(QUrl.fromLocalFile(m))
