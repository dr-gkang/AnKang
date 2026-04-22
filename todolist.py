from __future__ import annotations

import json
import os
import uuid
from html import escape as html_escape
from datetime import date, datetime, timedelta, time as dtime

from aqt.qt import *
from aqt import mw
from aqt.utils import askUser

from .ankang_profile_storage import profile_data_file
from .ankang_format_styles import (
    ankang_text_button_stylesheet,
    format_user_date,
    format_user_datetime,
    mark_ankang_text_button,
)

ARCHIVE_RETENTION_DAYS = 7


def _media_icon_paths(addon_dir: str, unpressed_base: str, pressed_base: str) -> tuple[str, str]:
    u = os.path.join(addon_dir, "media", "Buttons", "Unpressed", f"{unpressed_base}.png")
    p = os.path.join(addon_dir, "media", "Buttons", "Pressed", f"{pressed_base}.png")
    return u, p


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


class _WrappedDeckLabel(QLabel):
    """Word-wrapped label that reports correct height for layout (avoids overlap on resize)."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        m = self.contentsMargins()
        inner_w = max(width - m.left() - m.right(), 1)
        doc = QTextDocument()
        doc.setDefaultFont(self.font())
        doc.setPlainText(self.text())
        doc.setTextWidth(inner_w)
        return int(doc.size().height()) + m.top() + m.bottom() + 4


def _make_icon_toolbutton(
    addon_dir: str,
    unpressed_base: str,
    pressed_base: str,
    icon_size: QSize,
    tooltip: str,
    parent: QWidget | None,
) -> QWidget:
    u_path, p_path = _media_icon_paths(addon_dir, unpressed_base, pressed_base)
    if os.path.exists(u_path) and os.path.exists(p_path):
        btn = IconSwapButton(
            QIcon(u_path),
            QIcon(p_path),
            icon_size=icon_size,
            tooltip=tooltip,
            parent=parent,
        )
        btn.setFixedSize(icon_size.width() + 8, icon_size.height() + 8)
        return btn
    fallback = QPushButton("•")
    fallback.setToolTip(tooltip)
    fallback.setFixedSize(36, 36)
    mark_ankang_text_button(fallback)
    return fallback


def _parse_due_datetime(due_date: str | None, due_time: str | None) -> datetime | None:
    if not due_date:
        return None
    try:
        y, m, d = (int(x) for x in due_date.split("-"))
        base = datetime(y, m, d)
    except (ValueError, AttributeError):
        return None
    if due_time:
        try:
            parts = due_time.replace(":", " ").split()
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            return datetime.combine(base.date(), dtime(hh, mm, 0))
        except (ValueError, IndexError):
            return None
    return datetime.combine(base.date(), dtime(23, 59, 59))


_TIME_QUARTERS = (0, 15, 30, 45)


def _snap_quarter_minute(minute: int) -> int:
    return min(_TIME_QUARTERS, key=lambda x: abs(x - (int(minute) % 60)))


def _hhmm_to_12h_parts(hhmm: str | None) -> tuple[int, int, str]:
    """Parse stored HH:mm to (hour 1–12, minute in quarters, AM|PM)."""
    if hhmm:
        qt = QTime.fromString(hhmm, "HH:mm")
        if qt.isValid():
            h24, mm = qt.hour(), qt.minute()
        else:
            now = QTime.currentTime()
            h24, mm = now.hour(), now.minute()
    else:
        now = QTime.currentTime()
        h24, mm = now.hour(), now.minute()
    mm = _snap_quarter_minute(mm)
    if h24 == 0:
        return 12, mm, "AM"
    if h24 < 12:
        return h24, mm, "AM"
    if h24 == 12:
        return 12, mm, "PM"
    return h24 - 12, mm, "PM"


def _12h_parts_to_hhmm(hour_12: int, minute: int, ampm: str) -> str:
    ap = (ampm or "AM").strip().upper()
    if ap == "AM":
        h24 = 0 if hour_12 == 12 else hour_12
    else:
        h24 = hour_12 + 12 if hour_12 != 12 else 12
    return f"{h24:02d}:{minute:02d}"


def _active_sort_key(item: dict) -> tuple:
    deck = (item.get("deck") or "").lower()
    if item.get("completed"):
        return (3, deck)
    due_date = item.get("due_date")
    due_time = item.get("due_time")
    if due_date:
        dt = _parse_due_datetime(due_date, due_time)
        ts = dt.timestamp() if dt else float("inf")
        return (0, ts, deck)
    return (1, deck)


def _countdown_parts(now: datetime, target: datetime) -> tuple[int, int, int]:
    total_secs = int((target - now).total_seconds())
    if total_secs < 0:
        total_secs = -total_secs
    days, rem = divmod(total_secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    return days, hours, mins


_DECK_FONT_PARENT_PX = 12
_DECK_FONT_CHILD_PX = _DECK_FONT_PARENT_PX + 2


def _deck_font(px: int, bold: bool) -> QFont:
    f = QFont()
    f.setPixelSize(px)
    f.setBold(bold)
    return f


def _deck_color_stylesheet(color: str, strikethrough: bool) -> str:
    deco = "text-decoration: line-through;" if strikethrough else ""
    return f"color: {color}; {deco}"


def _make_task_title_column(
    task_title: str,
    linked_deck: str | None,
    color: str,
    strikethrough: bool,
    on_open_deck: callable | None = None,
) -> QWidget:
    """Task title plus optional linked full deck path under it."""
    col = QWidget()
    v = QVBoxLayout(col)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(2)
    col.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    col.setMinimumWidth(1)
    sheet = _deck_color_stylesheet(color, strikethrough)

    if not task_title.strip():
        empty = QLabel("")
        empty.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        v.addWidget(empty)
        return col

    title_lbl = _WrappedDeckLabel(task_title)
    title_lbl.setFont(_deck_font(_DECK_FONT_CHILD_PX, True))
    title_lbl.setStyleSheet(sheet)
    v.addWidget(title_lbl)

    if linked_deck:
        link = QLabel(
            f'<a href="{html_escape(linked_deck)}">{html_escape(linked_deck)}</a>'
        )
        link.setTextFormat(Qt.TextFormat.RichText)
        link.setWordWrap(True)
        link.setOpenExternalLinks(False)
        link.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        link.setFont(_deck_font(max(9, _DECK_FONT_PARENT_PX - 1), False))
        link_color = "#9ecbff" if not strikethrough else "#777777"
        link.setStyleSheet(f"color: {link_color};")
        link.setToolTip("Open this deck in Review")
        if on_open_deck is not None:
            link.linkActivated.connect(lambda _=None, d=linked_deck: on_open_deck(d))
        v.addWidget(link)

    return col


def _task_row_style(now: datetime, item: dict) -> tuple[str, str, str]:
    """
    Returns (deck_color, countdown_text, countdown_tooltip).
    """
    due_date = item.get("due_date")
    due_time = item.get("due_time")
    completed = bool(item.get("completed"))

    if completed:
        return "#dddddd", "Done", ""

    if not due_date:
        return "#ffffff", "No due date", "No due date set"

    dt_full = _parse_due_datetime(due_date, due_time)
    if not dt_full:
        return "#ffffff", "—", ""

    tooltip = (
        format_user_datetime(dt_full)
        if due_time
        else f"{format_user_date(dt_full)} (end of day)"
    )

    if now > dt_full:
        d, h, m = _countdown_parts(now, dt_full)
        return "#ff6b6b", f"Overdue ({d}d {h}h {m}m)", tooltip

    delta = dt_full - now
    d, h, m = _countdown_parts(now, dt_full)
    label = f"{d}d {h}h {m}m"

    if delta <= timedelta(hours=24):
        return "#ffab40", label, tooltip

    return "#ffffff", label, tooltip


def _migrate_legacy_item(raw: dict, col) -> dict | None:
    """Convert legacy {text, deck} to new schema."""
    if not isinstance(raw, dict):
        return None
    if raw.get("deck") and isinstance(raw["deck"], str) and "::" in raw["deck"]:
        deck = raw["deck"]
    else:
        leaf = raw.get("deck")
        if not leaf:
            return None
        names = col.decks.all_names()
        matches = [n for n in names if n == leaf or n.split("::")[-1] == leaf]
        if not matches:
            return None
        deck = sorted(matches)[0] if len(matches) > 1 else matches[0]

    return {
        "id": raw.get("id") or uuid.uuid4().hex,
        "deck": deck,
        "linked_deck": None,
        "due_date": raw.get("due_date"),
        "due_time": raw.get("due_time"),
        "completed": bool(raw.get("completed", False)),
    }


def _normalize_item(raw: dict, col) -> dict | None:
    if not isinstance(raw, dict):
        return None
    if "text" in raw:
        migrated = _migrate_legacy_item(raw, col)
        if migrated:
            return migrated
        return None
    deck = raw.get("deck")
    if not deck or not isinstance(deck, str):
        return None
    linked_deck = raw.get("linked_deck")
    if not isinstance(linked_deck, str) or not linked_deck.strip():
        linked_deck = None
    return {
        "id": raw.get("id") or uuid.uuid4().hex,
        "deck": deck,
        "linked_deck": linked_deck,
        "due_date": raw.get("due_date") if raw.get("due_date") else None,
        "due_time": raw.get("due_time") if raw.get("due_time") else None,
        "completed": bool(raw.get("completed", False)),
    }


def _normalize_archived_item(raw: dict, col) -> dict | None:
    base = _normalize_item(raw, col) if isinstance(raw, dict) else None
    if not base:
        return None
    at = raw.get("archived_at")
    if not at or not isinstance(at, str):
        base["archived_at"] = datetime.now().isoformat(timespec="seconds")
    else:
        base["archived_at"] = at
    base["completed"] = True
    return base


class TaskFormDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        addon_dir: str,
        initial: dict | None = None,
        edit_mode: bool = False,
    ):
        super().__init__(parent or mw)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setWindowTitle("Edit Task" if edit_mode else "Add New Task")
        self._edit_mode = edit_mode
        self._deletion_requested = False
        self.addon_dir = addon_dir

        initial = initial or {}
        self._full_deck_list = sorted(mw.col.decks.all_names())

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        deck_box = QGroupBox("Task")
        deck_lay = QVBoxLayout()
        self._task_text = QLineEdit()
        self._task_text.setPlaceholderText("Task title")
        self._deck_combo = QComboBox()
        self._deck_combo.setEditable(True)
        self._deck_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._deck_combo.addItems(self._full_deck_list)
        self._deck_combo.setCurrentIndex(-1)
        self._deck_combo.setEditText("")
        if self._deck_combo.lineEdit() is not None:
            self._deck_combo.lineEdit().setPlaceholderText(
                "Optional: Select a deck for your task"
            )
        comp = QCompleter(self._full_deck_list, self._deck_combo)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        self._deck_combo.setCompleter(comp)
        deck_lay.addWidget(self._task_text)
        deck_lay.addWidget(self._deck_combo)
        self._deck_name_hint = QLabel(
            "If a Task title is not selected, the deck name will be used."
        )
        self._deck_name_hint.setWordWrap(True)
        self._deck_name_hint.setStyleSheet("color: #888888; font-size: 11px;")
        self._deck_name_hint.setVisible(not edit_mode)
        deck_lay.addWidget(self._deck_name_hint)
        deck_box.setLayout(deck_lay)
        root.addWidget(deck_box)

        due_box = QGroupBox("Due Date/Time")
        due_outer = QVBoxLayout()
        due_checks = QHBoxLayout()
        self._has_date = QCheckBox("Set due date")
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("MM/dd/yyyy")
        self._date_edit.setDate(QDate.currentDate())

        self._has_time = QCheckBox("Set due time")
        self._hour_combo = QComboBox()
        self._hour_combo.addItems([str(i) for i in range(1, 13)])
        self._min_combo = QComboBox()
        self._min_combo.addItems([f"{m:02d}" for m in _TIME_QUARTERS])
        self._ampm_combo = QComboBox()
        self._ampm_combo.addItems(["AM", "PM"])
        for cb in (self._hour_combo, self._min_combo, self._ampm_combo):
            cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)

        due_checks.addWidget(self._has_date)
        due_checks.addWidget(self._has_time)
        due_checks.addStretch()
        due_outer.addLayout(due_checks)

        due_date_row = QHBoxLayout()
        due_date_row.addWidget(self._date_edit, 1)
        due_outer.addLayout(due_date_row)

        time_row = QHBoxLayout()
        time_row.addWidget(self._hour_combo, 1)
        time_row.addWidget(self._min_combo, 1)
        time_row.addWidget(self._ampm_combo, 1)
        due_outer.addLayout(time_row)
        self._due_time_hint = QLabel(
            "If due date is set but no due time, task will be due at 11:59pm"
        )
        self._due_time_hint.setWordWrap(True)
        self._due_time_hint.setStyleSheet("color: #888888; font-size: 11px;")
        due_outer.addWidget(self._due_time_hint)
        due_box.setLayout(due_outer)
        root.addWidget(due_box)

        self._has_date.toggled.connect(self._sync_due_controls)
        self._has_time.toggled.connect(self._sync_due_controls)

        btn_row = QHBoxLayout()
        self._delete_btn = QPushButton("Delete task")
        mark_ankang_text_button(self._delete_btn)
        self._delete_btn.setVisible(edit_mode)
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        btn_row.addWidget(self._delete_btn)
        btn_row.addStretch()

        ok_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        for b in (ok_btn, cancel_btn):
            mark_ankang_text_button(b)
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

        self.setStyleSheet(ankang_text_button_stylesheet())

        # Populate
        task_title = initial.get("deck")
        linked_deck = initial.get("linked_deck")
        if task_title:
            self._task_text.setText(task_title)
        if linked_deck and linked_deck in self._full_deck_list:
            self._deck_combo.setCurrentText(linked_deck)
        elif linked_deck:
            self._deck_combo.insertItem(0, linked_deck)
            self._deck_combo.setCurrentIndex(0)
        elif task_title and task_title in self._full_deck_list:
            # Backward compatibility for old entries where deck/title were conflated.
            self._deck_combo.setCurrentText(task_title)

        dd = initial.get("due_date")
        tm = initial.get("due_time")
        if dd:
            self._has_date.setChecked(True)
            qd = QDate.fromString(dd, Qt.DateFormat.ISODate)
            if qd.isValid():
                self._date_edit.setDate(qd)
        if tm:
            self._has_time.setChecked(True)
            h12, mm, ap = _hhmm_to_12h_parts(tm)
            self._hour_combo.setCurrentText(str(h12))
            self._min_combo.setCurrentText(f"{mm:02d}")
            mi = self._ampm_combo.findText(ap)
            if mi >= 0:
                self._ampm_combo.setCurrentIndex(mi)
        else:
            h12, mm, ap = _hhmm_to_12h_parts(None)
            self._hour_combo.setCurrentText(str(h12))
            self._min_combo.setCurrentText(f"{mm:02d}")
            mi = self._ampm_combo.findText(ap)
            if mi >= 0:
                self._ampm_combo.setCurrentIndex(mi)
        self._sync_due_controls()

        # Fixed size (~1.5× prior 200×280) so labels and combos are not clipped.
        self.setFixedWidth(350)
        self.resize(350, 200)

    def _sync_due_controls(self) -> None:
        d_on = self._has_date.isChecked()
        self._date_edit.setEnabled(d_on)
        self._has_time.setEnabled(d_on)
        t_on = d_on and self._has_time.isChecked()
        self._hour_combo.setEnabled(t_on)
        self._min_combo.setEnabled(t_on)
        self._ampm_combo.setEnabled(t_on)
        if not d_on:
            self._has_time.setChecked(False)

    def _resolved_task_label(self) -> str:
        typed = self._task_text.text().strip()
        if typed:
            return typed
        deck_text = self._deck_combo.currentText().strip()
        if "::" in deck_text:
            return deck_text.rsplit("::", 1)[-1].strip()
        return deck_text

    def _on_delete_clicked(self) -> None:
        if askUser("Delete this task permanently?"):
            self._deletion_requested = True
            self.accept()

    def _on_ok(self) -> None:
        task = self._resolved_task_label()
        if not task:
            from aqt.utils import showWarning

            showWarning("Please enter a task title.")
            return
        self.accept()

    def deletion_requested(self) -> bool:
        return self._deletion_requested

    def build_payload(self) -> dict:
        deck = self._resolved_task_label()
        linked_deck = self._deck_combo.currentText().strip() or None
        due_date = None
        due_time = None
        if self._has_date.isChecked():
            due_date = self._date_edit.date().toString(Qt.DateFormat.ISODate)
            if self._has_time.isChecked():
                h12 = int(self._hour_combo.currentText())
                minute = int(self._min_combo.currentText())
                due_time = _12h_parts_to_hhmm(
                    h12, minute, self._ampm_combo.currentText()
                )
        return {
            "deck": deck,
            "linked_deck": linked_deck,
            "due_date": due_date,
            "due_time": due_time,
        }


class TodoDialog(QDialog):
    def __init__(self, parent=None):
        # Top-level: no Qt parent, so the OS can show it as a separate taskbar / dock item.
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        self.setWindowTitle("AnKang To-Do List")
        try:
            app = QApplication.instance()
            icon = None
            if app is not None:
                icon = app.windowIcon()
            if (icon is None or icon.isNull()) and mw is not None:
                icon = mw.windowIcon()
            if icon is not None and not icon.isNull():
                self.setWindowIcon(icon)
        except Exception:
            pass
        self.resize(420, 620)
        self.setMinimumSize(280, 360)

        self.addon_path = os.path.dirname(__file__)
        self.save_file = profile_data_file("todo_storage.json")
        self.data = self.load_data()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh_ui)
        self._timer.start(30_000)

        self.setup_ui()

    def showEvent(self, event):
        self._purge_old_archived()
        self.save_data()
        self.refresh_ui()
        return super().showEvent(event)

    def setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setSpacing(8)

        top = QHBoxLayout()
        top.addStretch()
        self._btn_add = _make_icon_toolbutton(
            self.addon_path,
            "C_Plus",
            "CP_Plus",
            QSize(28, 28),
            "Add New Task",
            self,
        )
        self._btn_add.clicked.connect(self._open_add_task)
        top.addWidget(self._btn_add, alignment=Qt.AlignmentFlag.AlignRight)

        self._archive_toggle_btn = _make_icon_toolbutton(
            self.addon_path,
            "C_TrashClosed",
            "CP_TrashOpen",
            QSize(28, 28),
            "Show archived tasks",
            self,
        )
        self._archive_toggle_btn.setCheckable(True)
        self._archive_toggle_btn.toggled.connect(self._toggle_archive)
        top.addWidget(self._archive_toggle_btn, alignment=Qt.AlignmentFlag.AlignRight)
        self.main_layout.addLayout(top)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll, 1)

        self.archive_widget = QWidget()
        self.archive_widget.setVisible(False)
        archive_vbox = QVBoxLayout(self.archive_widget)

        self.archive_list = QListWidget()
        archive_vbox.addWidget(self.archive_list)

        archive_btns_layout = QVBoxLayout()
        unarchive_btn = QPushButton("Unarchive selected")
        unarchive_btn.clicked.connect(self.unarchive_item)
        del_single_btn = QPushButton("Delete selected")
        del_single_btn.clicked.connect(self.delete_archived_item)
        clear_all_btn = QPushButton("Delete all archived")
        clear_all_btn.clicked.connect(self.clear_entire_archive)
        for _b in (unarchive_btn, del_single_btn, clear_all_btn):
            mark_ankang_text_button(_b)
        archive_btns_layout.addWidget(unarchive_btn)
        archive_btns_layout.addWidget(del_single_btn)
        archive_btns_layout.addWidget(clear_all_btn)
        archive_vbox.addLayout(archive_btns_layout)

        note = QLabel(
            "Archived items are automatically deleted after 7 days."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #888; font-size: 11px;")
        archive_vbox.addWidget(note)

        self.main_layout.addWidget(self.archive_widget)

        self.setStyleSheet(ankang_text_button_stylesheet())
        self.refresh_ui()

    def _toggle_archive(self, checked: bool) -> None:
        self.archive_widget.setVisible(checked)
        self._archive_toggle_btn.setToolTip(
            "Hide archived tasks" if checked else "Show archived tasks"
        )

    def _open_add_task(self) -> None:
        dlg = TaskFormDialog(self, addon_dir=self.addon_path, edit_mode=False)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        p = dlg.build_payload()
        self.data["active"].append(
            {
                "id": uuid.uuid4().hex,
                "deck": p["deck"],
                "linked_deck": p.get("linked_deck"),
                "due_date": p["due_date"],
                "due_time": p["due_time"],
                "completed": False,
            }
        )
        self.save_data()
        self.refresh_ui()

    def _open_edit_task(self, task_id: str) -> None:
        item = self._find_active_by_id(task_id)
        if not item:
            return
        dlg = TaskFormDialog(
            self,
            addon_dir=self.addon_path,
            initial=dict(item),
            edit_mode=True,
        )
        code = dlg.exec()
        if dlg.deletion_requested():
            self.data["active"] = [t for t in self.data["active"] if t.get("id") != task_id]
            self.save_data()
            self.refresh_ui()
            return
        if code != QDialog.DialogCode.Accepted:
            return
        p = dlg.build_payload()
        item.update(p)
        self.save_data()
        self.refresh_ui()

    def _find_active_by_id(self, task_id: str) -> dict | None:
        for t in self.data["active"]:
            if t.get("id") == task_id:
                return t
        return None

    def _open_linked_deck_review(self, deck_name: str) -> None:
        if not deck_name or not mw.col:
            return
        deck = mw.col.decks.by_name(deck_name)
        if not deck:
            from aqt.utils import showWarning

            showWarning(f"Deck not found:\n{deck_name}")
            return
        try:
            did = int(deck["id"]) if isinstance(deck, dict) else int(deck.id)
            mw.col.decks.select(did)
            mw.moveToState("overview")
            overview = getattr(mw, "overview", None)
            if overview and hasattr(overview, "onStudyKey"):
                overview.onStudyKey()
        except Exception:
            from aqt.utils import showWarning

            showWarning(f"Could not open deck for review:\n{deck_name}")

    def _toggle_completed(self, task_id: str) -> None:
        item = self._find_active_by_id(task_id)
        if not item:
            return
        item["completed"] = not item.get("completed", False)
        self.save_data()
        self.refresh_ui()

    def _archive_task(self, task_id: str) -> None:
        item = self._find_active_by_id(task_id)
        if not item:
            return
        self.data["active"] = [t for t in self.data["active"] if t.get("id") != task_id]
        arch = {
            "id": item.get("id") or uuid.uuid4().hex,
            "deck": item["deck"],
            "linked_deck": item.get("linked_deck"),
            "due_date": item.get("due_date"),
            "due_time": item.get("due_time"),
            "completed": True,
            "archived_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.data["archived"].append(arch)
        self.save_data()
        self.refresh_ui()

    def _clear_task_rows(self) -> None:
        """Remove rows from the layout and unparent widgets so they do not keep painting."""
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def refresh_ui(self) -> None:
        n_archived_before = len(self.data.get("archived", []))
        self._purge_old_archived()
        archive_purged = len(self.data.get("archived", [])) != n_archived_before

        self._clear_task_rows()

        now = datetime.now()
        active = [t for t in self.data["active"] if isinstance(t, dict)]
        for t in active:
            if "id" not in t or not t["id"]:
                t["id"] = uuid.uuid4().hex
        active.sort(key=_active_sort_key)

        for item in active:
            tid = item["id"]
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.StyledPanel)
            grid = QGridLayout(frame)
            grid.setContentsMargins(4, 4, 4, 4)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(2)

            done = bool(item.get("completed"))
            complete_btn = QPushButton("✓" if done else "")
            complete_btn.setFixedSize(28, 28)
            complete_btn.setToolTip("Mark complete" if not done else "Mark incomplete")
            complete_btn.setStyleSheet(
                "QPushButton { font-weight: bold; border: 1px solid #888; border-radius: 4px; background: #3a3a3a; color: #ccc; }"
                "QPushButton:hover { border: 1px solid #bbb; }"
                + (
                    "QPushButton { background: #4caf50; color: white; border-color: #2e7d32; }"
                    if done
                    else ""
                )
            )
            complete_btn.clicked.connect(lambda *_, tid=tid: self._toggle_completed(tid))

            deck_color, cd_text, cd_tip = _task_row_style(now, item)
            task_title = item.get("deck") or ""
            linked_deck = item.get("linked_deck")
            deck_col = _make_task_title_column(
                task_title,
                linked_deck,
                deck_color,
                done,
                on_open_deck=self._open_linked_deck_review,
            )

            cd_lbl = QLabel(cd_text)
            cd_lbl.setWordWrap(False)
            cd_lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            cd_lbl.setStyleSheet(f"color: {deck_color}; font-size: 11px;")
            cd_lbl.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
            )
            if cd_tip:
                cd_lbl.setToolTip(cd_tip)

            if item.get("completed"):
                side_btn = _make_icon_toolbutton(
                    self.addon_path,
                    "C_TrashClosed",
                    "CP_TrashOpen",
                    QSize(22, 22),
                    "Archive task",
                    frame,
                )
                side_btn.clicked.connect(lambda _=None, i=tid: self._archive_task(i))
            else:
                side_btn = _make_icon_toolbutton(
                    self.addon_path,
                    "C_Tool",
                    "CP_Tool",
                    QSize(22, 22),
                    "Edit task",
                    frame,
                )
                side_btn.clicked.connect(lambda _=None, i=tid: self._open_edit_task(i))

            side_btn.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )

            right_wrap = QWidget(frame)
            right_row = QHBoxLayout(right_wrap)
            right_row.setContentsMargins(0, 0, 0, 0)
            right_row.setSpacing(6)
            right_row.addWidget(cd_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
            right_row.addWidget(side_btn, 0, Qt.AlignmentFlag.AlignVCenter)
            right_wrap.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
            )

            grid.addWidget(
                complete_btn,
                0,
                0,
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            )
            grid.addWidget(deck_col, 0, 1, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(
                right_wrap,
                0,
                2,
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
            )
            grid.setColumnStretch(1, 1)
            self.scroll_layout.addWidget(frame)

        self.archive_list.clear()
        for item in self.data["archived"]:
            if not isinstance(item, dict):
                continue
            d = item.get("deck", "")
            at = item.get("archived_at", "")
            extra = ""
            if at:
                try:
                    s = str(at).replace("Z", "")
                    if "+" in s:
                        s = s.split("+", 1)[0]
                    adt = datetime.fromisoformat(s)
                    extra = f" — archived {format_user_datetime(adt)}"
                except ValueError:
                    extra = f" — archived {at}"
            self.archive_list.addItem(f"{d}{extra}")

        if archive_purged:
            self.save_data()

    def _purge_old_archived(self) -> None:
        cutoff = datetime.now() - timedelta(days=ARCHIVE_RETENTION_DAYS)
        kept = []
        for item in self.data.get("archived", []):
            if not isinstance(item, dict):
                continue
            at_s = item.get("archived_at")
            if not at_s:
                item["archived_at"] = datetime.now().isoformat(timespec="seconds")
                kept.append(item)
                continue
            try:
                at = datetime.fromisoformat(at_s)
            except ValueError:
                kept.append(item)
                continue
            if at >= cutoff:
                kept.append(item)
        if len(kept) != len(self.data["archived"]):
            self.data["archived"] = kept

    def unarchive_item(self) -> None:
        row = self.archive_list.currentRow()
        if row < 0:
            return
        item = self.data["archived"].pop(row)
        item.pop("archived_at", None)
        item["completed"] = False
        if "id" not in item or not item["id"]:
            item["id"] = uuid.uuid4().hex
        self.data["active"].append(item)
        self.save_data()
        self.refresh_ui()

    def delete_archived_item(self) -> None:
        row = self.archive_list.currentRow()
        if row < 0:
            return
        if askUser("Delete this archived item?"):
            self.data["archived"].pop(row)
            self.save_data()
            self.refresh_ui()

    def clear_entire_archive(self) -> None:
        n = len(self.data["archived"])
        if n and askUser(f"Delete all {n} archived items?"):
            self.data["archived"] = []
            self.save_data()
            self.refresh_ui()

    def load_data(self) -> dict:
        if os.path.exists(self.save_file):
            try:
                with open(self.save_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    active_in = data.get("active", [])
                    arch_in = data.get("archived", [])
                    if not isinstance(active_in, list):
                        active_in = []
                    if not isinstance(arch_in, list):
                        arch_in = []
                    col = mw.col
                    if col is None:
                        return {"active": [], "archived": []}
                    active = []
                    for raw in active_in:
                        n = _normalize_item(raw, col) if isinstance(raw, dict) else None
                        if n:
                            active.append(n)
                    archived = []
                    for raw in arch_in:
                        n = _normalize_archived_item(raw, col) if isinstance(raw, dict) else None
                        if n:
                            archived.append(n)
                    return {"active": active, "archived": archived}
            except (OSError, json.JSONDecodeError):
                pass
        return {"active": [], "archived": []}

    def save_data(self) -> None:
        self._purge_old_archived()
        try:
            with open(self.save_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except OSError:
            pass


class TodoWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._todo_dialog: TodoDialog | None = None
        self.save_file = profile_data_file("todo_storage.json")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        addon_path = os.path.dirname(__file__)
        icon_normal_path = os.path.join(addon_path, "media", "Buttons", "Unpressed", "C_Task1.png")
        icon_active_path = os.path.join(addon_path, "media", "Buttons", "Pressed", "CP_Task1.png")

        if os.path.exists(icon_normal_path) and os.path.exists(icon_active_path):
            icon_normal = QIcon(icon_normal_path)
            icon_active = QIcon(icon_active_path)
            self.btn = IconSwapButton(
                icon_normal,
                icon_active,
                icon_size=QSize(56, 56),
                tooltip=self._build_tooltip_text(),
                parent=self,
            )
            self.btn.setFixedSize(64, 64)
            self.btn.clicked.connect(self._open_todo_dialog)
            layout.addWidget(self.btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        else:
            self.btn = QPushButton("TODO")
            self.btn.setToolTip(self._build_tooltip_text())
            self.btn.setFixedSize(50, 42)
            self.btn.clicked.connect(self._open_todo_dialog)
            mark_ankang_text_button(self.btn)
            layout.addWidget(self.btn)

    def _open_todo_dialog(self) -> None:
        self.btn.setToolTip(self._build_tooltip_text())
        if self._todo_dialog is None:
            self._todo_dialog = TodoDialog(None)
            self._todo_dialog.destroyed.connect(self._on_todo_dialog_closed)
        self._todo_dialog.show()
        self._todo_dialog.raise_()
        self._todo_dialog.activateWindow()

    def _on_todo_dialog_closed(self) -> None:
        self._todo_dialog = None
        self.btn.setToolTip(self._build_tooltip_text())

    def _build_tooltip_text(self) -> str:
        tasks = self._load_active_tasks_for_tooltip()
        tooltip_rows: list[tuple[str, str]] = []
        now = datetime.now()

        for item in tasks:
            title = (item.get("deck") or "").strip()
            if not title:
                continue
            due_dt = _parse_due_datetime(item.get("due_date"), item.get("due_time"))
            if due_dt is None:
                due_text = "No due date"
            else:
                remaining_seconds_raw = int((due_dt - now).total_seconds())
                if remaining_seconds_raw < 0:
                    due_text = "OVERDUE"
                elif remaining_seconds_raw < 24 * 60 * 60:
                    remaining_seconds = remaining_seconds_raw
                    hours, rem = divmod(remaining_seconds, 3600)
                    minutes = rem // 60
                    due_text = f"Due in {hours}h {minutes}m"
                else:
                    days_until = max(0, (due_dt.date() - now.date()).days)
                    due_text = f"Due in {days_until}d"
            tooltip_rows.append((title, due_text))

        lines = ["AnKang To-Do List:", ""]
        if not tooltip_rows:
            lines.append("No tasks. Add one now!")
            return "\n".join(lines)

        for title, due_text in tooltip_rows[:5]:
            lines.append(f"{title} - {due_text}")
        return "\n".join(lines)

    def _load_active_tasks_for_tooltip(self) -> list[dict]:
        if not os.path.exists(self.save_file):
            return []
        try:
            with open(self.save_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, dict):
            return []
        active = data.get("active", [])
        if not isinstance(active, list):
            return []
        out: list[dict] = []
        for item in active:
            if not isinstance(item, dict):
                continue
            if item.get("completed"):
                continue
            out.append(item)
        out.sort(key=_active_sort_key)
        return out
