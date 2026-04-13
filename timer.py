from __future__ import annotations

import os
import time

from aqt import mw
from aqt.qt import *


def _format_since_complete_hms(total_seconds: int) -> str:
    total_seconds = max(0, int(total_seconds))
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return f"- {h:02d}:{m:02d}:{s:02d}"


class TimerCompleteDialog(QDialog):
    """Shown when the timer reaches zero; close only via the window close button."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent or mw)
        self.setWindowTitle("Timer complete")
        self.setModal(True)
        self._t0 = time.perf_counter()

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        msg = QLabel("Congratulations! Timer is complete!")
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        root.addWidget(msg)
        root.addStretch(1)
        self._elapsed_lbl = QLabel("- 00:00:00")
        self._elapsed_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f = QFont()
        f.setBold(True)
        f.setPointSize(11)
        self._elapsed_lbl.setFont(f)
        root.addWidget(self._elapsed_lbl)

        self._upd = QTimer(self)
        self._upd.timeout.connect(self._refresh_elapsed)
        self._upd.start(1000)
        self._refresh_elapsed()

        self.setMinimumWidth(280)

    def _refresh_elapsed(self) -> None:
        sec = int(time.perf_counter() - self._t0)
        self._elapsed_lbl.setText(_format_since_complete_hms(sec))

    def closeEvent(self, event):
        self._upd.stop()
        return super().closeEvent(event)

class IconSwapButton(QToolButton):
    def __init__(
        self,
        icon_normal: QIcon,
        icon_active: QIcon,
        *,
        icon_size: QSize,
        tooltip: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._icon_normal = icon_normal
        self._icon_active = icon_active
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(self._icon_normal)
        self.setIconSize(icon_size)
        self.setAutoRaise(True)
        self.setStyleSheet(
            "QToolButton { border: none; background: transparent; padding: 0px; }"
        )

    def enterEvent(self, event):
        self.setIcon(self._icon_active)
        return super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self._icon_normal)
        return super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.setIcon(self._icon_active)
        return super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setIcon(self._icon_active if self.underMouse() else self._icon_normal)
        return super().mouseReleaseEvent(event)

_TIMER_DURATION_MINUTES = (5, 10, 15, 25, 30, 50, 60)


class TimerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._btn_size = 40
        self._icon_size = 35

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Force the widget to accept its own color scheme
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.heading_label = QLabel("Timer")
        self.heading_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.heading_label.setStyleSheet("color: #000000; font-weight: 700; font-size: 12px;")
        layout.addWidget(self.heading_label)

        self.time_label = QLabel("25:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.time_label.setStyleSheet("color: #000000; font-weight: 800; font-size: 16px;")
        layout.addWidget(self.time_label)

        addon_path = os.path.dirname(__file__)
        def icon(path_parts: list[str]) -> QIcon:
            return QIcon(os.path.join(addon_path, *path_parts))

        self._play_normal = icon(["media", "Buttons", "Unpressed", "C_RightArrow2.png"])
        self._play_active = icon(["media", "Buttons", "Pressed", "CP_RightArrow2.png"])
        self._pause_normal = icon(["media", "Buttons", "Unpressed", "C_Pause.png"])
        self._pause_active = icon(["media", "Buttons", "Pressed", "CP_Pause.png"])

        reset_normal_path = os.path.join(addon_path, "media", "Buttons", "Unpressed", "C_Return1.png")
        reset_active_path = os.path.join(addon_path, "media", "Buttons", "Pressed", "CP_Return1.png")
        self._reset_normal = QIcon(reset_normal_path)
        self._reset_active = QIcon(reset_active_path)

        self._tool_normal = icon(["media", "Buttons", "Unpressed", "C_Tool.png"])
        self._tool_active = icon(["media", "Buttons", "Pressed", "CP_Tool.png"])

        self.play_btn = IconSwapButton(
            self._play_normal,
            self._play_active,
            icon_size=QSize(self._icon_size, self._icon_size),
            tooltip="Timer: Start/Pause",
            parent=self,
        )
        self.play_btn.setFixedSize(self._btn_size, self._btn_size)
        self.play_btn.clicked.connect(self.toggle_timer)

        self.settings_btn = IconSwapButton(
            self._tool_normal,
            self._tool_active,
            icon_size=QSize(self._icon_size, self._icon_size),
            tooltip="Timer: Set duration",
            parent=self,
        )
        self.settings_btn.setFixedSize(self._btn_size, self._btn_size)
        self.settings_btn.clicked.connect(self.show_settings_menu)

        self.reset_btn = IconSwapButton(
            self._reset_normal,
            self._reset_active,
            icon_size=QSize(self._icon_size, self._icon_size),
            tooltip="Timer: Reset",
            parent=self,
        )
        self.reset_btn.setFixedSize(self._btn_size, self._btn_size)
        self.reset_btn.clicked.connect(self.reset_timer)

        # Second slot: Settings only when idle at full duration; Reset while running
        # or whenever time has diverged from a full-duration idle (incl. mid-run pause).
        self.secondary_stack = QStackedWidget(self)
        self.secondary_stack.setFixedSize(self._btn_size, self._btn_size)
        self.secondary_stack.addWidget(self.settings_btn)  # index 0
        self.secondary_stack.addWidget(self.reset_btn)     # index 1

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addStretch()
        row.addWidget(self.play_btn)
        row.addWidget(self.secondary_stack)
        row.addStretch()
        layout.addLayout(row)

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self._duration_seconds = 25 * 60
        self._remaining_seconds = self._duration_seconds
        self._render_time()
        self.is_running = False
        self._sync_buttons()
        self.set_text_color("#000000")

    def _open_completion_dialog(self) -> None:
        TimerCompleteDialog(self).exec()

    def toggle_timer(self):
        if self.is_running:
            self._tick.stop()
            self.is_running = False
            self._set_play_mode(paused=True)
            self._sync_buttons()
            return

        if self._remaining_seconds <= 0:
            self._remaining_seconds = self._duration_seconds
            self._render_time()

        self._tick.start(1000)
        self.is_running = True
        self._set_play_mode(paused=False)
        self._sync_buttons()

    def show_settings_menu(self):
        if self.is_running:
            return
        menu = QMenu(self)
        dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        fg = "#ffffff" if dark else "#000000"
        bg = "#3a3a3a" if dark else "#f3f3f3"
        menu.setStyleSheet(f"QMenu {{ background-color: {bg}; color: {fg}; border: 1px solid #5DA9DF; }}")
        for minutes in _TIMER_DURATION_MINUTES:
            act = menu.addAction(f"{minutes}m")
            act.setData(minutes)
        chosen = menu.exec(QCursor.pos())
        if chosen is None:
            return
        data = chosen.data()
        if data is not None:
            self._set_duration_minutes(int(data))

    def reset_timer(self):
        self._tick.stop()
        self.is_running = False
        self._remaining_seconds = self._duration_seconds
        self._render_time()
        self._set_play_mode(paused=True, reset=True)
        self._sync_buttons()

    def _set_play_mode(self, *, paused: bool, reset: bool = False):
        if paused:
            self.play_btn._icon_normal = self._play_normal
            self.play_btn._icon_active = self._play_active
            self.play_btn.setIcon(self._play_active if self.play_btn.underMouse() else self._play_normal)
            self.play_btn.setToolTip("Timer: Start" if reset else "Timer: Start/Pause")
        else:
            self.play_btn._icon_normal = self._pause_normal
            self.play_btn._icon_active = self._pause_active
            self.play_btn.setIcon(self._pause_active if self.play_btn.underMouse() else self._pause_normal)
            self.play_btn.setToolTip("Timer: Pause")

    def _on_tick(self):
        self._remaining_seconds -= 1
        if self._remaining_seconds <= 0:
            self._remaining_seconds = 0
            self._tick.stop()
            self.is_running = False
            self._set_play_mode(paused=True)
            self._sync_buttons()
            self._render_time()
            QTimer.singleShot(0, self._open_completion_dialog)
            return
        self._render_time()

    def _render_time(self):
        m = self._remaining_seconds // 60
        s = self._remaining_seconds % 60
        self.time_label.setText(f"{m:02d}:{s:02d}")

    def _set_duration_minutes(self, minutes: int):
        self._duration_seconds = max(1, minutes) * 60
        self.reset_timer()

    def _sync_buttons(self):
        idle_at_full = (
            not self.is_running
            and self._remaining_seconds == self._duration_seconds
        )
        # 0 = settings, 1 = reset
        self.secondary_stack.setCurrentIndex(0 if idle_at_full else 1)

    def set_text_color(self, color_hex: str):
        self.heading_label.setStyleSheet(
            f"color: {color_hex}; font-weight: 700; font-size: 12px;"
        )
        self.time_label.setStyleSheet(
            f"color: {color_hex}; font-weight: 800; font-size: 16px;"
        )