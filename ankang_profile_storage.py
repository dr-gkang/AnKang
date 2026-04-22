"""User data paths under the Anki profile (survives add-on updates)."""

from __future__ import annotations

import os
import shutil

from aqt import mw

PROFILE_SUBDIR = "Ankang"
ADDON_ROOT = os.path.dirname(__file__)

_migrated_profiles: set[str] = set()


def profile_data_dir() -> str:
    d = os.path.join(mw.pm.profileFolder(), PROFILE_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return d


def profile_data_file(filename: str) -> str:
    ensure_addon_data_migrated_for_profile()
    return os.path.join(profile_data_dir(), filename)


def ensure_addon_data_migrated_for_profile() -> None:
    pf = mw.pm.profileFolder()
    if pf in _migrated_profiles:
        return
    dest_root = profile_data_dir()

    def move_into_profile(src_name: str, dest_name: str | None = None) -> None:
        dest_name = dest_name or src_name
        dest = os.path.join(dest_root, dest_name)
        if os.path.exists(dest):
            return
        src = os.path.join(ADDON_ROOT, src_name)
        if not os.path.exists(src):
            return
        try:
            shutil.move(src, dest)
        except OSError:
            try:
                shutil.copy2(src, dest)
            except OSError:
                pass

    move_into_profile("todo_storage.json")
    move_into_profile("ankang_sidebar_notes.json")
    move_into_profile("ankang_sidebar_notes.txt")

    exam_dest = os.path.join(dest_root, "exam_cntdwn_storage.json")
    if not os.path.exists(exam_dest):
        if os.path.exists(os.path.join(ADDON_ROOT, "exam_cntdwn_storage.json")):
            move_into_profile("exam_cntdwn_storage.json")
        elif os.path.exists(os.path.join(ADDON_ROOT, "ankang_exam_countdown.json")):
            move_into_profile("ankang_exam_countdown.json", "exam_cntdwn_storage.json")

    _migrated_profiles.add(pf)
