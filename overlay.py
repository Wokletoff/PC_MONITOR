"""Отрисовка оверлея. Один и тот же OverlayModel рисует и окно поверх игры,
и предпросмотр в настройках — поэтому они всегда выглядят одинаково."""
import random
import re

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF)
from PySide6.QtWidgets import QWidget

from effects import Animator
from metrics import GIB, METRICS, SECTION_TITLES
from themes import THEMES

PAD = 12
WHITE = QColor("#FFFFFF")
SOFT = QColor("#D8D8D8")


def short_name(name):
    """'AMD Ryzen 7 7800X3D 8-Core Processor' -> 'Ryzen 7 7800X3D', 'NVIDIA GeForce RTX 5060 Ti' -> 'RTX 5060 Ti'."""
    if not name:
        return None
    s = re.sub(r"\((R|TM)\)|NVIDIA|GeForce|AMD|Radeon(?= RX)|Intel|\d+-Core|Processor|CPU|"
               r"with Radeon Graphics|@.*", "", name, flags=re.I)
    return re.sub(r"\s+", " ", s).strip() or name


# Фирменные цвета. У Intel основной синий (#0071C5) почти не виден на тёмном фоне,
# поэтому взят их второй фирменный, Energy Blue.
VENDOR_COLORS = {"NVIDIA": "#76B900", "AMD": "#ED4D1C", "Intel": "#00C7FD"}
# свой цвет процессора; для производителей, которых здесь нет, он вычисляется из цвета видеокарты
VENDOR_CPU_COLORS = {"AMD": "#ED1C24"}


def vendor_of(name):
    n = (name or "").lower()
    if "nvidia" in n or "geforce" in n:
        return "NVIDIA"
    if "amd" in n or "radeon" in n or "ryzen" in n:
        return "AMD"
    if "intel" in n:
        return "Intel"
    return None


# Палитры для блоков «Видеокарта» и «Процессор»: (цвет подписей, цвет значений)
PALETTES = {
    "vendor": {"name": "Фирменные"},       # цвета производителя, определяются по названию железа
    "custom": {"name": "Свои цвета"},      # цвета из пикеров ниже
    "aurora": {"name": "Сев. сияние", "gpu": ("#5EEAD4", "#F0FDFA"), "cpu": ("#A78BFA", "#F5F3FF")},
    "sunset": {"name": "Закат", "gpu": ("#FB923C", "#FFF7ED"), "cpu": ("#F472B6", "#FDF2F8")},
    "fire_ice": {"name": "Лёд и пламя", "gpu": ("#60A5FA", "#EFF6FF"), "cpu": ("#F87171", "#FEF2F2")},
    "neon": {"name": "Неон", "gpu": ("#00E5FF", "#FFFFFF"), "cpu": ("#FF2E88", "#FFFFFF")},
    "retro": {"name": "Ретро", "gpu": ("#39FF6A", "#E8FFE6"), "cpu": ("#FFB000", "#FFF4D6")},
    "mono": {"name": "Монохром", "gpu": ("#D4D4D4", "#FFFFFF"), "cpu": ("#9CA3AF", "#FFFFFF")},
}


def _vendor_color(sec, name):
    vendor = vendor_of(name)
    if not vendor:
        return None
    c = QColor(VENDOR_COLORS[vendor])
    if sec == "cpu" and vendor in VENDOR_CPU_COLORS:
        return VENDOR_CPU_COLORS[vendor]
    if sec == "cpu":  # процессор — тот же цвет, чуть сдвинутый, чтобы отличался от видеокарты
        h, s, l, a = c.getHslF()
        c = QColor.fromHslF(((h * 360 - 10) % 360) / 360, max(0.0, s - 0.08), min(0.8, l + 0.07), a)
    return c.name()


def section_colors(sec, d, cfg):
    """(цвет подписей, цвет значений) для блока с учётом выбранной палитры."""
    palette = cfg["look.palette"]
    if sec in ("gpu", "cpu"):
        preset = PALETTES.get(palette, {})
        if sec in preset:
            return preset[sec]
        if palette == "vendor":
            c = _vendor_color(sec, d.get("name"))
            if c:
                return c, "#FFFFFF"
    return cfg[f"look.color_{sec}"], "#FFFFFF"


def palette_preview(key, cfg):
    """Цвета для карточки палитры: на примере NVIDIA + AMD."""
    cfg = dict(cfg, **{"look.palette": key})
    return (section_colors("gpu", {"name": "NVIDIA GeForce"}, cfg),
            section_colors("cpu", {"name": "AMD Ryzen"}, cfg))


def overlay_effect(cfg):
    """Снег/искры на фоне оверлея, если выбрана сезонная тема и анимация не выключена."""
    if not cfg.get("look.overlay_effects", True):
        return None
    return THEMES.get(cfg.get("ui.theme"), {}).get("effect")


def make_overlay_animator(on_frame):
    # в оверлее частицы мельче и прозрачнее, чтобы не мешать читать цифры; 24 кадра/с достаточно
    return Animator(on_frame, fps=24, size_scale=0.85, opacity=0.8, rate_scale=1.8)


def _font(px, bold=False):
    f = QFont("Segoe UI")
    f.setPixelSize(px)
    f.setBold(bold)
    return f


_FONTS = {}


def _fonts(size):
    """Шрифты и их метрики создаются один раз на размер, а не на каждом обновлении."""
    if size not in _FONTS:
        f = {"big": _font(round(size * 1.75), True), "head": _font(round(size * 1.15), True),
             "body": _font(size), "val": _font(size, True), "small": _font(max(8, size - 1))}
        _FONTS[size] = (f, {k: QFontMetrics(v) for k, v in f.items()})
    return _FONTS[size]


def _n(v, pattern="{:.0f}"):
    return "—" if v is None else pattern.format(v)


class OverlayModel:
    def __init__(self, snap, cfg):
        self.snap, self.cfg = snap, cfg
        self.f, self.m = _fonts(cfg["look.font_size"])
        self.rows = self._compose()
        self.width = max(cfg["look.width"], max((self._row_w(r) for r in self.rows), default=0) + 2 * PAD)
        self.height = sum(self._row_h(r) for r in self.rows) + 2 * PAD

    # ---------- что показываем ----------
    def _compose(self):
        """Блоки и показатели идут в порядке, заданном перетаскиванием в настройках."""
        rows = []
        for block in self.cfg["layout.blocks"]:
            if block == "fps":
                self._fps_block(rows)
            elif block == "graph":
                if self.cfg["graph.show"]:
                    rows.append(("graph",))
            else:
                self._section(block, rows)
        return rows

    def _fps_block(self, rows):
        cfg, fps = self.cfg, self.snap.get("fps") or {}
        if not cfg["fps.show"]:
            return
        if rows:
            rows.append(("sep",))
        rows.append(("title", "FPS", _n(fps.get("fps")), cfg["look.color_fps"]))
        stats = [f"{label}: {_n(fps.get(k))}" for key, label, k in
                 (("stats.avg", "AVG", "avg"), ("stats.low1", "1% Low", "low1"),
                  ("stats.low01", "0.1% Low", "low01")) if cfg[key]]
        if stats:
            rows.append(("small", "   ".join(stats)))
        if cfg["fps.latency"]:
            rows.append(("small", f"Latency: {_n(fps.get('latency'), '{:.1f}')} мс"))
        if cfg["fps.window"]:
            rows.append(("small", f"Окно: {fps.get('process') or '—'}"))

    def _section(self, sec, rows):
        cfg = self.cfg
        if not cfg[f"{sec}.show"]:
            return
        d = self.snap.get(sec) or {}
        color, value_color = section_colors(sec, d, cfg)
        if rows:
            rows.append(("sep",))
        title = "ОЗУ" if sec == "ram" else short_name(d.get("name")) or SECTION_TITLES[sec]
        rows.append(("head", title, color))
        by_key = {m[0]: m for m in METRICS[sec]}
        for key in cfg[f"layout.{sec}"]:
            m = by_key.get(key)
            if m and cfg[f"{sec}.{key}"]:
                rows.append(("kv", m[1], m[2](d) or "—", color, value_color))

    # ---------- размеры ----------
    def _row_h(self, r):
        k = r[0]
        if k == "title":
            return self.m["big"].height()
        if k == "small":
            return self.m["small"].height()
        if k == "head":
            return self.m["head"].height() + 2
        if k == "kv":
            return self.m["body"].height()
        if k == "sep":
            return 11
        return self.cfg["graph.height"] + 8  # graph

    def _row_w(self, r):
        k = r[0]
        if k == "title":
            return self.m["big"].horizontalAdvance(r[1]) + 30 + self.m["big"].horizontalAdvance(r[2])
        if k == "small":
            return self.m["small"].horizontalAdvance(r[1])
        if k == "head":
            return self.m["head"].horizontalAdvance(r[1])
        if k == "kv":
            return self.m["body"].horizontalAdvance(r[1]) + 24 + self.m["val"].horizontalAdvance(r[2])
        return 0

    # ---------- отрисовка ----------
    def paint(self, p: QPainter, particles=None):
        """Фон → частицы → текст. Если есть анимация, текст рисуется один раз в картинку
        (кэш живёт, пока не пришли новые данные), а на каждом кадре только копируется —
        так кадр анимации стоит в разы дешевле."""
        cfg = self.cfg
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        bg = QColor(12, 12, 14)
        bg.setAlphaF(cfg["look.opacity"] / 100)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        radius = cfg["look.radius"]
        p.drawRoundedRect(QRectF(0, 0, self.width, self.height), radius, radius)
        if particles is not None:  # анимация между фоном и текстом, не выходя за скругления
            path = QPainterPath()
            path.addRoundedRect(QRectF(0, 0, self.width, self.height), radius, radius)
            p.save()
            p.setClipPath(path)
            particles.paint(p)
            p.restore()
            if not p.transform().isScaling():  # в уменьшенном предпросмотре кэш был бы размытым
                p.drawPixmap(0, 0, self._content_pixmap(p.device().devicePixelRatioF()))
                return
        self._paint_content(p)

    def _content_pixmap(self, dpr):
        key = (int(self.width), dpr)
        if getattr(self, "_cache_key", None) != key:
            pm = QPixmap(int((self.width + 1) * dpr), int((self.height + 1) * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.Antialiasing)
            q.setRenderHint(QPainter.TextAntialiasing)
            self._paint_content(q)
            q.end()
            self._cache, self._cache_key = pm, key
        return self._cache

    def _paint_content(self, p):
        cfg = self.cfg
        x0, x1, y = PAD, self.width - PAD, PAD
        left, right = Qt.AlignLeft | Qt.AlignVCenter, Qt.AlignRight | Qt.AlignVCenter
        for r in self.rows:
            h = self._row_h(r)
            rect = QRectF(x0, y, x1 - x0, h)
            k = r[0]
            if k == "title":
                p.setFont(self.f["big"])
                p.setPen(WHITE)
                p.drawText(rect, left, r[1])
                p.setPen(QColor(r[3]))
                p.drawText(rect, right, r[2])
            elif k == "small":
                p.setFont(self.f["small"])
                p.setPen(SOFT)
                p.drawText(rect, left, r[1])
            elif k == "head":
                p.setFont(self.f["head"])
                p.setPen(QColor(r[2]))
                p.drawText(rect, left, r[1])
            elif k == "kv":
                p.setFont(self.f["body"])
                p.setPen(QColor(r[3]))
                p.drawText(rect, left, r[1])
                p.setFont(self.f["val"])
                p.setPen(QColor(r[4]) if len(r) > 4 else WHITE)
                p.drawText(rect, right, r[2])
            elif k == "sep":
                p.setPen(QPen(QColor(255, 255, 255, 45), 1))
                p.drawLine(QPointF(x0, y + h / 2), QPointF(x1, y + h / 2))
            else:
                self._graph(p, QRectF(x0, y + 6, x1 - x0, cfg["graph.height"]))
            y += h

    def _graph(self, p, rect):
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 180))
        p.drawRect(rect)
        color = QColor(self.cfg["look.color_graph"])
        fts = (self.snap.get("fps") or {}).get("frametimes") or []

        if len(fts) >= 2:
            n = max(2, int(rect.width()))
            if len(fts) > n:  # прореживание: максимум в каждой корзине, чтобы не терять пики
                step = len(fts) / n
                fts_d = []
                for i in range(n):
                    a = int(i * step)
                    fts_d.append(max(fts[a:max(a + 1, int((i + 1) * step))]))
            else:
                fts_d = fts
            top = max(33.4, max(fts_d) * 1.15)
            dx = rect.width() / (len(fts_d) - 1)
            poly = QPolygonF([QPointF(rect.left() + i * dx, rect.bottom() - min(v, top) / top * rect.height())
                              for i, v in enumerate(fts_d)])
            p.setPen(QPen(color, 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawPolyline(poly)
            label = f"{fts[-1]:.1f} ms"
        else:
            label = "нет данных"

        f = QFont(self.f["small"])
        f.setBold(True)
        p.setFont(f)
        p.setPen(color)
        p.drawText(rect.adjusted(5, 0, 0, -4), Qt.AlignLeft | Qt.AlignBottom, label)
        p.restore()


def demo_snapshot(t):
    """Демо-данные для предпросмотра, когда игра не запущена."""
    rnd = random.Random(int(t * 2))
    fts = [6.9 + rnd.uniform(-0.25, 0.25) for _ in range(500)]
    for i in (rnd.randint(60, 200), rnd.randint(280, 450)):
        fts[i] = rnd.uniform(11, 18)
    return {
        "fps": {"fps": rnd.randint(140, 148), "avg": 142, "low1": 101, "low01": 77,
                "latency": 17.6, "process": "game.exe", "frametimes": fts},
        "gpu": {"name": "NVIDIA GeForce RTX 5060 Ti", "load": 95, "temp": 63, "clock": 2426,
                "voltage": 0.95, "power": 160, "fan_rpm": 1450, "fan_pct": 42, "hotspot": 74,
                "mem_temp": 70, "mem_clock": 28000, "vram_used": 9.8 * GIB, "vram_total": 16 * GIB},
        "cpu": {"name": "AMD Ryzen 7 7800X3D 8-Core Processor", "load": 36, "temp": 68,
                "clock": 4983, "power": 73},
        "ram": {"used": 14.2 * GIB, "total": 32 * GIB, "load": 44, "speed": 6000},
    }


class OverlayWindow(QWidget):
    """Прозрачное окно поверх всех окон, клики проходят сквозь него."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.model = None
        self._cfg, self._w = None, 0
        self.anim = make_overlay_animator(lambda _: self.update())

    def refresh(self, snap, cfg, visible=True):
        if not (visible and cfg["general.enabled"]):
            self.hide()
            return
        self.model = OverlayModel(snap, cfg)
        # ширина только растёт (сбрасывается при смене настроек), иначе окно
        # дёргается каждый раз, когда меняется длина какого-нибудь числа
        if cfg is not self._cfg:
            self._cfg, self._w = cfg, 0
        self._w = max(self._w, self.model.width)
        self.model.width = self._w
        w, h = int(self.model.width) + 1, int(self.model.height) + 1
        if self.size().width() != w or self.size().height() != h:
            self.resize(w, h)

        screen = next((sc for sc in QGuiApplication.screens() if sc.name() == cfg["general.screen"]),
                      None) or QGuiApplication.primaryScreen()  # экран отключён — на основной
        geo = screen.geometry()
        pos, ox, oy = cfg["general.position"], cfg["general.offset_x"], cfg["general.offset_y"]
        x = geo.left() + ox if "слева" in pos else geo.right() - w - ox
        y = geo.top() + oy if "Вверху" in pos else geo.bottom() - h - oy
        if self.x() != x or self.y() != y:
            self.move(x, y)

        self.anim.resize(w, h)
        self.anim.set_kind(overlay_effect(cfg))
        if not self.isVisible():
            self.show()
        self.raise_()  # игры в borderless иногда перекрывают topmost-окна
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        self.anim.set_running(True)

    def hideEvent(self, e):
        super().hideEvent(e)
        self.anim.set_running(False)  # оверлей скрыт — анимация не крутится

    def paintEvent(self, _):
        if self.model:
            p = QPainter(self)
            self.model.paint(p, self.anim.system)