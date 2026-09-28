"""Widgets shared by the analysis tabs."""

import re

from qgis.core import QgsProject, QgsRasterLayer
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                                 QListWidget, QListWidgetItem, QPushButton,
                                 QLineEdit)

from ..core.i18n import tr


class VarList(QWidget):
    """Checkable list of variable names with quick filters."""

    PRESETS = (
        ("vl.all", lambda n: True),
        ("vl.none", lambda n: False),
        ("vl.indices", lambda n: bool(re.search(
            r"_(NDVI|GCVI|NDMI|NDTI|NDRE|CIre)$", n))),
        ("vl.phen", lambda n: "_FEN_" in n),
        ("vl.rel", lambda n: "_REL" in n),
        ("vl.s2", lambda n: n.startswith("S2_")),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        self.buttons = []
        for key, fn in self.PRESETS:
            b = QPushButton(tr(key))
            b.clicked.connect(lambda _=False, f=fn, k=key: self._apply(f, k))
            self.buttons.append((b, key))
            row.addWidget(b)
        self.le_filter = QLineEdit()
        self.le_filter.setPlaceholderText(tr("vl.filter"))
        self.le_filter.textChanged.connect(self._filter)
        row.addWidget(self.le_filter, 1)
        lay.addLayout(row)
        self.list = QListWidget()
        lay.addWidget(self.list, 1)

    def retranslate(self):
        for b, key in self.buttons:
            b.setText(tr(key))
        self.le_filter.setPlaceholderText(tr("vl.filter"))

    def set_names(self, names, checked=None):
        prev = set(self.checked())
        self.list.clear()
        for n in names:
            it = QListWidgetItem(n)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            on = (n in prev) if prev else (checked(n) if checked else True)
            it.setCheckState(Qt.Checked if on else Qt.Unchecked)
            self.list.addItem(it)

    def names(self):
        return [self.list.item(i).text() for i in range(self.list.count())]

    def checked(self):
        return [self.list.item(i).text() for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]

    def set_checked(self, names):
        s = set(names)
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setCheckState(Qt.Checked if it.text() in s else Qt.Unchecked)

    def _apply(self, fn, key):
        # presets other than all/none add to the current selection
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.isHidden():
                continue
            if key in ("vl.all", "vl.none"):
                it.setCheckState(Qt.Checked if fn(it.text())
                                 else Qt.Unchecked)
            elif fn(it.text()):
                it.setCheckState(Qt.Checked)

    def _filter(self, text):
        t = text.lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(t) and t not in it.text().lower())


def add_raster(path, name, group="EloteSat"):
    lyr = QgsRasterLayer(path, name)  # loads the .qml next to it
    if not lyr.isValid():
        return None
    root = QgsProject.instance().layerTreeRoot()
    g = root.findGroup(group) or root.insertGroup(0, group)
    QgsProject.instance().addMapLayer(lyr, False)
    g.insertLayer(0, lyr)
    return lyr


def stage_series(names, means, sensor_prefix, var, kind="rel"):
    """From per-variable values pick '<S2|LS>_<window>_<var>' in order.
    kind 'rel': windows relative to the curve (REL1..REL4); 'fixed': the
    fixed stage folders. Returns (windows, values)."""
    out = []
    for n, v in zip(names, means):
        m = re.match(r"^%s_(.+)_%s$" % (sensor_prefix, re.escape(var)), n)
        if not m or m.group(1) == "FEN":
            continue
        if (kind == "rel") == m.group(1).startswith("REL"):
            out.append((m.group(1), v))
    out.sort()
    return [o[0] for o in out], [o[1] for o in out]
