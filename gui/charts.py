"""Two small charts drawn with QPainter (no matplotlib needed).

ProfileChart: one line per class/group over ordered categories (stages),
  mean with a faint band of +-1 sd. Legend always shown.
HistChart: overlaid histograms (outlines) per class for one variable, with
  an optional vertical threshold line. Legend always shown.
Colours follow the entity (class or group), never its rank.
"""

import numpy as np
from qgis.PyQt.QtCore import Qt, QPointF, QRectF
from qgis.PyQt.QtGui import QPainter, QPen, QColor, QBrush, QFont
from qgis.PyQt.QtWidgets import QWidget


class _Base(QWidget):
    L, R, T, B = 70, 14, 46, 44

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(230)
        self.title = ""
        self.empty_text = ""

    def _setup(self, p):
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        fg = pal.color(pal.WindowText)
        p.fillRect(self.rect(), pal.color(pal.Base))
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
        p.setFont(f)
        return pal, fg

    def _plot_rect(self):
        return QRectF(self.L, self.T, self.width() - self.L - self.R,
                      self.height() - self.T - self.B)

    def _yaxis(self, p, plot, v0, v1, fg):
        grid = QColor(fg)
        grid.setAlpha(35)
        for i in range(5):
            v = v0 + (v1 - v0) * i / 4
            yy = plot.bottom() - plot.height() * i / 4
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(plot.left(), yy), QPointF(plot.right(), yy))
            p.setPen(fg)
            p.drawText(QRectF(0, yy - 8, self.L - 6, 16),
                       Qt.AlignRight | Qt.AlignVCenter, "%.3g" % v)

    def _legend(self, p, plot, items, fg):
        # title on its own line, legend on the line below
        p.drawText(QRectF(plot.left(), 2, plot.width(), 14), Qt.AlignLeft,
                   self.title)
        x = plot.left()
        y = 20
        for label, col in items:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(col)))
            p.drawRoundedRect(QRectF(x, y + 4, 12, 4), 2, 2)
            p.setPen(fg)
            w = p.fontMetrics().horizontalAdvance(label) + 26
            p.drawText(QRectF(x + 16, y - 2, w, 16),
                       Qt.AlignLeft | Qt.AlignVCenter, label)
            x += w


class ProfileChart(_Base):
    def set_data(self, categories, series, title="", ylabel="",
                 empty_text=""):
        """series: [(label, colour, means[list], sds[list or None])]"""
        self.cats, self.series = list(categories), list(series)
        self.title, self.ylabel, self.empty_text = title, ylabel, empty_text
        self.update()

    def paintEvent(self, _ev):  # noqa: N802
        p = QPainter(self)
        pal, fg = self._setup(p)
        series = getattr(self, "series", [])
        vals = []
        for _, _, m, s in series:
            for i, v in enumerate(m):
                if v is None or not np.isfinite(v):
                    continue
                sd = s[i] if s and s[i] is not None and np.isfinite(s[i]) \
                    else 0
                vals += [v - sd, v + sd]
        if not series or not vals or not self.cats:
            p.setPen(fg)
            p.drawText(self.rect(), Qt.AlignCenter, self.empty_text)
            p.end()
            return
        plot = self._plot_rect()
        v0, v1 = min(vals), max(vals)
        pad = (v1 - v0) * 0.06 or 0.05
        v0, v1 = v0 - pad, v1 + pad
        n = len(self.cats)

        def x(i):
            return plot.left() + plot.width() * (i + 0.5) / n

        def y(v):
            return plot.bottom() - plot.height() * (v - v0) / (v1 - v0)

        self._yaxis(p, plot, v0, v1, fg)
        p.setPen(fg)
        for i, c in enumerate(self.cats):
            p.drawText(QRectF(x(i) - plot.width() / n / 2, plot.bottom() + 4,
                              plot.width() / n, 30),
                       Qt.AlignHCenter | Qt.TextWordWrap,
                       " ".join(c.split("_")[:2]))
        axis = QColor(fg)
        axis.setAlpha(120)
        p.setPen(QPen(axis, 1))
        p.drawLine(plot.bottomLeft(), plot.bottomRight())
        for label, col, m, s in series:
            c = QColor(col)
            band = QColor(col)
            band.setAlpha(40)
            pts = [(i, v) for i, v in enumerate(m)
                   if v is not None and np.isfinite(v)]
            if s:
                p.setPen(QPen(band, 6, Qt.SolidLine, Qt.RoundCap))
                for i, v in pts:
                    sd = s[i]
                    if sd is not None and np.isfinite(sd):
                        p.drawLine(QPointF(x(i), y(v - sd)),
                                   QPointF(x(i), y(v + sd)))
            p.setPen(QPen(c, 2))
            for (i0, a), (i1, b) in zip(pts, pts[1:]):
                p.drawLine(QPointF(x(i0), y(a)), QPointF(x(i1), y(b)))
            p.setPen(QPen(pal.color(pal.Base), 2))
            p.setBrush(QBrush(c))
            for i, v in pts:
                p.drawEllipse(QPointF(x(i), y(v)), 4.5, 4.5)
            # direct label at the last point (<= 4 series)
            if len(series) <= 4 and pts:
                i, v = pts[-1]
                p.setPen(fg)
                p.drawText(QRectF(x(i) + 7, y(v) - 8, 80, 16),
                           Qt.AlignLeft | Qt.AlignVCenter, label)
        p.setPen(fg)
        self._legend(p, plot, [(s[0], s[1]) for s in series], fg)
        p.save()
        p.translate(10, plot.center().y())
        p.rotate(-90)
        p.drawText(QRectF(-80, -10, 160, 20), Qt.AlignCenter, self.ylabel)
        p.restore()
        p.end()


class HistChart(_Base):
    def set_data(self, groups, title="", threshold=None, empty_text=""):
        """groups: [(label, colour, values array)]"""
        self.groups = [(lbl, col, np.asarray(v, float)[np.isfinite(v)])
                       for lbl, col, v in groups]
        self.title, self.thr, self.empty_text = (title, threshold,
                                                 empty_text)
        self.update()

    def set_threshold(self, thr):
        self.thr = thr
        self.update()

    def paintEvent(self, _ev):  # noqa: N802
        p = QPainter(self)
        pal, fg = self._setup(p)
        groups = [g for g in getattr(self, "groups", []) if len(g[2])]
        if not groups:
            p.setPen(fg)
            p.drawText(self.rect(), Qt.AlignCenter, self.empty_text)
            p.end()
            return
        plot = self._plot_rect()
        allv = np.concatenate([g[2] for g in groups])
        lo, hi = np.percentile(allv, [0.5, 99.5])
        if hi <= lo:
            lo, hi = lo - 0.5, hi + 0.5
        edges = np.linspace(lo, hi, 41)
        dens = []
        for _, _, v in groups:
            h, _ = np.histogram(np.clip(v, lo, hi), edges)
            dens.append(h / max(h.sum(), 1))
        top = max(d.max() for d in dens) * 1.08 or 1

        def x(v):
            return plot.left() + plot.width() * (v - lo) / (hi - lo)

        def y(d):
            return plot.bottom() - plot.height() * d / top

        self._yaxis(p, plot, 0, top, fg)
        p.setPen(fg)
        for i in range(5):
            v = lo + (hi - lo) * i / 4
            p.drawText(QRectF(x(v) - 40, plot.bottom() + 4, 80, 16),
                       Qt.AlignHCenter, "%.3g" % v)
        for (label, col, _), d in zip(groups, dens):
            c = QColor(col)
            fill = QColor(col)
            fill.setAlpha(45)
            pts = [QPointF(x(edges[0]), y(0))]
            for i, dv in enumerate(d):
                pts += [QPointF(x(edges[i]), y(dv)),
                        QPointF(x(edges[i + 1]), y(dv))]
            pts.append(QPointF(x(edges[-1]), y(0)))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(fill))
            p.drawPolygon(pts)
            p.setPen(QPen(c, 2))
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a, b)
        if self.thr is not None and np.isfinite(self.thr) and \
                lo <= self.thr <= hi:
            p.setPen(QPen(fg, 1.5, Qt.DashLine))
            p.drawLine(QPointF(x(self.thr), plot.top()),
                       QPointF(x(self.thr), plot.bottom()))
        axis = QColor(fg)
        axis.setAlpha(120)
        p.setPen(QPen(axis, 1))
        p.drawLine(plot.bottomLeft(), plot.bottomRight())
        p.setPen(fg)
        self._legend(p, plot, [(g[0], g[1]) for g in groups], fg)
        p.end()
