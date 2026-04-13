"""Shared date/time display strings and QPushButton chrome for AnKang sidebars."""

from datetime import datetime

from aqt.qt import QAbstractButton, QWidget

# --- User-facing date/time (mm/dd/yyyy, 12h am/pm) ---------------------------------


def format_user_date(dt: datetime) -> str:
    return f"{dt.month:02d}/{dt.day:02d}/{dt.year}"


def format_user_time_12h(dt: datetime) -> str:
    h = dt.hour
    m = dt.minute
    ap = "am" if h < 12 else "pm"
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    return f"{h12}:{m:02d} {ap}"


def format_user_datetime(dt: datetime) -> str:
    return f"{format_user_date(dt)} {format_user_time_12h(dt)}"


# --- Text QPushButton styling (excludes file-icon / QToolButton controls) --------

TEXT_BTN_PROP = "ankangTextButton"
ANKANG_TEXT_BUTTON_COLOR = "#745573"
ANKANG_TEXT_BUTTON_BG = "#fff7e4"
ANKANG_TEXT_BUTTON_BORDER = "#dccbb4"


def mark_ankang_text_button(btn: QAbstractButton) -> None:
    btn.setProperty(TEXT_BTN_PROP, True)
    _polish_dynamic_property(btn)


def _polish_dynamic_property(w: QWidget) -> None:
    style = w.style()
    style.unpolish(w)
    style.polish(w)


def ankang_text_button_stylesheet() -> str:
    """Append to a parent stylesheet or set on a single button (descendant rules)."""
    p = TEXT_BTN_PROP
    c = ANKANG_TEXT_BUTTON_COLOR
    bg = ANKANG_TEXT_BUTTON_BG
    bd = ANKANG_TEXT_BUTTON_BORDER
    return f"""
    QPushButton[{p}=true] {{
        background-color: {bg};
        color: {c};
        font-weight: bold;
        border: 1px solid {bd};
        border-radius: 4px;
    }}
    QPushButton[{p}=true]:hover {{
        border: 1px solid {c};
    }}
    QPushButton[{p}=true]:pressed {{
        background-color: #eee3d4;
    }}
    QPushButton[{p}=true]:checked {{
        background-color: #eee3d4;
        border: 1px solid {c};
    }}
    """
