from __future__ import annotations

from aqt import mw

from .startup_popups import (
    ANKANG_HELP_WIKI_URL,
    ankang_manifest_version,
    show_welcome_dialog,
    show_whats_new_dialog,
)


def _open_url(url: str) -> None:
    from aqt.qt import QDesktopServices, QUrl

    qurl = QUrl(url)
    if qurl.isValid():
        QDesktopServices.openUrl(qurl)


def _toggle_left_sidebar() -> None:
    dock = getattr(mw, "ankang_left_sidebar", None)
    if dock is not None:
        dock.setVisible(not dock.isVisible())


def _toggle_right_sidebar() -> None:
    dock = getattr(mw, "ankang_right_assistant", None)
    if dock is not None:
        dock.setVisible(not dock.isVisible())


def install_ankang_menu() -> None:
    if getattr(mw, "_ankang_menu_installed", False):
        return
    menubar = getattr(getattr(mw, "form", None), "menubar", None)
    if menubar is None:
        return
    menu = menubar.addMenu("AnKang")
    menu.addAction("Welcome Message").triggered.connect(
        lambda: show_welcome_dialog(force=True)
    )
    menu.addAction("What's New?").triggered.connect(
        lambda: show_whats_new_dialog(force=True)
    )
    menu.addAction("Help Wiki").triggered.connect(
        lambda: _open_url(ANKANG_HELP_WIKI_URL)
    )
    menu.addSeparator()
    menu.addAction("Toggle Left Sidebar").triggered.connect(_toggle_left_sidebar)
    menu.addAction("Toggle Right Sidebar").triggered.connect(_toggle_right_sidebar)
    menu.addSeparator()
    ver_action = menu.addAction(f"AnKang v{ankang_manifest_version()}")
    ver_action.setEnabled(False)
    mw._ankang_menu_installed = True
