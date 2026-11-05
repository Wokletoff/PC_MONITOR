"""Запуск: python main.py              (откроются настройки)
          python main.py --hidden     (сразу в трей, только оверлей)
          python main.py --no-admin   (не запрашивать права администратора)
          python main.py --console    (после запроса прав оставить окно консоли)"""
import os
import signal
import subprocess
import threading
import sys
import time
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import config
from overlay import OverlayWindow
from sensors import SensorHub, is_admin
from settings_ui import ACCENT, APP_NAME, SettingsWindow


def app_icon():
    pm = QPixmap(256, 256)  # рисуем крупно: из этой же иконки делается .ico для exe
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(4, 4)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(ACCENT))
    p.drawRoundedRect(4, 4, 56, 56, 12, 12)
    p.setBrush(QColor("#FFFFFF"))
    for i, h in enumerate((18, 30, 24, 40)):
        p.drawRoundedRect(12 + i * 11, 52 - h, 7, h, 2, 2)
    p.end()
    return QIcon(pm)


def ensure_admin():
    """Без прав администратора не работают датчики LibreHardwareMonitor,
    поэтому перезапускаемся с запросом UAC. Если отказаться — работаем без них."""
    if sys.platform != "win32" or is_admin() or "--no-admin" in sys.argv:
        return
    import ctypes
    args = sys.argv[1:] if getattr(sys, "frozen", False) else [os.path.abspath(sys.argv[0])] + sys.argv[1:]
    params = subprocess.list2cmdline(args)
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if "--console" not in sys.argv and os.path.exists(pythonw):
        exe = pythonw  # без окна консоли; диагностика пишется в monitor.log
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, os.getcwd(), 1)
    if rc > 32:  # новый процесс с правами запущен — этот завершаем
        sys.exit(0)
    print("Права администратора не получены, запуск без датчиков LibreHardwareMonitor")


def hide_console():
    """Прячет окно консоли при запуске через pythonw. В виртуальном окружении pythonw.exe —
    это лаунчер, который запускает настоящий интерпретатор, и консоль принадлежит лаунчеру,
    поэтому просто отключиться от неё мало: находим окно (своё или родителя) и скрываем."""
    if sys.platform != "win32" or "--console" in sys.argv \
            or os.path.basename(sys.executable).lower() != "pythonw.exe":
        return
    import ctypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    hwnd = k32.GetConsoleWindow()
    if not hwnd and k32.AttachConsole(-1):  # -1 = консоль родительского процесса
        hwnd = k32.GetConsoleWindow()
    if hwnd:
        u32.ShowWindow(hwnd, 0)  # SW_HIDE
    k32.FreeConsole()


def log(text):
    try:
        with open(config.APP_DIR / "monitor.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}\n")
    except OSError:
        pass


_mutex = None


def already_running():
    """Второй экземпляр запустил бы второй PresentMon с той же сессией — и FPS бы пропал."""
    global _mutex
    if sys.platform != "win32":
        return False
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _mutex = k32.CreateMutexW(None, False, "Local\\PCMonitorSingleInstance")
    return ctypes.get_last_error() in (183, 5)  # уже существует / создан процессом с правами админа


def main():
    ensure_admin()
    hide_console()
    app = QApplication(sys.argv)
    if already_running():
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(None, " ".join(APP_NAME),
                                "Программа уже запущена — её иконка в трее рядом с часами.")
        sys.exit(0)
    app.setWindowIcon(app_icon())
    state = {"cfg": config.load(), "visible": True}

    hub = SensorHub(lambda: state["cfg"]["general.interval"])
    hub.start()
    overlay = OverlayWindow()
    settings = SettingsWindow(state["cfg"], hub)

    def tick():
        cfg = state["cfg"]
        if not (state["visible"] and cfg["general.enabled"]):
            overlay.hide()  # оверлей скрыт — статистику FPS не считаем
            return
        overlay.refresh(hub.get(cfg), cfg)

    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(state["cfg"]["general.interval"])

    def on_apply(cfg):
        state["cfg"] = cfg
        timer.setInterval(cfg["general.interval"])
        tick()

    settings.applied.connect(on_apply)

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        app.setQuitOnLastWindowClosed(False)
        tray = QSystemTrayIcon(app_icon())
        tray.setToolTip(" ".join(APP_NAME))
        menu = QMenu()
        open_act = QAction("Настройки", menu)
        open_act.triggered.connect(lambda: (settings.showNormal(), settings.activateWindow()))
        toggle_act = QAction("Показывать оверлей", menu, checkable=True, checked=True)

        def toggle_overlay(on):
            state["visible"] = on
            tick()

        toggle_act.toggled.connect(toggle_overlay)
        quit_act = QAction("Выход", menu)
        quit_act.triggered.connect(app.quit)
        menu.addActions([open_act, toggle_act])
        menu.addSeparator()
        menu.addAction(quit_act)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda r: r == QSystemTrayIcon.DoubleClick and open_act.trigger())
        tray.show()
    else:
        settings.hide_on_close = False  # без трея закрытие настроек = выход

    def report():  # через 5 с после запуска: итог в monitor.log, проблемы — уведомлением
        diag = hub.diagnostics()
        log("Диагностика:\n" + "\n".join(f"  [{lvl}] {text}" for lvl, text in diag))
        problems = [t for lvl, t in diag if lvl != "ok"]
        if problems and tray:
            tray.showMessage("Есть проблемы с датчиками",
                             f"{problems[0]}\nПодробнее: Настройки → Диагностика",
                             QSystemTrayIcon.Warning, 8000)

    def on_error(etype, value, tb):  # любая необработанная ошибка — в «Диагностику», лог и уведомление
        log("".join(traceback.format_exception(etype, value, tb)))
        hub.note(f"Ошибка программы: {etype.__name__}: {value}")
        if tray:
            tray.showMessage("Ошибка", f"{etype.__name__}: {value}", QSystemTrayIcon.Critical, 8000)

    sys.excepthook = on_error
    # из фоновых потоков уведомления не показываем (Qt — только из главного потока)
    threading.excepthook = lambda a: (log("".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback))),
                                      hub.note(f"Ошибка в потоке: {a.exc_type.__name__}: {a.exc_value}"))

    QTimer.singleShot(5000, report)
    # Ctrl+C в консоли: корректный выход вместо KeyboardInterrupt внутри Qt.
    # Сигнал обрабатывается, когда срабатывает любой Python-таймер (оверлей тикает постоянно).
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    app.aboutToQuit.connect(hub.stop)
    if "--hidden" not in sys.argv:
        settings.show()
    tick()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()