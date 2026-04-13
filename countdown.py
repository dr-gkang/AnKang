from __future__ import annotations

import json
import os
from datetime import datetime

from aqt.qt import *

from .ankang_format_styles import format_user_datetime
from .todolist import _12h_parts_to_hhmm, _hhmm_to_12h_parts, _TIME_QUARTERS


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


def _parse_iso(s: str | None) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _default_exam_qdate() -> QDate:
    """Closest following Friday (if today is Friday, use the next Friday)."""
    d = QDate.currentDate()
    dow = d.dayOfWeek()
    delta = (5 - dow) % 7
    if delta == 0:
        return d.addDays(7)
    return d.addDays(delta)


def _default_exam_title(slot_index: int) -> str:
    return f"Exam {slot_index + 1}"


def _slot_name(slot: dict | None, slot_index: int) -> str:
    if not slot:
        return _default_exam_title(slot_index)
    n = (slot.get("name") or "").strip()
    return n or _default_exam_title(slot_index)


def _load_star_icons(addon_path: str, n: int) -> tuple[QIcon, QIcon]:
    """Star1..Star3 with fallback to Star if assets missing."""
    un = os.path.join(
        addon_path, "media", "Buttons", "Unpressed", f"C_Star{n}.png"
    )
    pr = os.path.join(addon_path, "media", "Buttons", "Pressed", f"CP_Star{n}.png")
    if os.path.exists(un) and os.path.exists(pr):
        return QIcon(un), QIcon(pr)
    un0 = os.path.join(addon_path, "media", "Buttons", "Unpressed", "C_Star.png")
    pr0 = os.path.join(addon_path, "media", "Buttons", "Pressed", "CP_Star.png")
    if os.path.exists(un0) and os.path.exists(pr0):
        return QIcon(un0), QIcon(pr0)
    return QIcon(), QIcon()


class ExamSlotDialog(QDialog):
    """Exam # — optional display name, then date + time (task due block, always on)."""

    def __init__(
        self,
        slot_index: int,
        *,
        initial: dict | None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.slot_index = slot_index
        self.setWindowTitle(f"Exam {slot_index + 1}")
        self.setMinimumWidth(320)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        root.addWidget(QLabel("Exam name"))
        self._name_edit = QLineEdit(self)
        self._name_edit.setPlaceholderText(_default_exam_title(slot_index))
        root.addWidget(self._name_edit)

        due_box = QGroupBox("Due Date/Time")
        due_outer = QVBoxLayout()

        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("MM/dd/yyyy")
        self._date_edit.setDate(_default_exam_qdate())

        self._hour_combo = QComboBox()
        self._hour_combo.addItems([str(i) for i in range(1, 13)])
        self._min_combo = QComboBox()
        self._min_combo.addItems([f"{m:02d}" for m in _TIME_QUARTERS])
        self._ampm_combo = QComboBox()
        self._ampm_combo.addItems(["AM", "PM"])
        for cb in (self._hour_combo, self._min_combo, self._ampm_combo):
            cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)

        due_date_row = QHBoxLayout()
        due_date_row.addWidget(self._date_edit, 1)
        due_outer.addLayout(due_date_row)

        time_row = QHBoxLayout()
        time_row.addWidget(self._hour_combo, 1)
        time_row.addWidget(self._min_combo, 1)
        time_row.addWidget(self._ampm_combo, 1)
        due_outer.addLayout(time_row)
        due_box.setLayout(due_outer)
        root.addWidget(due_box)

        btn_row = QHBoxLayout()
        remove_btn = QPushButton("Remove exam")
        remove_btn.clicked.connect(self._on_remove)
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)
        save_btn.clicked.connect(self._accept_save)
        cancel_btn.clicked.connect(self.reject)

        self._removed = False
        if initial:
            nm = (initial.get("name") or "").strip()
            if nm:
                self._name_edit.setText(nm)
        dt = _parse_iso(initial.get("when") if initial else None)
        if dt:
            self._date_edit.setDate(
                QDate(dt.year, dt.month, dt.day)
            )
            hhmm = f"{dt.hour:02d}:{dt.minute:02d}"
            h12, mm, ap = _hhmm_to_12h_parts(hhmm)
            self._hour_combo.setCurrentText(str(h12))
            self._min_combo.setCurrentText(f"{mm:02d}")
            mi = self._ampm_combo.findText(ap)
            if mi >= 0:
                self._ampm_combo.setCurrentIndex(mi)
        else:
            h12, mm, ap = _hhmm_to_12h_parts("09:00")
            self._hour_combo.setCurrentText(str(h12))
            self._min_combo.setCurrentText(f"{mm:02d}")
            mi = self._ampm_combo.findText(ap)
            if mi >= 0:
                self._ampm_combo.setCurrentIndex(mi)

        from .ankang_format_styles import ankang_text_button_stylesheet, mark_ankang_text_button

        for b in (remove_btn, save_btn, cancel_btn):
            mark_ankang_text_button(b)
        self.setStyleSheet(ankang_text_button_stylesheet())

    def _on_remove(self) -> None:
        self._removed = True
        self.accept()

    def _accept_save(self) -> None:
        self._removed = False
        self.accept()

    def removal_requested(self) -> bool:
        return self._removed

    def build_when_iso(self) -> str | None:
        if self._removed:
            return None
        d = self._date_edit.date()
        h12 = int(self._hour_combo.currentText())
        minute = int(self._min_combo.currentText())
        hhmm = _12h_parts_to_hhmm(h12, minute, self._ampm_combo.currentText())
        qt = QTime.fromString(hhmm, "HH:mm")
        if not qt.isValid():
            return None
        dt = datetime(d.year(), d.month(), d.day(), qt.hour(), qt.minute(), 0)
        return dt.isoformat(timespec="seconds")

    def build_slot(self) -> dict | None:
        if self._removed:
            return None
        when = self.build_when_iso()
        if not when:
            return None
        name = self._name_edit.text().strip() or _default_exam_title(self.slot_index)
        return {"when": when, "name": name}


class ExamCountdownConfigDialog(QDialog):
    """Pick Exam 1–3; each opens Exam # date/time dialog."""

    def __init__(self, slots: list[dict | None], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Exam countdowns")
        self.setMinimumWidth(300)
        self._slots: list[dict | None] = []
        for i in range(3):
            s = slots[i] if i < len(slots) else None
            if isinstance(s, dict) and s.get("when"):
                nm = str(s.get("name") or "").strip()
                self._slots.append(
                    {
                        "when": str(s["when"]),
                        "name": nm or _default_exam_title(i),
                    }
                )
            else:
                self._slots.append(None)

        layout = QVBoxLayout(self)
        hint = QLabel("Select an exam slot to add or edit its date and time.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._list = QListWidget(self)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)
        self._refresh_list()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        from .ankang_format_styles import ankang_text_button_stylesheet, mark_ankang_text_button

        mark_ankang_text_button(close_btn)
        self.setStyleSheet(ankang_text_button_stylesheet())

    def _row_label(self, i: int) -> str:
        slot = self._slots[i]
        if slot and slot.get("when"):
            when = _parse_iso(slot.get("when"))
            if when:
                return f"{_slot_name(slot, i)} — {format_user_datetime(when)}"
        return f"Add Exam {i + 1}"

    def _refresh_list(self) -> None:
        self._list.clear()
        for i in range(3):
            self._list.addItem(self._row_label(i))

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        row = self._list.row(item)
        if row < 0 or row > 2:
            return
        slot = self._slots[row]
        dlg = ExamSlotDialog(row, initial=slot, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.removal_requested():
            self._slots[row] = None
        else:
            built = dlg.build_slot()
            if built:
                self._slots[row] = built
        self._refresh_list()

    def slots(self) -> list[dict | None]:
        out: list[dict | None] = []
        for x in self._slots[:3]:
            out.append(None if x is None else dict(x))
        while len(out) < 3:
            out.append(None)
        return out[:3]


class ExamCountdownWidget(QWidget):
    _SWITCH_TT = "Switch Exam Countdown"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._btn_size = 40
        self._icon_size = 35
        self._addon_path = os.path.dirname(__file__)
        self._save_path = os.path.join(self._addon_path, "exam_cntdwn_storage.json")
        self._legacy_save = os.path.join(
            self._addon_path, "ankang_exam_countdown.json"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.heading_label = QLabel("Exam Countdown")
        self.heading_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.heading_label.setWordWrap(True)
        self.heading_label.setStyleSheet(
            "color: #000000; font-weight: 700; font-size: 12px;"
        )
        layout.addWidget(self.heading_label)

        self.time_label = QLabel("—")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.time_label.setStyleSheet(
            "color: #000000; font-weight: 800; font-size: 16px;"
        )
        layout.addWidget(self.time_label)

        un_star = os.path.join(
            self._addon_path, "media", "Buttons", "Unpressed", "C_Star.png"
        )
        pr_star = os.path.join(
            self._addon_path, "media", "Buttons", "Pressed", "CP_Star.png"
        )
        self._star_generic: tuple[QIcon, QIcon] = (
            QIcon(un_star) if os.path.exists(un_star) else QIcon(),
            QIcon(pr_star) if os.path.exists(pr_star) else QIcon(),
        )
        self._star_pairs: list[tuple[QIcon, QIcon]] = [
            _load_star_icons(self._addon_path, i) for i in (1, 2, 3)
        ]
        n0, a0 = self._star_pairs[0]
        self.switch_btn = IconSwapButton(
            n0,
            a0,
            icon_size=QSize(self._icon_size, self._icon_size),
            tooltip=self._SWITCH_TT,
            parent=self,
        )
        self.switch_btn.setFixedSize(self._btn_size, self._btn_size)
        self.switch_btn.clicked.connect(self._switch_exam)

        def icon(parts: list[str]) -> QIcon:
            return QIcon(os.path.join(self._addon_path, *parts))

        self._tool_normal = icon(["media", "Buttons", "Unpressed", "C_Tool.png"])
        self._tool_active = icon(["media", "Buttons", "Pressed", "CP_Tool.png"])

        self.config_btn = IconSwapButton(
            self._tool_normal,
            self._tool_active,
            icon_size=QSize(self._icon_size, self._icon_size),
            tooltip="Configure exam countdowns",
            parent=self,
        )
        self.config_btn.setFixedSize(self._btn_size, self._btn_size)
        self.config_btn.clicked.connect(self._open_config)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addStretch()
        row.addWidget(self.switch_btn)
        row.addWidget(self.config_btn)
        row.addStretch()
        layout.addLayout(row)

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._refresh)
        self._tick.start(60_000)

        self._slots: list[dict | None] = [None, None, None]
        self._current_slot = 0
        self._load()
        self._ensure_current_slot_valid()
        self._refresh()
        self.set_text_color("#000000")

    def _filled_slots(self) -> list[int]:
        return [i for i in range(3) if self._slots[i] and self._slots[i].get("when")]

    def _ensure_current_slot_valid(self) -> None:
        filled = self._filled_slots()
        if not filled:
            self._current_slot = 0
            return
        if self._current_slot not in filled:
            self._current_slot = filled[0]

    def _load(self) -> None:
        self._slots = [None, None, None]
        self._current_slot = 0
        path = self._save_path
        if not os.path.exists(path) and os.path.exists(self._legacy_save):
            path = self._legacy_save
        if not os.path.exists(path):
            return
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        if isinstance(raw.get("slots"), list):
            arr = raw["slots"][:3]
            for i, x in enumerate(arr):
                if isinstance(x, dict) and x.get("when"):
                    nm = str(x.get("name") or "").strip()
                    self._slots[i] = {
                        "when": str(x["when"]),
                        "name": nm or _default_exam_title(i),
                    }
        elif isinstance(raw.get("exams"), list):
            for i, x in enumerate(raw["exams"][:3]):
                if isinstance(x, dict) and x.get("when"):
                    nm = str(x.get("name") or "").strip()
                    self._slots[i] = {
                        "when": str(x["when"]),
                        "name": nm or _default_exam_title(i),
                    }
        idx = raw.get("current_slot", raw.get("current_index"))
        if isinstance(idx, int) and 0 <= idx <= 2:
            self._current_slot = idx
        if path == self._legacy_save and any(self._slots):
            self._save()

    def _save(self) -> None:
        try:
            with open(self._save_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"slots": self._slots, "current_slot": self._current_slot},
                    f,
                    indent=2,
                )
        except OSError:
            pass

    def _slot_when(self, i: int) -> datetime | None:
        s = self._slots[i]
        if not s:
            return None
        return _parse_iso(s.get("when"))

    def _next_filled_slot(self) -> int | None:
        filled = self._filled_slots()
        if len(filled) <= 1:
            return None
        pos = filled.index(self._current_slot)
        return filled[(pos + 1) % len(filled)]

    def _apply_switch_icons(self) -> None:
        filled = self._filled_slots()
        if not filled:
            n, a = self._star_generic
            if n.isNull() or a.isNull():
                n, a = self._star_pairs[0]
        else:
            n, a = self._star_pairs[self._current_slot]
            if n.isNull() or a.isNull():
                n, a = self._star_pairs[0]
        self.switch_btn._icon_normal = n
        self.switch_btn._icon_active = a
        self.switch_btn.setIcon(a if self.switch_btn.underMouse() else n)
        self.switch_btn.setToolTip(self._SWITCH_TT)

    def _switch_exam(self) -> None:
        nxt = self._next_filled_slot()
        if nxt is None:
            return
        self._current_slot = nxt
        self._save()
        self._apply_switch_icons()
        self._refresh()

    def _open_config(self) -> None:
        dlg = ExamCountdownConfigDialog(self._slots, self)
        dlg.exec()
        self._slots = dlg.slots()
        self._ensure_current_slot_valid()
        self._save()
        self._apply_switch_icons()
        self._refresh()

    @staticmethod
    def _format_remaining(target: datetime, now: datetime) -> str:
        if target <= now:
            return "Ended"
        total_seconds = int((target - now).total_seconds())
        if total_seconds >= 86400:
            days = total_seconds // 86400
            return "1 day" if days == 1 else f"{days} days"
        hours, rem = divmod(total_seconds, 3600)
        mins = rem // 60
        return f"{hours}h {mins:02d}m"

    def _refresh(self) -> None:
        self.switch_btn.setToolTip(self._SWITCH_TT)
        filled = self._filled_slots()
        self.switch_btn.setEnabled(len(filled) > 1)
        self._apply_switch_icons()

        when = self._slot_when(self._current_slot)
        if not when:
            self.heading_label.setText("Exam Countdown")
            self.time_label.setText("—")
            return

        slot = self._slots[self._current_slot]
        self.heading_label.setText(_slot_name(slot, self._current_slot))
        now = datetime.now()
        self.time_label.setText(self._format_remaining(when, now))

    def set_text_color(self, color_hex: str) -> None:
        self.heading_label.setStyleSheet(
            f"color: {color_hex}; font-weight: 700; font-size: 12px;"
        )
        self.time_label.setStyleSheet(
            f"color: {color_hex}; font-weight: 800; font-size: 16px;"
        )
