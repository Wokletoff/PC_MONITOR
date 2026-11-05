"""Цветовые схемы окна настроек. Оверлей они не меняют — у него свои цвета во «Внешнем виде»."""

THEMES = {
    "graphite": {
        "name": "Графит", "dark": True,
        "bg": "#141414", "panel": "#171717", "content": "#161616", "border": "#262626", "row": "#232323",
        "text": "#E6E6E6", "strong": "#FFFFFF", "muted": "#8C8C8C", "caption": "#777777", "disabled": "#555555",
        "hover": "#1E1E1E", "checked": "#242424", "input": "#1E1E1E", "input_border": "#333333",
        "button": "#101010", "accent": "#FF6A13", "accent_hover": "#FF7F33", "on_accent": "#FFFFFF",
        "track_off": "#3A3A3A", "knob_off": "#BDBDBD", "handle": "#6A6A6A",
        "preview": ("#1B2633", "#2A2421", "#3B2A1B"), "glow": (255, 140, 60),
    },
    "midnight": {
        "name": "Полночь", "dark": True,
        "bg": "#0B1220", "panel": "#0E1729", "content": "#0D1526", "border": "#1C2A44", "row": "#17233A",
        "text": "#DCE6F5", "strong": "#FFFFFF", "muted": "#7F93B3", "caption": "#6B7FA0", "disabled": "#3E4E6A",
        "hover": "#13203A", "checked": "#1A2B4D", "input": "#101C33", "input_border": "#24375A",
        "button": "#0A101C", "accent": "#38BDF8", "accent_hover": "#5CCBFA", "on_accent": "#04121F",
        "track_off": "#24375A", "knob_off": "#9FB2CF", "handle": "#4E6488",
        "preview": ("#0A1A33", "#10213F", "#1B1446"), "glow": (56, 189, 248),
    },
    "cyberpunk": {
        "name": "Киберпанк", "dark": True,
        "bg": "#0D0B14", "panel": "#120F1C", "content": "#100D19", "border": "#2A2140", "row": "#221A35",
        "text": "#E9E4F5", "strong": "#FFFFFF", "muted": "#8E84A8", "caption": "#7A6F96", "disabled": "#4A4060",
        "hover": "#1A1528", "checked": "#241C3A", "input": "#161124", "input_border": "#3A2D58",
        "button": "#0B0911", "accent": "#FF2E88", "accent_hover": "#FF5AA2", "on_accent": "#FFFFFF",
        "track_off": "#3A2D58", "knob_off": "#B9AED3", "handle": "#5D4F80",
        "preview": ("#1A0B2E", "#2B0F3D", "#0B2A3A"), "glow": (0, 229, 255),
    },
    "terminal": {
        "name": "Терминал", "dark": True, "font": "Consolas",
        "bg": "#070A07", "panel": "#0A0F0A", "content": "#090D09", "border": "#1A2A1A", "row": "#142114",
        "text": "#C8F7C5", "strong": "#E8FFE6", "muted": "#6E9C6B", "caption": "#5C875A", "disabled": "#2F4A2E",
        "hover": "#0F180F", "checked": "#132313", "input": "#0C140C", "input_border": "#224022",
        "button": "#050805", "accent": "#39FF6A", "accent_hover": "#6BFF91", "on_accent": "#031A08",
        "track_off": "#224022", "knob_off": "#8FB88C", "handle": "#3F6B3D",
        "preview": ("#04140A", "#0A1F0F", "#06100A"), "glow": (57, 255, 106),
    },
    "sakura": {
        "name": "Сакура", "dark": True,
        "bg": "#1A1218", "panel": "#1F151D", "content": "#1D141B", "border": "#3A2834", "row": "#31212C",
        "text": "#F3E6EE", "strong": "#FFFFFF", "muted": "#A88A9C", "caption": "#94788A", "disabled": "#5E4656",
        "hover": "#261A23", "checked": "#2E1F2A", "input": "#22171F", "input_border": "#4A3343",
        "button": "#160F14", "accent": "#FF8FB8", "accent_hover": "#FFA8C8", "on_accent": "#2A0F1C",
        "track_off": "#4A3343", "knob_off": "#CDB4C4", "handle": "#6E5466",
        "preview": ("#2A1626", "#3A1F2C", "#1F1A2E"), "glow": (255, 143, 184),
    },
    "latte": {
        "name": "Латте", "dark": False,
        "bg": "#F5F1EA", "panel": "#EFE9DF", "content": "#FBF8F3", "border": "#DDD3C4", "row": "#E8E0D3",
        "text": "#3B3127", "strong": "#1F1912", "muted": "#8A7B69", "caption": "#9A8A76", "disabled": "#BDB1A1",
        "hover": "#E9E1D4", "checked": "#E2D8C8", "input": "#FFFFFF", "input_border": "#D3C7B5",
        "button": "#FFFFFF", "accent": "#C2410C", "accent_hover": "#D9541C", "on_accent": "#FFFFFF",
        "track_off": "#D3C7B5", "knob_off": "#FFFFFF", "handle": "#B0A18D",
        "preview": ("#5B4A3A", "#3E3229", "#2A2420"), "glow": (255, 190, 120),
    },
    # ---- сезонные: с анимацией поверх окна (effect) ----
    "halloween": {
        "name": "Хэллоуин", "dark": True, "effect": "embers",
        "bg": "#0E0A12", "panel": "#140E18", "content": "#120C16", "border": "#2C1F33", "row": "#24192A",
        "text": "#F1E6D8", "strong": "#FFFFFF", "muted": "#A08C9E", "caption": "#8E7A8C", "disabled": "#4E3F52",
        "hover": "#1B1320", "checked": "#261A2D", "input": "#171019", "input_border": "#3B2944",
        "button": "#0B080E", "accent": "#FF7A1A", "accent_hover": "#FF9442", "on_accent": "#1A0B00",
        "track_off": "#3B2944", "knob_off": "#BFA9C2", "handle": "#6B5470",
        "preview": ("#1A0A24", "#2B0F1F", "#3A1A08"), "glow": (255, 122, 26),
    },
    "newyear": {
        "name": "Новый год", "dark": True, "effect": "snow",
        "bg": "#0A1220", "panel": "#0D1729", "content": "#0C1526", "border": "#1D2C47", "row": "#172440",
        "text": "#E6F0FF", "strong": "#FFFFFF", "muted": "#8EA3C4", "caption": "#7A90B3", "disabled": "#3E4F6C",
        "hover": "#12203A", "checked": "#1A2B4A", "input": "#0F1B31", "input_border": "#263A5E",
        "button": "#08101C", "accent": "#E5383B", "accent_hover": "#EF5A5D", "on_accent": "#FFFFFF",
        "track_off": "#263A5E", "knob_off": "#A9BAD6", "handle": "#4F6690",
        "preview": ("#0B1B33", "#102A44", "#0E3A2E"), "glow": (255, 214, 102),
    },
}

DEFAULT_THEME = "graphite"

# Текущая тема. Меняется на месте, поэтому виджеты, которые рисуют себя сами
# (переключатели, ручки, карточки тем), всегда берут актуальные цвета.
THEME = dict(THEMES[DEFAULT_THEME])


def set_theme(key):
    THEME.clear()
    THEME.update(THEMES.get(key, THEMES[DEFAULT_THEME]))
    return THEME


def build_qss(t):
    font = t.get("font", "Segoe UI")
    return f"""
QWidget {{ font-family: "{font}"; font-size: 14px; }}
#root {{ background: {t['bg']}; }}
QLabel {{ color: {t['text']}; background: transparent; }}
#header {{ background: {t['bg']}; border-bottom: 1px solid {t['border']}; }}
#badge, #kbd {{ color: {t['text']}; background: {t['input']}; border: 1px solid {t['input_border']};
               border-radius: 4px; padding: 1px 6px; font-family: Consolas, monospace; font-size: 12px; }}
#muted {{ color: {t['muted']}; }}
#crumb {{ color: {t['strong']}; font-weight: 600; }}
#sidebar {{ background: {t['panel']}; border-right: 1px solid {t['border']}; }}
#caption {{ color: {t['caption']}; font-size: 11px; font-weight: 600; padding: 16px 16px 8px 16px; }}
#hline {{ background: {t['border']}; border: none; min-height: 1px; max-height: 1px; }}
QPushButton#nav {{ text-align: left; padding: 9px 16px; border: none; background: transparent; color: {t['text']}; }}
QPushButton#nav:hover {{ background: {t['hover']}; }}
QPushButton#nav:checked {{ background: {t['checked']}; color: {t['strong']}; }}
#sidebottom {{ border-top: 1px solid {t['border']}; }}
QPushButton#ghost {{ background: transparent; border: none; border-right: 1px solid {t['border']};
                     color: {t['text']}; padding: 12px 0; }}
QPushButton#ghost:hover {{ background: {t['hover']}; color: {t['strong']}; }}
#content {{ background: {t['content']}; border-right: 1px solid {t['border']}; }}
#pagehead {{ border-bottom: 1px solid {t['border']}; min-height: 58px; max-height: 58px; }}
#pagetitle {{ font-size: 19px; font-weight: 600; color: {t['strong']}; }}
#pagesub {{ color: {t['muted']}; font-family: Consolas, monospace; font-size: 12px; }}
#caption2 {{ color: {t['caption']}; font-size: 11px; font-weight: 600; padding: 16px 24px 10px 24px;
             border-bottom: 1px solid {t['row']}; }}
#capinline {{ color: {t['caption']}; font-size: 11px; font-weight: 600; }}
#row {{ background: transparent; border-bottom: 1px solid {t['row']}; }}
#row QLabel:disabled {{ color: {t['disabled']}; }}
#row[drag="true"] {{ background: {t['checked']}; border: 1px solid {t['accent']}; }}
QPushButton#nav[drag="true"] {{ background: {t['checked']}; color: {t['strong']}; border-left: 2px solid {t['accent']}; }}
QScrollArea, #rows {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['input_border']}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QSpinBox, QComboBox, QPushButton#color {{ background: {t['input']}; border: 1px solid {t['input_border']};
    border-radius: 6px; padding: 5px 8px; color: {t['text']}; min-width: 110px; }}
QSpinBox:focus, QComboBox:focus {{ border-color: {t['accent']}; }}
QSpinBox:disabled, QComboBox:disabled, QPushButton#color:disabled {{ color: {t['disabled']}; }}
QComboBox QAbstractItemView {{ background: {t['input']}; border: 1px solid {t['input_border']}; color: {t['text']};
    selection-background-color: {t['accent']}; selection-color: {t['on_accent']}; }}
#preview {{ background: {t['bg']}; }}
QCheckBox {{ color: {t['muted']}; spacing: 6px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {t['input_border']}; border-radius: 3px;
    background: {t['input']}; }}
QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; }}
#footer {{ background: {t['bg']}; border-top: 1px solid {t['border']}; }}
QPushButton#primary {{ background: {t['accent']}; color: {t['on_accent']}; border: 1px solid {t['accent']};
    border-radius: 6px; padding: 9px 28px; font-weight: 600; }}
QPushButton#primary:hover {{ background: {t['accent_hover']}; border-color: {t['accent_hover']}; }}
QPushButton#primary:disabled {{ background: {t['input']}; color: {t['disabled']}; border-color: {t['border']}; }}
QPushButton#secondary {{ background: {t['button']}; color: {t['text']}; border: 1px solid {t['input_border']};
    border-radius: 6px; padding: 9px 28px; font-weight: 600; }}
QPushButton#secondary:hover {{ border-color: {t['accent']}; }}
QToolTip {{ background: {t['input']}; color: {t['text']}; border: 1px solid {t['input_border']}; padding: 4px; }}
"""