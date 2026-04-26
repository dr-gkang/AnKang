import os
from aqt import mw
from aqt.qt import *
from aqt.utils import openLink

from .ankang_format_styles import ankang_text_button_stylesheet, mark_ankang_text_button
from .sidebar_right import (
    AnkangCloseAssistantButton,
    _CLOSE_ASSISTANT_BTN_PX,
    _load_icon_from_path,
    _resolve_media_asset,
)
from .todolist import TodoWidget
from .notes import NotesWidget
from .timer import TimerWidget
from .stopwatch import StopwatchWidget
from .countdown import ExamCountdownWidget

# Support dialog: set AnkiWeb after you publish (e.g. https://ankiweb.net/shared/info/<id>).
_ANKANG_ANKIWEB_ADDON_URL = "https://ankiweb.net/shared/info/1680917863"
_ANKANG_KOFI_URL = "https://ko-fi.com/drgkang"
_ANKANG_GITHUB_REPO_URL = "https://github.com/dr-gkang/AnKang"


def ankang_divider_color(widget: QWidget) -> str:
    """Muted frame line: strong enough to read, softer than pure black."""
    dark = widget.palette().color(QPalette.ColorRole.Window).lightness() < 128
    return "#5a5a5a" if dark else "#6e6e6e"


def _ankang_github_issues_url() -> str:
    base = _ANKANG_GITHUB_REPO_URL.rstrip("/")
    if base.endswith("/issues"):
        return base
    return f"{base}/issues"


def _make_ankang_left_nav_button(
    addon_path: str,
    parent: QWidget,
    *,
    unpressed_base: str,
    pressed_base: str,
    object_name: str,
    tooltip: str,
    fallback_text: str,
) -> tuple[QPushButton, bool]:
    """Same 35×35 icon swap as the hide-sidebar button, or a text fallback if assets are missing."""
    up = _resolve_media_asset(
        addon_path, "Buttons", "Unpressed", base_name=unpressed_base
    )
    pr = _resolve_media_asset(addon_path, "Buttons", "Pressed", base_name=pressed_base)
    if up and pr:
        iu = _load_icon_from_path(up)
        ip = _load_icon_from_path(pr)
        if not iu.isNull() and not ip.isNull():
            btn = AnkangCloseAssistantButton(
                up, pr, parent, object_name=object_name
            )
            btn.setToolTip(tooltip)
            return btn, True
    btn = QPushButton(fallback_text, parent)
    btn.setObjectName(object_name)
    btn.setFlat(True)
    btn.setFixedSize(_CLOSE_ASSISTANT_BTN_PX, _CLOSE_ASSISTANT_BTN_PX)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    mark_ankang_text_button(btn)
    return btn, False


def _ankang_support_dialog(parent: QWidget) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle("Rate/Support AnKang")
    root = QVBoxLayout(dlg)
    root.setContentsMargins(12, 12, 12, 12)
    root.setSpacing(10)
    msg = QLabel(
        "Thanks for downloading AnKang.\n\n"
        "If you'd like to support development, leaving a rating on AnkiWeb and donating on Ko-fi helps a lot."
    )
    msg.setWordWrap(True)
    root.addWidget(msg)
    row = QHBoxLayout()
    row.addStretch(1)
    b_anki = QPushButton("Open AnkiWeb")
    b_kofi = QPushButton("Open Ko-fi")
    for b in (b_anki, b_kofi):
        mark_ankang_text_button(b)
    b_anki.clicked.connect(lambda: openLink(_ANKANG_ANKIWEB_ADDON_URL))
    b_kofi.clicked.connect(lambda: openLink(_ANKANG_KOFI_URL))
    row.addWidget(b_anki)
    row.addWidget(b_kofi)
    root.addLayout(row)
    dlg.setStyleSheet(ankang_text_button_stylesheet())
    dlg.exec()


def _ankang_feedback_dialog(parent: QWidget) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle("Bug Report / Feature Request")
    root = QVBoxLayout(dlg)
    root.setContentsMargins(12, 12, 12, 12)
    root.setSpacing(10)
    msg = QLabel(
        "Report a bug or request a feature using the AnKang GitHub Issues page."
    )
    msg.setWordWrap(True)
    root.addWidget(msg)
    row = QHBoxLayout()
    row.addStretch(1)
    b_issues = QPushButton("Open GitHub Issues")
    for b in (b_issues,):
        mark_ankang_text_button(b)
    b_issues.clicked.connect(lambda: openLink(_ankang_github_issues_url()))
    row.addWidget(b_issues)
    root.addLayout(row)
    dlg.setStyleSheet(ankang_text_button_stylesheet())
    dlg.exec()


# ... (Keep SVG Import Logic) ...

class AnkangLeftSidebar(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setObjectName("AnkangLeftSidebar")
        # Wide enough for support + feedback + hide (3×35px) with margins and spacing.
        self.setFixedWidth(132)
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea)
        # Remove any title-bar reservation so the dock sits flush at top.
        self.setTitleBarWidget(QWidget())

        self.main_widget = QWidget()
        self.main_widget.setObjectName("AnkangLeftMain")
        self.layout = QVBoxLayout(self.main_widget)
        self.layout.setContentsMargins(1, 0, 1, 2)
        self.layout.setSpacing(8)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        addon_path = os.path.dirname(__file__)

        # Top bar (35px): parallels right sidebar nav row so arrow buttons line up.
        up_la = _resolve_media_asset(
            addon_path, "Buttons", "Unpressed", base_name="C_LeftArrow1"
        )
        pr_la = _resolve_media_asset(
            addon_path, "Buttons", "Pressed", base_name="CP_LeftArrow1"
        ) or _resolve_media_asset(
            addon_path, "Buttons", "Unpressed", base_name="CP_LeftArrow1"
        )
        if up_la and pr_la:
            iu = _load_icon_from_path(up_la)
            ip = _load_icon_from_path(pr_la)
            if not iu.isNull() and not ip.isNull():
                self.minimize_btn = AnkangCloseAssistantButton(
                    up_la,
                    pr_la,
                    self,
                    object_name="AnkangLeftMinimizeBtn",
                )
                self.minimize_btn.setToolTip("Hide left sidebar")
                self._left_min_uses_icons = True
            else:
                self.minimize_btn, self._left_min_uses_icons = _make_ankang_left_nav_button(
                    addon_path,
                    self,
                    unpressed_base="C_LeftArrow1",
                    pressed_base="CP_LeftArrow1",
                    object_name="AnkangLeftMinimizeBtn",
                    tooltip="Hide left sidebar",
                    fallback_text="«",
                )
        else:
            self.minimize_btn, self._left_min_uses_icons = _make_ankang_left_nav_button(
                addon_path,
                self,
                unpressed_base="C_LeftArrow1",
                pressed_base="CP_LeftArrow1",
                object_name="AnkangLeftMinimizeBtn",
                tooltip="Hide left sidebar",
                fallback_text="«",
            )

        self.minimize_btn.clicked.connect(self.hide)
        if not self._left_min_uses_icons:
            mark_ankang_text_button(self.minimize_btn)

        self.support_btn, self._left_support_uses_icons = _make_ankang_left_nav_button(
            addon_path,
            self,
            unpressed_base="C_Heart",
            pressed_base="CP_Heart",
            object_name="AnkangLeftSupportBtn",
            tooltip="Rate/Support AnKang",
            fallback_text="♥",
        )
        self.support_btn.clicked.connect(
            lambda: _ankang_support_dialog(self)
        )

        self.feedback_btn, self._left_feedback_uses_icons = _make_ankang_left_nav_button(
            addon_path,
            self,
            unpressed_base="C_Skull",
            pressed_base="CP_Skull",
            object_name="AnkangLeftFeedbackBtn",
            tooltip="Bug Report / Feature Request",
            fallback_text="☠",
        )
        self.feedback_btn.clicked.connect(
            lambda: _ankang_feedback_dialog(self)
        )

        nav_wrap = QWidget()
        nav_wrap.setFixedHeight(35)
        nav_row = QHBoxLayout(nav_wrap)
        nav_row.setContentsMargins(5, 0, 5, 0)
        nav_row.setSpacing(5)
        nav_row.addStretch(1)
        nav_row.addWidget(
            self.support_btn,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        nav_row.addWidget(
            self.feedback_btn,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        nav_row.addWidget(
            self.minimize_btn,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        self.layout.addWidget(nav_wrap)

    

        # LOGO
        logo_path = os.path.join(addon_path, "media", "logo.svg")
        if os.path.exists(logo_path):
            logo_label = QLabel()
            logo_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            logo_size = QSize(96, 98)
            logo_pixmap = QIcon(logo_path).pixmap(logo_size)
            if not logo_pixmap.isNull():
                logo_label.setPixmap(logo_pixmap)
                self.layout.addWidget(logo_label, alignment=Qt.AlignmentFlag.AlignHCenter)
            elif "QSvgWidget" in globals():
                svg = QSvgWidget(logo_path)
                svg.setFixedSize(96, 98)
                self.layout.addWidget(svg, alignment=Qt.AlignmentFlag.AlignHCenter)

        # ADDING THE WIDGETS
        self.todo_widget = TodoWidget()
        self.notes_widget = NotesWidget()
        self.timer_widget = TimerWidget()
        self.stopwatch_widget = StopwatchWidget()
        self.countdown_widget = ExamCountdownWidget()

        self.layout.addWidget(self.todo_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.layout.addWidget(self.notes_widget, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Push functional widgets to bottom.
        self.layout.addStretch(1)
        self.layout.addWidget(self.countdown_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.layout.addWidget(self.timer_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.layout.addWidget(self.stopwatch_widget, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.layout.addStretch()
        self.setWidget(self.main_widget)
        self.apply_theme()

    def _is_dark_mode(self) -> bool:
        window_color = self.palette().color(QPalette.ColorRole.Window)
        return window_color.lightness() < 128

    def apply_theme(self, main_divider_px: int = 1):
        dark = self._is_dark_mode()
        bg = "#303030" if dark else "#f9f9f9"
        text = "#ffffff" if dark else "#000000"
        px = max(1, int(main_divider_px))
        line = ankang_divider_color(self)

        def _nav_icon_chrome_rules(object_name: str) -> str:
            return f"""
            QPushButton#{object_name} {{
                background-color: transparent;
                border: none;
            }}
            QPushButton#{object_name}:hover,
            QPushButton#{object_name}:pressed {{
                background-color: transparent;
                border: none;
            }}
            """

        nav_icon_qss_parts: list[str] = []
        if getattr(self, "_left_min_uses_icons", False):
            nav_icon_qss_parts.append(_nav_icon_chrome_rules("AnkangLeftMinimizeBtn"))
        if getattr(self, "_left_support_uses_icons", False):
            nav_icon_qss_parts.append(_nav_icon_chrome_rules("AnkangLeftSupportBtn"))
        if getattr(self, "_left_feedback_uses_icons", False):
            nav_icon_qss_parts.append(_nav_icon_chrome_rules("AnkangLeftFeedbackBtn"))
        left_nav_icon_qss = "".join(nav_icon_qss_parts)

        self.main_widget.setStyleSheet(
            f"""
            QWidget#AnkangLeftMain {{
                background-color: {bg};
                border-right: {px}px solid {line};
            }}
            {left_nav_icon_qss}
            {ankang_text_button_stylesheet()}
            """
        )

        _per_btn_icon_qss = """
            QPushButton#%s {
                border: none;
                background: transparent;
                padding: 0px;
            }
            QPushButton#%s:hover,
            QPushButton#%s:pressed {
                border: none;
                background: transparent;
            }
            """
        for btn, uses, oid in (
            (self.minimize_btn, getattr(self, "_left_min_uses_icons", False), "AnkangLeftMinimizeBtn"),
            (self.support_btn, getattr(self, "_left_support_uses_icons", False), "AnkangLeftSupportBtn"),
            (self.feedback_btn, getattr(self, "_left_feedback_uses_icons", False), "AnkangLeftFeedbackBtn"),
        ):
            if uses:
                btn.setStyleSheet(_per_btn_icon_qss % (oid, oid, oid))
            else:
                btn.setStyleSheet("")
        self.timer_widget.set_text_color(text)
        self.stopwatch_widget.set_text_color(text)
        self.countdown_widget.set_text_color(text)