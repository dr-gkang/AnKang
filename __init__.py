from __future__ import annotations

import os
from aqt import mw
from aqt.qt import *
from aqt import gui_hooks

from .ankang_profile_storage import ensure_addon_data_migrated_for_profile
from .ankang_format_styles import ankang_text_button_stylesheet, mark_ankang_text_button
from .notes import ankang_open_notes_with_quote
from .sidebar_left import AnkangLeftSidebar, ankang_divider_color
from .sidebar_right import (
    AnkangCloseAssistantButton,
    AnkangRightSidebar,
    _CLOSE_ASSISTANT_BTN_PX,
    _load_icon_from_path,
    _resolve_media_asset,
)

ANKANG_MW_STYLE_BEGIN = "/*ankang-mw-style-begin*/"
ANKANG_MW_STYLE_END = "/*ankang-mw-style-end*/"


def _remove_ankang_style_block(ss: str, begin: str, end: str) -> str:
    if begin not in ss or end not in ss:
        return ss
    out = []
    i = 0
    while i < len(ss):
        j = ss.find(begin, i)
        if j == -1:
            out.append(ss[i:])
            break
        out.append(ss[i:j])
        k = ss.find(end, j + len(begin))
        if k == -1:
            out.append(ss[j:])
            break
        i = k + len(end)
    return "".join(out).strip()


def apply_ankang_main_window_chrome(border_left_px: int = 1):
    """Dock resize strips (QMainWindow::separator) match sidebar background in light/dark."""
    if not (
        hasattr(mw, "ankang_left_sidebar")
        or hasattr(mw, "ankang_right_assistant")
    ):
        return
    dark = mw.palette().color(QPalette.ColorRole.Window).lightness() < 128
    bg = "#303030" if dark else "#f9f9f9"
    bl = max(1, int(border_left_px))
    line = ankang_divider_color(mw)
    # border-left faces the central widget, so this draws the main|resize line
    # (central-widget stylesheets are unreliable on Anki because the central
    # widget is replaced and restyled after add-ons run).
    block = (
        f"{ANKANG_MW_STYLE_BEGIN} QMainWindow::separator {{ "
        f"background-color: {bg}; width: 6px; border-left: {bl}px solid {line}; "
        f"}} {ANKANG_MW_STYLE_END}"
    )
    ss = _remove_ankang_style_block(mw.styleSheet() or "", ANKANG_MW_STYLE_BEGIN, ANKANG_MW_STYLE_END)
    mw.setStyleSheet(ss + ("\n" if ss else "") + block)


def _cursor_in_left_sidebar() -> bool:
    w = QApplication.widgetAt(QCursor.pos())
    dock = mw.ankang_left_sidebar
    while w:
        if w is dock or dock.isAncestorOf(w):
            return True
        w = w.parentWidget()
    return False


def _cursor_in_right_sidebar_or_resize_strip() -> bool:
    w = QApplication.widgetAt(QCursor.pos())
    dock = mw.ankang_right_assistant
    while w:
        if w is dock or dock.isAncestorOf(w):
            return True
        w = w.parentWidget()
    # Main-window vertical separator: narrow strip immediately left of the dock.
    p = QCursor.pos()
    if not mw.isVisible():
        return False
    local = mw.mapFromGlobal(p)
    if not mw.rect().contains(local):
        return False
    top_left = dock.mapTo(mw, QPoint(0, 0))
    bottom_left = dock.mapTo(mw, QPoint(0, dock.height()))
    dock_left = top_left.x()
    y_top = min(top_left.y(), bottom_left.y())
    y_bottom = max(top_left.y(), bottom_left.y())
    if not (y_top <= local.y() <= y_bottom):
        return False
    sep_slop = 12
    return dock_left - sep_slop <= local.x() < dock_left


def _ankang_chrome_hover_tick():
    if not mw.isVisible():
        return
    if not hasattr(mw, "ankang_left_sidebar") or not hasattr(mw, "ankang_right_assistant"):
        return
    hover_left = _cursor_in_left_sidebar()
    hover_right = _cursor_in_right_sidebar_or_resize_strip()
    prev = getattr(mw, "_ankang_chrome_hover_state", None)
    state = (hover_left, hover_right)
    if state == prev:
        return
    mw._ankang_chrome_hover_state = state
    apply_ankang_main_window_chrome(border_left_px=2 if hover_right else 1)
    mw.ankang_left_sidebar.apply_theme(main_divider_px=2 if hover_left else 1)
    mw.ankang_right_assistant.apply_theme()


def refresh_ankang_chrome_and_sidebars():
    hover = getattr(mw, "_ankang_chrome_hover_state", (False, False))
    apply_ankang_main_window_chrome(border_left_px=2 if hover[1] else 1)
    if hasattr(mw, "ankang_left_sidebar"):
        mw.ankang_left_sidebar.apply_theme(main_divider_px=2 if hover[0] else 1)
    if hasattr(mw, "ankang_right_assistant"):
        mw.ankang_right_assistant.apply_theme()


def _on_theme_did_change(*_args):
    refresh_ankang_chrome_and_sidebars()
    QTimer.singleShot(0, _ankang_sync_toolbar_wrap_height)


def _ankang_toolbar_reopen_btn_style(object_name: str) -> str:
    return f"""
        QPushButton#{object_name} {{
            border: none;
            background: transparent;
            padding: 0px;
        }}
        QPushButton#{object_name}:hover,
        QPushButton#{object_name}:pressed {{
            border: none;
            background: transparent;
        }}
    """


class _AnkangToolbarWrapHeightFilter(QObject):
    """Keeps the toolbar row only as tall as Anki's top webview (prevents vertical stretch)."""

    def __init__(self, wrap: QWidget, tweb: QWidget) -> None:
        super().__init__(tweb)
        self._wrap = wrap
        self._tweb = tweb

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._tweb and event.type() == QEvent.Type.Resize:
            _ankang_sync_toolbar_wrap_height()
        return False


def _ankang_sync_toolbar_wrap_height() -> None:
    wrap = getattr(mw, "_ankang_toolbar_reopen_wrap", None)
    tweb = getattr(mw, "toolbarWeb", None)
    if not wrap or not tweb:
        return
    h = max(_CLOSE_ASSISTANT_BTN_PX, tweb.height())
    wrap.setFixedHeight(h)


def _ankang_on_top_toolbar_did_redraw(toolbar) -> None:
    if getattr(toolbar, "mw", None) is mw:
        QTimer.singleShot(0, _ankang_sync_toolbar_wrap_height)


def _ankang_build_toolbar_reopen_button(
    *,
    unpressed_name: str,
    pressed_name: str,
    object_name: str,
    tooltip: str,
    parent: QWidget,
    fallback_text: str,
) -> QPushButton:
    addon_dir = os.path.dirname(__file__)
    up = _resolve_media_asset(addon_dir, "Buttons", "Unpressed", base_name=unpressed_name)
    pr = _resolve_media_asset(addon_dir, "Buttons", "Pressed", base_name=pressed_name)
    if up and pr:
        iu = _load_icon_from_path(up)
        ip = _load_icon_from_path(pr)
        if not iu.isNull() and not ip.isNull():
            btn = AnkangCloseAssistantButton(
                up, pr, parent, object_name=object_name
            )
            btn.setStyleSheet(_ankang_toolbar_reopen_btn_style(object_name))
            btn.setToolTip(tooltip)
            return btn
    btn = QPushButton(fallback_text, parent)
    btn.setObjectName(object_name)
    btn.setFlat(True)
    btn.setFixedSize(_CLOSE_ASSISTANT_BTN_PX, _CLOSE_ASSISTANT_BTN_PX)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    mark_ankang_text_button(btn)
    btn.setStyleSheet(ankang_text_button_stylesheet())
    return btn


def _ankang_inject_toolbar_reopen_row() -> None:
    """Wrap the top toolbar webview in a row with 35×35 reopen buttons (same row as Decks / Sync)."""
    if getattr(mw, "_ankang_toolbar_reopen_injected", False):
        return
    tweb = getattr(mw, "toolbarWeb", None)
    main_layout = getattr(mw, "mainLayout", None)
    cw = getattr(getattr(mw, "form", None), "centralwidget", None)
    if not tweb or not main_layout or cw is None:
        n = getattr(mw, "_ankang_toolbar_inject_failures", 0) + 1
        mw._ankang_toolbar_inject_failures = n
        if n < 40:
            QTimer.singleShot(200, _ankang_inject_toolbar_reopen_row)
        return

    idx = -1
    for i in range(main_layout.count()):
        item = main_layout.itemAt(i)
        w = item.widget()
        if w is tweb:
            idx = i
            break
    if idx < 0:
        n = getattr(mw, "_ankang_toolbar_inject_failures", 0) + 1
        mw._ankang_toolbar_inject_failures = n
        if n < 40:
            QTimer.singleShot(200, _ankang_inject_toolbar_reopen_row)
        return
    mw._ankang_toolbar_inject_failures = 0

    old_float = getattr(mw, "ankang_reopen_btn", None)
    if old_float is not None:
        old_float.hide()
        old_float.deleteLater()
        del mw.ankang_reopen_btn

    main_layout.takeAt(idx)
    tweb.setParent(None)

    wrap = QWidget(cw)
    wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    row = QHBoxLayout(wrap)
    row.setContentsMargins(4, 0, 4, 0)
    row.setSpacing(0)

    left_btn = _ankang_build_toolbar_reopen_button(
        unpressed_name="C_RightArrow1",
        pressed_name="CP_RightArrow1",
        object_name="AnkangToolbarLeftReopenBtn",
        tooltip="Show left sidebar",
        parent=wrap,
        fallback_text="»",
    )
    left_btn.clicked.connect(lambda: mw.ankang_left_sidebar.show())

    right_btn = _ankang_build_toolbar_reopen_button(
        unpressed_name="C_LeftArrow1",
        pressed_name="CP_LeftArrow1",
        object_name="AnkangToolbarRightReopenBtn",
        tooltip="Show right sidebar",
        parent=wrap,
        fallback_text="«",
    )
    right_btn.clicked.connect(lambda: mw.ankang_right_assistant.show())

    row.addWidget(left_btn, 0, Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(tweb, 1)
    row.addWidget(right_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    main_layout.insertWidget(idx, wrap)

    _ankang_sync_toolbar_wrap_height()
    filt = _AnkangToolbarWrapHeightFilter(wrap, tweb)
    tweb.installEventFilter(filt)
    mw._ankang_toolbar_wrap_height_filter = filt

    if not getattr(mw, "_ankang_top_toolbar_redraw_hooked", False):
        try:
            gui_hooks.top_toolbar_did_redraw.append(_ankang_on_top_toolbar_did_redraw)
        except AttributeError:
            pass
        mw._ankang_top_toolbar_redraw_hooked = True

    def _sync_toolbar_reopen_visibility(*_args) -> None:
        left_btn.setVisible(not mw.ankang_left_sidebar.isVisible())
        right_btn.setVisible(not mw.ankang_right_assistant.isVisible())

    mw.ankang_left_sidebar.visibilityChanged.connect(_sync_toolbar_reopen_visibility)
    mw.ankang_right_assistant.visibilityChanged.connect(_sync_toolbar_reopen_visibility)
    _sync_toolbar_reopen_visibility()

    mw._ankang_toolbar_reopen_wrap = wrap
    mw._ankang_left_toolbar_reopen_btn = left_btn
    mw._ankang_right_toolbar_reopen_btn = right_btn
    mw._ankang_toolbar_reopen_injected = True


def setup_ankang_ui():
    """Initializes the full Ankang Dashboard Suite"""
    ensure_addon_data_migrated_for_profile()

    # 1. Setup Left Sidebar
    if not hasattr(mw, "ankang_left_sidebar"):
        mw.ankang_left_sidebar = AnkangLeftSidebar(mw)
        mw.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, mw.ankang_left_sidebar)

    # 2. Setup Right Sidebar (Assistant)
    if not hasattr(mw, "ankang_right_assistant"):
        mw.ankang_right_assistant = AnkangRightSidebar(mw)
        mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, mw.ankang_right_assistant)

    if not hasattr(mw, "_ankang_chrome_hover_state"):
        mw._ankang_chrome_hover_state = (False, False)

    for delay_ms in (0, 250, 2000):
        QTimer.singleShot(delay_ms, refresh_ankang_chrome_and_sidebars)

    if not hasattr(mw, "_ankang_chrome_hover_timer"):
        ht = QTimer(mw)
        ht.setInterval(50)
        ht.timeout.connect(_ankang_chrome_hover_tick)
        ht.start()
        mw._ankang_chrome_hover_timer = ht

    for delay_ms in (0, 100, 500):
        QTimer.singleShot(delay_ms, _ankang_inject_toolbar_reopen_row)

def _anki_note_and_card_ids_for_webview(webview):
    """If the webview is the reviewer card area, return (note id, card id) for Browser search."""
    r = getattr(mw, "reviewer", None)
    if not r or getattr(r, "web", None) is not webview:
        return None, None
    c = getattr(r, "card", None)
    if not c:
        return None, None
    return c.nid, c.id


# --- CONTEXT MENU HOOK (Right-click search / notes) ---
def on_context_menu(webview, menu):
    selected = webview.page().selectedText().strip()
    if not selected:
        return
    if hasattr(mw, "ankang_right_assistant"):
        # Submenu: hovering "AnKang Search" opens choices (platform menu behavior).
        sub = menu.addMenu("AnKang Search")
        sty = getattr(mw.ankang_right_assistant, "_menu_style", None)
        if sty:
            sub.setStyleSheet(sty)
        sub.addAction("Paste into AI chat").triggered.connect(
            lambda _=False, s=selected: mw.ankang_right_assistant.external_search_paste_ai(s)
        )
        sub.addAction("Google search").triggered.connect(
            lambda _=False, s=selected: mw.ankang_right_assistant.external_search_google(s)
        )
    nid, cid = _anki_note_and_card_ids_for_webview(webview)
    menu.addAction("AnKang Notes").triggered.connect(
        lambda _=False, s=selected, n=nid, c=cid: ankang_open_notes_with_quote(s, n, c)
    )


def _install_ankang_gui_hooks() -> None:
    """Register once so add-on reload does not duplicate handlers."""
    if globals().get("_ANKANG_GUI_HOOKS_REGISTERED"):
        return
    try:
        gui_hooks.theme_did_change.append(_on_theme_did_change)
        gui_hooks.webview_will_show_context_menu.append(on_context_menu)
        gui_hooks.profile_did_open.append(setup_ankang_ui)
    except AttributeError:
        return
    globals()["_ANKANG_GUI_HOOKS_REGISTERED"] = True


_install_ankang_gui_hooks()