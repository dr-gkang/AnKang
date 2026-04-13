import os
import json
from typing import Optional
from urllib.parse import quote_plus
from aqt.qt import *
from aqt import mw, gui_hooks
from aqt.utils import tooltip

from .ankang_format_styles import ankang_text_button_stylesheet, mark_ankang_text_button

# Try to import WebEngine for the AI/Browser features
try:
    from aqt.qt import QWebEngineView
except ImportError:
    QWebEngineView = None

try:
    from aqt.qt import QWebEnginePage, QWebEngineProfile
except ImportError:
    QWebEnginePage = None
    QWebEngineProfile = None

_DEFAULT_AI_URL = "https://chat.openai.com"
_DEFAULT_WEB_URL = "https://www.google.com"

_ANKANG_CTRL_STRIP_HEIGHT = 35

_AI_STRIP_CARD_LABELS_LONG = ("Explain Card", "Simplify Card", "Practice Ques")
_AI_STRIP_CARD_LABELS_SHORT = ("Explain", "Simplify", "PQ")

_NAV_AI_LABEL_LONG = "AI Chatbot"
_NAV_AI_LABEL_SHORT = "AI"
_NAV_WEB_LABEL_LONG = "Web Browser"
_NAV_WEB_LABEL_SHORT = "Web"


def _ankang_push_button_contents_width(btn: QPushButton) -> int:
    """Width Qt reserves for label+icon inside a QPushButton (respects padding / style)."""
    bw = btn.width()
    if bw <= 0:
        return 0
    opt = QStyleOptionButton()
    btn.initStyleOption(opt)
    try:
        se = QStyle.SubElement.SE_PushButtonContents
    except AttributeError:
        se = QStyle.SE_PushButtonContents  # type: ignore[attr-defined]
    rect = btn.style().subElementRect(se, opt, btn)
    style_w = max(0, rect.width())
    # Stylesheet %-padding is not always reflected in subElementRect (often → stuck short labels).
    approx = max(1, int(bw * 0.88) - 4)
    return max(style_w, approx)


class _AnkangStackedByCurrentPage(QStackedWidget):
    """Only the visible page contributes to size hints; Qt's default stack uses max(all pages)."""

    def minimumSizeHint(self):
        w = self.currentWidget()
        if w is not None:
            return w.minimumSizeHint()
        return super().minimumSizeHint()

    def sizeHint(self):
        w = self.currentWidget()
        if w is not None:
            return w.sizeHint()
        return super().sizeHint()


class _AnkangRightSidebarContents(QWidget):
    """Clamp horizontal minimumSizeHint so QWebEngineView / layouts cannot block narrowing."""

    def __init__(self, dock: QWidget):
        super().__init__(dock)
        self._ankang_dock = dock

    def minimumSizeHint(self):
        sz = super().minimumSizeHint()
        cap_w = 48
        try:
            cap_w = max(48, int(self._ankang_dock.minimumWidth()))
        except (TypeError, ValueError):
            pass
        tw = sz.width()
        w = cap_w if tw <= 0 else min(tw, cap_w)
        return QSize(w, sz.height())

_USMLE_CARD_PLACEHOLDER = "<<<ANKANG_CARD_FIELDS>>>"
_USMLE_CARD_PROMPT_TEMPLATE = (
    "Using this Anki Card:\n\n"
    + _USMLE_CARD_PLACEHOLDER
    + "\n\n"
    "give me one second-order multiple-choice question based on the card that has a difficulty level "
    'equivalent to advanced board-style questions. Avoid negative phrasing (no "NOT," '
    '"least likely," etc.). Each question must have five plausible options (A–E) with the correct '
    "answer randomized (not predictable). For the question, after the user answers, provide the correct "
    "answer, and then a brief explanation why it is correct and why other options are incorrect. "
    "If the first choice is wrong, give the user one more try to try and get the question right."
)


def _resolve_media_asset(addon_dir: str, *subpath: str, base_name: str) -> Optional[str]:
    folder = os.path.join(addon_dir, "media", *subpath)
    for ext in (".png", ".webp", ".svg", ".jpg", ".jpeg"):
        candidate = os.path.join(folder, f"{base_name}{ext}")
        if os.path.isfile(candidate):
            return os.path.normpath(candidate)
    plain = os.path.join(folder, base_name)
    if os.path.isfile(plain):
        return os.path.normpath(plain)
    return None


def _load_icon_from_path(path: str) -> QIcon:
    """QIcon(path) plus SVG raster fallback (QSS image: URLs are unreliable on Windows)."""
    ico = QIcon(path)
    if not ico.isNull():
        return ico
    if path.lower().endswith(".svg"):
        try:
            from aqt.qt import QSvgRenderer
        except ImportError:
            return QIcon()
        r = QSvgRenderer(path)
        if not r.isValid():
            return QIcon()
        sz = r.defaultSize()
        if sz.width() <= 0 or sz.height() <= 0:
            w, h = 28, 28
        else:
            w = int(min(64, max(16, sz.width())))
            h = int(min(64, max(16, sz.height())))
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        qp = QPainter(pm)
        r.render(qp, QRectF(0, 0, w, h))
        qp.end()
        return QIcon(pm)
    pm = QPixmap(path)
    return QIcon(pm) if not pm.isNull() else QIcon()


_CLOSE_ASSISTANT_BTN_PX = 35


class AnkangCloseAssistantButton(QPushButton):
    """Arrow / icon button: QIcon + hover swap (avoids stylesheet url() loading issues)."""

    def __init__(
        self,
        path_up: str,
        path_pr: str,
        parent: Optional[QWidget] = None,
        *,
        object_name: str = "AnkangCloseAssistantBtn",
    ):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._icon_up = _load_icon_from_path(path_up)
        self._icon_pr = _load_icon_from_path(path_pr)
        self.setIcon(self._icon_up)
        self._apply_icon_size()

    def _apply_icon_size(self) -> None:
        side = _CLOSE_ASSISTANT_BTN_PX
        inner = max(16, side - 6)
        self.setIconSize(QSize(inner, inner))
        self.setFixedSize(side, side)

    def enterEvent(self, event):
        self.setIcon(self._icon_pr)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self._icon_up)
        super().leaveEvent(event)


class AnkangMediaHoverIconButton(QPushButton):
    """35×35 media icon: unpressed by default, pressed on hover and while held (puzzle + web strip)."""

    def __init__(
        self,
        path_up: str,
        path_pr: str,
        parent: Optional[QWidget] = None,
        *,
        object_name: str,
    ):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._icon_up = _load_icon_from_path(path_up)
        self._icon_pr = _load_icon_from_path(path_pr)
        self.setIcon(self._icon_up)
        self._apply_icon_size()

    def _apply_icon_size(self) -> None:
        side = _CLOSE_ASSISTANT_BTN_PX
        inner = max(16, side - 6)
        self.setIconSize(QSize(inner, inner))
        self.setFixedSize(side, side)

    def enterEvent(self, event):
        self.setIcon(self._icon_pr)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setIcon(self._icon_up)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self.setIcon(self._icon_pr)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.setIcon(self._icon_pr if self.underMouse() else self._icon_up)


class AnkangAiPuzzleToggleButton(AnkangMediaHoverIconButton):
    """AI-tab puzzle: switches Gemini / ChatGPT."""

    def __init__(
        self,
        path_up: str,
        path_pr: str,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(
            path_up, path_pr, parent, object_name="AnkangAiStripToggle"
        )


class AnkangRightSidebar(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setObjectName("AnkangRightSidebar")
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea)
        self.setMinimumWidth(50)
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        # Remove any title-bar reservation so the dock sits flush at top.
        self.setTitleBarWidget(QWidget())

        self.main_container = _AnkangRightSidebarContents(self)
        self.main_container.setObjectName("AnkangRightMain")
        self.main_container.setMinimumWidth(0)
        self.main_layout = QVBoxLayout(self.main_container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.control_stack = _AnkangStackedByCurrentPage()
        self.control_stack.setMinimumWidth(0)
        self.browser_stack = _AnkangStackedByCurrentPage()
        self.browser_stack.setMinimumWidth(0)

        self.setup_primary_nav()
        self.setup_tabs()

        self.main_layout.addWidget(self.control_stack)
        self.main_layout.addWidget(self.browser_stack)
        self.setWidget(self.main_container)
        self.apply_theme()

    def minimumSizeHint(self):
        """QDockWidget normally uses max(self, widget) width; WebEngine forces a wide widget hint."""
        cap_w = max(48, int(self.minimumWidth()))
        h = 160
        if self.widget() is not None:
            wh = self.widget().minimumSizeHint().height()
            if wh > 0:
                h = wh
        return QSize(cap_w, h)

    def setup_primary_nav(self):
        addon_dir = os.path.dirname(__file__)
        up = _resolve_media_asset(
            addon_dir, "Buttons", "Unpressed", base_name="C_RightArrow1"
        )
        pr = _resolve_media_asset(
            addon_dir, "Buttons", "Pressed", base_name="CP_RightArrow1"
        )
        self._close_btn_icon_unpressed = up
        self._close_btn_icon_pressed = pr

        self._close_btn_uses_icons = False
        if up and pr:
            iu = _load_icon_from_path(up)
            ip = _load_icon_from_path(pr)
            if not iu.isNull() and not ip.isNull():
                self.close_btn = AnkangCloseAssistantButton(up, pr, self)
                self._close_btn_uses_icons = True
            else:
                self.close_btn = QPushButton()
                self.close_btn.setObjectName("AnkangCloseAssistantBtn")
                self.close_btn.setFlat(True)
                self.close_btn.setText("x")
                self.close_btn.setFixedSize(_CLOSE_ASSISTANT_BTN_PX, _CLOSE_ASSISTANT_BTN_PX)
        else:
            self.close_btn = QPushButton()
            self.close_btn.setObjectName("AnkangCloseAssistantBtn")
            self.close_btn.setFlat(True)
            self.close_btn.setText("x")
            self.close_btn.setFixedSize(_CLOSE_ASSISTANT_BTN_PX, _CLOSE_ASSISTANT_BTN_PX)

        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Hide right sidebar")
        self.close_btn.clicked.connect(self.hide)
        if not self._close_btn_uses_icons:
            mark_ankang_text_button(self.close_btn)

        self._nav_ai_btn = QPushButton(_NAV_AI_LABEL_SHORT)
        self._nav_ai_btn.setObjectName("AnkangRightNavAi")
        self._nav_ai_btn.setFixedHeight(28)
        self._nav_ai_btn.setMinimumWidth(0)
        self._nav_ai_btn.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
        )
        self._nav_ai_btn.clicked.connect(lambda: self.switch_tab(0))

        self._nav_web_btn = QPushButton(_NAV_WEB_LABEL_SHORT)
        self._nav_web_btn.setObjectName("AnkangRightNavWeb")
        self._nav_web_btn.setFixedHeight(28)
        self._nav_web_btn.setMinimumWidth(0)
        self._nav_web_btn.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
        )
        self._nav_web_btn.clicked.connect(lambda: self.switch_tab(1))
        for _tb in (self._nav_ai_btn, self._nav_web_btn):
            mark_ankang_text_button(_tb)

        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(5, 0, 5, 0)
        nav_row.setSpacing(5)
        nav_row.addWidget(self.close_btn, 0)
        nav_row.addWidget(self._nav_ai_btn, 1)
        nav_row.addWidget(self._nav_web_btn, 1)
        
        nav_widget = QWidget()
        nav_widget.setMinimumWidth(0)
        nav_widget.setFixedHeight(35)
        nav_widget.setLayout(nav_row)
        self.main_layout.addWidget(nav_widget)

    def setup_tabs(self):
        # AI TAB — one row: switch + card actions
        ai_ctrl = QWidget()
        ai_ctrl.setMinimumWidth(0)
        ai_ctrl.setFixedHeight(_ANKANG_CTRL_STRIP_HEIGHT)
        ai_layout = QHBoxLayout(ai_ctrl)
        ai_layout.setContentsMargins(5, 0, 5, 0)
        ai_layout.setSpacing(5)

        # Short card labels first so the dock minimum width stays small until widen.
        addon_dir = os.path.dirname(__file__)
        pz_up = _resolve_media_asset(
            addon_dir, "Buttons", "Unpressed", base_name="C_PuzzlePiece"
        )
        pz_pr = _resolve_media_asset(
            addon_dir, "Buttons", "Pressed", base_name="CP_PuzzlePiece"
        )
        self._ai_puzzle_toggle_uses_icons = False
        if pz_up and pz_pr:
            iu = _load_icon_from_path(pz_up)
            ip = _load_icon_from_path(pz_pr)
            if not iu.isNull() and not ip.isNull():
                self.ai_toggle_btn = AnkangAiPuzzleToggleButton(pz_up, pz_pr, ai_ctrl)
                self._ai_puzzle_toggle_uses_icons = True
            else:
                self.ai_toggle_btn = QPushButton("AI")
                self.ai_toggle_btn.setObjectName("AnkangAiStripToggle")
                self.ai_toggle_btn.setFixedSize(
                    _CLOSE_ASSISTANT_BTN_PX, _CLOSE_ASSISTANT_BTN_PX
                )
        else:
            self.ai_toggle_btn = QPushButton("AI")
            self.ai_toggle_btn.setObjectName("AnkangAiStripToggle")
            self.ai_toggle_btn.setFixedSize(
                _CLOSE_ASSISTANT_BTN_PX, _CLOSE_ASSISTANT_BTN_PX
            )

        self.ai_toggle_btn.setMinimumWidth(0)
        self.ai_toggle_btn.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.ai_toggle_btn.setToolTip("Switch AI Chatbot")
        self.ai_toggle_btn.clicked.connect(self.toggle_ai_service)
        if not self._ai_puzzle_toggle_uses_icons:
            mark_ankang_text_button(self.ai_toggle_btn)
        ai_layout.addWidget(self.ai_toggle_btn, 0)

        self._btn_explain_card = QPushButton(_AI_STRIP_CARD_LABELS_SHORT[0])
        self._btn_simplify_card = QPushButton(_AI_STRIP_CARD_LABELS_SHORT[1])
        self._btn_usmle = QPushButton(_AI_STRIP_CARD_LABELS_SHORT[2])
        self._btn_explain_card.setObjectName("AnkangAiStripExplain")
        self._btn_simplify_card.setObjectName("AnkangAiStripSimplify")
        self._btn_usmle.setObjectName("AnkangAiStripPQ")
        self._btn_usmle.setToolTip(
            "Practice Ques — board-style multiple-choice from this card"
        )
        for b in (self._btn_explain_card, self._btn_simplify_card, self._btn_usmle):
            b.setFixedHeight(28)
            b.setMinimumWidth(0)
            b.setSizePolicy(
                QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
            )
        self._btn_explain_card.clicked.connect(self._ai_action_explain_card)
        self._btn_simplify_card.clicked.connect(self._ai_action_simplify_card)
        self._btn_usmle.clicked.connect(self._ai_action_usmle_question)
        for _tb in (
            self._btn_explain_card,
            self._btn_simplify_card,
            self._btn_usmle,
        ):
            mark_ankang_text_button(_tb)

        # Growing strip so each card button receives width (a bare QSpacerItem would take it all).
        self._ai_card_actions_wrap = QWidget(ai_ctrl)
        self._ai_card_actions_wrap.setMinimumWidth(0)
        _ai_cards = QHBoxLayout(self._ai_card_actions_wrap)
        _ai_cards.setContentsMargins(0, 0, 0, 0)
        _ai_cards.setSpacing(5)
        _ai_cards.addStretch(1)
        _ai_cards.addWidget(self._btn_explain_card, 1)
        _ai_cards.addWidget(self._btn_simplify_card, 1)
        _ai_cards.addWidget(self._btn_usmle, 1)
        ai_layout.addWidget(self._ai_card_actions_wrap, 1)

        # WEB TAB — back, forward, reload, home, URL bar, enter (icons match AI puzzle size)
        web_ctrl = QWidget()
        web_ctrl.setMinimumWidth(0)
        web_ctrl.setFixedHeight(_ANKANG_CTRL_STRIP_HEIGHT)
        web_layout = QHBoxLayout(web_ctrl)
        web_layout.setContentsMargins(5, 0, 5, 0)
        web_layout.setSpacing(0)

        def _web_strip_button(
            u_base: str, p_base: str, object_name: str, tooltip: str = ""
        ) -> QPushButton:
            up = _resolve_media_asset(
                addon_dir, "Buttons", "Unpressed", base_name=u_base
            )
            pr = _resolve_media_asset(
                addon_dir, "Buttons", "Pressed", base_name=p_base
            )
            if up and pr:
                iu = _load_icon_from_path(up)
                ip = _load_icon_from_path(pr)
                if not iu.isNull() and not ip.isNull():
                    b = AnkangMediaHoverIconButton(
                        up, pr, web_ctrl, object_name=object_name
                    )
                    if tooltip:
                        b.setToolTip(tooltip)
                    return b
            fb = QPushButton("·")
            fb.setObjectName(object_name)
            fb.setFixedSize(_CLOSE_ASSISTANT_BTN_PX, _CLOSE_ASSISTANT_BTN_PX)
            if tooltip:
                fb.setToolTip(tooltip)
            return fb

        self._web_back_btn = _web_strip_button(
            "C_LeftArrow1", "CP_LeftArrow1", "AnkangWebStripBack", "Back"
        )
        self._web_forward_btn = _web_strip_button(
            "C_RightArrow1", "CP_RightArrow1", "AnkangWebStripForward", "Forward"
        )
        self._web_reload_btn = _web_strip_button(
            "C_Return2", "CP_Return2", "AnkangWebStripReload", "Reload"
        )
        self._web_home_btn = _web_strip_button(
            "C_Home1", "CP_Home1", "AnkangWebStripHome", "Home"
        )
        self._web_enter_btn = _web_strip_button(
            "C_MagnifyingGlass",
            "CP_MagnifyingGlass",
            "AnkangWebStripEnter",
            "Go / search",
        )
        self._web_strip_uses_icons = all(
            isinstance(b, AnkangMediaHoverIconButton)
            for b in (
                self._web_back_btn,
                self._web_forward_btn,
                self._web_reload_btn,
                self._web_home_btn,
                self._web_enter_btn,
            )
        )

        self.url_bar = QLineEdit()
        self.url_bar.setFixedHeight(30)
        self.url_bar.setMinimumWidth(0)
        self.url_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.url_bar.setPlaceholderText("Search Google / Paste url")
        try:
            _align_left = Qt.AlignmentFlag.AlignLeft
        except AttributeError:
            _align_left = Qt.AlignLeft  # type: ignore[attr-defined]
        self.url_bar.setAlignment(_align_left)

        web_layout.addWidget(self._web_back_btn, 0)
        web_layout.addSpacing(1)
        web_layout.addWidget(self._web_forward_btn, 0)
        web_layout.addSpacing(1)
        web_layout.addWidget(self._web_reload_btn, 0)
        web_layout.addSpacing(1)
        web_layout.addWidget(self._web_home_btn, 0)
        web_layout.addSpacing(5)
        web_layout.addWidget(self.url_bar, 1)
        web_layout.addSpacing(5)
        web_layout.addWidget(self._web_enter_btn, 0)
        self._web_back_btn.setEnabled(False)
        self._web_forward_btn.setEnabled(False)

        self.control_stack.addWidget(ai_ctrl)
        self.control_stack.addWidget(web_ctrl)
        self.control_stack.setFixedHeight(_ANKANG_CTRL_STRIP_HEIGHT)

        if QWebEngineView:
            self._session_restoring = False
            self.ai_view = QWebEngineView()
            self.web_view = QWebEngineView()

            if QWebEngineProfile and QWebEnginePage:
                wdir = os.path.join(mw.pm.profileFolder(), "AnkangSidebar", "qtwebengine")
                os.makedirs(wdir, exist_ok=True)
                self._engine_profile = QWebEngineProfile("ankang_right_sidebar", mw)
                self._engine_profile.setPersistentStoragePath(wdir)
                self._engine_profile.setCachePath(os.path.join(wdir, "cache"))
                try:
                    _cookies = QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies
                except AttributeError:
                    _cookies = QWebEngineProfile.AllowPersistentCookies
                self._engine_profile.setPersistentCookiesPolicy(_cookies)
                self.ai_view.setPage(
                    QWebEnginePage(self._engine_profile, self.ai_view)
                )
                self.web_view.setPage(
                    QWebEnginePage(self._engine_profile, self.web_view)
                )
            else:
                self._engine_profile = None

            self.url_bar.returnPressed.connect(self.navigate_to_url)
            self.url_bar.editingFinished.connect(self._on_url_bar_editing_finished)
            self._web_enter_btn.clicked.connect(self.navigate_to_url)
            self._web_back_btn.clicked.connect(self._web_view_back)
            self._web_forward_btn.clicked.connect(self._web_view_forward)
            self._web_reload_btn.clicked.connect(self._web_view_reload)
            self._web_home_btn.clicked.connect(self._web_view_home)

            self.ai_view.urlChanged.connect(self._on_ai_view_url_changed)
            self.web_view.urlChanged.connect(self._on_web_view_url_changed)
            self.web_view.loadFinished.connect(self._on_web_load_finished)
            self.ai_view.setMinimumSize(0, 0)
            self.web_view.setMinimumSize(0, 0)
            _web_sp = QSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
            )
            self.ai_view.setSizePolicy(_web_sp)
            self.web_view.setSizePolicy(_web_sp)
            self.browser_stack.addWidget(self.ai_view)
            self.browser_stack.addWidget(self.web_view)

            self._persist_timer = QTimer(self)
            self._persist_timer.setSingleShot(True)
            self._persist_timer.setInterval(800)
            self._persist_timer.timeout.connect(self._persist_session_state)

            QTimer.singleShot(0, self._initialize_web_views_from_session)

    def toggle_ai_service(self):
        if not QWebEngineView:
            return
        current_url = self.ai_view.url().toString()
        if "gemini" in current_url:
            self.ai_view.setUrl(QUrl(_DEFAULT_AI_URL))
        else:
            self.ai_view.setUrl(QUrl("https://gemini.google.com"))

    def _sidebar_session_json_path(self) -> str:
        return os.path.join(mw.pm.profileFolder(), "AnkangSidebar", "session.json")

    def _on_ai_view_url_changed(self, _url=None) -> None:
        self._debounced_persist_session()
        self._sync_web_nav_chrome()

    def _on_web_view_url_changed(self, _url=None) -> None:
        self._debounced_persist_session()
        self._sync_web_nav_chrome()
        self._sync_url_bar_from_web_view()

    def _debounced_persist_session(self) -> None:
        if getattr(self, "_session_restoring", False):
            return
        if hasattr(self, "_persist_timer"):
            self._persist_timer.start()

    def _persist_session_state(self) -> None:
        if not QWebEngineView or not hasattr(self, "ai_view") or not hasattr(self, "web_view"):
            return
        if getattr(self, "_session_restoring", False):
            return
        path = self._sidebar_session_json_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            data = {
                "main_tab": self.browser_stack.currentIndex(),
                "ai_url": self.ai_view.url().toString(),
                "web_url": self.web_view.url().toString(),
                "url_bar": self.url_bar.text(),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def save_session_state(self) -> None:
        """Persist URLs, tab, and url bar (called on profile close)."""
        self._persist_session_state()

    def _initialize_web_views_from_session(self) -> None:
        if not QWebEngineView or not hasattr(self, "ai_view"):
            return

        def _safe_http_url(s: str, fallback: str) -> QUrl:
            q = QUrl(s) if isinstance(s, str) else QUrl()
            if q.isValid() and q.scheme() in ("http", "https"):
                return q
            return QUrl(fallback)

        tab = 0
        ai_u = _DEFAULT_AI_URL
        web_u = _DEFAULT_WEB_URL
        path = self._sidebar_session_json_path()
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                tab = int(d.get("main_tab", 0))
                if tab not in (0, 1):
                    tab = 0
                if isinstance(d.get("ai_url"), str) and d["ai_url"].strip():
                    ai_u = d["ai_url"].strip()
                if isinstance(d.get("web_url"), str) and d["web_url"].strip():
                    web_u = d["web_url"].strip()
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                pass

        self._session_restoring = True
        try:
            self.ai_view.setUrl(_safe_http_url(ai_u, _DEFAULT_AI_URL))
            self.web_view.setUrl(_safe_http_url(web_u, _DEFAULT_WEB_URL))
            self._set_url_bar_shown_url(web_u)
            self.switch_tab(tab)
        finally:
            self._session_restoring = False
            QTimer.singleShot(0, self._sync_web_nav_chrome)

    def navigate_to_url(self):
        if not QWebEngineView or not hasattr(self, "web_view"):
            return
        q = self.url_bar.text()
        query = q.strip()
        if not query:
            return
        url = (
            "https://www.google.com/search?q=" + quote_plus(query)
            if "." not in query
            else (query if query.startswith("http") else "https://" + query)
        )
        self._set_url_bar_shown_url(url)
        self.web_view.setUrl(QUrl(url))
        self._sync_web_nav_chrome()

    def _on_url_bar_editing_finished(self) -> None:
        if not QWebEngineView or not hasattr(self, "web_view"):
            return
        if self.browser_stack.currentIndex() != 1:
            return
        if self.url_bar.text().strip():
            return
        self._sync_url_bar_from_web_view()

    def _on_web_load_finished(self, _ok: bool) -> None:
        self._sync_web_nav_chrome()
        self._sync_url_bar_from_web_view()

    def _set_url_bar_shown_url(self, text: str) -> None:
        """Fill the URL bar and scroll the viewport so the start of the URL is visible."""
        self.url_bar.setText(text)
        self.url_bar.home(False)

    def _sync_url_bar_from_web_view(self) -> None:
        if not QWebEngineView or not hasattr(self, "web_view"):
            return
        if self.browser_stack.currentIndex() != 1:
            return
        if self.url_bar.hasFocus():
            return
        if getattr(self, "_session_restoring", False):
            return
        self._set_url_bar_shown_url(self.web_view.url().toString())

    def _web_view_back(self) -> None:
        if QWebEngineView and hasattr(self, "web_view"):
            self.web_view.back()
            self._sync_web_nav_chrome()

    def _web_view_forward(self) -> None:
        if QWebEngineView and hasattr(self, "web_view"):
            self.web_view.forward()
            self._sync_web_nav_chrome()

    def _web_view_reload(self) -> None:
        if QWebEngineView and hasattr(self, "web_view"):
            self.web_view.reload()

    def _web_view_home(self) -> None:
        if QWebEngineView and hasattr(self, "web_view"):
            self.web_view.setUrl(QUrl(_DEFAULT_WEB_URL))
            self._sync_web_nav_chrome()

    def _sync_web_nav_chrome(self) -> None:
        if not QWebEngineView or not hasattr(self, "web_view"):
            return
        if not hasattr(self, "_web_back_btn"):
            return
        h = self.web_view.history()
        self._web_back_btn.setEnabled(h.canGoBack())
        self._web_forward_btn.setEnabled(h.canGoForward())

    def switch_tab(self, index):
        self.control_stack.setCurrentIndex(index)
        self.browser_stack.setCurrentIndex(index)
        self.control_stack.updateGeometry()
        self.browser_stack.updateGeometry()
        QTimer.singleShot(0, self._sync_ai_strip_card_button_labels)
        QTimer.singleShot(0, self._sync_web_nav_chrome)
        if index == 1:
            QTimer.singleShot(0, self._sync_url_bar_from_web_view)
        self._debounced_persist_session()

    def _reviewer_answer_card_context(self) -> Optional[str]:
        """Return combined Text / Extra / Back Extra when reviewing with answer side up."""
        if not getattr(mw, "col", None):
            tooltip("Open a profile with a collection loaded.")
            return None
        if mw.state != "review":
            tooltip("Use this from the review screen while studying a deck.")
            return None
        rev = getattr(mw, "reviewer", None)
        if not rev or not getattr(rev, "card", None):
            tooltip("No card is being reviewed.")
            return None
        if getattr(rev, "state", None) != "answer":
            tooltip("Flip the card to the answer side first.")
            return None
        note = rev.card.note()
        parts = []
        for fn in ("Text", "Extra", "Back Extra"):
            try:
                raw = note[fn]
            except KeyError:
                continue
            v = (raw or "").strip()
            if v:
                parts.append(f"=== {fn} ===\n{v}")
        if not parts:
            tooltip("This note has no Text, Extra, or Back Extra content.")
            return None
        return "\n\n".join(parts)

    def paste_prompt_into_ai_chat(self, full_text: str) -> None:
        """Show AI tab, paste ``full_text`` into the chat input, and trigger send (best-effort)."""
        if not QWebEngineView or not hasattr(self, "ai_view"):
            return
        self.show()
        self.switch_tab(0)
        js_prompt = json.dumps(full_text)
        js_script = f"""
        (function() {{
            var inputField = document.querySelector('div[contenteditable="true"]') ||
                             document.querySelector('textarea') ||
                             document.querySelector('input');
            if (inputField) {{
                if (inputField.tagName === 'DIV') {{ inputField.innerText = {js_prompt}; }}
                else {{ inputField.value = {js_prompt}; }}
                inputField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                setTimeout(() => {{
                    var btn = document.querySelector('button[aria-label*="Send"]') ||
                              document.querySelector('button[data-testid*="send"]');
                    if (btn) btn.click();
                }}, 500);
            }}
        }})();
        """
        self.ai_view.page().runJavaScript(js_script)

    def _ai_action_explain_card(self) -> None:
        ctx = self._reviewer_answer_card_context()
        if ctx is None:
            return
        self.paste_prompt_into_ai_chat(f"Explain this Anki Card:\n\n{ctx}")

    def _ai_action_simplify_card(self) -> None:
        ctx = self._reviewer_answer_card_context()
        if ctx is None:
            return
        self.paste_prompt_into_ai_chat(f"Simplify this Anki Card:\n\n{ctx}")

    def _ai_action_usmle_question(self) -> None:
        ctx = self._reviewer_answer_card_context()
        if ctx is None:
            return
        self.paste_prompt_into_ai_chat(
            _USMLE_CARD_PROMPT_TEMPLATE.replace(_USMLE_CARD_PLACEHOLDER, ctx)
        )

    def external_search_google(self, text: str) -> None:
        """Open right sidebar on Web tab with a Google search for ``text``."""
        if not QWebEngineView or not hasattr(self, "ai_view") or not hasattr(self, "web_view"):
            return
        self.show()
        self.switch_tab(1)
        url = f"https://www.google.com/search?q={quote_plus(text)}"
        self.web_view.setUrl(QUrl(url))
        self._set_url_bar_shown_url(url)

    def external_search_paste_ai(self, text: str) -> None:
        """Open right sidebar on AI tab and paste a prompt about ``text``."""
        if not QWebEngineView or not hasattr(self, "ai_view") or not hasattr(self, "web_view"):
            return
        self.paste_prompt_into_ai_chat(f"Can you explain what {text} means?")

    def _is_dark_mode(self) -> bool:
        window_color = self.palette().color(QPalette.ColorRole.Window)
        return window_color.lightness() < 128

    def _apply_close_button_appearance(self) -> None:
        """Flat chrome only; icons come from QIcon on AnkangCloseAssistantButton."""
        if not getattr(self, "_close_btn_uses_icons", False):
            return
        self.close_btn.setStyleSheet(
            """
            QPushButton#AnkangCloseAssistantBtn {
                border: none;
                background: transparent;
                padding: 0px;
            }
            QPushButton#AnkangCloseAssistantBtn:hover,
            QPushButton#AnkangCloseAssistantBtn:pressed {
                border: none;
                background: transparent;
            }
            """
        )

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._sync_ai_strip_card_button_labels)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._sync_ai_strip_card_button_labels)

    def _sync_ai_strip_card_button_labels(self) -> None:
        """Use long label only when that button's content rect fits the text; otherwise short."""
        if not hasattr(self, "_btn_explain_card"):
            return
        self.ai_toggle_btn.setToolTip("Switch AI Chatbot")
        nav_specs = (
            (
                self._nav_ai_btn,
                _NAV_AI_LABEL_LONG,
                _NAV_AI_LABEL_SHORT,
                _NAV_AI_LABEL_LONG,
                "",
            ),
            (
                self._nav_web_btn,
                _NAV_WEB_LABEL_LONG,
                _NAV_WEB_LABEL_SHORT,
                _NAV_WEB_LABEL_LONG,
                "",
            ),
        )
        specs = (
            (
                self._btn_explain_card,
                _AI_STRIP_CARD_LABELS_LONG[0],
                _AI_STRIP_CARD_LABELS_SHORT[0],
                "Explain Card",
                "",
            ),
            (
                self._btn_simplify_card,
                _AI_STRIP_CARD_LABELS_LONG[1],
                _AI_STRIP_CARD_LABELS_SHORT[1],
                "Simplify Card",
                "",
            ),
            (
                self._btn_usmle,
                _AI_STRIP_CARD_LABELS_LONG[2],
                _AI_STRIP_CARD_LABELS_SHORT[2],
                "Practice Ques — board-style multiple-choice from this card",
                "Board-style multiple-choice question from this card",
            ),
        )
        for btn, long_t, short_t, tip_short, tip_long in nav_specs + specs:
            inner = _ankang_push_button_contents_width(btn)
            fm = QFontMetrics(btn.font())
            use_long = inner > 0 and fm.horizontalAdvance(long_t) + 1 <= inner
            btn.setText(long_t if use_long else short_t)
            btn.setToolTip(tip_long if use_long else tip_short)

    def apply_theme(self):
        dark = self._is_dark_mode()
        bg = "#303030" if dark else "#f9f9f9"
        panel = "#3a3a3a" if dark else "#efefef"
        text = "#ffffff" if dark else "#000000"
        border = "#4a4a4a" if dark else "#d8d8d8"

        self.setStyleSheet(
            f"QDockWidget#AnkangRightSidebar {{ background-color: {bg}; }}"
        )
        if getattr(self, "_close_btn_uses_icons", False):
            close_chrome_qss = """
            QPushButton#AnkangCloseAssistantBtn {
                background-color: transparent;
                border: none;
            }
            QPushButton#AnkangCloseAssistantBtn:hover,
            QPushButton#AnkangCloseAssistantBtn:pressed {
                background-color: transparent;
                border: none;
            }
            """
        else:
            close_chrome_qss = ""
        if getattr(self, "_ai_puzzle_toggle_uses_icons", False):
            puzzle_toggle_qss = """
            QPushButton#AnkangAiStripToggle {
                border: none;
                background: transparent;
                padding: 0px;
            }
            QPushButton#AnkangAiStripToggle:hover,
            QPushButton#AnkangAiStripToggle:pressed {
                border: none;
                background: transparent;
            }
            """
        else:
            puzzle_toggle_qss = ""
        if getattr(self, "_web_strip_uses_icons", False):
            web_strip_icon_qss = """
            QPushButton#AnkangWebStripBack,
            QPushButton#AnkangWebStripForward,
            QPushButton#AnkangWebStripReload,
            QPushButton#AnkangWebStripHome,
            QPushButton#AnkangWebStripEnter {
                border: none;
                background: transparent;
                padding: 0px;
            }
            QPushButton#AnkangWebStripBack:hover,
            QPushButton#AnkangWebStripBack:pressed,
            QPushButton#AnkangWebStripForward:hover,
            QPushButton#AnkangWebStripForward:pressed,
            QPushButton#AnkangWebStripReload:hover,
            QPushButton#AnkangWebStripReload:pressed,
            QPushButton#AnkangWebStripHome:hover,
            QPushButton#AnkangWebStripHome:pressed,
            QPushButton#AnkangWebStripEnter:hover,
            QPushButton#AnkangWebStripEnter:pressed {
                border: none;
                background: transparent;
            }
            """
        else:
            web_strip_icon_qss = ""
        self.main_container.setStyleSheet(
            f"""
            QWidget#AnkangRightMain {{
                background-color: {bg};
                color: {text};
            }}
            QWidget {{
                color: {text};
            }}
            QPushButton {{
                background-color: {panel};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border: 1px solid #5DA9DF;
            }}
            {puzzle_toggle_qss}
            {web_strip_icon_qss}
            {ankang_text_button_stylesheet()}
            QPushButton#AnkangRightNavAi,
            QPushButton#AnkangRightNavWeb,
            QPushButton#AnkangAiStripExplain,
            QPushButton#AnkangAiStripSimplify,
            QPushButton#AnkangAiStripPQ {{
                padding-left: 5%;
                padding-right: 5%;
            }}
            QLineEdit {{
                background-color: {panel};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 3px 6px;
            }}
            {close_chrome_qss}
            """
        )
        if getattr(self, "_close_btn_uses_icons", False):
            self._apply_close_button_appearance()
        else:
            self.close_btn.setStyleSheet("")
        menu_bg = "#3a3a3a" if dark else "#f3f3f3"
        self._menu_style = f"QMenu {{ background-color: {menu_bg}; color: {text}; border: 1px solid #5DA9DF; }}"
        QTimer.singleShot(0, self._sync_ai_strip_card_button_labels)
        QTimer.singleShot(0, self._sync_web_nav_chrome)


def _ankang_right_sidebar_profile_will_close() -> None:
    dock = getattr(mw, "ankang_right_assistant", None)
    if dock is not None:
        try:
            dock.save_session_state()
        except Exception:
            pass


if not globals().get("_ANKANG_RIGHT_SIDEBAR_PROFILE_HOOK_REGISTERED"):
    try:
        gui_hooks.profile_will_close.append(_ankang_right_sidebar_profile_will_close)
        globals()["_ANKANG_RIGHT_SIDEBAR_PROFILE_HOOK_REGISTERED"] = True
    except AttributeError:
        pass