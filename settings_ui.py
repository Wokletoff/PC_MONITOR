import json
import sys
import time

from PySide6.QtCore import Property, QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QIcon, QPen, QKeySequence, QLinearGradient, QPainter, QPixmap,
                           QRadialGradient, QShortcut)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox,
                               QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

import config
from metrics import METRICS
from overlay import (PALETTES, OverlayModel, demo_snapshot, make_overlay_animator, overlay_effect,
                     palette_preview)
from effects import EffectLayer
from themes import THEME, THEMES, build_qss, set_theme

APP_NAME = ("PC", "Мониторинг")  # поменяйте на своё название
VERSION = "1.0.0"
ACCENT = "#FF6A13"  # фирменный цвет иконки; цвета окна берутся из темы (themes.py)


def _metric_fields(sec, show_label):
    return [("toggle", f"{sec}.show", show_label)] + \
           [("toggle", f"{sec}.{key}", label) for key, label, _, _ in METRICS[sec]]


# (группа, [(id, название, значок, подзаголовок списка, поля)])
PAGES = [
    ("ОВЕРЛЕЙ", [
        ("general", "Общие", "⚙", "ПАРАМЕТРЫ", [
            ("toggle", "general.enabled", "Показывать оверлей"),
            ("screen", "general.screen", "Экран"),
            ("action", "identify", "Номера экранов", "Показать"),
            ("combo", "general.position", "Положение на экране", config.POSITIONS),
            ("spin", "general.offset_x", "Отступ по горизонтали", 0, 3000, 1, " px"),
            ("spin", "general.offset_y", "Отступ по вертикали", 0, 3000, 1, " px"),
            ("spin", "general.interval", "Интервал обновления", 100, 2000, 50, " мс"),
            ("blocks", "layout.blocks", "Порядок блоков в оверлее"),
        ]),
        ("look", "Внешний вид", "◐", "ПАРАМЕТРЫ", [
            ("theme", "ui.theme", "Тема интерфейса"),
            ("toggle", "ui.effects", "Анимация праздничных тем в окне настроек"),
            ("toggle", "look.overlay_effects", "Анимация праздничных тем на фоне оверлея"),
            ("spin", "look.font_size", "Размер шрифта", 8, 24, 1, " px"),
            ("spin", "look.opacity", "Непрозрачность фона", 0, 100, 5, " %"),
            ("spin", "look.width", "Минимальная ширина", 120, 600, 10, " px"),
            ("spin", "look.radius", "Скругление углов", 0, 24, 1, " px"),
            ("palette", "look.palette", "Палитра видеокарты и процессора"),
            ("color", "look.color_fps", "Цвет FPS"),
            ("color", "look.color_gpu", "Свой цвет видеокарты"),
            ("color", "look.color_cpu", "Свой цвет процессора"),
            ("color", "look.color_ram", "Цвет блока «ОЗУ»"),
            ("color", "look.color_graph", "Цвет графика"),
        ]),
    ]),
    ("ПОКАЗАТЕЛИ", [
        ("fps", "FPS", "◷", "ПОКАЗАТЕЛИ", [
            ("toggle", "fps.show", "Показывать блок «FPS»"),
            ("toggle", "fps.latency", "Задержка (Latency)"),
            ("toggle", "fps.window", "Имя процесса игры"),
            ("toggle", "stats.avg", "Средний FPS (AVG)"),
            ("toggle", "stats.low1", "1% Low"),
            ("toggle", "stats.low01", "0.1% Low"),
            ("spin", "stats.seconds", "Период расчёта статистики", 5, 300, 5, " с"),
        ]),
        ("gpu", "Видеокарта", "▣", "ПОКАЗАТЕЛИ", _metric_fields("gpu", "Показывать блок «Видеокарта»")),
        ("cpu", "Процессор", "▦", "ПОКАЗАТЕЛИ", _metric_fields("cpu", "Показывать блок «Процессор»")),
        ("ram", "ОЗУ", "▤", "ПОКАЗАТЕЛИ", _metric_fields("ram", "Показывать блок «ОЗУ»")),
        ("graph", "График времени кадра", "∿", "ПОКАЗАТЕЛИ", [
            ("toggle", "graph.show", "Показывать график"),
            ("spin", "graph.height", "Высота", 30, 300, 5, " px"),
            ("spin", "graph.seconds", "Отрезок времени", 2, 60, 1, " с"),
        ]),
    ]),
    ("СИСТЕМА", [
        ("diag", "Диагностика", "⚑", "СОСТОЯНИЕ ИСТОЧНИКОВ ДАННЫХ", []),
    ]),
]

# блоки оверлея: (id, название, значок) — из группы «ПОКАЗАТЕЛИ» меню
BLOCKS = [(pid, title, icon) for caption, pages in PAGES if caption == "ПОКАЗАТЕЛИ"
          for pid, title, icon, _, _ in pages]

LEVEL_COLORS = {"ok": "#3DDC6B", "warn": "#F5A524", "error": "#FF4D4F"}

class Toggle(QAbstractButton):
    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(34, 20)
        self._k = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_silent(self, on):
        self.blockSignals(True)
        self.setChecked(bool(on))
        self.blockSignals(False)
        self._k = 1.0 if on else 0.0
        self.update()

    def _get(self):
        return self._k

    def _set(self, v):
        self._k = v
        self.update()

    knob = Property(float, _get, _set)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off, on, t = QColor(THEME["track_off"]), QColor(THEME["accent"]), self._k
        track = QColor(int(off.red() + (on.red() - off.red()) * t),
                       int(off.green() + (on.green() - off.green()) * t),
                       int(off.blue() + (on.blue() - off.blue()) * t))
        if not self.isEnabled():
            track.setAlphaF(0.35)
        h = self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(self.rect()), h / 2, h / 2)
        d = h - 6
        knob = QColor(THEME["on_accent"]) if t > 0.5 else QColor(THEME["knob_off"])
        if not self.isEnabled():
            knob.setAlphaF(0.4)
        p.setBrush(knob)
        p.drawEllipse(QRectF(3 + t * (self.width() - d - 6), 3, d, d))


class ColorButton(QPushButton):
    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("color")
        self.setCursor(Qt.PointingHandCursor)
        self.setLayoutDirection(Qt.RightToLeft)  # образец цвета справа от кода
        self._c = "#FFFFFF"
        self.clicked.connect(self._pick)

    def set_color(self, c):
        self._c = c.upper()
        self.setText(self._c)
        pm = QPixmap(14, 14)
        pm.fill(QColor(c))
        self.setIcon(QIcon(pm))

    def _pick(self):
        c = QColorDialog.getColor(QColor(self._c), self, "Выбор цвета")
        if c.isValid():
            self.set_color(c.name())
            self.changed.emit(self._c)


class PreviewCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.model = None
        self.setMinimumSize(320, 300)
        self._ov_rect = None  # где нарисован оверлей — анимация перерисовывает только его
        self.anim = make_overlay_animator(
            lambda _: self.update(self._ov_rect) if self._ov_rect else self.update())

    def set_model(self, m):
        self.model = m
        self.anim.resize(m.width, m.height)
        self.anim.set_kind(overlay_effect(m.cfg))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        g = QLinearGradient(0, 0, w, h)
        c0, c1, c2 = THEME["preview"]
        g.setColorAt(0, QColor(c0))
        g.setColorAt(0.6, QColor(c1))
        g.setColorAt(1, QColor(c2))
        p.fillRect(self.rect(), g)
        glow = QRadialGradient(w * 0.8, h * 0.25, w * 0.7)
        glow.setColorAt(0, QColor(*THEME["glow"], 55))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), glow)
        if not self.model:
            return
        m, margin = self.model, 24
        s = min(1.0, (w - 2 * margin) / m.width, (h - 2 * margin) / m.height)
        x0, y0 = (w - m.width * s) / 2, max(margin, (h - m.height * s) / 2)
        self._ov_rect = QRectF(x0, y0, m.width * s, m.height * s).toAlignedRect().adjusted(-2, -2, 2, 2)
        p.translate(x0, y0)
        p.scale(s, s)
        m.paint(p, self.anim.system)


class ThemeCard(QAbstractButton):
    """Мини-превью темы: боковая панель, строки, переключатель и кнопка в её цветах."""

    def __init__(self, key):
        super().__init__()
        self.key, self.t = key, THEMES[key]
        self.setCheckable(True)
        self.setFixedSize(128, 80)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _):
        t, on = self.t, self.isChecked()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1.5, 1.5, self.width() - 3, 56)
        p.setPen(QPen(QColor(THEME["accent"] if on else THEME["border"]), 2 if on else 1))
        p.setBrush(QColor(t["bg"]))
        p.drawRoundedRect(r, 7, 7)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t["panel"]))
        p.drawRoundedRect(QRectF(r.left() + 5, r.top() + 5, 28, r.height() - 10), 3, 3)
        for i in range(3):  # пункты меню
            p.setBrush(QColor(t["accent"] if i == 1 else t["muted"]))
            p.drawRoundedRect(QRectF(r.left() + 9, r.top() + 11 + i * 10, 14 if i else 18, 3), 1.5, 1.5)
        p.setBrush(QColor(t["strong"]))
        p.drawRoundedRect(QRectF(r.left() + 40, r.top() + 10, 42, 4), 2, 2)
        p.setBrush(QColor(t["muted"]))
        for i in range(2):
            p.drawRoundedRect(QRectF(r.left() + 40, r.top() + 22 + i * 9, 34 - i * 8, 3), 1.5, 1.5)
        p.setBrush(QColor(t["accent"]))  # включённый переключатель
        p.drawRoundedRect(QRectF(r.right() - 27, r.top() + 19, 19, 10), 5, 5)
        p.setBrush(QColor(t["on_accent"]))
        p.drawEllipse(QPointF(r.right() - 13, r.top() + 24), 3.2, 3.2)
        p.setBrush(QColor(t["accent"]))  # кнопка «Применить»
        p.drawRoundedRect(QRectF(r.right() - 38, r.bottom() - 15, 30, 8), 3, 3)
        effect = t.get("effect")
        if effect:  # намёк на анимацию: снежинки или искры
            dots = ((44, 40), (58, 47), (72, 37), (86, 49), (66, 9), (98, 44))
            p.setBrush(QColor(255, 255, 255, 200) if effect == "snow" else QColor("#FF9F1C"))
            for i, (x, y) in enumerate(dots):
                p.drawEllipse(QPointF(r.left() + x, r.top() + y), 1.4 if i % 2 else 1.0, 1.4 if i % 2 else 1.0)

        f = QFont(self.font())
        f.setBold(on)
        p.setFont(f)
        p.setPen(QColor(THEME["strong"] if on else THEME["muted"]))
        p.drawText(QRectF(0, 60, self.width(), 20), Qt.AlignCenter, t["name"])


class PaletteCard(QAbstractButton):
    """Мини-оверлей: блок видеокарты и блок процессора в цветах палитры."""

    def __init__(self, name, colors_fn):
        super().__init__()
        self.name, self.colors_fn = name, colors_fn
        self.setCheckable(True)
        self.setFixedSize(128, 80)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, _):
        on = self.isChecked()
        (gl, gv), (cl, cv) = self.colors_fn()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1.5, 1.5, self.width() - 3, 56)
        p.setPen(QPen(QColor(THEME["accent"] if on else THEME["border"]), 2 if on else 1))
        p.setBrush(QColor("#0C0C0E"))
        p.drawRoundedRect(r, 7, 7)
        p.setPen(Qt.NoPen)
        x0, x1 = r.left() + 10, r.right() - 10
        for top, label, value in ((r.top() + 7, gl, gv), (r.top() + 31, cl, cv)):
            p.setBrush(QColor(label))
            p.drawRoundedRect(QRectF(x0, top, 38, 4), 2, 2)          # заголовок блока
            for i in range(2):
                y = top + 8 + i * 6
                p.setBrush(QColor(label))
                p.drawRoundedRect(QRectF(x0, y, 30 - i * 6, 3), 1.5, 1.5)  # подпись
                p.setBrush(QColor(value))
                p.drawRoundedRect(QRectF(x1 - 16, y, 16, 3), 1.5, 1.5)     # значение
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRect(QRectF(x0, r.top() + 27, x1 - x0, 1))
        f = QFont(self.font())
        f.setBold(on)
        p.setFont(f)
        p.setPen(QColor(THEME["strong"] if on else THEME["muted"]))
        p.drawText(QRectF(0, 60, self.width(), 20), Qt.AlignCenter, self.name)


class CardPicker(QWidget):
    """Сетка карточек-вариантов (темы, палитры), выбран один."""
    changed = Signal(str)

    def __init__(self, cards):
        super().__init__()
        from PySide6.QtWidgets import QGridLayout
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self.group = QButtonGroup(self)
        self.cards = cards
        for i, (key, card) in enumerate(cards.items()):
            card.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self.group.addButton(card)
            grid.addWidget(card, i // 3, i % 3)

    def set_value(self, key):
        (self.cards.get(key) or next(iter(self.cards.values()))).setChecked(True)

    def refresh(self):
        for card in self.cards.values():
            card.update()


class DragHandle(QWidget):
    """Шесть точек слева от строки — за них строку можно перетащить."""

    def __init__(self):
        super().__init__()
        self.setFixedSize(14, 20)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("Перетащите, чтобы изменить порядок")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(THEME["handle"] if self.isEnabled() else THEME["disabled"]))
        for cx in (4, 10):
            for cy in (5, 10, 15):
                p.drawEllipse(QPointF(cx, cy), 1.6, 1.6)


class SortableList(QWidget):
    """Вертикальный список, элементы которого меняются местами перетаскиванием.
    Порядок меняется прямо во время перетаскивания, поэтому предпросмотр обновляется сразу."""
    reordered = Signal(list)

    def __init__(self):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(0)
        self.items = []      # [(ключ, виджет)] в текущем порядке
        self.handles = {}    # за что тянуть -> виджет
        self._press = self._cand = self._drag = None

    def add(self, key, widget, handle):
        self.items.append((key, widget))
        self.lay.addWidget(widget)
        self.handles[handle] = widget
        handle.installEventFilter(self)

    def keys(self):
        return [k for k, _ in self.items]

    def set_order(self, keys):
        pos = {k: i for i, k in enumerate(keys)}
        self.items.sort(key=lambda kw: pos.get(kw[0], len(pos)))
        for _, w in self.items:
            self.lay.removeWidget(w)
        for _, w in self.items:
            self.lay.addWidget(w)
        self.lay.activate()

    def eventFilter(self, obj, e):
        widget = self.handles.get(obj)
        if widget is None:
            return False
        t = e.type()
        if t == QEvent.MouseButtonPress and e.button() == Qt.LeftButton:
            self._press, self._cand = e.globalPosition().toPoint(), widget
            return False
        if t == QEvent.MouseMove and self._press is not None and e.buttons() & Qt.LeftButton:
            gp = e.globalPosition().toPoint()
            if self._drag is None:
                if (gp - self._press).manhattanLength() < QApplication.startDragDistance():
                    return False
                self._drag = self._cand
                self._mark(self._drag, True)
                QApplication.setOverrideCursor(Qt.ClosedHandCursor)
            self._move_to(self.mapFromGlobal(gp).y())
            return True
        if t == QEvent.MouseButtonRelease and self._press is not None:
            self._press = None
            if self._drag is not None:
                self._mark(self._drag, False)
                self._drag = None
                QApplication.restoreOverrideCursor()
                if isinstance(obj, QAbstractButton):
                    obj.setDown(False)
                self.reordered.emit(self.keys())
                return True  # отпускание после перетаскивания — не клик
        return False

    def _move_to(self, y):
        cur = next(i for i, (_, w) in enumerate(self.items) if w is self._drag)
        idx = sum(1 for _, w in self.items if w is not self._drag and w.geometry().center().y() < y)
        if idx != cur:
            self.items.insert(idx, self.items.pop(cur))
            self.lay.removeWidget(self._drag)
            self.lay.insertWidget(idx, self._drag)
            self.lay.activate()
            self.reordered.emit(self.keys())

    @staticmethod
    def _mark(w, on):
        w.setProperty("drag", on)
        w.style().unpolish(w)
        w.style().polish(w)
        w.update()


class SettingsWindow(QWidget):
    applied = Signal(dict)

    def __init__(self, cfg, hub):
        super().__init__()
        self.hub = hub
        self.saved, self.draft = dict(cfg), dict(cfg)
        self.setters, self.page_rows, self.sub_labels = {}, {}, {}
        self.nav, self.page_lists, self._diag = {}, {}, None
        self.block_lists = []  # все списки порядка блоков (меню и «Общие») — держим их синхронными
        self.hide_on_close = True

        self.setObjectName("root")
        self.setWindowTitle(f"{' '.join(APP_NAME)} — настройки")
        self.resize(1180, 740)
        self.setMinimumSize(1000, 600)
        self._theme_key = None

        self.stack = QStackedWidget()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self._sidebar())
        content = QFrame(objectName="content")
        content.setMinimumWidth(440)
        QVBoxLayout(content).setContentsMargins(0, 0, 0, 0)
        content.layout().addWidget(self.stack)
        body.addWidget(content, 1)
        body.addWidget(self._preview(), 1)
        root.addLayout(body, 1)
        root.addWidget(self._footer())

        QShortcut(QKeySequence("Ctrl+S"), self, self.apply)
        QShortcut(QKeySequence("Esc"), self, self.cancel)

        self.effects = EffectLayer(self)  # создаётся последним — рисуется поверх всего окна
        self.effects.setGeometry(self.rect())
        self._load_controls()
        self.first_nav.click()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        # таймер запускается в showEvent, чтобы при старте в трей ничего не крутилось
        self._dark_titlebar(THEME["dark"])

    # ---------------- построение интерфейса ----------------
    def _header(self):
        f = QFrame(objectName="header")
        f.setFixedHeight(52)
        h = QHBoxLayout(f)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(10)
        self.title_lbl = QLabel()
        h.addWidget(self.title_lbl)
        h.addWidget(QLabel(VERSION, objectName="badge"), 0, Qt.AlignVCenter)
        h.addSpacing(14)
        for text in ("/", "Настройки", "/"):
            h.addWidget(QLabel(text, objectName="muted"))
        self.crumb = QLabel(objectName="crumb")
        h.addWidget(self.crumb)
        h.addStretch()
        return f

    def _sidebar(self):
        f = QFrame(objectName="sidebar")
        f.setFixedWidth(236)
        v = QVBoxLayout(f)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        group = QButtonGroup(self)
        self.first_nav = None
        for gi, (caption, pages) in enumerate(PAGES):
            if gi:
                v.addSpacing(8)
                v.addWidget(QFrame(objectName="hline"))
            v.addWidget(QLabel(caption, objectName="caption"))
            # блоки оверлея в меню можно перетаскивать — так меняется их порядок в оверлее
            blocks = SortableList() if caption == "ПОКАЗАТЕЛИ" else None
            for pid, title, icon, list_caption, fields in pages:
                idx = self.stack.addWidget(self._page(pid, title, list_caption, fields))
                b = QPushButton(f"{icon}   {title}", objectName="nav")
                b.setCheckable(True)
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, i=idx, t=title: (self.stack.setCurrentIndex(i),
                                                                   self.crumb.setText(t)))
                group.addButton(b)
                if blocks:
                    b.setToolTip("Перетащите, чтобы изменить порядок блоков в оверлее")
                    blocks.add(pid, b, b)
                else:
                    v.addWidget(b)
                self.nav[pid] = (b, icon, title)
                self.first_nav = self.first_nav or b
            if blocks:
                v.addWidget(blocks)
                blocks.reordered.connect(lambda keys, src=blocks: self._set_blocks(keys, src))
                self.block_lists.append(blocks)
                self.setters["layout.blocks"] = lambda order: [l.set_order(order) for l in self.block_lists]
        v.addStretch()
        bottom = QFrame(objectName="sidebottom")
        bh = QHBoxLayout(bottom)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(0)
        for text, fn in (("Экспорт", self.export), ("Импорт", self.import_), ("Сброс", self.reset)):
            b = QPushButton(text, objectName="ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            bh.addWidget(b)
        v.addWidget(bottom)
        return f

    def _page(self, pid, title, caption, fields):
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        head = QFrame(objectName="pagehead")
        h = QHBoxLayout(head)
        h.setContentsMargins(24, 0, 24, 0)
        h.addWidget(QLabel(title, objectName="pagetitle"))
        h.addStretch()
        sub = QLabel(self._hw_label(pid), objectName="pagesub")
        self.sub_labels[pid] = sub
        h.addWidget(sub)
        if pid == "diag":
            copy = QPushButton("Копировать", objectName="secondary")
            copy.setCursor(Qt.PointingHandCursor)
            copy.setStyleSheet("padding: 5px 14px; font-weight: 500;")
            h.addSpacing(10)
            copy.clicked.connect(self._copy_diag)
            h.addWidget(copy)
        v.addWidget(head)
        if pid in METRICS:
            caption += "  ·  ПОРЯДОК МЕНЯЕТСЯ ПЕРЕТАСКИВАНИЕМ"
        v.addWidget(QLabel(caption, objectName="caption2"))

        inner = QWidget(objectName="rows")
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(0)
        rows = []
        sortable = SortableList() if pid in METRICS else None  # показатели GPU/CPU/ОЗУ
        for i, f in enumerate(fields):
            if f[0] == "blocks":  # заголовок + список блоков, которые можно перетаскивать
                head = QFrame(objectName="row")
                head.setFixedHeight(46)
                hl = QHBoxLayout(head)
                hl.setContentsMargins(24, 0, 24, 0)
                hl.addWidget(QLabel(f[2]))
                hl.addStretch()
                hl.addWidget(QLabel("перетаскивайте", objectName="muted"))
                iv.addWidget(head)
                iv.addWidget(self._blocks_list())
                rows.append((f[1], head))
                continue
            if f[0] in ("theme", "palette"):  # высокая строка: подпись сверху, карточки тем под ней
                row = QFrame(objectName="row")
                rl = QVBoxLayout(row)
                rl.setContentsMargins(24, 14, 24, 16)
                rl.setSpacing(12)
                rl.addWidget(QLabel(f[2]))
                rl.addWidget(self._control(f), 0, Qt.AlignLeft)
                iv.addWidget(row)
                rows.append((f[1], row))
                continue
            row = QFrame(objectName="row")
            row.setFixedHeight(46)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(14 if sortable else 24, 0, 24, 0)
            rl.setSpacing(10)
            handle = None
            if sortable:
                handle = DragHandle() if i else QWidget()  # у «Показывать блок» ручки нет
                handle.setFixedSize(14, 20)
                rl.addWidget(handle)
            rl.addWidget(QLabel(f[2]))
            rl.addStretch()
            rl.addWidget(self._control(f))
            if sortable and i:
                sortable.add(f[1].split(".", 1)[1], row, handle)
            else:
                iv.addWidget(row)
            rows.append((f[1], row))
        if sortable:
            iv.addWidget(sortable)
            sortable.reordered.connect(lambda keys, k=f"layout.{pid}": self._set(k, keys))
            self.setters[f"layout.{pid}"] = sortable.set_order
        iv.addStretch()
        self.page_lists[pid] = iv
        self.page_rows[pid] = rows

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(inner)
        scroll.viewport().setAutoFillBackground(False)
        v.addWidget(scroll, 1)
        return page

    def _control(self, f):
        kind, key = f[0], f[1]
        if kind == "toggle":
            w = Toggle()
            w.toggled.connect(lambda v, k=key: self._set(k, v))
            self.setters[key] = w.set_silent
        elif kind == "spin":
            lo, hi, step, suffix = f[3:]
            w = QSpinBox()
            w.setRange(lo, hi)
            w.setSingleStep(step)
            w.setSuffix(suffix)
            w.setAlignment(Qt.AlignRight)
            w.valueChanged.connect(lambda v, k=key: self._set(k, v))
            self.setters[key] = lambda v, w=w: self._silent(w, w.setValue, v)
        elif kind == "combo":
            w = QComboBox()
            w.addItems(f[3])
            w.currentTextChanged.connect(lambda v, k=key: self._set(k, v))
            self.setters[key] = lambda v, w=w: self._silent(w, w.setCurrentText, v)
        elif kind == "screen":
            w = QComboBox()
            self.screen_combo = w
            w.currentIndexChanged.connect(lambda i, w=w, k=key: self._set(k, w.itemData(i) or ""))
            self.setters[key] = self._select_screen
            self._fill_screens()
            app = QGuiApplication.instance()  # монитор подключили/отключили — обновляем список
            app.screenAdded.connect(lambda *_: self._fill_screens())
            app.screenRemoved.connect(lambda *_: self._fill_screens())
        elif kind == "theme":
            w = CardPicker({k: ThemeCard(k) for k in THEMES})
            w.changed.connect(lambda v, k=key: self._set(k, v))
            self.setters[key] = w.set_value
        elif kind == "palette":
            w = CardPicker({k: PaletteCard(p["name"], lambda k=k: palette_preview(k, self.draft))
                            for k, p in PALETTES.items()})
            w.changed.connect(lambda v, k=key: self._set(k, v))
            self.setters[key] = w.set_value
            self.palette_picker = w
        elif kind == "action":
            w = QPushButton(f[3], objectName="secondary")
            w.setCursor(Qt.PointingHandCursor)
            w.setStyleSheet("padding: 5px 14px; font-weight: 500;")
            w.clicked.connect(self._identify_screens)
        else:
            w = ColorButton()
            w.changed.connect(lambda v, k=key: self._set(k, v))
            self.setters[key] = w.set_color
        return w

    # ---------------- экраны ----------------
    def _fill_screens(self):
        w = self.screen_combo
        w.blockSignals(True)
        w.clear()
        w.addItem("Основной экран", "")
        primary = QGuiApplication.primaryScreen()
        for i, sc in enumerate(QGuiApplication.screens()):
            g = sc.geometry()
            model = " ".join(x for x in (sc.manufacturer(), sc.model()) if x).strip()
            label = f"Экран {i + 1}" + (f" — {model}" if model else "") + \
                    f" ({g.width()}×{g.height()})" + (" · основной" if sc is primary else "")
            w.addItem(label, sc.name())
        w.blockSignals(False)
        self._select_screen(self.draft.get("general.screen", ""))

    def _select_screen(self, name):
        w = self.screen_combo
        i = w.findData(name)
        w.blockSignals(True)
        w.setCurrentIndex(i if i >= 0 else 0)  # сохранённый экран не подключён — «Основной»
        w.blockSignals(False)

    def _identify_screens(self):
        """Крупные номера на каждом экране на 2,5 секунды — как «Определить» в настройках Windows."""
        self._marks = []
        for i, sc in enumerate(QGuiApplication.screens()):
            m = QLabel(str(i + 1))
            m.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
            m.setAlignment(Qt.AlignCenter)
            m.setStyleSheet(f"background: {THEME['bg']}; color: {THEME['accent']}; font-size: 110px;"
                            f"font-weight: 700; border: 3px solid {THEME['accent']};")
            m.resize(180, 180)
            g = sc.geometry()
            m.move(g.left() + 40, g.top() + 40)
            m.show()
            self._marks.append(m)
        QTimer.singleShot(2500, lambda: [m.close() for m in self._marks])

    def _blocks_list(self):
        lst = SortableList()
        for pid, title, icon in BLOCKS:
            row = QFrame(objectName="row")
            row.setFixedHeight(42)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(24, 0, 24, 0)
            rl.setSpacing(12)
            handle = DragHandle()
            rl.addWidget(handle)
            rl.addWidget(QLabel(f"{icon}   {title}"))
            rl.addStretch()
            lst.add(pid, row, handle)
        lst.reordered.connect(lambda keys, src=lst: self._set_blocks(keys, src))
        self.block_lists.append(lst)
        return lst

    def _set_blocks(self, keys, source):
        for lst in self.block_lists:
            if lst is not source:  # перетаскиваемый список уже в нужном порядке
                lst.set_order(keys)
        self._set("layout.blocks", keys)

    @staticmethod
    def _silent(widget, setter, value):
        widget.blockSignals(True)
        setter(value)
        widget.blockSignals(False)

    def _preview(self):
        f = QFrame(objectName="preview")
        f.setMinimumWidth(360)
        v = QVBoxLayout(f)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        head = QFrame(objectName="pagehead")
        h = QHBoxLayout(head)
        h.setContentsMargins(16, 0, 16, 0)
        h.addWidget(QLabel("ПРЕДПРОСМОТР", objectName="capinline"))
        h.addStretch()
        self.demo = QCheckBox("демо-данные")
        self.demo.setChecked(True)
        self.demo.toggled.connect(self._tick)
        h.addWidget(self.demo)
        h.addSpacing(14)
        self.status_lbl = QLabel(objectName="muted")
        h.addWidget(self.status_lbl)
        v.addWidget(head)
        self.canvas = PreviewCanvas()
        v.addWidget(self.canvas, 1)
        return f

    def _footer(self):
        f = QFrame(objectName="footer")
        f.setFixedHeight(64)
        h = QHBoxLayout(f)
        h.setContentsMargins(16, 0, 16, 0)
        h.setSpacing(8)
        self.changed_lbl = QLabel()
        h.addWidget(self.changed_lbl)
        h.addSpacing(18)
        for key, text in (("Esc", "отмена"), ("Ctrl+S", "применить")):
            h.addWidget(QLabel(key, objectName="kbd"), 0, Qt.AlignVCenter)
            h.addWidget(QLabel(text, objectName="muted"))
            h.addSpacing(12)
        h.addStretch()
        self.cancel_btn = QPushButton("Отмена", objectName="secondary")
        self.cancel_btn.clicked.connect(self.cancel)
        self.apply_btn = QPushButton("Применить", objectName="primary")
        self.apply_btn.clicked.connect(self.apply)
        h.addWidget(self.cancel_btn)
        h.addWidget(self.apply_btn)
        return f

    # ---------------- логика ----------------
    def _hw_label(self, pid):
        if pid == "gpu":
            return self.hub.gpu_name or "видеокарта не найдена"
        if pid == "cpu":
            return self.hub.cpu_name or ""
        if pid == "ram":
            return f"{self.hub.ram_total / 2 ** 30:.0f} ГБ"
        return ""

    def _set(self, key, value):
        self.draft[key] = list(value) if isinstance(value, list) else value
        if key == "ui.theme":
            self._apply_theme(value)  # тема видна сразу, «Отмена» вернёт прежнюю
        if key == "ui.effects":
            self._sync_effects()
        if key.startswith("look.color_") and hasattr(self, "palette_picker"):
            self.palette_picker.refresh()  # карточка «Свои цвета» показывает выбранные цвета
        self._sync_enabled()
        self._update_changed()
        self._tick()

    def _load_controls(self):
        self._apply_theme(self.draft["ui.theme"])
        for key, setter in self.setters.items():
            setter(self.draft[key])
        if hasattr(self, "palette_picker"):
            self.palette_picker.refresh()
        self._sync_enabled()
        self._update_changed()

    def _sync_enabled(self):
        """Если блок выключен, его показатели становятся неактивными."""
        for rows in self.page_rows.values():
            master = next((k for k, _ in rows if k.endswith(".show")), None)
            if master:
                for k, row in rows:
                    if k != master:
                        row.setEnabled(bool(self.draft[master]))
        # ручные цвета GPU и CPU работают только в палитре «Свои цвета»,
        # переключатель анимации — только у сезонных тем
        seasonal = bool(THEMES.get(self.draft["ui.theme"], {}).get("effect"))
        for k, row in self.page_rows["look"]:
            if k in ("look.color_gpu", "look.color_cpu"):
                row.setEnabled(self.draft["look.palette"] == "custom")
            elif k in ("ui.effects", "look.overlay_effects"):
                row.setEnabled(seasonal)

    def _update_changed(self):
        n = sum(self.draft[k] != self.saved.get(k) for k in self.draft)
        self.changed_lbl.setText(f"<span style='color:{THEME['muted']}'>Изменено</span>&nbsp; <b>{n}</b>")
        self.apply_btn.setEnabled(n > 0)
        self.status_lbl.setText("черновик" if n else "применено")

    def showEvent(self, e):
        super().showEvent(e)
        self.timer.start(500)
        self.effects.set_running(True)
        self.canvas.anim.set_running(True)
        self._tick()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.timer.stop()  # окно в трее — предпросмотр и анимацию не крутим
        self.effects.set_running(False)
        self.canvas.anim.set_running(False)

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.WindowStateChange:  # свернули/развернули
            on = not self.isMinimized() and self.isVisible()
            self.effects.set_running(on)
            self.canvas.anim.set_running(on)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.effects.setGeometry(self.rect())

    def _tick(self):
        if self.isMinimized():
            return
        live = self.hub.get(self.draft)
        snap = demo_snapshot(time.time()) if self.demo.isChecked() else live
        self.canvas.set_model(OverlayModel(snap, self.draft))
        status = (live.get("fps") or {}).get("status")
        self.sub_labels["fps"].setText(f"PresentMon: {status}" if status else "")
        self._refresh_diag()

    def _refresh_diag(self):
        diag = getattr(self.hub, "diagnostics", lambda: [])()
        if diag == self._diag:
            return
        old, self._diag = self._diag, diag
        if old and [l for l, _ in old] == [l for l, _ in diag]:
            # набор строк тот же, поменялся только текст (например, нагрузка) — без перестройки
            for (level, text), (dot, msg) in zip(diag, self._diag_widgets):
                if msg.text() != text:
                    msg.setText(text)
            return
        lay = self.page_lists["diag"]
        while lay.count() > 1:  # всё, кроме растяжки в конце
            w = lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._diag_widgets = []
        for i, (level, text) in enumerate(diag):
            row = QFrame(objectName="row")
            row.setMinimumHeight(46)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(24, 10, 24, 10)
            rl.setSpacing(12)
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {LEVEL_COLORS[level]};")
            dot.setAlignment(Qt.AlignTop)
            msg = QLabel(text)
            msg.setWordWrap(True)
            msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
            rl.addWidget(dot)
            rl.addWidget(msg, 1)
            lay.insertWidget(i, row)
            self._diag_widgets.append((dot, msg))
        problems = sum(level != "ok" for level, _ in diag)
        b, icon, title = self.nav["diag"]
        b.setText(f"{icon}   {title}" + (f"  ({problems})" if problems else ""))
        self.sub_labels["diag"].setText("всё в порядке" if not problems else f"проблем: {problems}")

    def _copy_diag(self):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(f"[{lvl}] {t}" for lvl, t in self._diag or []))

    def apply(self):
        self.saved = dict(self.draft)
        try:
            config.save(self.saved)
        except OSError as e:
            self.status_lbl.setText(f"не удалось сохранить: {e}")
        self.applied.emit(dict(self.saved))
        self._update_changed()

    def cancel(self):
        self.draft = dict(self.saved)
        self._load_controls()
        self._tick()

    def reset(self):
        self.draft = dict(config.DEFAULTS)
        self._load_controls()
        self._tick()

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт настроек", "monitor-settings.json", "JSON (*.json)")
        if path:
            config.save(self.draft, path)

    def import_(self):
        path, _ = QFileDialog.getOpenFileName(self, "Импорт настроек", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                self.draft.update(config.sanitize(json.load(fh)))
        except (OSError, ValueError):
            self.status_lbl.setText("файл настроек не прочитан")
            return
        self._load_controls()
        self._tick()

    def _sync_effects(self):
        on = self.draft.get("ui.effects", True)
        self.effects.set_kind(THEME.get("effect") if on else None)

    def _apply_theme(self, key):
        if key == self._theme_key:
            return
        self._theme_key = key
        t = set_theme(key)
        self.setStyleSheet(build_qss(t))
        self.title_lbl.setText(f"<b>{APP_NAME[0]}</b> <b style='color:{t['accent']}'>{APP_NAME[1]}</b>")
        self._dark_titlebar(t["dark"])
        self._sync_effects()
        for w in self.findChildren(QWidget):  # сами себя рисующие виджеты берут цвета из темы
            w.update()
        if hasattr(self, "changed_lbl"):
            self._update_changed()

    def _dark_titlebar(self, dark=True):
        if sys.platform == "win32":
            import ctypes
            value = ctypes.c_int(1 if dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 20, ctypes.byref(value), 4)

    def closeEvent(self, e):
        if self.hide_on_close:
            e.ignore()
            self.hide()
        else:
            e.accept()