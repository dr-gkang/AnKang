from __future__ import annotations

import json
import os

from aqt import mw
from aqt.qt import *

from .ankang_format_styles import ankang_text_button_stylesheet, mark_ankang_text_button
from .ankang_profile_storage import load_profile_ui_state, save_profile_ui_state

ANKANG_HELP_WIKI_URL = "https://github.com/dr-gkang/AnKang/wiki"
ANKANG_ISSUES_URL = "https://github.com/dr-gkang/AnKang/issues"
ANKANG_ANKIWEB_REVIEW_URL = "https://ankiweb.net/shared/review/1680917863"
ANKANG_KOFI_URL = "https://ko-fi.com/drgkang"


def ankang_manifest_version() -> str:
    manifest_path = os.path.join(os.path.dirname(__file__), "manifest.json")
    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        version = str(data.get("version") or "").strip()
        if version:
            return version
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return "dev"


def _seen_version_state() -> tuple[dict, str, str]:
    state = load_profile_ui_state()
    current = ankang_manifest_version()
    last_seen = str(state.get("last_seen_version") or "").strip()
    return state, current, last_seen


def _set_welcome_seen(seen: bool) -> None:
    state = load_profile_ui_state()
    state["welcome_seen"] = bool(seen)
    save_profile_ui_state(state)


def _open_url(url: str) -> None:
    qurl = QUrl(url)
    if qurl.isValid():
        QDesktopServices.openUrl(qurl)


def show_welcome_dialog(*, force: bool = False) -> None:
    state = load_profile_ui_state()
    if not force and bool(state.get("welcome_seen", False)):
        return
    dlg = QDialog(mw)
    dlg.setWindowTitle("Welcome to AnKang")
    dlg.setMinimumWidth(560)
    root = QVBoxLayout(dlg)
    root.setContentsMargins(16, 16, 16, 16)
    root.setSpacing(12)

    logo_path = os.path.join(os.path.dirname(__file__), "media", "logo.svg")
    if os.path.isfile(logo_path):
        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        pm = QIcon(logo_path).pixmap(QSize(220, 225))
        if not pm.isNull():
            logo.setPixmap(pm)
            root.addWidget(logo)

    title = QLabel("Welcome to AnKang!")
    title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    title.setStyleSheet("font-size: 18px; font-weight: 700;")
    root.addWidget(title)

    msg = QLabel(
        "Thank you for intalling AnKang! Your support is greatly appreciated!\n\n"
        "If you ever want help using AnKang, take a look at the AnKang Wiki for guidance on how to use this add-on.\n\n"
        "To report bugs or request features, please use the AnKang GitHub Issues page.\n\n"
        "If AnKang helps your workflow, please leave a rating on AnkiWeb and consider donating on Ko-fi."
    )
    msg.setWordWrap(True)
    msg.setStyleSheet("font-size: 13px; line-height: 1.35em;")
    root.addWidget(msg)

    dont_show = QCheckBox("Don't show again")
    dont_show.setStyleSheet("padding-top: 4px;")
    root.addWidget(dont_show)

    row1 = QHBoxLayout()
    row1.setSpacing(8)
    wiki_btn = QPushButton("AnKang Wiki")
    issues_btn = QPushButton("Report Bug / Request Feature")
    mark_ankang_text_button(wiki_btn)
    mark_ankang_text_button(issues_btn)
    wiki_btn.setMinimumHeight(34)
    issues_btn.setMinimumHeight(34)
    wiki_btn.clicked.connect(lambda: _open_url(ANKANG_HELP_WIKI_URL))
    issues_btn.clicked.connect(lambda: _open_url(ANKANG_ISSUES_URL))
    row1.addWidget(wiki_btn, 1)
    row1.addWidget(issues_btn, 1)
    root.addLayout(row1)

    row2 = QHBoxLayout()
    row2.setSpacing(8)
    rating_btn = QPushButton("Leave a rating!")
    donate_btn = QPushButton("Donate to support!")
    mark_ankang_text_button(rating_btn)
    mark_ankang_text_button(donate_btn)
    rating_btn.setMinimumHeight(34)
    donate_btn.setMinimumHeight(34)
    rating_btn.clicked.connect(lambda: _open_url(ANKANG_ANKIWEB_REVIEW_URL))
    donate_btn.clicked.connect(lambda: _open_url(ANKANG_KOFI_URL))
    row2.addWidget(rating_btn, 1)
    row2.addWidget(donate_btn, 1)
    root.addLayout(row2)

    close_row = QHBoxLayout()
    close_row.addStretch(1)
    close_btn = QPushButton("Close")
    mark_ankang_text_button(close_btn)
    close_btn.clicked.connect(dlg.accept)
    close_row.addWidget(close_btn)
    root.addLayout(close_row)

    dlg.setStyleSheet(ankang_text_button_stylesheet())
    dlg.exec()
    if dont_show.isChecked():
        _set_welcome_seen(True)


def show_whats_new_dialog(*, force: bool = False) -> None:
    state, current, last_seen = _seen_version_state()
    if not force and last_seen == current:
        return
    dlg = QDialog(mw)
    dlg.setWindowTitle(f"What's New - AnKang {current}")
    dlg.setMinimumWidth(520)
    root = QVBoxLayout(dlg)
    root.setContentsMargins(16, 16, 16, 16)
    root.setSpacing(10)

    title = QLabel(f"What's New in AnKang v{current}?!")
    title.setWordWrap(True)
    title.setStyleSheet("font-size: 17px; font-weight: 700;")
    root.addWidget(title)

    msg = QLabel(
        "<ul>"
        "<li>"
        "<b>Added shortcuts to toggle Sidebars</b>"
        "<ul>"
        "<li>Shift+Left to toggle Left Sidebar</li>"
        "<li>Shift+Right to toggle Right Sidebar</li>"
        "</ul></li>"
        "</ul>"
    )
    msg.setWordWrap(True)
    msg.setTextFormat(Qt.TextFormat.RichText)
    msg.setStyleSheet("font-size: 13px;")
    root.addWidget(msg)

    row = QHBoxLayout()
    row.addStretch(1)
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dlg.accept)
    row.addWidget(close_btn)
    root.addLayout(row)
    dlg.exec()
    state["last_seen_version"] = current
    save_profile_ui_state(state)


def show_startup_popups() -> None:
    show_welcome_dialog()
    show_whats_new_dialog()
