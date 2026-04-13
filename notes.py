from __future__ import annotations

import json
import os
import uuid

from aqt import mw
from aqt.qt import *
from aqt.utils import askUser, showWarning

from .ankang_format_styles import ankang_text_button_stylesheet, mark_ankang_text_button


def _safe_anki_id(val: object) -> int | None:
    """Parse note/card id from JSON (int/str) without raising."""
    if val is None or isinstance(val, bool):
        return None
    try:
        if isinstance(val, int):
            return val
        if isinstance(val, float):
            return int(val) if val == int(val) else None
        return int(str(val).strip())
    except (TypeError, ValueError):
        return None


def open_anki_card_in_browser(anki_note_id: int | None, anki_card_id: int | None) -> None:
    """Open the Anki Browser filtered to the linked note or card."""
    nid = _safe_anki_id(anki_note_id)
    cid = _safe_anki_id(anki_card_id)
    if cid is None and nid is None:
        showWarning("This note has no valid linked Anki card id.")
        return
    query = f"cid:{cid}" if cid is not None else f"nid:{nid}"

    def _go() -> None:
        import aqt

        browser = aqt.dialogs.open("Browser", mw)
        browser.form.searchEdit.lineEdit().setText(query)
        browser.onSearchActivated()

    QTimer.singleShot(0, _go)

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


def _empty_notes_root() -> dict:
    """Fresh install: no books until the user adds one."""
    return {"version": 2, "books": {}}


def _notes_toolbar_icon_button(
    addon_dir: str,
    unpressed_base: str,
    pressed_base: str,
    tooltip: str,
    parent: QWidget,
    *,
    icon_px: int = 22,
) -> QWidget:
    """Small IconSwapButton for notes dialog toolbar, or text fallback if assets missing."""
    u = os.path.join(addon_dir, "media", "Buttons", "Unpressed", f"{unpressed_base}.png")
    p = os.path.join(addon_dir, "media", "Buttons", "Pressed", f"{pressed_base}.png")
    pad = 6
    btn_w = icon_px + pad
    if os.path.exists(u) and os.path.exists(p):
        btn = IconSwapButton(
            QIcon(u),
            QIcon(p),
            icon_size=QSize(icon_px, icon_px),
            tooltip=tooltip,
            parent=parent,
        )
        btn.setFixedSize(btn_w, btn_w)
        return btn
    fb = QPushButton("•")
    fb.setToolTip(tooltip)
    fb.setFixedSize(btn_w, btn_w)
    mark_ankang_text_button(fb)
    return fb


def _ensure_books_shape(data: dict) -> None:
    books = data.setdefault("books", {})
    if not isinstance(books, dict):
        data["books"] = {}
        books = data["books"]
    for book_name, chmap in list(books.items()):
        if not isinstance(book_name, str) or not book_name.strip():
            del books[book_name]
            continue
        if not isinstance(chmap, dict):
            books[book_name] = {}
            chmap = books[book_name]
        for ch_name, lst in list(chmap.items()):
            if not isinstance(ch_name, str) or not ch_name.strip():
                del chmap[ch_name]
                continue
            if not isinstance(lst, list):
                chmap[ch_name] = []


class MoveNoteDialog(QDialog):
    """Choose an existing book and chapter, then confirm to move the note."""

    def __init__(self, notes_dialog, source_book: str, source_chapter: str):
        super().__init__(notes_dialog)
        self.setWindowTitle("Move note")
        self.setModal(True)
        self._nd = notes_dialog

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)
        root.addWidget(
            QLabel("Choose a book and chapter, then click Confirm to move the note.")
        )
        root.addWidget(QLabel("Book:"))
        self._book = QComboBox(self)
        for b in self._nd._books_dict().keys():
            self._book.addItem(b)
        if self._book.findText(source_book) >= 0:
            self._book.setCurrentText(source_book)
        root.addWidget(self._book)

        root.addWidget(QLabel("Chapter:"))
        self._chapter = QComboBox(self)
        root.addWidget(self._chapter)

        self._book.currentTextChanged.connect(self._refill_chapters)
        self._refill_chapters(prefer_chapter=source_chapter)

        row = QHBoxLayout()
        row.addStretch()
        confirm = QPushButton("Confirm")
        cancel = QPushButton("Cancel")
        for b in (confirm, cancel):
            mark_ankang_text_button(b)
        confirm.clicked.connect(self._try_accept)
        cancel.clicked.connect(self.reject)
        row.addWidget(confirm)
        row.addWidget(cancel)
        root.addLayout(row)

        self.setStyleSheet(ankang_text_button_stylesheet())
        self.setMinimumWidth(320)

    def _refill_chapters(self, prefer_chapter: str | None = None) -> None:
        self._chapter.blockSignals(True)
        self._chapter.clear()
        b = self._book.currentText()
        chm = self._nd._books_dict().get(b, {})
        if isinstance(chm, dict):
            for c in chm.keys():
                self._chapter.addItem(c)
        self._chapter.blockSignals(False)
        if not self._chapter.count():
            return
        if prefer_chapter and self._chapter.findText(prefer_chapter) >= 0:
            self._chapter.setCurrentText(prefer_chapter)
        else:
            self._chapter.setCurrentIndex(0)

    def _try_accept(self) -> None:
        if self._chapter.count() == 0:
            showWarning("That book has no chapters. Add a chapter first.")
            return
        self.accept()

    def destination(self) -> tuple[str, str]:
        return self._book.currentText().strip(), self._chapter.currentText().strip()


class NotesDialog(QDialog):
    """Dynamic books → chapters → notes (JSON on disk)."""

    def __init__(self, save_path: str, legacy_txt: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._save_path = save_path
        self._legacy_txt = legacy_txt
        self.setWindowTitle("AnKang Notes")
        self.resize(520, 560)
        self.setMinimumSize(380, 420)

        self._data = _empty_notes_root()
        self._load_or_migrate()
        self._current_note_id: str | None = None
        self._prev_book = ""
        self._prev_chapter = ""
        self._addon_path = os.path.dirname(__file__)

        root = QVBoxLayout(self)
        root.setSpacing(6)

        row_book = QHBoxLayout()
        row_book.setSpacing(4)
        ap = self._addon_path
        self._book_add_btn = _notes_toolbar_icon_button(
            ap, "C_Plus", "CP_Plus", "Add New Book", self
        )
        self._book_rename_btn = _notes_toolbar_icon_button(
            ap, "C_Note2", "CP_Note2", "Rename Book", self
        )
        self._book_del_btn = _notes_toolbar_icon_button(
            ap, "C_TrashClosed", "CP_TrashOpen", "Delete Book", self
        )
        self._book_add_btn.clicked.connect(self._new_book)
        self._book_rename_btn.clicked.connect(self._rename_book)
        self._book_del_btn.clicked.connect(self._delete_book)
        for w in (self._book_add_btn, self._book_rename_btn, self._book_del_btn):
            row_book.addWidget(w)
        row_book.addWidget(QLabel("Book:"))
        self._book = QComboBox(self)
        row_book.addWidget(self._book, 1)
        root.addLayout(row_book)

        row_ch = QHBoxLayout()
        row_ch.setSpacing(4)
        self._ch_add_btn = _notes_toolbar_icon_button(
            ap, "C_Plus", "CP_Plus", "Add New Chapter", self
        )
        self._ch_rename_btn = _notes_toolbar_icon_button(
            ap, "C_Note2", "CP_Note2", "Rename Chapter", self
        )
        self._ch_del_btn = _notes_toolbar_icon_button(
            ap, "C_TrashClosed", "CP_TrashOpen", "Delete Chapter", self
        )
        self._ch_add_btn.clicked.connect(self._new_chapter)
        self._ch_rename_btn.clicked.connect(self._rename_chapter)
        self._ch_del_btn.clicked.connect(self._delete_chapter)
        for w in (self._ch_add_btn, self._ch_rename_btn, self._ch_del_btn):
            row_ch.addWidget(w)
        row_ch.addWidget(QLabel("Chapter:"))
        self._chapter = QComboBox(self)
        row_ch.addWidget(self._chapter, 1)
        root.addLayout(row_ch)

        mid = QHBoxLayout()
        list_col = QVBoxLayout()
        list_col.setSpacing(4)
        note_actions = QHBoxLayout()
        note_actions.setSpacing(6)
        self._new_note_btn = QPushButton("New note")
        mark_ankang_text_button(self._new_note_btn)
        self._new_note_btn.clicked.connect(self._new_note)
        note_actions.addWidget(self._new_note_btn)
        self._del_note_btn = _notes_toolbar_icon_button(
            ap, "C_TrashClosed", "CP_TrashOpen", "Delete note", self
        )
        self._del_note_btn.clicked.connect(self._delete_note)
        note_actions.addWidget(self._del_note_btn)
        note_actions.addStretch(1)
        list_col.addLayout(note_actions)
        self._list = QListWidget(self)
        self._list.setMinimumWidth(160)
        list_col.addWidget(self._list, 1)
        mid.addLayout(list_col, 1)

        editor_col = QVBoxLayout()
        editor_col.addWidget(QLabel("Title"))
        self._title = QLineEdit(self)
        editor_col.addWidget(self._title)
        editor_col.addWidget(QLabel("Note"))
        self._body = QTextEdit(self)
        self._body.setPlaceholderText("Write your note…")
        editor_col.addWidget(self._body, 1)
        mid.addLayout(editor_col, 2)
        root.addLayout(mid, 1)

        btn_row = QHBoxLayout()
        self._move_note_btn = QPushButton("Move Note")
        mark_ankang_text_button(self._move_note_btn)
        self._move_note_btn.clicked.connect(self._move_note)
        self._open_anki_btn = QPushButton("Open Anki card")
        mark_ankang_text_button(self._open_anki_btn)
        self._open_anki_btn.setToolTip("Open the linked card in the Anki Browser")
        self._open_anki_btn.clicked.connect(self._on_open_anki_card)
        self._open_anki_btn.hide()
        save_btn = QPushButton("Save")
        close_btn = QPushButton("Close")
        for b in (save_btn, close_btn):
            mark_ankang_text_button(b)
        save_btn.clicked.connect(self._save_note_and_file)
        close_btn.clicked.connect(self._on_close)
        btn_row.addWidget(self._move_note_btn)
        btn_row.addWidget(self._open_anki_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        self._book.currentTextChanged.connect(self._on_book_changed)
        self._chapter.currentTextChanged.connect(self._on_chapter_changed)
        self._list.currentItemChanged.connect(self._on_note_selected)

        self.setStyleSheet(ankang_text_button_stylesheet())
        _ensure_books_shape(self._data)
        self._refresh_book_combo()
        self._refresh_chapter_combo()
        self._prev_book = self._book.currentText()
        self._prev_chapter = self._chapter.currentText()
        self._sync_list_from_data()

    def _books_dict(self) -> dict:
        return self._data.setdefault("books", {})

    def _load_or_migrate(self) -> None:
        if os.path.exists(self._save_path):
            try:
                with open(self._save_path, encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict) and isinstance(raw.get("books"), dict):
                    self._data = raw
            except (OSError, json.JSONDecodeError):
                pass
        elif os.path.exists(self._legacy_txt):
            try:
                with open(self._legacy_txt, encoding="utf-8") as f:
                    txt = f.read()
            except OSError:
                txt = ""
            self._data = _empty_notes_root()
            _ensure_books_shape(self._data)
            nid = uuid.uuid4().hex
            self._books_dict()["Exam"] = {"Lecture": [{"id": nid, "title": "Imported", "body": txt}]}
        _ensure_books_shape(self._data)

    def _current_book(self) -> str:
        return self._book.currentText().strip()

    def _current_chapter(self) -> str:
        return self._chapter.currentText().strip()

    def _notes_at(self, book: str, chapter: str) -> list:
        _ensure_books_shape(self._data)
        if not book or not chapter:
            return []
        bmap = self._books_dict().setdefault(book, {})
        return bmap.setdefault(chapter, [])

    def _chapter_list(self) -> list:
        return self._notes_at(self._current_book(), self._current_chapter())

    def _refresh_book_combo(self, *, select_name: str | None = None) -> None:
        self._book.blockSignals(True)
        self._book.clear()
        books = self._books_dict()
        for name in books.keys():
            self._book.addItem(name)
        self._book.blockSignals(False)
        if self._book.count() == 0:
            return
        if select_name and self._book.findText(select_name) >= 0:
            self._book.setCurrentText(select_name)
        else:
            self._book.setCurrentIndex(0)

    def _refresh_chapter_combo(self, *, select_name: str | None = None) -> None:
        self._chapter.blockSignals(True)
        self._chapter.clear()
        book = self._current_book()
        chmap = self._books_dict().get(book)
        if isinstance(chmap, dict):
            for name in chmap.keys():
                self._chapter.addItem(name)
        self._chapter.blockSignals(False)
        if self._chapter.count() == 0:
            return
        if select_name and self._chapter.findText(select_name) >= 0:
            self._chapter.setCurrentText(select_name)
        else:
            self._chapter.setCurrentIndex(0)

    def _list_set_title_for_id(self, nid: str, title: str) -> None:
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it is not None and it.data(Qt.ItemDataRole.UserRole) == nid:
                it.setText(title)
                break

    def _flush_into_path(self, book: str, chapter: str) -> None:
        if not self._current_note_id:
            return
        if not book or not chapter:
            return
        for note in self._notes_at(book, chapter):
            if note.get("id") == self._current_note_id:
                note["title"] = self._title.text().strip() or "Untitled"
                note["body"] = self._body.toPlainText()
                self._list_set_title_for_id(self._current_note_id, note["title"])
                break

    def _refresh_anki_link_button(self) -> None:
        self._open_anki_btn.hide()
        nid = self._current_note_id
        if not nid:
            return
        for note in self._chapter_list():
            if note.get("id") == nid:
                if _safe_anki_id(note.get("anki_card_id")) is not None or _safe_anki_id(
                    note.get("anki_note_id")
                ) is not None:
                    self._open_anki_btn.show()
                return

    def _on_open_anki_card(self) -> None:
        nid = self._current_note_id
        if not nid:
            return
        for note in self._chapter_list():
            if note.get("id") == nid:
                an = note.get("anki_note_id")
                ac = note.get("anki_card_id")
                open_anki_card_in_browser(an, ac)
                return

    def _ensure_note_target(self) -> None:
        """Ensure at least one book/chapter exists; select a target for new notes."""
        _ensure_books_shape(self._data)
        books = self._books_dict()
        created = False
        if not books:
            books["Clippings"] = {"Inbox": []}
            created = True
        if created:
            select_book, select_ch = "Clippings", "Inbox"
        else:
            clippings = books.get("Clippings")
            if isinstance(clippings, dict):
                select_book = "Clippings"
                if "Inbox" in clippings:
                    select_ch = "Inbox"
                elif not clippings:
                    clippings["Inbox"] = []
                    select_ch = "Inbox"
                else:
                    select_ch = sorted(clippings.keys())[0]
            else:
                select_book = sorted(books.keys())[0]
                chmap = books.setdefault(select_book, {})
                if not chmap:
                    chmap["Inbox"] = []
                select_ch = sorted(chmap.keys())[0]
        self._refresh_book_combo(select_name=select_book)
        self._refresh_chapter_combo(select_name=select_ch)
        self._prev_book = self._current_book()
        self._prev_chapter = self._current_chapter()
        self._sync_list_from_data()

    def _prepare_quote_note(
        self,
        quote: str,
        anki_note_id: int | None,
        anki_card_id: int | None,
    ) -> None:
        """Append a note with quoted text and optional Anki Browser link metadata."""
        self._ensure_note_target()
        book, ch = self._current_book(), self._current_chapter()
        if not book or not ch:
            showWarning("Could not pick a book/chapter for the new note.")
            return
        q = quote.replace("\r\n", "\n").strip()
        lines = q.split("\n") if q else [""]
        sn = _safe_anki_id(anki_note_id)
        sc = _safe_anki_id(anki_card_id)
        body = "\n".join(f"> {line}" for line in lines)
        if sn is not None or sc is not None:
            body += '\n\n—\nOpen the linked card with "Open Anki card" below.'

        first_line = lines[0].strip() if lines else ""
        title = (first_line[:60] + "…") if len(first_line) > 60 else first_line
        if not title:
            title = "Quote from Anki"

        nid = uuid.uuid4().hex
        note: dict = {"id": nid, "title": title, "body": body}
        if sn is not None:
            note["anki_note_id"] = sn
        if sc is not None:
            note["anki_card_id"] = sc

        self._flush_into_path(book, ch)
        self._notes_at(book, ch).append(note)
        self._sync_list_from_data(select_note_id=nid)
        self._persist()

    def _sync_list_from_data(self, *, select_note_id: str | None = None) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        book, ch = self._current_book(), self._current_chapter()
        if not book or not ch:
            self._list.blockSignals(False)
            self._current_note_id = None
            self._title.clear()
            self._body.clear()
            self._open_anki_btn.hide()
            return
        for note in self._notes_at(book, ch):
            nid = note.get("id") or ""
            title = (note.get("title") or "Untitled").strip() or "Untitled"
            it = QListWidgetItem(title)
            it.setData(Qt.ItemDataRole.UserRole, nid)
            self._list.addItem(it)
        self._list.blockSignals(False)
        if not self._list.count():
            self._current_note_id = None
            self._title.clear()
            self._body.clear()
            self._open_anki_btn.hide()
            return
        if select_note_id:
            for i in range(self._list.count()):
                it = self._list.item(i)
                if it is not None and it.data(Qt.ItemDataRole.UserRole) == select_note_id:
                    self._list.blockSignals(True)
                    self._list.setCurrentRow(i)
                    self._list.blockSignals(False)
                    self._current_note_id = select_note_id
                    for note in self._notes_at(book, ch):
                        if note.get("id") == select_note_id:
                            self._title.setText(note.get("title") or "")
                            self._body.setPlainText(note.get("body") or "")
                            break
                    self._prev_book = book
                    self._prev_chapter = ch
                    self._refresh_anki_link_button()
                    return
        self._list.setCurrentRow(0)
        self._refresh_anki_link_button()

    def _on_book_changed(self, _t: str) -> None:
        self._flush_into_path(self._prev_book, self._prev_chapter)
        self._prev_book = self._current_book()
        self._refresh_chapter_combo()
        self._prev_chapter = self._current_chapter()
        self._sync_list_from_data()

    def _on_chapter_changed(self, _t: str) -> None:
        self._flush_into_path(self._prev_book, self._prev_chapter)
        self._prev_book = self._current_book()
        self._prev_chapter = self._current_chapter()
        self._sync_list_from_data()

    def _on_note_selected(self, cur: QListWidgetItem | None, _prev) -> None:
        if cur is None:
            return
        self._flush_into_path(self._prev_book, self._prev_chapter)
        self._prev_book = self._current_book()
        self._prev_chapter = self._current_chapter()
        nid = cur.data(Qt.ItemDataRole.UserRole)
        if not isinstance(nid, str):
            return
        self._current_note_id = nid
        for note in self._chapter_list():
            if note.get("id") == nid:
                self._title.setText(note.get("title") or "")
                self._body.setPlainText(note.get("body") or "")
                break
        self._refresh_anki_link_button()

    def _new_book(self) -> None:
        name, ok = QInputDialog.getText(self, "New book", "Book name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            showWarning("Book name cannot be empty.")
            return
        if name in self._books_dict():
            showWarning("A book with that name already exists.")
            return
        self._flush_into_path(self._prev_book, self._prev_chapter)
        self._books_dict()[name] = {"Chapter 1": []}
        self._refresh_book_combo(select_name=name)
        self._refresh_chapter_combo(select_name="Chapter 1")
        self._prev_book = self._current_book()
        self._prev_chapter = self._current_chapter()
        self._sync_list_from_data()
        self._persist()

    def _rename_book(self) -> None:
        old = self._current_book()
        if not old:
            return
        new, ok = QInputDialog.getText(
            self, "Rename book", "New book name:", text=old
        )
        if not ok:
            return
        new = new.strip()
        if not new:
            showWarning("Book name cannot be empty.")
            return
        if new == old:
            return
        if new in self._books_dict():
            showWarning("A book with that name already exists.")
            return
        self._flush_into_path(self._prev_book, self._prev_chapter)
        books = self._books_dict()
        books[new] = books.pop(old)
        self._refresh_book_combo(select_name=new)
        self._refresh_chapter_combo()
        self._prev_book = self._current_book()
        self._prev_chapter = self._current_chapter()
        self._sync_list_from_data()
        self._persist()

    def _delete_book(self) -> None:
        book = self._current_book()
        if not book:
            return
        nch = len(self._books_dict().get(book, {}))
        nnotes = sum(len(v) for v in self._books_dict().get(book, {}).values() if isinstance(v, list))
        msg = f'Delete book "{book}" and all {nch} chapter(s) / {nnotes} note(s) inside it?'
        if not askUser(msg):
            return
        self._flush_into_path(self._prev_book, self._prev_chapter)
        self._books_dict().pop(book, None)
        self._current_note_id = None
        self._title.clear()
        self._body.clear()
        self._refresh_book_combo()
        self._refresh_chapter_combo()
        self._prev_book = self._current_book()
        self._prev_chapter = self._current_chapter()
        self._sync_list_from_data()
        self._persist()

    def _new_chapter(self) -> None:
        book = self._current_book()
        if not book:
            showWarning("Select or create a book first.")
            return
        name, ok = QInputDialog.getText(self, "New chapter", "Chapter name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            showWarning("Chapter name cannot be empty.")
            return
        chmap = self._books_dict().setdefault(book, {})
        if name in chmap:
            showWarning("A chapter with that name already exists in this book.")
            return
        self._flush_into_path(self._prev_book, self._prev_chapter)
        chmap[name] = []
        self._refresh_chapter_combo(select_name=name)
        self._prev_book = self._current_book()
        self._prev_chapter = self._current_chapter()
        self._sync_list_from_data()
        self._persist()

    def _rename_chapter(self) -> None:
        book = self._current_book()
        old = self._current_chapter()
        if not book or not old:
            showWarning("Select a book and chapter first.")
            return
        new, ok = QInputDialog.getText(
            self, "Rename chapter", "New chapter name:", text=old
        )
        if not ok:
            return
        new = new.strip()
        if not new:
            showWarning("Chapter name cannot be empty.")
            return
        if new == old:
            return
        chmap = self._books_dict().get(book)
        if not isinstance(chmap, dict):
            return
        if new in chmap:
            showWarning("A chapter with that name already exists in this book.")
            return
        self._flush_into_path(self._prev_book, self._prev_chapter)
        chmap[new] = chmap.pop(old)
        self._refresh_chapter_combo(select_name=new)
        self._prev_book = self._current_book()
        self._prev_chapter = self._current_chapter()
        self._sync_list_from_data()
        self._persist()

    def _delete_chapter(self) -> None:
        book = self._current_book()
        chapter = self._current_chapter()
        if not book or not chapter:
            return
        chmap = self._books_dict().get(book)
        if not isinstance(chmap, dict) or chapter not in chmap:
            return
        nnotes = len(chmap[chapter]) if isinstance(chmap[chapter], list) else 0
        if not askUser(f'Delete chapter "{chapter}" and its {nnotes} note(s)?'):
            return
        self._flush_into_path(self._prev_book, self._prev_chapter)
        chmap.pop(chapter, None)
        self._current_note_id = None
        self._title.clear()
        self._body.clear()
        self._refresh_chapter_combo()
        self._prev_book = self._current_book()
        self._prev_chapter = self._current_chapter()
        self._sync_list_from_data()
        self._persist()

    def _new_note(self) -> None:
        book, ch = self._current_book(), self._current_chapter()
        if not book or not ch:
            showWarning("Select a book and chapter first.")
            return
        # Flush using visible book/chapter so edits are saved before the list is rebuilt.
        self._flush_into_path(book, ch)
        had_selection = self._current_note_id is not None
        self._prev_book = book
        self._prev_chapter = ch
        nid = uuid.uuid4().hex
        if had_selection:
            self._chapter_list().append({"id": nid, "title": "New note", "body": ""})
        else:
            # No row selected: typed title/body belong to the new note, not a lost flush.
            t = self._title.text().strip() or "New note"
            b = self._body.toPlainText()
            self._chapter_list().append({"id": nid, "title": t, "body": b})
        self._sync_list_from_data(select_note_id=nid)
        self._persist()

    def _delete_note(self) -> None:
        self._flush_into_path(self._current_book(), self._current_chapter())
        row = self._list.currentRow()
        if row < 0:
            return
        it = self._list.item(row)
        nid = it.data(Qt.ItemDataRole.UserRole)
        title = (it.text() or "").strip() or "Untitled"
        if not askUser(f'Delete note "{title}"?'):
            return
        lst = self._chapter_list()
        self._chapter_list()[:] = [n for n in lst if n.get("id") != nid]
        self._current_note_id = None
        self._title.clear()
        self._body.clear()
        self._sync_list_from_data()
        self._persist()

    def _move_note(self) -> None:
        self._flush_into_path(self._current_book(), self._current_chapter())
        nid = self._current_note_id
        if not nid or self._list.currentRow() < 0:
            showWarning("Select a note to move first.")
            return
        src_b, src_c = self._current_book(), self._current_chapter()
        if not src_b or not src_c:
            showWarning("Select a book and chapter first.")
            return
        note_obj: dict | None = None
        for n in self._notes_at(src_b, src_c):
            if n.get("id") == nid:
                note_obj = {
                    "id": str(n["id"]),
                    "title": n.get("title") or "",
                    "body": n.get("body") or "",
                }
                for key in ("anki_note_id", "anki_card_id"):
                    if key in n:
                        note_obj[key] = n[key]
                break
        if not note_obj:
            showWarning("Could not find that note.")
            return
        if not self._books_dict():
            return
        dlg = MoveNoteDialog(self, src_b, src_c)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        dst_b, dst_c = dlg.destination()
        if not dst_b or not dst_c:
            return
        if dst_b == src_b and dst_c == src_c:
            return
        src_list = self._notes_at(src_b, src_c)
        src_list[:] = [x for x in src_list if x.get("id") != nid]
        dest_list = self._notes_at(dst_b, dst_c)
        dest_list.append(note_obj)
        self._book.blockSignals(True)
        self._chapter.blockSignals(True)
        if self._book.findText(dst_b) >= 0:
            self._book.setCurrentText(dst_b)
        self._refresh_chapter_combo(select_name=dst_c)
        self._chapter.blockSignals(False)
        self._book.blockSignals(False)
        self._prev_book = dst_b
        self._prev_chapter = dst_c
        self._sync_list_from_data(select_note_id=nid)
        self._persist()

    def _save_note_and_file(self) -> None:
        self._flush_into_path(self._current_book(), self._current_chapter())
        self._persist()

    def _on_close(self) -> None:
        self._flush_into_path(self._current_book(), self._current_chapter())
        self._persist()
        self.accept()

    def _persist(self) -> None:
        _ensure_books_shape(self._data)
        try:
            with open(self._save_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError:
            pass


def ankang_open_notes_with_quote(
    quote: str,
    anki_note_id: int | None,
    anki_card_id: int | None,
) -> None:
    """Open AnKang Notes with a new note: quoted selection and optional Anki Browser link."""
    addon_dir = os.path.dirname(__file__)
    save_path = os.path.join(addon_dir, "ankang_sidebar_notes.json")
    legacy_txt = os.path.join(addon_dir, "ankang_sidebar_notes.txt")
    dlg = NotesDialog(save_path, legacy_txt, mw)
    dlg._prepare_quote_note(quote, anki_note_id, anki_card_id)
    dlg.exec()


class NotesWidget(QWidget):
    """Large icon button (same chrome as To-do List) opening structured notes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        addon_path = os.path.dirname(__file__)
        icon_normal_path = os.path.join(
            addon_path, "media", "Buttons", "Unpressed", "C_Note1.png"
        )
        icon_active_path = os.path.join(
            addon_path, "media", "Buttons", "Pressed", "CP_Note1.png"
        )
        self._save_path = os.path.join(addon_path, "ankang_sidebar_notes.json")
        self._legacy_txt = os.path.join(addon_path, "ankang_sidebar_notes.txt")

        if os.path.exists(icon_normal_path) and os.path.exists(icon_active_path):
            self.btn = IconSwapButton(
                QIcon(icon_normal_path),
                QIcon(icon_active_path),
                icon_size=QSize(56, 56),
                tooltip="Notes",
                parent=self,
            )
            self.btn.setFixedSize(64, 64)
            self.btn.clicked.connect(self._open)
            layout.addWidget(self.btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        else:
            self.btn = QPushButton("Notes")
            self.btn.setToolTip("Notes")
            self.btn.setFixedSize(50, 42)
            self.btn.clicked.connect(self._open)
            mark_ankang_text_button(self.btn)
            layout.addWidget(self.btn)

    def _open(self) -> None:
        NotesDialog(self._save_path, self._legacy_txt, self).exec()
