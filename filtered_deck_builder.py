from __future__ import annotations

from dataclasses import dataclass

from aqt import mw
from aqt.qt import *
from aqt.utils import showInfo, showWarning

from .ankang_format_styles import ankang_text_button_stylesheet, mark_ankang_text_button

_STEP1_ROOT = "#AK_Step1_v12"
_RESOURCE_TAGS: tuple[str, ...] = (
    f"{_STEP1_ROOT}::#Bootcamp",
    f"{_STEP1_ROOT}::#Pathoma",
    f"{_STEP1_ROOT}::#SketchyMicro",
    f"{_STEP1_ROOT}::#SketchyPharm",
)
_YIELD_ROOT = f"{_STEP1_ROOT}::#Low/HighYield"


@dataclass
class _BuilderState:
    query: str
    count: int


def _collection_tags() -> list[str]:
    tags_obj = getattr(getattr(mw, "col", None), "tags", None)
    if tags_obj is None:
        return []
    raw = []
    if hasattr(tags_obj, "all"):
        try:
            raw = tags_obj.all()
        except Exception:
            raw = []
    elif hasattr(tags_obj, "all_tags"):
        try:
            raw = tags_obj.all_tags()
        except Exception:
            raw = []
    out: list[str] = []
    for t in raw or []:
        if isinstance(t, str) and t.strip():
            out.append(t.strip())
    return sorted(set(out), key=str.lower)


def _child_tags(prefix: str, all_tags: list[str]) -> list[str]:
    """Return all direct children under prefix, including branch nodes."""
    pref = prefix + "::"
    out: set[str] = set()
    for t in all_tags:
        if not t.startswith(pref):
            continue
        tail = t[len(pref):]
        if not tail:
            continue
        child_name = tail.split("::", 1)[0]
        if not child_name:
            continue
        out.add(f"{prefix}::{child_name}")
    return sorted(out, key=str.lower)


def _quote_tag(tag: str) -> str:
    return f'tag:"{tag}"'


def _segment_name(tag: str) -> str:
    return tag.rsplit("::", 1)[-1].strip()


class Step1V12DeckBuilderDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent or mw)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
        self.setWindowTitle("AnKang Filtered Deck Builder")
        self.setMinimumWidth(680)
        self._all_tags = _collection_tags()
        self._last_preview = _BuilderState(query="", count=0)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        info = QLabel(
            "Build a filtered deck (currently only using select AnKing* Step 1 v12 tags).\n"
            "Select one required resource, optional sub-tags, and optional Low/HighYield filters."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._resource_combo = QComboBox()
        self._resource_combo.setMinimumWidth(320)
        for tag in _RESOURCE_TAGS:
            self._resource_combo.addItem(_segment_name(tag), tag)
        self._resource_combo.currentTextChanged.connect(self._refresh_resource_subtags)
        form.addRow("3rd-Party Resource:", self._resource_combo)

        self._subtag_combos: list[QComboBox] = []
        for i in range(3):
            cb = QComboBox()
            cb.addItem("(none)")
            self._subtag_combos.append(cb)
            form.addRow(f"Optional sub-tag {i+1}:", cb)
        self._subtag_combos[0].currentTextChanged.connect(self._refresh_subtag2)
        self._subtag_combos[1].currentTextChanged.connect(self._refresh_subtag3)

        self._yield_combo = QComboBox()
        self._yield_list = QListWidget()
        self._yield_list.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self._yield_list.setMinimumHeight(82)
        self._yield_list.setMaximumHeight(110)
        self._all_yields_item = QListWidgetItem("All Yields")
        self._all_yields_item.setData(Qt.ItemDataRole.UserRole, None)
        self._yield_list.addItem(self._all_yields_item)
        for t in _child_tags(_YIELD_ROOT, self._all_tags):
            it = QListWidgetItem(_segment_name(t))
            it.setData(Qt.ItemDataRole.UserRole, t)
            self._yield_list.addItem(it)
        self._yield_syncing = False
        self._all_yields_item.setSelected(True)
        self._yield_list.itemSelectionChanged.connect(self._on_yield_selection_changed)
        form.addRow("Low/HighYield (AND):", self._yield_list)

        root.addLayout(form)

        self._preview_label = QLabel("Preview: not run yet")
        self._preview_label.setWordWrap(True)
        self._preview_query = QTextEdit()
        self._preview_query.setReadOnly(True)
        self._preview_query.setFixedHeight(72)
        root.addWidget(self._preview_label)
        root.addWidget(self._preview_query)

        disclaimer = QLabel(
            "Disclaimer: AnKang is not affiliated, associated, authorized, endorsed by, or in any way officially connected with "
            "AnKing, Bootcamp, FSMB, NBME, Pathoma, Sketchy, USMLE or any of their subsidiaries or its affiliates."
        )
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("font-size: 10px; color: #8f8f8f;")
        root.addWidget(disclaimer)

        btn_row = QHBoxLayout()
        preview_btn = QPushButton("Preview")
        build_btn = QPushButton("Create / Update Deck")
        close_btn = QPushButton("Close")
        for b in (preview_btn, build_btn, close_btn):
            mark_ankang_text_button(b)
        preview_btn.clicked.connect(self._run_preview)
        build_btn.clicked.connect(self._create_or_update)
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(preview_btn)
        btn_row.addWidget(build_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        self.setStyleSheet(ankang_text_button_stylesheet())
        self._refresh_resource_subtags()

    def _refresh_resource_subtags(self) -> None:
        resource = self._combo_selected_tag(self._resource_combo)
        resource = resource or _RESOURCE_TAGS[0]
        self._fill_combo_with_tags(self._subtag_combos[0], _child_tags(resource, self._all_tags))
        self._fill_combo_with_tags(self._subtag_combos[1], [])
        self._fill_combo_with_tags(self._subtag_combos[2], [])

    def _refresh_subtag2(self) -> None:
        s1 = self._combo_selected_tag(self._subtag_combos[0])
        if not s1:
            self._fill_combo_with_tags(self._subtag_combos[1], [])
            self._fill_combo_with_tags(self._subtag_combos[2], [])
            return
        self._fill_combo_with_tags(self._subtag_combos[1], _child_tags(s1, self._all_tags))
        self._fill_combo_with_tags(self._subtag_combos[2], [])

    def _refresh_subtag3(self) -> None:
        s2 = self._combo_selected_tag(self._subtag_combos[1])
        if not s2:
            self._fill_combo_with_tags(self._subtag_combos[2], [])
            return
        self._fill_combo_with_tags(self._subtag_combos[2], _child_tags(s2, self._all_tags))

    @staticmethod
    def _fill_combo_with_tags(cb: QComboBox, tags: list[str]) -> None:
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("(none)", None)
        for t in tags:
            cb.addItem(_segment_name(t), t)
        cb.setCurrentIndex(0)
        cb.blockSignals(False)

    @staticmethod
    def _combo_selected_tag(cb: QComboBox) -> str | None:
        data = cb.currentData()
        if isinstance(data, str) and data.strip():
            return data.strip()
        return None

    def _build_query(self) -> str:
        focus = self._selected_focus_tag()
        clauses = [_quote_tag(focus)]
        for y in self._selected_yield_tags():
            clauses.append(_quote_tag(y))
        return " ".join(clauses)

    def _selected_focus_tag(self) -> str:
        for cb in reversed(self._subtag_combos):
            tag = self._combo_selected_tag(cb)
            if tag:
                return tag
        return self._combo_selected_tag(self._resource_combo) or _RESOURCE_TAGS[0]

    def _auto_deck_name(self) -> str:
        resource_label = self._resource_combo.currentText().strip()
        deepest_label = resource_label
        for cb in self._subtag_combos:
            txt = cb.currentText().strip()
            if txt and txt != "(none)":
                deepest_label = txt
        base = f"{resource_label} - {deepest_label}"
        y_labels = self._selected_yield_labels()
        if len(y_labels) == 1:
            return f"{base} - Only {y_labels[0]}"
        if len(y_labels) > 1:
            return f"{base} - Only {len(y_labels)} yield tags"
        return base

    def _selected_yield_tags(self) -> list[str]:
        out: list[str] = []
        for it in self._yield_list.selectedItems():
            tag = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(tag, str) and tag.strip():
                out.append(tag.strip())
        return out

    def _selected_yield_labels(self) -> list[str]:
        out: list[str] = []
        for it in self._yield_list.selectedItems():
            tag = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(tag, str) and tag.strip():
                out.append(it.text().strip())
        return out

    def _on_yield_selection_changed(self) -> None:
        if self._yield_syncing:
            return
        self._yield_syncing = True
        try:
            selected = self._yield_list.selectedItems()
            any_specific = any(
                isinstance(it.data(Qt.ItemDataRole.UserRole), str) and it.data(Qt.ItemDataRole.UserRole).strip()
                for it in selected
            )
            all_selected = self._all_yields_item.isSelected()

            if all_selected and any_specific:
                # Specific yields override the "All Yields" placeholder.
                self._all_yields_item.setSelected(False)
            elif not all_selected and not any_specific:
                # Keep a clear default state visible to users.
                self._all_yields_item.setSelected(True)
        finally:
            self._yield_syncing = False

    def _find_card_count(self, query: str) -> int:
        return len(self._find_cards(query))

    def _find_cards(self, query: str) -> list[int]:
        col = getattr(mw, "col", None)
        if col is None:
            return []
        try:
            return list(col.find_cards(query))
        except Exception:
            return []

    def _run_preview(self) -> None:
        query = self._build_query()
        count = len(self._find_cards(query))
        self._last_preview = _BuilderState(query=query, count=count)
        self._preview_label.setText(
            f'Preview: {count} cards matched for "{self._auto_deck_name()}"'
        )
        self._preview_query.setPlainText(query)

    def _create_or_update(self) -> None:
        name = f"AnKang Deck Builder::{self._auto_deck_name()}"
        query = self._build_query()
        card_ids = self._find_cards(query)
        self._last_preview = _BuilderState(query=query, count=len(card_ids))
        self._preview_label.setText(
            f'Preview: {len(card_ids)} cards matched for "{self._auto_deck_name()}"'
        )
        self._preview_query.setPlainText(query)
        if not card_ids:
            showWarning("No cards matched your current filters.")
            return
        _unsuspend_cards(card_ids)
        did = _ensure_filtered_deck(name)
        if did is None:
            showWarning("Could not create or update filtered deck.")
            return
        if not _set_filtered_deck_search(did, query):
            showWarning("Could not apply filtered deck search.")
            return
        _rebuild_filtered_deck(did)
        showInfo(f'Updated "{name}" with {len(card_ids)} cards.')


def _ensure_filtered_deck(name: str) -> int | None:
    col = getattr(mw, "col", None)
    if col is None:
        return None
    decks = col.decks
    try:
        existing = decks.by_name(name)
        if existing:
            if isinstance(existing, dict) and "id" in existing:
                return int(existing["id"])
            if hasattr(existing, "id"):
                return int(existing.id)
    except Exception:
        pass
    for meth in ("new_filtered", "add_filtered_deck", "id"):
        fn = getattr(decks, meth, None)
        if callable(fn):
            try:
                out = fn(name)
                if isinstance(out, int):
                    return out
                if isinstance(out, dict) and "id" in out:
                    return int(out["id"])
            except Exception:
                continue
    return None


def _set_filtered_deck_search(did: int, query: str) -> bool:
    col = getattr(mw, "col", None)
    if col is None:
        return False
    decks = col.decks
    deck = None
    for meth in ("get",):
        fn = getattr(decks, meth, None)
        if callable(fn):
            try:
                deck = fn(did)
                if deck:
                    break
            except Exception:
                pass
    if not deck:
        return False
    try:
        deck["dyn"] = 1
        deck["terms"] = [[query, 99999, 0]]
        deck["resched"] = True
        save_fn = getattr(decks, "save", None)
        if callable(save_fn):
            save_fn(deck)
        else:
            update_fn = getattr(decks, "update_dict", None)
            if callable(update_fn):
                update_fn(deck)
        return True
    except Exception:
        return False


def _rebuild_filtered_deck(did: int) -> None:
    sched = getattr(getattr(mw, "col", None), "sched", None)
    if sched is None:
        return
    for meth in ("rebuild_filtered_deck", "rebuildDyn"):
        fn = getattr(sched, meth, None)
        if callable(fn):
            try:
                fn(did)
                return
            except Exception:
                continue


def _unsuspend_cards(card_ids: list[int]) -> None:
    if not card_ids:
        return
    sched = getattr(getattr(mw, "col", None), "sched", None)
    if sched is None:
        return
    for meth in ("unsuspend_cards", "unsuspendCards"):
        fn = getattr(sched, meth, None)
        if callable(fn):
            try:
                fn(card_ids)
                return
            except Exception:
                continue


def open_step1_v12_builder() -> None:
    if not getattr(mw, "col", None):
        showWarning("Open a profile first.")
        return
    existing = getattr(mw, "_ankang_filtered_deck_builder_dialog", None)
    if existing is not None:
        try:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return
        except Exception:
            pass
    dlg = Step1V12DeckBuilderDialog(None)
    mw._ankang_filtered_deck_builder_dialog = dlg
    dlg.destroyed.connect(
        lambda *_: setattr(mw, "_ankang_filtered_deck_builder_dialog", None)
    )
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
