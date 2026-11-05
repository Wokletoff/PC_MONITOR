import json
import sys
from pathlib import Path

from metrics import METRICS

# В собранном exe файлы (config.json, lhm/, PresentMon) лежат рядом с exe, а не рядом с .py
APP_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"

POSITIONS = ["Вверху слева", "Вверху справа", "Внизу слева", "Внизу справа"]

DEFAULTS = {
    "general.enabled": True,
    "general.screen": "",          # имя экрана (QScreen.name()); пусто = основной
    "general.position": POSITIONS[0],
    "general.offset_x": 20,
    "general.offset_y": 20,
    "general.interval": 500,

    "ui.theme": "graphite",        # тема окна настроек (themes.py)
    "ui.effects": True,            # анимация сезонных тем в окне настроек
    "look.overlay_effects": True,  # анимация сезонных тем на фоне оверлея
    "look.font_size": 12,
    "look.opacity": 80,
    "look.width": 220,
    "look.radius": 10,
    "look.vendor_colors": True,    # устарело, оставлено для чтения старых config.json
    "look.palette": "vendor",      # палитра GPU/CPU в оверлее (overlay.PALETTES)
    "look.color_fps": "#FF6A13",
    "look.color_gpu": "#3DDC6B",
    "look.color_cpu": "#4EA8FF",
    "look.color_ram": "#B784FF",
    "look.color_graph": "#E02424",

    "fps.show": True,
    "fps.latency": True,
    "fps.window": True,

    "stats.avg": True,
    "stats.low1": True,
    "stats.low01": True,
    "stats.seconds": 30,

    "graph.show": True,
    "graph.height": 80,
    "graph.seconds": 10,
}
# порядок блоков в оверлее и показателей внутри блоков (меняется перетаскиванием в настройках)
DEFAULTS["layout.blocks"] = ["fps", "gpu", "cpu", "ram", "graph"]
for _section, _items in METRICS.items():
    DEFAULTS[f"{_section}.show"] = True
    DEFAULTS[f"layout.{_section}"] = [m[0] for m in _items]
    for _key, _label, _fmt, _on in _items:
        DEFAULTS[f"{_section}.{_key}"] = _on


def sanitize(data):
    """Берём только известные ключи с правильным типом — защита от битого/чужого файла.
    В списках порядка выкидываем неизвестное и дописываем в конец новые пункты."""
    out = {}
    for k, v in data.items():
        if k not in DEFAULTS or type(v) is not type(DEFAULTS[k]):
            continue
        if isinstance(v, list):
            known = DEFAULTS[k]
            v = list(dict.fromkeys(x for x in v if x in known))
            v += [x for x in known if x not in v]
        out[k] = v
    return out


def load(path=CONFIG_PATH):
    cfg = dict(DEFAULTS)
    try:
        data = sanitize(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return cfg
    if "look.palette" not in data and data.get("look.vendor_colors") is False:
        data["look.palette"] = "custom"  # раньше фирменные цвета были выключены — значит, свои
    cfg.update(data)
    return cfg


def save(cfg, path=CONFIG_PATH):
    Path(path).write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")