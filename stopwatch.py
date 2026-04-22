from __future__ import annotations

import os
from aqt.qt import *
from aqt import mw

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

class StopwatchWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Keep same size as timer buttons for visual consistency.
        self._btn_size = 40
        self._icon_size = 35

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.heading_label = QLabel("Stopwatch")
        self.heading_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.heading_label.setStyleSheet("color: #000000; font-weight: 700; font-size: 12px;")
        layout.addWidget(self.heading_label)

        self.time_label = QLabel("00:00:00")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.time_label.setStyleSheet("color: #000000; font-weight: 800; font-size: 16px;")
        layout.addWidget(self.time_label)

        addon_path = os.path.dirname(__file__)
        def icon(path_parts: list[str]) -> QIcon:
            return QIcon(os.path.join(addon_path, *path_parts))

        # Play/Pause icon sets
        self._play_normal = icon(["media", "Buttons", "Unpressed", "C_RightArrow2.png"])
        self._play_active = icon(["media", "Buttons", "Pressed", "CP_RightArrow2.png"])
        self._pause_normal = icon(["media", "Buttons", "Unpressed", "C_Pause.png"])
        self._pause_active = icon(["media", "Buttons", "Pressed", "CP_Pause.png"])

        # Reset icon set
        reset_normal_path = os.path.join(addon_path, "media", "Buttons", "Unpressed", "C_Return1.png")
        reset_active_path = os.path.join(addon_path, "media", "Buttons", "Pressed", "CP_Return1.png")
        self._reset_normal = QIcon(reset_normal_path)
        self._reset_active = QIcon(reset_active_path)

        self.play_btn = IconSwapButton(
            self._play_normal,
            self._play_active,
            icon_size=QSize(self._icon_size, self._icon_size),
            tooltip="Stopwatch: Start/Pause",
            parent=self,
        )
        self.play_btn.setFixedSize(self._btn_size, self._btn_size)
        self.play_btn.clicked.connect(self.toggle_stopwatch)

        self.reset_btn = IconSwapButton(
            self._reset_normal,
            self._reset_active,
            icon_size=QSize(self._icon_size, self._icon_size),
            tooltip="Stopwatch: Reset",
            parent=self,
        )
        self.reset_btn.setFixedSize(self._btn_size, self._btn_size)
        self.reset_btn.clicked.connect(self.reset_stopwatch)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addStretch()
        row.addWidget(self.play_btn)
        row.addWidget(self.reset_btn)
        row.addStretch()
        layout.addLayout(row)
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_time)
        self.seconds = 0
        self.is_running = False
        self.set_text_color("#000000")

    def toggle_stopwatch(self):
        if not self.is_running:
            self.timer.start(1000)
            self._set_play_mode(paused=False)
        else:
            self.timer.stop()
            self._set_play_mode(paused=True)
        self.is_running = not self.is_running

    def update_time(self):
        self.seconds += 1
        self.time_label.setText(self._format_hhmmss(self.seconds))

    def reset_stopwatch(self):
        self.timer.stop()
        self.seconds = 0
        self.is_running = False
        self.time_label.setText("00:00:00")
        self._set_play_mode(paused=True, reset=True)

    def _set_play_mode(self, *, paused: bool, reset: bool = False):
        # paused=True means show play icon.
        if paused:
            self.play_btn._icon_normal = self._play_normal
            self.play_btn._icon_active = self._play_active
            self.play_btn.setIcon(self._play_active if self.play_btn.underMouse() else self._play_normal)
            if reset:
                self.play_btn.setToolTip("Stopwatch: Start")
            else:
                self.play_btn.setToolTip(f"Stopwatch: {self.seconds}s (click to start)")
        else:
            self.play_btn._icon_normal = self._pause_normal
            self.play_btn._icon_active = self._pause_active
            self.play_btn.setIcon(self._pause_active if self.play_btn.underMouse() else self._pause_normal)
            self.play_btn.setToolTip(f"Stopwatch: {self.seconds}s (click to pause)")

    @staticmethod
    def _format_hhmmss(total_seconds: int) -> str:
        total_seconds = max(0, int(total_seconds))
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def set_text_color(self, color_hex: str):
        self.heading_label.setStyleSheet(
            f"color: {color_hex}; font-weight: 700; font-size: 12px;"
        )
        self.time_label.setStyleSheet(
            f"color: {color_hex}; font-weight: 800; font-size: 16px;"
        )