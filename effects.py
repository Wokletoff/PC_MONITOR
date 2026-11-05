"""Праздничная анимация: падающий снег («*») или искры, поднимающиеся вверх.

ParticleSystem — только расчёт и отрисовка частиц, без окна. Её используют:
  EffectLayer — слой поверх окна настроек;
  оверлей и предпросмотр — фон панели (через Animator).

Чтобы выглядело живо, частицы появляются не по таймеру, а как случайный (пуассоновский) поток:
интервал до следующей частицы — экспоненциально распределённая случайная величина, а её
средняя частота медленно «дышит» и иногда сменяется порывами и затишьями.
"""
import math
import random
import time

from PySide6.QtCore import QObject, QPointF, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

EMBER_COLORS = ("#FF7A1A", "#FF9F1C", "#FFB347", "#A855F7")  # тыква, янтарь, фиолетовый
_FONTS = {}


def _snow_font(px):
    f = _FONTS.get(px)
    if f is None:
        f = _FONTS[px] = QFont("Segoe UI")
        f.setPixelSize(px)
        f.setBold(True)
    return f


class Particle:
    __slots__ = ("x", "base_x", "y", "size", "vy", "amp", "freq", "phase", "alpha", "age", "life", "color")


class ParticleSystem:
    MAX_PARTICLES = 160

    def __init__(self, kind, size_scale=1.0, opacity=1.0, rate_scale=1.0):
        self.kind = kind
        self.size_scale, self.opacity, self.rate_scale = size_scale, opacity, rate_scale
        self.w = self.h = 1
        self.parts = []
        self._t = self._next = 0.0
        self._burst_until = self._lull_until = 0.0
        self._ph = [random.uniform(0, math.tau) for _ in range(4)]
        self._prefilled = False

    def resize(self, w, h):
        self.w, self.h = max(1, int(w)), max(1, int(h))
        if not self._prefilled and self.w > 10 and self.h > 10:  # чтобы при включении не было пусто — часть частиц сразу на месте
            self._prefilled = True
            self._prefill()

    # ---------- «хаотичный» поток появления ----------
    def _rate(self, dt):
        t = self._t
        base = 7.0 if self.kind == "snow" else 4.5
        wave = 1 + 0.45 * math.sin(t * 0.23 + self._ph[0]) + 0.25 * math.sin(t * 0.71 + self._ph[1])
        if t < self._burst_until:          # порыв
            wave *= 2.6
        elif t < self._lull_until:         # затишье
            wave *= 0.15
        elif random.random() < dt * 0.05:
            self._burst_until = t + random.uniform(1.5, 4)
        elif random.random() < dt * 0.04:
            self._lull_until = t + random.uniform(2, 5)
        return max(0.2, base * wave * max(0.4, self.w / 1180) * self.rate_scale)

    def _wind(self):
        t = self._t
        return 18 * math.sin(t * 0.11 + self._ph[2]) + 8 * math.sin(t * 0.37 + self._ph[3])

    def _spawn(self, x=None):
        p = Particle()
        k = self.size_scale
        p.age, p.phase = 0.0, random.uniform(0, math.tau)
        if self.kind == "snow":
            p.size = max(6, round((9 + random.random() ** 2 * 10) * k))  # мелких больше
            p.x = p.base_x = random.uniform(-20, self.w + 20) if x is None else x
            p.y = -p.size
            p.vy = (18 + p.size / k * 3.2 + random.uniform(-6, 6)) * (0.6 + 0.4 * k)  # крупные быстрее
            p.amp, p.freq = random.uniform(5, 25) * k, random.uniform(0.3, 1.1)
            p.alpha = int((110 + (p.size / k - 9) * 12) * self.opacity)
            p.life, p.color = 0, None
        else:
            p.size = random.uniform(1.4, 3.2) * k
            p.x = p.base_x = random.uniform(0, self.w) if x is None else x
            p.y = self.h + 5
            p.vy = -random.uniform(25, 65) * (0.6 + 0.4 * k)
            p.amp, p.freq = random.uniform(4, 16) * k, random.uniform(0.4, 1.4)
            p.life = random.uniform(5, 11)
            p.alpha = 255
            p.color = QColor(random.choices(EMBER_COLORS, weights=(5, 3, 2, 1))[0])
        self.parts.append(p)

    def _prefill(self):
        for _ in range(int((35 if self.kind == "snow" else 20) * max(0.3, self.w / 1180))):
            self._spawn()
            p = self.parts[-1]
            if self.kind == "snow":
                p.y = random.uniform(0, self.h)
            else:
                p.age = random.uniform(0.6, p.life * 0.7)
                p.y = self.h + 5 + p.vy * p.age

    # ---------- кадр ----------
    def rect(self, p):
        if self.kind == "snow":
            return QRect(int(p.x) - 3, int(p.y - p.size) - 2, p.size + 6, p.size + 6)
        r = int(p.size * 3) + 2
        return QRect(int(p.x) - r, int(p.y) - r, 2 * r, 2 * r)

    def step(self, dt):
        """Сдвигает частицы на dt секунд, возвращает области, которые нужно перерисовать."""
        self._t += dt
        dirty = [self.rect(p) for p in self.parts]
        rate = self._rate(dt)
        while self._next <= self._t:
            if len(self.parts) < self.MAX_PARTICLES:
                self._spawn()
                if random.random() < 0.12:  # иногда — маленькая стайка рядом
                    x0 = self.parts[-1].base_x
                    for _ in range(random.randint(1, 2)):
                        self._spawn(x0 + random.uniform(-30, 30) * self.size_scale)
            self._next += random.expovariate(rate)  # хаотичный интервал до следующей

        wind, alive = self._wind() * self.size_scale, []
        for p in self.parts:
            p.age += dt
            p.y += p.vy * dt
            if self.kind == "snow":
                p.base_x += wind * dt * (p.size / 14)
                if p.y > self.h + 20:
                    continue
            else:
                p.base_x += wind * 0.3 * dt
                if p.age > p.life or p.y < -10:
                    continue
            p.x = p.base_x + p.amp * math.sin(math.tau * p.freq * p.age + p.phase)
            alive.append(p)
        self.parts = alive
        return dirty + [self.rect(p) for p in alive]

    def paint(self, p, clip=None):
        if not self.parts:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        if self.kind == "snow":
            for s in self.parts:
                if clip is not None and not clip.intersects(self.rect(s)):
                    continue
                p.setFont(_snow_font(s.size))
                p.setPen(QColor(255, 255, 255, max(0, min(255, s.alpha))))
                p.drawText(QPointF(s.x, s.y), "*")
        else:
            p.setPen(Qt.NoPen)
            for s in self.parts:
                if clip is not None and not clip.intersects(self.rect(s)):
                    continue
                fade = min(1.0, s.age / 0.6) * max(0.0, 1 - s.age / s.life)  # плавно появляется и гаснет
                a = fade * (0.65 + 0.35 * math.sin(s.age * 9 + s.phase)) * self.opacity
                c = QColor(s.color)
                c.setAlphaF(0.25 * a)  # мягкое свечение
                p.setBrush(c)
                p.drawEllipse(QPointF(s.x, s.y), s.size * 2.8, s.size * 2.8)
                c.setAlphaF(0.9 * a)
                p.setBrush(c)
                p.drawEllipse(QPointF(s.x, s.y), s.size, s.size)
        p.restore()


class Animator(QObject):
    """Таймер + система частиц. on_frame(dirty_rects) вызывается на каждом кадре."""

    def __init__(self, on_frame, fps=30, **params):
        super().__init__()
        self.on_frame, self.fps, self.params = on_frame, fps, params
        self.system = None
        self.running = False
        self._size = (1, 1)
        self._last = 0.0
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.CoarseTimer)
        self.timer.timeout.connect(self._frame)

    def set_kind(self, kind):
        if (self.system.kind if self.system else None) != kind:
            self.system = ParticleSystem(kind, **self.params) if kind else None
            if self.system:
                self.system.resize(*self._size)
            self.on_frame([])
            self._sync()

    def resize(self, w, h):
        self._size = (w, h)
        if self.system:
            self.system.resize(w, h)

    def set_running(self, on):
        self.running = on
        self._sync()

    def _sync(self):
        if self.system and self.running:
            if not self.timer.isActive():
                self._last = time.perf_counter()
                self.timer.start(1000 // self.fps)
        else:
            self.timer.stop()

    def _frame(self):
        now = time.perf_counter()
        dt, self._last = min(0.1, now - self._last), now
        self.on_frame(self.system.step(dt))


class EffectLayer(QWidget):
    """Слой поверх окна настроек. Клики проходят насквозь; перерисовываются только места вокруг частиц."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.anim = Animator(self._dirty, fps=30)

    @property
    def kind(self):
        return self.anim.system.kind if self.anim.system else None

    @property
    def parts(self):
        return self.anim.system.parts if self.anim.system else []

    @property
    def timer(self):
        return self.anim.timer

    def set_kind(self, kind):
        self.anim.set_kind(kind)
        self.update()

    def set_running(self, on):
        self.anim.set_running(on)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.anim.resize(self.width(), self.height())

    def _dirty(self, rects):
        for r in rects:
            self.update(r)

    def paintEvent(self, e):
        if self.anim.system:
            self.anim.system.paint(QPainter(self), e.rect())