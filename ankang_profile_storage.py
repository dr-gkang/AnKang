"""User data paths under the Anki profile (survives add-on updates)."""

from __future__ import annotations

import os
import shutil

from aqt import mw

# …/<profile>/AnKang_Data/{Widgets|R_Sidebar}/…
PROFILE_DATA_ROOT = "AnKang_Data"
WIDGETS_SUBDIR = "Widgets"
R_SIDEBAR_SUBDIR = "R_Sidebar"

# Parent of any add-on folder under Anki’s addons21 directory.
_ADDONS21_ROOT = os.path.dirname(os.path.dirname(__file__))

# AnkiWeb installs use numeric folder names under addons21.
ANKANG_ANKIWEB_PACKAGE_IDS: tuple[str, ...] = ("1680917863",)

_LEGACY_ROWS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("todo_storage.json",), "todo_storage.json"),
    (("ankang_sidebar_notes.json",), "ankang_sidebar_notes.json"),
    (("ankang_sidebar_notes.txt",), "ankang_sidebar_notes.txt"),
    (
        ("exam_cntdwn_storage.json", "ankang_exam_countdown.json"),
        "exam_cntdwn_storage.json",
    ),
)

_migrated_profiles: set[str] = set()


def _ankang_data_root() -> str:
    r = os.path.join(mw.pm.profileFolder(), PROFILE_DATA_ROOT)
    os.makedirs(r, exist_ok=True)
    return r


def profile_data_dir() -> str:
    """Widget JSON etc.: AnKang_Data/Widgets. Call after ensure_addon_data_migrated_for_profile."""
    d = os.path.join(_ankang_data_root(), WIDGETS_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


def profile_r_sidebar_dir() -> str:
    """Right sidebar session + qtwebengine parent: AnKang_Data/R_Sidebar."""
    d = os.path.join(_ankang_data_root(), R_SIDEBAR_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


def profile_r_sidebar_session_path() -> str:
    ensure_addon_data_migrated_for_profile()
    return os.path.join(profile_r_sidebar_dir(), "session.json")


def profile_r_sidebar_qtwebengine_dir() -> str:
    ensure_addon_data_migrated_for_profile()
    d = os.path.join(profile_r_sidebar_dir(), "qtwebengine")
    os.makedirs(d, exist_ok=True)
    return d


def _migrate_legacy_profile_layout(profile_root: str) -> None:
    """Move former Ankang / AnkangSidebar paths into AnKang_Data subfolders."""
    old_widgets = os.path.join(profile_root, "Ankang")
    old_rsidebar = os.path.join(profile_root, "AnkangSidebar")
    new_widgets = os.path.join(profile_root, PROFILE_DATA_ROOT, WIDGETS_SUBDIR)
    new_rsidebar = os.path.join(profile_root, PROFILE_DATA_ROOT, R_SIDEBAR_SUBDIR)

    if os.path.isdir(old_widgets):
        os.makedirs(new_widgets, exist_ok=True)
        for name in os.listdir(old_widgets):
            src = os.path.join(old_widgets, name)
            dst = os.path.join(new_widgets, name)
            if os.path.isfile(src) and not os.path.exists(dst):
                try:
                    shutil.move(src, dst)
                except OSError:
                    try:
                        shutil.copy2(src, dst)
                    except OSError:
                        pass
        try:
            os.rmdir(old_widgets)
        except OSError:
            pass

    if os.path.isdir(old_rsidebar):
        os.makedirs(new_rsidebar, exist_ok=True)
        old_sess = os.path.join(old_rsidebar, "session.json")
        new_sess = os.path.join(new_rsidebar, "session.json")
        if os.path.isfile(old_sess) and not os.path.isfile(new_sess):
            try:
                shutil.move(old_sess, new_sess)
            except OSError:
                pass
        old_qt = os.path.join(old_rsidebar, "qtwebengine")
        new_qt = os.path.join(new_rsidebar, "qtwebengine")
        if os.path.isdir(old_qt) and not os.path.isdir(new_qt):
            try:
                shutil.move(old_qt, new_qt)
            except OSError:
                pass
        try:
            if os.path.isdir(old_rsidebar) and not os.listdir(old_rsidebar):
                os.rmdir(old_rsidebar)
        except OSError:
            pass


def _best_candidate_path(filename: str) -> str | None:
    candidates: list[tuple[float, str]] = []
    try:
        names = os.listdir(_ADDONS21_ROOT)
    except OSError:
        return None
    for name in names:
        addon_dir = os.path.join(_ADDONS21_ROOT, name)
        if not os.path.isdir(addon_dir) or name.startswith("."):
            continue
        path = os.path.join(addon_dir, filename)
        if os.path.isfile(path):
            try:
                candidates.append((os.path.getmtime(path), path))
            except OSError:
                continue
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _best_source_among(*src_names: str) -> str | None:
    best_m = -1.0
    best_p: str | None = None
    for name in src_names:
        p = _best_candidate_path(name)
        if not p:
            continue
        try:
            m = os.path.getmtime(p)
        except OSError:
            continue
        if m > best_m:
            best_m = m
            best_p = p
    return best_p


def _sync_widget_file_from_addons21(
    dest_root: str, dest_name: str, src_names: tuple[str, ...]
) -> None:
    """Copy newest matching file from addons21 into the profile.

    If the profile file already exists (e.g. from the other AnKang install), we still
    copy over when any add-on folder has a *newer* mtime than the profile copy, so
    editing in 1680917863 then opening the dev add-on picks up those changes.
    """
    dest = os.path.join(dest_root, dest_name)
    src = _best_source_among(*src_names)
    if not src:
        return
    try:
        src_m = os.path.getmtime(src)
    except OSError:
        return
    if not os.path.isfile(dest):
        try:
            shutil.copy2(src, dest)
        except OSError:
            pass
        return
    try:
        dest_m = os.path.getmtime(dest)
    except OSError:
        try:
            shutil.copy2(src, dest)
        except OSError:
            pass
        return
    if src_m > dest_m:
        try:
            shutil.copy2(src, dest)
        except OSError:
            pass


def _purge_legacy_json_under_addons21(dest_root: str) -> None:
    try:
        folder_names = os.listdir(_ADDONS21_ROOT)
    except OSError:
        return

    official = frozenset(ANKANG_ANKIWEB_PACKAGE_IDS)

    for src_names, profile_dest_name in _LEGACY_ROWS:
        dest = os.path.join(dest_root, profile_dest_name)
        if not os.path.isfile(dest):
            continue

        for folder in folder_names:
            if folder.startswith("."):
                continue
            addon_dir = os.path.join(_ADDONS21_ROOT, folder)
            if not os.path.isdir(addon_dir):
                continue
            if folder not in official and not _addon_dir_has_ankang_marker(addon_dir):
                continue
            for sn in src_names:
                path = os.path.join(addon_dir, sn)
                if not os.path.isfile(path):
                    continue
                try:
                    os.remove(path)
                except OSError:
                    pass


def _addon_dir_has_ankang_marker(addon_dir: str) -> bool:
    if not os.path.isfile(os.path.join(addon_dir, "__init__.py")):
        return False
    if os.path.isfile(os.path.join(addon_dir, "ankang_profile_storage.py")):
        return True
    if os.path.isfile(os.path.join(addon_dir, "todolist.py")) and os.path.isfile(
        os.path.join(addon_dir, "sidebar_right.py")
    ):
        return True
    return False


def profile_data_file(filename: str) -> str:
    ensure_addon_data_migrated_for_profile()
    return os.path.join(profile_data_dir(), filename)


def ensure_addon_data_migrated_for_profile() -> None:
    pf = mw.pm.profileFolder()
    if pf in _migrated_profiles:
        return

    _migrate_legacy_profile_layout(pf)

    dest_root = profile_data_dir()

    _sync_widget_file_from_addons21(dest_root, "todo_storage.json", ("todo_storage.json",))
    _sync_widget_file_from_addons21(
        dest_root, "ankang_sidebar_notes.json", ("ankang_sidebar_notes.json",)
    )
    _sync_widget_file_from_addons21(
        dest_root, "ankang_sidebar_notes.txt", ("ankang_sidebar_notes.txt",)
    )
    _sync_widget_file_from_addons21(
        dest_root,
        "exam_cntdwn_storage.json",
        ("exam_cntdwn_storage.json", "ankang_exam_countdown.json"),
    )

    _purge_legacy_json_under_addons21(dest_root)

    _migrated_profiles.add(pf)
