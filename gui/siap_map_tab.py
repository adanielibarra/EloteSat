"""Tab 7: maps of the SIAP by municipality, styled, with an optional print
layout (title, legend, scale, north arrow, sources)."""

import datetime as dt
import os

from qgis.core import (
    QgsCategorizedSymbolRenderer, QgsClassificationJenks,
    QgsClassificationQuantile, QgsFeature, QgsField, QgsFillSymbol,
    QgsGraduatedSymbolRenderer, QgsLayoutItemLabel,
    QgsLayoutItemLegend, QgsLayoutItemMap, QgsLayoutItemPicture,
    QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize, QgsPalLayerSettings,
    QgsPrintLayout, QgsProject, QgsRendererCategory, QgsStyle,
    QgsTextBufferSettings, QgsTextFormat, QgsUnitTypes, QgsVectorLayer,
    QgsVectorLayerSimpleLabeling, QgsLayoutExporter)
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QComboBox,
    QSpinBox, QPushButton, QLabel, QCheckBox, QMessageBox, QFileDialog,
    QPlainTextEdit)

from ..core import siap_maps as siap
from ..core.i18n import tr
from .translatable import Translatable

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROUP = "EloteSat · SIAP"
RAMPS = ("YlGn", "YlOrBr", "Greens", "Oranges", "Viridis", "Magma",
         "RdYlGn", "Blues")
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep",
          "oct", "nov", "dic")
MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
             "Oct", "Nov", "Dec")
VAR_UNITS = {"sembrada_ha": "ha", "cosechada_ha": "ha", "siniestrada_ha": "ha",
             "produccion": "t", "rendimiento": "t/ha", "pct_siniestrada": "%"}


class SiapMapTab(QWidget, Translatable):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.layer = None
        lay = QVBoxLayout(self)
        intro = self._lbl("mp.intro")
        intro.setWordWrap(True)
        lay.addWidget(intro)

        g = QGroupBox()
        self._t(g.setTitle, "mp.what")
        f = QFormLayout(g)
        self.cb_cycle = QComboBox()
        for c in siap.CYCLES:
            self.cb_cycle.addItem(c, c)
        self.cb_year = QComboBox()
        self.cb_reg = QComboBox()
        for k in ("both", "riego", "temporal"):
            self.cb_reg.addItem(tr("cs.reg." + k), k)
        self.cb_crop = QComboBox()
        for k in ("both", "maiz", "sorgo"):
            self.cb_crop.addItem(tr("mp.crop." + k), k)
        self.cb_var = QComboBox()
        for v in siap.SUMMARY_VARS:
            self.cb_var.addItem(tr("mp.var." + v), v)
        self.cb_cut = QComboBox()
        f.addRow(self._lbl("dl.cycle"), self.cb_cycle)
        f.addRow(self._lbl("mp.year"), self.cb_year)
        f.addRow(self._lbl("mp.reg"), self.cb_reg)
        f.addRow(self._lbl("mp.crop"), self.cb_crop)
        f.addRow(self._lbl("mp.var"), self.cb_var)
        f.addRow(self._lbl("mp.cut"), self.cb_cut)
        self.lbl_state = QLabel()
        self.lbl_state.setWordWrap(True)
        f.addRow(self.lbl_state)
        lay.addWidget(g)

        g2 = QGroupBox()
        self._t(g2.setTitle, "mp.style")
        f2 = QFormLayout(g2)
        self.cb_method = QComboBox()
        for k in ("jenks", "quantile"):
            self.cb_method.addItem(tr("mp.method." + k), k)
        self.sp_classes = QSpinBox()
        self.sp_classes.setRange(3, 9)
        self.sp_classes.setValue(5)
        self.cb_ramp = QComboBox()
        names = QgsStyle.defaultStyle().colorRampNames()
        for r in RAMPS:
            if r in names:
                self.cb_ramp.addItem(r, r)
        self.chk_labels = QCheckBox()
        self._t(self.chk_labels.setText, "mp.labels")
        self.chk_labels.setChecked(True)
        self.chk_values = QCheckBox()
        self._t(self.chk_values.setText, "mp.values")
        self.chk_values.setChecked(True)
        lrow = QHBoxLayout()
        lrow.addWidget(self.chk_labels)
        lrow.addWidget(self.chk_values)
        lrow.addStretch()
        f2.addRow(self._lbl("mp.method"), self.cb_method)
        f2.addRow(self._lbl("mp.classes"), self.sp_classes)
        f2.addRow(self._lbl("mp.ramp"), self.cb_ramp)
        f2.addRow(lrow)
        lay.addWidget(g2)

        row = QHBoxLayout()
        self.btn_map = QPushButton()
        self._t(self.btn_map.setText, "mp.run")
        self.btn_map.clicked.connect(self.make_map)
        self.btn_layout = QPushButton()
        self._t(self.btn_layout.setText, "mp.layout")
        self._t(self.btn_layout.setToolTip, "mp.layout.tip")
        self.btn_layout.clicked.connect(self.make_layout)
        self.btn_layout.setEnabled(False)
        self.btn_csv = QPushButton()
        self._t(self.btn_csv.setText, "mp.csv")
        self.btn_csv.clicked.connect(self.export_csv)
        self.btn_csv.setEnabled(False)
        row.addStretch()
        row.addWidget(self.btn_map)
        row.addWidget(self.btn_layout)
        row.addWidget(self.btn_csv)
        lay.addLayout(row)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        lay.addWidget(self.log, 1)
        credits = self._lbl("mp.credits")
        credits.setWordWrap(True)
        credits.setOpenExternalLinks(True)
        lay.addWidget(credits)

        self.cb_cycle.currentIndexChanged.connect(
            lambda *_: self._fill_years(reset=True))
        self.cb_year.currentIndexChanged.connect(self._fill_cuts)
        self.cb_var.currentIndexChanged.connect(self._var_changed)
        self.reload()

    # ---------- helpers
    def _lbl(self, key):
        lab = QLabel()
        self._t(lab.setText, key)
        return lab

    def _retranslate_extra(self):
        for cb, pfx in ((self.cb_reg, "cs.reg."), (self.cb_crop, "mp.crop."),
                        (self.cb_var, "mp.var."),
                        (self.cb_method, "mp.method.")):
            for i in range(cb.count()):
                cb.setItemText(i, tr(pfx + cb.itemData(i)))
        self._fill_cuts()

    def reload(self):
        try:
            self.data = siap.Data()
        except Exception as e:
            self.data = None
            self.log.appendPlainText(tr("error", e))
            return
        self._fill_years()

    def _fill_years(self, *_, reset=False):
        if not self.data:
            return
        cur = None if reset else self.cb_year.currentData()
        self.cb_year.blockSignals(True)
        self.cb_year.clear()
        c = self.cb_cycle.currentData()
        for y in reversed(self.data.years(c)):
            ok = all(self.data.cycle_state(c, y))
            self.cb_year.addItem("%d%s" % (y, "" if ok else "  (%s)" %
                                           tr("mp.incomplete")), y)
        i = self.cb_year.findData(cur)
        if i < 0:  # by default the latest complete cycle
            done = self.data.complete_years(c)
            i = self.cb_year.findData(done[-1]) if done else 0
        self.cb_year.setCurrentIndex(max(i, 0))
        self.cb_year.blockSignals(False)
        self._fill_cuts()

    def _fill_cuts(self, *_):
        if not self.data:
            return
        c, y = self.cb_cycle.currentData(), self.cb_year.currentData()
        cur = self.cb_cut.currentData()
        self.cb_cut.clear()
        self.cb_cut.addItem(tr("mp.cut.close"), None)
        if y is None:
            return
        for d in reversed(self.data.cutoffs(c, y)):
            self.cb_cut.addItem(d.isoformat(), d.isoformat())
        i = self.cb_cut.findData(cur)
        self.cb_cut.setCurrentIndex(max(i, 0))
        w = siap.cycle_warning(self.data, c, y)
        self.lbl_state.setText(tr("mp.state." + "_".join(w)) if w else "")

    def _var_changed(self, *_):
        dates = self.cb_var.currentData().startswith("p50")
        self.cb_method.setEnabled(not dates)
        self.sp_classes.setEnabled(not dates)

    def _selection(self):
        c, y = self.cb_cycle.currentData(), self.cb_year.currentData()
        reg, crop = self.cb_reg.currentData(), self.cb_crop.currentData()
        regs = tuple(siap.REGIMES) if reg == "both" else (reg,)
        crops = tuple(siap.CROPS) if crop == "both" else (crop,)
        cut = self.cb_cut.currentData()
        cut = dt.date.fromisoformat(cut) if cut else None
        return c, y, reg, regs, crop, crops, self.cb_var.currentData(), cut

    def title(self):
        c, y, reg, _, crop, _, var, cut = self._selection()
        return "%s · %s %d · %s · %s%s" % (
            tr("mp.var." + var), c, y, tr("mp.crop." + crop),
            tr("cs.reg." + reg), " · %s" % cut.isoformat() if cut else "")

    def subtitle(self):
        _, _, _, _, _, _, _, cut = self._selection()
        return tr("mp.sub", cut.isoformat() if cut else tr("mp.cut.close"))

    # ---------- map
    def make_map(self):
        if not self.data:
            return
        c, y, reg, regs, crop, crops, var, cut = self._selection()
        if y is None:
            QMessageBox.warning(self, "EloteSat", tr("mp.err.nodata"))
            return
        vals = siap.summary(self.data, c, y, regs, crops, var, cut)
        vals = {k: v for k, v in vals.items() if v is not None}
        if not vals:
            QMessageBox.warning(self, "EloteSat", tr("mp.err.nodata"))
            return
        is_date = var.startswith("p50")
        src = QgsVectorLayer("%s|layername=municipios" % self.data.path,
                             "municipios", "ogr")
        mem = QgsVectorLayer("MultiPolygon?crs=%s" % src.crs().authid(),
                             self.title(), "memory")
        pr = mem.dataProvider()
        fields = [QgsField("cvegeo", QVariant.String),
                  QgsField("municipio", QVariant.String),
                  QgsField("valor", QVariant.Double),
                  QgsField("fecha", QVariant.String),
                  QgsField("mes", QVariant.Int),
                  QgsField("etiqueta", QVariant.String)]
        pr.addAttributes(fields)
        mem.updateFields()
        feats = []
        self.rows = []
        for f in src.getFeatures():
            cv = f["cvegeo"]
            v = vals.get(cv)
            nf = QgsFeature(mem.fields())
            g = f.geometry()
            g.convertToMultiType()
            nf.setGeometry(g)
            val = fecha = mes = None
            lab = f["municipio"]
            if v is not None:
                if is_date:
                    fecha = v
                    mes = int(v[5:7])
                    lab += "\n%d %s" % (int(v[8:10]), self._month(mes))
                else:
                    val = float(v)
                    lab += "\n" + self._fmt(val, var)
            nf.setAttributes([cv, f["municipio"], val, fecha, mes, lab])
            feats.append(nf)
            self.rows.append({"cvegeo": cv, "municipio": f["municipio"],
                              "valor": val, "fecha": fecha})
        pr.addFeatures(feats)
        mem.updateExtents()
        if is_date:
            self._style_dates(mem)
        else:
            self._style_graduated(mem, var)
        self._style_labels(mem)
        proj = QgsProject.instance()
        root = proj.layerTreeRoot()
        grp = root.findGroup(GROUP) or root.insertGroup(0, GROUP)
        proj.addMapLayer(mem, False)
        grp.insertLayer(0, mem)
        self.layer = mem
        self.btn_layout.setEnabled(True)
        self.btn_csv.setEnabled(True)
        w = siap.cycle_warning(self.data, c, y)
        self.log.appendPlainText(tr("mp.done", mem.name(), len(vals)) + (
            " " + tr("cs.incomplete") if w else ""))
        return mem

    def _month(self, m):
        from ..core import i18n
        return (MONTHS if i18n.lang() == "es" else MONTHS_EN)[m - 1]

    @staticmethod
    def _fmt(v, var):
        if var in ("rendimiento",):
            return "%.2f %s" % (v, VAR_UNITS[var])
        if var == "pct_siniestrada":
            return "%.1f %%" % v
        return "{:,.0f} {}".format(v, VAR_UNITS.get(var, "")).replace(",", " ")

    def _nodata_symbol(self):
        return QgsFillSymbol.createSimple({
            "color": "#eeeeee", "outline_color": "#bdbdbd",
            "outline_width": "0.2", "style": "b_diagonal"})

    def _style_graduated(self, lyr, var):
        ramp = QgsStyle.defaultStyle().colorRamp(self.cb_ramp.currentData() or
                                                 "YlGn")
        base = QgsFillSymbol.createSimple({"outline_color": "#ffffff",
                                           "outline_width": "0.3"})
        r = QgsGraduatedSymbolRenderer("valor")
        r.setSourceSymbol(base)
        r.setSourceColorRamp(ramp)
        meth = QgsClassificationJenks() if self.cb_method.currentData() == \
            "jenks" else QgsClassificationQuantile()
        meth.setLabelPrecision(2 if var == "rendimiento" else 0)
        meth.setLabelTrimTrailingZeroes(True)
        r.setClassificationMethod(meth)
        r.updateClasses(lyr, self.sp_classes.value())
        r.updateColorRamp(ramp)
        lyr.setRenderer(r)
        self._add_nodata_rule(lyr)

    def _add_nodata_rule(self, lyr):
        """Wrap the renderer in rules so NULL values get their own symbol."""
        from qgis.core import QgsRuleBasedRenderer
        rr = QgsRuleBasedRenderer.convertFromRenderer(lyr.renderer())
        if rr is None:
            return
        rule = QgsRuleBasedRenderer.Rule(self._nodata_symbol(),
                                         filterExp='"valor" IS NULL AND '
                                                   '"fecha" IS NULL',
                                         label=tr("mp.nodata"))
        rr.rootRule().appendChild(rule)
        lyr.setRenderer(rr)

    def _style_dates(self, lyr):
        ramp = QgsStyle.defaultStyle().colorRamp(self.cb_ramp.currentData() or
                                                 "YlGn")
        months = sorted({f["mes"] for f in lyr.getFeatures()
                         if f["mes"] not in (None, "") and
                         not (isinstance(f["mes"], QVariant) and
                              f["mes"].isNull())})
        # months in the order of the cycle (OI from October, PV from April)
        first = 10 if self.cb_cycle.currentData() == "OI" else 4
        months.sort(key=lambda m: (int(m) - first) % 12)
        cats = []
        n = max(len(months) - 1, 1)
        for i, m in enumerate(months):
            sym = QgsFillSymbol.createSimple({"outline_color": "#ffffff",
                                              "outline_width": "0.3"})
            sym.setColor(ramp.color(i / n))
            cats.append(QgsRendererCategory(m, sym, self._month(int(m))))
        r = QgsCategorizedSymbolRenderer("mes", cats)
        lyr.setRenderer(r)
        self._add_nodata_rule(lyr)

    def _style_labels(self, lyr):
        if not self.chk_labels.isChecked():
            lyr.setLabelsEnabled(False)
            return
        s = QgsPalLayerSettings()
        s.fieldName = "etiqueta" if self.chk_values.isChecked() else \
            "municipio"
        s.isExpression = False
        s.placement = QgsPalLayerSettings.AroundPoint \
            if hasattr(QgsPalLayerSettings, "AroundPoint") else s.placement
        fmt = QgsTextFormat()
        fnt = QFont("Sans Serif")
        fnt.setPointSizeF(7)
        fmt.setFont(fnt)
        fmt.setSize(7)
        fmt.setColor(QColor("#222222"))
        buf = QgsTextBufferSettings()
        buf.setEnabled(True)
        buf.setSize(0.8)
        buf.setColor(QColor(255, 255, 255, 220))
        fmt.setBuffer(buf)
        s.setFormat(fmt)
        s.multilineAlign = QgsPalLayerSettings.MultiCenter \
            if hasattr(QgsPalLayerSettings, "MultiCenter") else 1
        lyr.setLabeling(QgsVectorLayerSimpleLabeling(s))
        lyr.setLabelsEnabled(True)

    # ---------- print layout
    def make_layout(self, export_path=None):
        """A4 landscape layout: map, title, subtitle, legend, scale bar,
        north arrow, logo and sources. Optionally exported to PDF/PNG."""
        if self.layer is None:
            return None
        proj = QgsProject.instance()
        mgr = proj.layoutManager()
        name = "EloteSat SIAP · " + self.layer.name()
        old = mgr.layoutByName(name)
        if old:
            mgr.removeLayout(old)
        lo = QgsPrintLayout(proj)
        lo.initializeDefaults()
        lo.setName(name)
        page = lo.pageCollection().page(0)
        page.setPageSize("A4", page.Landscape)
        W = 297

        m = QgsLayoutItemMap(lo)
        m.attemptMove(QgsLayoutPoint(8, 26, QgsUnitTypes.LayoutMillimeters))
        m.attemptResize(QgsLayoutSize(200, 176,
                                      QgsUnitTypes.LayoutMillimeters))
        m.setCrs(self.layer.crs())   # the project may have no CRS yet
        m.setLayers([self.layer])
        m.setKeepLayerSet(True)
        ext = self.layer.extent()
        ext.scale(1.04)
        m.zoomToExtent(ext)
        m.setFrameEnabled(True)
        lo.addLayoutItem(m)

        def label(text, x, y, w, h, size, bold=False, color="#1b1b1b",
                  align=Qt.AlignLeft):
            it = QgsLayoutItemLabel(lo)
            it.setText(text)
            f = QFont("Sans Serif")
            f.setPointSizeF(size)
            f.setBold(bold)
            tf = QgsTextFormat()
            tf.setFont(f)
            tf.setSize(size)
            tf.setColor(QColor(color))
            if hasattr(it, "setTextFormat"):
                it.setTextFormat(tf)
            else:
                it.setFont(f)
                it.setFontColor(QColor(color))
            it.setHAlign(align)
            it.attemptMove(QgsLayoutPoint(x, y,
                                          QgsUnitTypes.LayoutMillimeters))
            it.attemptResize(QgsLayoutSize(w, h,
                                           QgsUnitTypes.LayoutMillimeters))
            lo.addLayoutItem(it)
            return it

        label(self.title(), 8, 6, 240, 10, 15, True)
        label(self.subtitle(), 8, 16, 240, 7, 9, False, "#555555")

        leg = QgsLayoutItemLegend(lo)
        leg.setLinkedMap(m)
        leg.setAutoUpdateModel(False)
        leg.model().rootGroup().clear()
        node = leg.model().rootGroup().addLayer(self.layer)
        _, _, _, _, _, _, var, _ = self._selection()
        unit = VAR_UNITS.get(var)
        node.setName(tr("mp.var." + var) + (" (%s)" % unit if unit else ""))
        leg.setTitle("")
        try:
            from qgis.core import QgsLegendStyle
            for part, size in ((QgsLegendStyle.Group, 9),
                               (QgsLegendStyle.Subgroup, 9),
                               (QgsLegendStyle.SymbolLabel, 8)):
                st = leg.style(part)
                tf = st.textFormat()
                tf.setSize(size)
                st.setTextFormat(tf)
                leg.setStyle(part, st)
        except Exception:
            pass
        leg.attemptMove(QgsLayoutPoint(214, 30,
                                       QgsUnitTypes.LayoutMillimeters))
        lo.addLayoutItem(leg)
        leg.adjustBoxSize()

        sb = QgsLayoutItemScaleBar(lo)
        sb.setStyle("Single Box")
        sb.setLinkedMap(m)
        sb.setUnits(QgsUnitTypes.DistanceKilometers)
        sb.setUnitsPerSegment(25)
        sb.setNumberOfSegments(4)
        sb.setNumberOfSegmentsLeft(0)
        sb.setUnitLabel("km")
        sb.setHeight(2.5)
        sfmt = QgsTextFormat()
        sf = QFont("Sans Serif")
        sf.setPointSizeF(7)
        sfmt.setFont(sf)
        sfmt.setSize(7)
        if hasattr(sb, "setTextFormat"):
            sb.setTextFormat(sfmt)
        sb.update()
        sb.attemptMove(QgsLayoutPoint(12, 188,
                                      QgsUnitTypes.LayoutMillimeters))
        lo.addLayoutItem(sb)

        north = QgsLayoutItemPicture(lo)
        svg = os.path.join(QgsApplicationPath.svg(), "arrows",
                           "NorthArrow_02.svg")
        if os.path.exists(svg):
            north.setPicturePath(svg)
            north.attemptMove(QgsLayoutPoint(190, 30,
                                             QgsUnitTypes.LayoutMillimeters))
            north.attemptResize(QgsLayoutSize(12, 14,
                                              QgsUnitTypes.LayoutMillimeters))
            lo.addLayoutItem(north)

        logo = os.path.join(PLUGIN_DIR, "logos", "elotesat.png")
        if os.path.exists(logo):
            pic = QgsLayoutItemPicture(lo)
            pic.setPicturePath(logo)
            pic.attemptMove(QgsLayoutPoint(W - 30, 6,
                                           QgsUnitTypes.LayoutMillimeters))
            pic.attemptResize(QgsLayoutSize(22, 22,
                                            QgsUnitTypes.LayoutMillimeters))
            lo.addLayoutItem(pic)

        c, y, *_ = self._selection()
        warn = siap.cycle_warning(self.data, c, y)
        label(tr("mp.sources", dt.date.today().isoformat()) +
              ("\n" + tr("cs.incomplete") if warn else ""),
              214, 150, 76, 52, 6.5, False, "#444444")
        mgr.addLayout(lo)
        if export_path:
            ex = QgsLayoutExporter(lo)
            if export_path.lower().endswith(".pdf"):
                ex.exportToPdf(export_path,
                               QgsLayoutExporter.PdfExportSettings())
            else:
                ex.exportToImage(export_path,
                                 QgsLayoutExporter.ImageExportSettings())
        self.log.appendPlainText(tr("mp.layout.done", name))
        return lo

    def export_csv(self):
        if not getattr(self, "rows", None):
            return
        p, _ = QFileDialog.getSaveFileName(
            self, "EloteSat", "siap_%s.csv" % self.layer.name().replace(
                " · ", "_").replace(" ", "_"), "CSV (*.csv)")
        if p:
            siap.write_csv(self.rows, p)
            self.log.appendPlainText(p)


class QgsApplicationPath:
    @staticmethod
    def svg():
        from qgis.core import QgsApplication
        paths = QgsApplication.svgPaths()
        for p in paths:
            if os.path.isdir(os.path.join(p, "arrows")):
                return p
        return paths[0] if paths else ""
