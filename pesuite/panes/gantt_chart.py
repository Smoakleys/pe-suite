"""Native read-only Gantt chart, custom-painted from the engine's schedule.

A QAbstractScrollArea with two frozen panes (the task-label column on the left and the
date header on top) and a scrollable timeline body. Everything is drawn from a
`LoadedProject`: bar geometry comes from each task's computed start / effective finish,
critical-path tasks are highlighted, parent tasks render as summary bars, and finish-to-
start dependencies are drawn as connectors. A "today" line marks the project's now.

The widget is read-only — editing happens in the Streamlit editor (Launch Editor). It
exists to give an instant, polished view of the schedule without a browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QAbstractScrollArea

from pesuite.core import LoadedProject, TaskStatus, task_rows

# Geometry
LABEL_W = 260          # frozen left column width
HEADER_H = 48          # frozen top header height (month band + day band)
MONTH_BAND_H = 22
ROW_H = 30
BAR_PAD = 6            # vertical padding inside a row
INDENT = 16            # per-depth indent in the label column
MIN_BAR_W = 6
DEFAULT_DAY_W = 26
MIN_DAY_W = 8
MAX_DAY_W = 64
PAD_DAYS = 3           # blank days padded around the schedule range

# Colors
C_GRID = QColor("#eceff4")
C_GRID_WEEK = QColor("#d3d9e3")
C_HEADER_BG = QColor("#f4f6fa")
C_HEADER_LINE = QColor("#d8dce4")
C_STRIPE_A = QColor("#ffffff")
C_STRIPE_B = QColor("#f7f9fc")
C_LABEL_BG = QColor("#ffffff")
C_TEXT = QColor("#1c2430")
C_MUTED = QColor("#7a8494")
C_TODAY = QColor("#c0392b")
C_DEP = QColor("#aab3c2")

C_BAR_NORMAL = QColor("#4a78b5")
C_BAR_NORMAL_EDGE = QColor("#34598c")
C_BAR_CRIT = QColor("#d9534f")
C_BAR_CRIT_EDGE = QColor("#b23f3b")
C_BAR_DONE = QColor("#74ad77")
C_BAR_DONE_EDGE = QColor("#548c57")
C_SUMMARY = QColor("#2b3a52")


@dataclass(frozen=True)
class _Row:
    task_id: str
    name: str
    depth: int
    is_parent: bool
    is_complete: bool
    is_critical: bool
    status: TaskStatus
    start: date | None
    finish: date | None


class GanttChart(QAbstractScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QAbstractScrollArea.NoFrame)
        self.viewport().setMouseTracking(True)
        self._day_w = DEFAULT_DAY_W
        self._fit_pending = False
        self._rows: list[_Row] = []
        self._row_index: dict[str, int] = {}
        self._edges: list[tuple[str, str]] = []  # (pred_id, succ_id), leaf->leaf FS-ish
        self._start: date | None = None
        self._end: date | None = None
        self._today: date | None = None
        self._num_days = 0

    # -- data ------------------------------------------------------------
    def set_project(self, loaded: LoadedProject | None) -> None:
        self._rows = []
        self._row_index = {}
        self._edges = []
        self._start = self._end = self._today = None
        self._num_days = 0

        if loaded is not None:
            self._build(loaded)
            self._fit_pending = True

        self._update_scrollbars()
        self._maybe_fit()
        self.viewport().update()

    def has_data(self) -> bool:
        return bool(self._rows) and self._start is not None

    def _build(self, loaded: LoadedProject) -> None:
        self._today = loaded.today
        starts: list[date] = []
        ends: list[date] = []

        for r in task_rows(loaded):
            self._rows.append(_Row(
                task_id=r.id, name=r.name, depth=r.depth,
                is_parent=r.is_parent, is_complete=r.is_complete,
                is_critical=r.is_critical, status=r.status,
                start=r.start, finish=r.finish,
            ))
            if r.start:
                starts.append(r.start)
            if r.finish:
                ends.append(r.finish)
        self._row_index = {r.task_id: i for i, r in enumerate(self._rows)}

        # Leaf -> leaf dependency edges (drawn as connectors).
        leaf_ids = {r.task_id for r in self._rows if not r.is_parent}
        for task in loaded.project.tasks:
            if task.id not in leaf_ids:
                continue
            for dep in task.dependencies:
                if dep.id in leaf_ids:
                    self._edges.append((dep.id, task.id))

        anchor = [d for d in (*starts, *ends, self._today) if d]
        if not anchor:
            return
        self._start = min(anchor) - timedelta(days=PAD_DAYS)
        self._end = max(anchor) + timedelta(days=PAD_DAYS)
        self._num_days = (self._end - self._start).days + 1

    # -- scrolling -------------------------------------------------------
    def _content_w(self) -> int:
        return self._num_days * self._day_w

    def _content_h(self) -> int:
        return len(self._rows) * ROW_H

    def _update_scrollbars(self) -> None:
        vp = self.viewport()
        body_w = max(0, vp.width() - LABEL_W)
        body_h = max(0, vp.height() - HEADER_H)

        h = self.horizontalScrollBar()
        h.setPageStep(body_w)
        h.setSingleStep(self._day_w)
        h.setRange(0, max(0, self._content_w() - body_w))

        v = self.verticalScrollBar()
        v.setPageStep(body_h)
        v.setSingleStep(ROW_H)
        v.setRange(0, max(0, self._content_h() - body_h))

    def _maybe_fit(self) -> None:
        """On first display of a project, size the day width so the whole timeline
        fits the viewport (clamped). Cleared once the user zooms manually."""
        if not self._fit_pending or not self.has_data():
            return
        body_w = self.viewport().width() - LABEL_W
        if body_w <= 40:  # not laid out yet; try again on resize
            return
        ideal = body_w / self._num_days
        self._day_w = int(max(MIN_DAY_W, min(MAX_DAY_W, ideal)))
        self._fit_pending = False
        self._update_scrollbars()
        self.horizontalScrollBar().setValue(0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scrollbars()
        self._maybe_fit()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        self.viewport().update()

    def wheelEvent(self, event) -> None:
        # Ctrl + wheel = zoom the timeline; Shift + wheel = horizontal scroll.
        mods = event.modifiers()
        if mods & Qt.ControlModifier:
            self._zoom(event.angleDelta().y(), event.position().toPoint())
            event.accept()
            return
        if mods & Qt.ShiftModifier:
            h = self.horizontalScrollBar()
            h.setValue(h.value() - event.angleDelta().y())
            event.accept()
            return
        super().wheelEvent(event)

    def _zoom(self, delta: int, anchor: QPoint) -> None:
        if self._start is None:
            return
        # Keep the date under the cursor stationary while zooming.
        old_w = self._day_w
        h_off = self.horizontalScrollBar().value()
        cursor_x = max(0, anchor.x() - LABEL_W) + h_off
        day_at_cursor = cursor_x / old_w if old_w else 0

        self._fit_pending = False  # user took manual control of zoom
        step = 2 if delta > 0 else -2
        self._day_w = max(MIN_DAY_W, min(MAX_DAY_W, self._day_w + step))
        if self._day_w == old_w:
            return
        self._update_scrollbars()
        new_off = int(day_at_cursor * self._day_w - max(0, anchor.x() - LABEL_W))
        self.horizontalScrollBar().setValue(new_off)
        self.viewport().update()

    # -- geometry helpers ------------------------------------------------
    def _date_to_x(self, d: date) -> int:
        h_off = self.horizontalScrollBar().value()
        return LABEL_W + (d - self._start).days * self._day_w - h_off

    def _row_top(self, i: int) -> int:
        return HEADER_H + i * ROW_H - self.verticalScrollBar().value()

    # -- painting --------------------------------------------------------
    def paintEvent(self, event) -> None:
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing, True)
        vp = self.viewport().rect()
        p.fillRect(vp, C_STRIPE_A)

        if not self.has_data():
            p.setPen(C_MUTED)
            p.drawText(vp, Qt.AlignCenter, "No schedule to display.")
            p.end()
            return

        self._paint_body(p, vp)
        self._paint_label_column(p, vp)
        self._paint_header(p, vp)
        self._paint_corner(p)
        p.end()

    def _paint_body(self, p: QPainter, vp: QRect) -> None:
        p.save()
        body = QRect(LABEL_W, HEADER_H, vp.width() - LABEL_W, vp.height() - HEADER_H)
        p.setClipRect(body)

        # Row stripes
        for i in range(len(self._rows)):
            top = self._row_top(i)
            if top + ROW_H < HEADER_H or top > vp.height():
                continue
            p.fillRect(LABEL_W, top, vp.width() - LABEL_W, ROW_H,
                       C_STRIPE_B if i % 2 else C_STRIPE_A)

        # Day / week gridlines
        for day in range(self._num_days):
            d = self._start + timedelta(days=day)
            x = self._date_to_x(d)
            if x < LABEL_W or x > vp.width():
                continue
            is_week = d.weekday() == 0  # Monday
            p.setPen(QPen(C_GRID_WEEK if is_week else C_GRID, 1))
            p.drawLine(x, HEADER_H, x, vp.height())

        self._paint_dependencies(p)
        self._paint_bars(p)
        self._paint_today_line(p, vp, full=True)
        p.restore()

    def _paint_bars(self, p: QPainter) -> None:
        for i, r in enumerate(self._rows):
            if r.start is None or r.finish is None:
                continue
            top = self._row_top(i)
            x0 = self._date_to_x(r.start)
            x1 = self._date_to_x(r.finish) + self._day_w
            w = max(MIN_BAR_W, x1 - x0)

            if r.is_parent:
                self._paint_summary_bar(p, x0, w, top)
            else:
                self._paint_task_bar(p, r, x0, w, top)

    def _paint_task_bar(self, p: QPainter, r: _Row, x0: int, w: int, top: int) -> None:
        if r.is_complete:
            fill, edge = C_BAR_DONE, C_BAR_DONE_EDGE
        elif r.is_critical:
            fill, edge = C_BAR_CRIT, C_BAR_CRIT_EDGE
        else:
            fill, edge = C_BAR_NORMAL, C_BAR_NORMAL_EDGE

        rect = QRectF(x0, top + BAR_PAD, w, ROW_H - 2 * BAR_PAD)
        p.setPen(QPen(edge, 1))
        p.setBrush(fill)
        p.drawRoundedRect(rect, 4, 4)

    def _paint_summary_bar(self, p: QPainter, x0: int, w: int, top: int) -> None:
        cy = top + ROW_H / 2
        h = 7
        rect = QRectF(x0, cy - h / 2, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(C_SUMMARY)
        p.drawRect(rect)
        # End caps (downward triangles), the classic summary-bar look.
        for cx in (x0, x0 + w):
            tri = QPolygonF([
                QPoint(int(cx - 4), int(cy + h / 2)),
                QPoint(int(cx + 4), int(cy + h / 2)),
                QPoint(int(cx), int(cy + h / 2 + 6)),
            ])
            p.drawPolygon(tri)

    def _paint_dependencies(self, p: QPainter) -> None:
        p.setBrush(C_DEP)
        pen = QPen(C_DEP, 1.4)
        for pred_id, succ_id in self._edges:
            pi = self._row_index.get(pred_id)
            si = self._row_index.get(succ_id)
            if pi is None or si is None:
                continue
            pr, sr = self._rows[pi], self._rows[si]
            if pr.finish is None or sr.start is None:
                continue
            x_from = self._date_to_x(pr.finish) + self._day_w
            y_from = self._row_top(pi) + ROW_H // 2
            x_to = self._date_to_x(sr.start)
            y_to = self._row_top(si) + ROW_H // 2

            p.setPen(pen)
            midx = max(x_from + 8, x_to - 8)
            p.drawLine(x_from, y_from, midx, y_from)
            p.drawLine(midx, y_from, midx, y_to)
            p.drawLine(midx, y_to, x_to, y_to)
            # arrowhead into successor start
            head = QPolygonF([
                QPoint(x_to, y_to),
                QPoint(x_to - 6, y_to - 3),
                QPoint(x_to - 6, y_to + 3),
            ])
            p.setPen(Qt.NoPen)
            p.drawPolygon(head)

    def _paint_today_line(self, p: QPainter, vp: QRect, full: bool) -> None:
        if self._today is None:
            return
        x = self._date_to_x(self._today)
        if x < LABEL_W or x > vp.width():
            return
        p.setPen(QPen(C_TODAY, 1.5, Qt.DashLine))
        top = HEADER_H if full else MONTH_BAND_H
        p.drawLine(x, top, x, vp.height())

    def _paint_label_column(self, p: QPainter, vp: QRect) -> None:
        p.save()
        col = QRect(0, HEADER_H, LABEL_W, vp.height() - HEADER_H)
        p.setClipRect(col)
        p.fillRect(col, C_LABEL_BG)

        fm = QFontMetrics(self.font())
        for i, r in enumerate(self._rows):
            top = self._row_top(i)
            if top + ROW_H < HEADER_H or top > vp.height():
                continue
            if i % 2:
                p.fillRect(0, top, LABEL_W, ROW_H, C_STRIPE_B)

            # critical marker dot
            tx = 10 + r.depth * INDENT
            if r.is_critical:
                p.setBrush(C_BAR_CRIT)
                p.setPen(Qt.NoPen)
                p.drawEllipse(QPoint(tx, top + ROW_H // 2), 3, 3)
            tx += 10

            font = QFont(self.font())
            font.setBold(r.is_parent)
            p.setFont(font)
            p.setPen(C_TEXT if not r.is_complete else C_MUTED)
            avail = LABEL_W - tx - 8
            text = fm.elidedText(r.name, Qt.ElideRight, avail)
            p.drawText(QRect(tx, top, avail, ROW_H), Qt.AlignVCenter | Qt.AlignLeft, text)

        # column separator
        p.setPen(QPen(C_HEADER_LINE, 1))
        p.drawLine(LABEL_W, HEADER_H, LABEL_W, vp.height())
        p.restore()

    def _paint_header(self, p: QPainter, vp: QRect) -> None:
        p.save()
        header = QRect(LABEL_W, 0, vp.width() - LABEL_W, HEADER_H)
        p.setClipRect(header)
        p.fillRect(header, C_HEADER_BG)

        # Month band
        self._paint_month_band(p, vp)

        # Day band: week-start labels + light day ticks
        fm = QFontMetrics(self.font())
        for day in range(self._num_days):
            d = self._start + timedelta(days=day)
            x = self._date_to_x(d)
            if x < LABEL_W - self._day_w or x > vp.width():
                continue
            if d.weekday() == 0:  # Monday → label the week
                p.setPen(QPen(C_GRID_WEEK, 1))
                p.drawLine(x, MONTH_BAND_H, x, HEADER_H)
                p.setPen(C_MUTED)
                label = d.strftime("%b %d").lstrip("0")
                p.drawText(QRect(x + 3, MONTH_BAND_H, 60, HEADER_H - MONTH_BAND_H),
                           Qt.AlignVCenter | Qt.AlignLeft, label)
            elif self._day_w >= 22:
                p.setPen(C_MUTED)
                p.drawText(QRect(x, MONTH_BAND_H, self._day_w, HEADER_H - MONTH_BAND_H),
                           Qt.AlignCenter, str(d.day))

        self._paint_today_line(p, vp, full=False)
        p.setPen(QPen(C_HEADER_LINE, 1))
        p.drawLine(LABEL_W, HEADER_H - 1, vp.width(), HEADER_H - 1)
        p.drawLine(LABEL_W, MONTH_BAND_H, vp.width(), MONTH_BAND_H)
        p.restore()

    def _paint_month_band(self, p: QPainter, vp: QRect) -> None:
        d = self._start
        font = QFont(self.font())
        font.setBold(True)
        p.setFont(font)
        while d <= self._end:
            # first of this month within range
            month_start = d
            if d.month == 12:
                next_month = date(d.year + 1, 1, 1)
            else:
                next_month = date(d.year, d.month + 1, 1)
            seg_end = min(self._end + timedelta(days=1), next_month)
            x0 = self._date_to_x(month_start)
            x1 = self._date_to_x(seg_end)
            if x1 > LABEL_W and x0 < vp.width():
                p.setPen(QPen(C_HEADER_LINE, 1))
                p.drawLine(max(x0, LABEL_W), 0, max(x0, LABEL_W), MONTH_BAND_H)
                p.setPen(C_TEXT)
                label = month_start.strftime("%B %Y")
                p.drawText(QRect(int(max(x0, LABEL_W) + 6), 0, int(x1 - max(x0, LABEL_W)), MONTH_BAND_H),
                           Qt.AlignVCenter | Qt.AlignLeft, label)
            d = next_month
        p.setFont(self.font())

    def _paint_corner(self, p: QPainter) -> None:
        corner = QRect(0, 0, LABEL_W, HEADER_H)
        p.fillRect(corner, C_HEADER_BG)
        p.setPen(C_MUTED)
        p.drawText(corner.adjusted(10, 0, -8, 0), Qt.AlignVCenter | Qt.AlignLeft, "Task")
        p.setPen(QPen(C_HEADER_LINE, 1))
        p.drawLine(LABEL_W, 0, LABEL_W, HEADER_H)
        p.drawLine(0, HEADER_H - 1, LABEL_W, HEADER_H - 1)

    # -- interaction -----------------------------------------------------
    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        if pos.y() < HEADER_H or pos.x() < 0:
            self.setToolTip("")
            return
        i = (pos.y() - HEADER_H + self.verticalScrollBar().value()) // ROW_H
        if 0 <= i < len(self._rows):
            r = self._rows[i]
            s = r.start.isoformat() if r.start else "—"
            f = r.finish.isoformat() if r.finish else "—"
            crit = " · critical path" if r.is_critical else ""
            self.setToolTip(f"{r.name}\n{s} → {f}{crit}")
        else:
            self.setToolTip("")
        super().mouseMoveEvent(event)
