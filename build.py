r"""Сборка в exe и ярлык на рабочем столе.

    .venv\Scripts\pip install pyinstaller
    .venv\Scripts\python build.py

Результат: dist\PCMonitor\PCMonitor.exe + ярлык «PC Мониторинг» на рабочем столе.
Exe сам запрашивает права администратора (окно UAC) и запускается без консоли.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "PCMonitor"            # имя exe и папки
LABEL = "PC Мониторинг"       # подпись ярлыка
DIST = ROOT / "dist" / NAME


def make_icon():
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication([])  # noqa: F841 — без него QPixmap не работает
    from main import app_icon
    path = ROOT / "icon.ico"
    app_icon().pixmap(256, 256).save(str(path))
    return path


def build(icon):
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "main.py",
        "--name", NAME,
        "--icon", str(icon),
        "--windowed",            # без окна консоли
        "--uac-admin",           # права администратора через манифест
        "--noconfirm", "--clean",
        "--collect-all", "pythonnet",
        "--collect-all", "clr_loader",
        "--hidden-import", "clr",
    ], cwd=ROOT, check=True)


def copy_extras():
    """Всё, что программа ищет рядом с собой."""
    extras = [ROOT / "lhm", ROOT / "tools", ROOT / "config.json",
              *ROOT.glob("PresentMon*.exe"), *ROOT.glob("PawnIO*.exe"), *ROOT.glob("*.dll")]
    for src in extras:
        if not src.exists():
            continue
        dst = DIST / src.name
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        print("скопировано:", src.name)


def make_shortcut():
    exe = DIST / f"{NAME}.exe"
    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d '" + LABEL + ".lnk'));"
        f"$s.TargetPath='{exe}';$s.WorkingDirectory='{DIST}';$s.IconLocation='{exe},0';$s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    print("ярлык создан на рабочем столе:", LABEL)


if __name__ == "__main__":
    build(make_icon())
    copy_extras()
    make_shortcut()
    print("\nГотово:", DIST / f"{NAME}.exe")
