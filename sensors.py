"""Сбор данных (Windows 10 1709+). Всё работает в фоновых потоках, интерфейс только забирает готовый снимок.

Источники:
  DXGI          — список видеокарт от драйвера (вендор, VRAM, LUID)
  PDH-счётчики  — загрузка GPU и VRAM для любого вендора, частота CPU
  NVML          — NVIDIA: температура, частоты, потребление, вентилятор
  LibreHardwareMonitor (опционально, нужны права админа) — температура/потребление CPU,
                  напряжение, hotspot, температура памяти, обороты для любых GPU
  PresentMon (опционально) — FPS, frametime, задержка
"""
import ctypes
import heapq
import os
import re
import subprocess
import threading
import time
import winreg
from collections import defaultdict, deque
from ctypes import wintypes

import psutil

from config import APP_DIR

# dll можно положить в папку lhm/ или прямо рядом с main.py
LHM_DLL = next((p for p in (APP_DIR / "lhm" / "LibreHardwareMonitorLib.dll",
                            APP_DIR / "LibreHardwareMonitorLib.dll") if p.exists()), None)
LHM_PERIOD = 1.0  # секунд между опросами LibreHardwareMonitor
VENDORS = {0x10DE: "NVIDIA", 0x1002: "AMD", 0x8086: "Intel"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


# ======================= Видеокарты через DXGI =======================

class GUID(ctypes.Structure):
    _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD),
                ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]


class LUID(ctypes.Structure):
    _fields_ = [("Low", wintypes.DWORD), ("High", wintypes.LONG)]


class DXGI_ADAPTER_DESC1(ctypes.Structure):
    _fields_ = [("Description", wintypes.WCHAR * 128),
                ("VendorId", wintypes.UINT), ("DeviceId", wintypes.UINT),
                ("SubSysId", wintypes.UINT), ("Revision", wintypes.UINT),
                ("DedicatedVideoMemory", ctypes.c_size_t),
                ("DedicatedSystemMemory", ctypes.c_size_t),
                ("SharedSystemMemory", ctypes.c_size_t),
                ("AdapterLuid", LUID), ("Flags", wintypes.UINT)]


IID_IDXGIFactory1 = GUID(0x770AAE78, 0xF26F, 0x4DBA,
                         (ctypes.c_ubyte * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))


def _method(obj, index, *argtypes):
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[index])
    return lambda *args: fn(obj, *args) & 0xFFFFFFFF


def detect_gpus():
    factory = ctypes.c_void_p()
    if ctypes.WinDLL("dxgi").CreateDXGIFactory1(ctypes.byref(IID_IDXGIFactory1), ctypes.byref(factory)):
        return []
    enum_adapters1 = _method(factory, 12, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p))
    gpus, seen, i = [], set(), 0
    while True:
        adapter = ctypes.c_void_p()
        if enum_adapters1(i, ctypes.byref(adapter)):
            break
        i += 1
        desc = DXGI_ADAPTER_DESC1()
        _method(adapter, 10, ctypes.POINTER(DXGI_ADAPTER_DESC1))(ctypes.byref(desc))
        _method(adapter, 2)()
        luid = f"0x{desc.AdapterLuid.High & 0xFFFFFFFF:08x}_0x{desc.AdapterLuid.Low:08x}"
        if desc.Flags & 2 or luid in seen:  # программный адаптер или дубль
            continue
        seen.add(luid)
        gpus.append({"name": desc.Description, "luid": luid,
                     "vendor": VENDORS.get(desc.VendorId, "Other"),
                     "vram_total": desc.DedicatedVideoMemory})
    _method(factory, 2)()
    return gpus


# ======================= Счётчики производительности Windows =======================

LUID_RE = re.compile(r"luid_(0x[0-9a-f]+_0x[0-9a-f]+)", re.I)


class PdhCounters:
    def __init__(self):
        import win32pdh as pdh
        self.pdh = pdh
        self.q = pdh.OpenQuery()
        self.c = {}
        for name, path in (("eng", r"\GPU Engine(*)\Utilization Percentage"),
                           ("mem", r"\GPU Adapter Memory(*)\Dedicated Usage"),
                           ("perf", r"\Processor Information(_Total)\% Processor Performance")):
            try:
                self.c[name] = pdh.AddEnglishCounter(self.q, path)
            except pdh.error:
                pass
        pdh.CollectQueryData(self.q)

    def _items(self, name):
        try:
            return self.pdh.GetFormattedCounterArray(self.c[name], self.pdh.PDH_FMT_DOUBLE).items()
        except (KeyError, self.pdh.error):
            return ()

    def read(self):
        self.pdh.CollectQueryData(self.q)
        engines = defaultdict(float)
        for inst, val in self._items("eng"):
            m = LUID_RE.search(inst)
            if m:
                engines[(m.group(1).lower(), inst.rsplit("engtype_", 1)[-1])] += val
        load = defaultdict(float)
        for (luid, _), val in engines.items():
            load[luid] = max(load[luid], val)
        vram = defaultdict(float)
        for inst, val in self._items("mem"):
            m = LUID_RE.search(inst)
            if m:
                vram[m.group(1).lower()] += val
        perf = None
        if "perf" in self.c:
            try:
                perf = self.pdh.GetFormattedCounterValue(self.c["perf"], self.pdh.PDH_FMT_DOUBLE)[1]
            except self.pdh.error:
                pass
        return load, vram, perf


# ======================= NVIDIA =======================

class NvmlReader:
    def __init__(self):
        import pynvml as nv
        nv.nvmlInit()
        self.nv = nv
        self.devices = {}
        for i in range(nv.nvmlDeviceGetCount()):
            h = nv.nvmlDeviceGetHandleByIndex(i)
            name = nv.nvmlDeviceGetName(h)
            self.devices[name.decode() if isinstance(name, bytes) else name] = h

    def read(self, name):
        h = self.devices.get(name) or (next(iter(self.devices.values())) if len(self.devices) == 1 else None)
        if h is None:
            return {}
        nv, out = self.nv, {}
        calls = {
            "load": lambda: nv.nvmlDeviceGetUtilizationRates(h).gpu,
            "temp": lambda: nv.nvmlDeviceGetTemperature(h, nv.NVML_TEMPERATURE_GPU),
            "clock": lambda: nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_GRAPHICS),
            "mem_clock": lambda: nv.nvmlDeviceGetClockInfo(h, nv.NVML_CLOCK_MEM),
            "power": lambda: nv.nvmlDeviceGetPowerUsage(h) / 1000,
            "fan_pct": lambda: nv.nvmlDeviceGetFanSpeed(h),
        }
        for key, fn in calls.items():
            try:
                out[key] = fn()
            except nv.NVMLError:
                pass
        try:
            mem = nv.nvmlDeviceGetMemoryInfo(h)
            out["vram_used"], out["vram_total"] = mem.used, mem.total
        except nv.NVMLError:
            pass
        return out


# ======================= LibreHardwareMonitor (опционально) =======================

class LhmReader:
    def __init__(self, dll):
        import clr  # pip install pythonnet
        clr.AddReference(str(dll))
        from LibreHardwareMonitor.Hardware import Computer
        self.pc = Computer()
        self.pc.IsCpuEnabled = True
        self.pc.IsGpuEnabled = True
        self.pc.Open()
        self.last = {"cpu": {}, "gpu": {}}
        self.found = set()  # что увидел LHM — для диагностики

    def read(self):
        out = {"cpu": {}, "gpu": {}}
        for hw in self.pc.Hardware:
            kind = str(hw.HardwareType).split(".")[-1]  # "Cpu" или "HardwareType.Cpu" — зависит от версии pythonnet
            if kind != "Cpu" and not kind.startswith("Gpu"):
                continue
            hw.Update()
            sensors = {(str(s.SensorType).split(".")[-1], str(s.Name)): float(s.Value)
                       for s in hw.Sensors if s.Value is not None}
            if kind == "Cpu":
                out["cpu"] = sensors
                self.found.add(f"CPU: {hw.Name} ({len(sensors)} датчиков)")
            else:
                out["gpu"][str(hw.Name)] = sensors
                self.found.add(f"GPU: {hw.Name} ({len(sensors)} датчиков)")
        self.last = out
        return out


def pick(sensors, *candidates):
    """Первый найденный датчик. Имя с '*' на конце — поиск по префиксу."""
    for typ, name in candidates:
        if name.startswith("*") and name.endswith("*") and len(name) > 2:
            for (t, n), v in sensors.items():
                if t == typ and name[1:-1] in n:
                    return v
        elif name.endswith("*"):
            for (t, n), v in sensors.items():
                if t == typ and n.startswith(name[:-1]):
                    return v
        elif (typ, name) in sensors:
            return sensors[(typ, name)]
    return None


LHM_CPU = {
    "temp": [("Temperature", "Core (Tctl/Tdie)"), ("Temperature", "CPU Package"),
             ("Temperature", "Core Average"), ("Temperature", "Core Max"),
             ("Temperature", "CCD1*"), ("Temperature", "*")],
    "power": [("Power", "Package"), ("Power", "CPU Package"), ("Power", "*Package*")],
}
LHM_GPU = {
    "load": [("Load", "GPU Core")],
    "temp": [("Temperature", "GPU Core")],
    "hotspot": [("Temperature", "GPU Hot Spot")],
    "mem_temp": [("Temperature", "GPU Memory Junction"), ("Temperature", "GPU Memory")],
    "voltage": [("Voltage", "GPU Core")],
    "clock": [("Clock", "GPU Core")],
    "mem_clock": [("Clock", "GPU Memory")],
    "power": [("Power", "GPU Package"), ("Power", "GPU Power"), ("Power", "GPU Core")],
    "fan_rpm": [("Fan", "GPU Fan*"), ("Fan", "*")],
    "fan_pct": [("Control", "GPU Fan*"), ("Control", "*")],
}


# Без драйвера LHM отдаёт по этим датчикам 0 вместо «нет данных»
NONZERO = {"temp", "hotspot", "mem_temp", "power", "voltage"}


def nz(key, value):
    return None if key in NONZERO and not value else value


def drop_zero(sensors):
    return {k: v for k, v in sensors.items() if not (k[0] in ("Temperature", "Power", "Voltage") and not v)}


def fill(d, key, value):
    if d.get(key) is None and value is not None:
        d[key] = value


# ======================= FPS через PresentMon =======================

def foreground_pid():
    try:
        import win32gui
        import win32process
        return win32process.GetWindowThreadProcessId(win32gui.GetForegroundWindow())[1]
    except Exception:
        return None


class FrameCapture(threading.Thread):
    FT_COLS = ("MsBetweenPresents", "msBetweenPresents", "FrameTime")
    LAT_COLS = ("MsPCLatency", "MsUntilDisplayed", "msUntilDisplayed", "DisplayLatency")

    def __init__(self, exe):
        super().__init__(daemon=True)
        self.exe = str(exe)
        self.lock = threading.Lock()
        self.frames = defaultdict(lambda: deque(maxlen=80000))  # pid -> (время, frametime, latency)
        self.names = {}
        self.target = None
        self.status = "запуск…"
        self.proc = None
        self._cache = (None, 0, None)  # (аргументы, время, результат)

    def _kill_leftovers(self):
        """PresentMon, оставшийся от прошлого запуска (например, после аварийного закрытия),
        держит ETW-сессию, и новый не стартует."""
        for p in psutil.process_iter(["name", "exe"]):
            try:
                if (p.info["name"] or "").lower().startswith("presentmon") and \
                        (p.info["exe"] or "").lower() == self.exe.lower():
                    p.kill()
                    p.wait(3)
            except (psutil.Error, OSError):
                pass

    def run(self):
        self._kill_leftovers()
        cmd = [self.exe, "--output_stdout", "--stop_existing_session", "--session_name", "PCMonitor"]
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                         text=True, bufsize=1, creationflags=NO_WINDOW)
        except OSError as e:
            self.status = f"не запустился: {e}"
            return

        cols, last_msg = None, ""
        for line in self.proc.stdout:
            if cols is None:
                parts = line.rstrip("\r\n").split(",")
                if "Application" in parts and "ProcessID" in parts:
                    idx = {n: i for i, n in enumerate(parts)}
                    i_ft = next((idx[c] for c in self.FT_COLS if c in idx), None)
                    i_lat = next((idx[c] for c in self.LAT_COLS if c in idx), None)
                    i_app, i_pid = idx["Application"], idx["ProcessID"]
                    if i_ft is None:
                        self.status = "неизвестный формат вывода"
                        break
                    cols = True
                    max_col = max(i for i in (i_app, i_pid, i_ft, i_lat) if i is not None)
                    self.status = "активен"
                elif line.strip():
                    last_msg = line.strip()
                continue
            parts = line.split(",", max_col + 1)  # хвост строки не разбираем
            try:
                pid, ft = int(parts[i_pid]), float(parts[i_ft])
            except (ValueError, IndexError):
                continue
            if ft <= 0:
                continue
            lat = None
            if i_lat is not None:
                try:
                    lat = float(parts[i_lat])
                except (ValueError, IndexError):
                    pass
            with self.lock:
                self.frames[pid].append((time.perf_counter(), ft, lat))
                self.names[pid] = parts[i_app]

        if self.status in ("запуск…", "активен"):
            self.status = "остановлен" + (f": {last_msg[:80]}" if last_msg else
                                          " (нужен запуск от администратора)")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(3)
            except subprocess.TimeoutExpired:
                pass

    def stats(self, stats_seconds, graph_seconds):
        now = time.perf_counter()
        key = (stats_seconds, graph_seconds)
        if self._cache[0] == key and now - self._cache[1] < 0.05:
            return self._cache[2]  # оверлей и предпросмотр спрашивают почти одновременно
        result = self._stats(now, stats_seconds, graph_seconds)
        self._cache = (key, now, result)
        return result

    def _stats(self, now, stats_seconds, graph_seconds):
        fg = foreground_pid()
        horizon = max(stats_seconds, graph_seconds)
        with self.lock:
            def alive(pid):
                q = self.frames.get(pid)
                return bool(q) and now - q[-1][0] < 2
            for pid in [p for p, q in self.frames.items() if not q or now - q[-1][0] > 30]:
                del self.frames[pid]  # процессы, которые давно не рисуют
            if fg and fg != os.getpid() and alive(fg):
                self.target = fg
            elif not (self.target and alive(self.target)):
                self.target = None
            if self.target is None:
                return {"status": self.status}
            # берём с конца только нужный отрезок, а не копируем всю очередь
            recent = []
            for f in reversed(self.frames[self.target]):
                if now - f[0] > horizon:
                    break
                recent.append(f)
            name = self.names.get(self.target)
        recent.reverse()

        window, last, lats, graph = [], [], [], []
        for t, ft, lat in recent:  # один проход вместо нескольких списков
            age = now - t
            if age <= stats_seconds:
                window.append(ft)
            if age <= graph_seconds:
                graph.append(ft)
            if age <= 1.0:
                last.append(ft)
                if lat is not None:
                    lats.append(lat)
        if not last:
            last = [recent[-1][1]]
        if not window:
            window = last

        def low(share):  # 1% low = FPS по самым долгим 1% кадров; heap быстрее полной сортировки
            k = max(1, int(len(window) * share))
            return 1000 / heapq.nlargest(k, window)[-1]

        return {
            "status": self.status,
            "process": name,
            "fps": 1000 / (sum(last) / len(last)),
            "avg": 1000 / (sum(window) / len(window)),
            "low1": low(0.01),
            "low01": low(0.001),
            "latency": sum(lats) / len(lats) if lats else None,
            "frametimes": graph,
        }


# ======================= Драйвер PawnIO =======================
# LibreHardwareMonitor читает датчики процессора (температура, потребление) через этот драйвер.

SERVICE_STATES = {1: "остановлен", 2: "запускается", 3: "останавливается", 4: "работает",
                  5: "возобновляется", 6: "приостанавливается", 7: "приостановлен"}


def service_state(name):
    """Состояние службы/драйвера: код (4 = работает) или None, если не установлен."""
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.OpenSCManagerW.restype = ctypes.c_void_p
    adv.OpenSCManagerW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD)
    adv.OpenServiceW.restype = ctypes.c_void_p
    adv.OpenServiceW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR, wintypes.DWORD)
    adv.QueryServiceStatus.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    adv.CloseServiceHandle.argtypes = (ctypes.c_void_p,)
    scm = adv.OpenSCManagerW(None, None, 0x0001)  # SC_MANAGER_CONNECT
    if not scm:
        return None
    try:
        svc = adv.OpenServiceW(scm, name, 0x0004)  # SERVICE_QUERY_STATUS
        if not svc:
            return None
        try:
            status = (wintypes.DWORD * 7)()
            return status[1] if adv.QueryServiceStatus(svc, status) else 0
        finally:
            adv.CloseServiceHandle(svc)
    finally:
        adv.CloseServiceHandle(scm)


def installed_version(display_name):
    """Версия программы из списка «Установленные приложения»."""
    roots = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
             r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")
    for root in roots:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root) as base:
                for i in range(winreg.QueryInfoKey(base)[0]):
                    try:
                        with winreg.OpenKey(base, winreg.EnumKey(base, i)) as k:
                            if display_name.lower() in str(winreg.QueryValueEx(k, "DisplayName")[0]).lower():
                                return str(winreg.QueryValueEx(k, "DisplayVersion")[0])
                    except OSError:
                        continue
        except OSError:
            continue
    return None


class PawnIOStatus:
    """Проверка драйвера с кэшем: страница диагностики обновляется дважды в секунду."""
    TTL = 10

    def __init__(self):
        self._t, self._value = 0, None

    def get(self):
        if time.monotonic() - self._t > self.TTL:
            try:
                state = service_state("PawnIO")
            except OSError:
                state = None
            self._value = (state, installed_version("PawnIO") if state is not None else None)
            self._t = time.monotonic()
        return self._value


# ======================= Общий сборщик =======================

class SensorHub(threading.Thread):
    def __init__(self, get_interval_ms):
        super().__init__(daemon=True)
        self.get_interval_ms = get_interval_ms
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self.snapshot = {}
        self.notes = []
        self.lhm = None
        self.pawnio = PawnIOStatus()
        self._proc, self._pm = psutil.Process(), None
        self.usage = {}
        self._last = {}  # (блок, показатель) -> (значение, время)

        self.gpus = detect_gpus()
        self.gpu = max(self.gpus, key=lambda g: g["vram_total"], default=None)  # дискретная обычно с большей VRAM
        self.gpu_name = self.gpu["name"] if self.gpu else None
        self.cpu_name, self.cpu_base_mhz = self._cpu_info()
        self.ram_total = psutil.virtual_memory().total
        self.ram_speed = None
        threading.Thread(target=self._query_ram_speed, daemon=True).start()

        exe = next(iter(sorted(APP_DIR.glob("PresentMon*.exe")) + sorted(APP_DIR.glob("tools/PresentMon*.exe"))), None)
        self.frames = FrameCapture(exe) if exe else None
        self.fps_status = "PresentMon не найден" if not exe else ""
        if self.frames:
            self.frames.start()

    @staticmethod
    def _cpu_info():
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return winreg.QueryValueEx(k, "ProcessorNameString")[0].strip(), winreg.QueryValueEx(k, "~MHz")[0]
        except OSError:
            return None, None

    def _query_ram_speed(self):
        cmd = ["powershell", "-NoProfile", "-Command",
               "(Get-CimInstance Win32_PhysicalMemory | Measure-Object ConfiguredClockSpeed -Maximum).Maximum"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW)
            self.ram_speed = int(out.stdout.strip()) or None
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

    def _try(self, factory, label):
        try:
            return factory()
        except Exception as e:
            self.note(f"{label}: {e}")
            return None

    def note(self, text):
        """Ошибка для страницы «Диагностика» (без повторов, не больше 20)."""
        if text not in self.notes:
            self.notes.append(text)
            del self.notes[:-20]

    def _pawnio_line(self):
        state, version = self.pawnio.get()
        cpu = self.lhm.last.get("cpu", {}) if self.lhm else {}
        cpu_ok = any(v for (t, _), v in cpu.items() if t in ("Temperature", "Power"))
        ver = f" {version}" if version else ""
        if state is None:
            setup = next(iter(APP_DIR.glob("PawnIO*setup*.exe")), None)
            hint = f"запустите {setup.name} и перезапустите монитор" if setup else \
                "установите его с pawnio.eu и перезапустите монитор"
            return ("warn", f"Драйвер PawnIO не установлен — нет температуры и потребления CPU; {hint}")
        if state == 4:
            if self.lhm and cpu and not cpu_ok:
                return ("warn", f"PawnIO{ver} работает, но LibreHardwareMonitor не получает данные CPU — "
                                "обновите LibreHardwareMonitor до свежей версии")
            return ("ok", f"Драйвер PawnIO{ver}: работает")
        text = SERVICE_STATES.get(state, f"код {state}")
        if cpu_ok:  # драйвер запускается по требованию, и данные идут
            return ("ok", f"Драйвер PawnIO{ver}: установлен ({text}), данные CPU поступают")
        return ("warn", f"Драйвер PawnIO{ver} установлен, но {text} — перезагрузите компьютер")

    def diagnostics(self):
        """Список (уровень, текст) для страницы «Диагностика»; уровень: ok / warn / error."""
        d = [("ok", "Запущено с правами администратора") if is_admin() else
             ("warn", "Нет прав администратора — температуры и потребление недоступны")]
        if self.gpu:
            d.append(("ok", f"Видеокарта: {self.gpu['name']}"))
        else:
            d.append(("error", "Видеокарта не определена"))
        if self.frames:
            st = self.frames.status
            d.append(("ok" if st == "активен" else "error", f"PresentMon: {st}"))
        else:
            d.append(("warn", "PresentMon не найден — положите PresentMon*.exe рядом с main.py"))
        if LHM_DLL is None:
            d.append(("warn", "LibreHardwareMonitorLib.dll не найдена — нет температур и потребления"))
        elif self.lhm:
            found = ", ".join(sorted(list(self.lhm.found))) or "устройства не найдены"
            d.append(("ok", f"LibreHardwareMonitor: {found}"))
        d.append(self._pawnio_line())
        u = self.usage
        if u:
            text = f"Нагрузка монитора: CPU {u['cpu']:.1f} %, RAM {u['ram'] / 2 ** 20:.0f} МБ"
            if "pm_cpu" in u:
                text += f"; PresentMon: CPU {u['pm_cpu']:.1f} %, RAM {u['pm_ram'] / 2 ** 20:.0f} МБ"
            d.append(("warn" if u["cpu"] + u.get("pm_cpu", 0) > 3 else "ok", text))
        d += [("error", n) for n in self.notes]
        return d

    def run(self):
        pdhc = self._try(PdhCounters, "PDH")
        nvml = self._try(NvmlReader, "NVML") if any(g["vendor"] == "NVIDIA" for g in self.gpus) else None
        lhm = None
        if LHM_DLL is not None and is_admin():
            lhm = self._try(lambda: LhmReader(LHM_DLL), "LibreHardwareMonitor")
        self.lhm = lhm
        psutil.cpu_percent(None)
        lh, lh_time = {"cpu": {}, "gpu": {}}, 0.0

        while not self._stop.is_set():
            try:
                # температуры и мощность меняются медленно — LHM опрашиваем не чаще раза в LHM_PERIOD
                if lhm and time.monotonic() - lh_time >= LHM_PERIOD:
                    lh, lh_time = lhm.read(), time.monotonic()
                snap = self._hold(self._collect(pdhc, nvml, lh))
                with self.lock:
                    self.snapshot = snap
                self.usage = self._measure_self()
            except Exception as e:  # один сбойный датчик не должен ронять монитор
                self.note(f"Сбор данных: {e}")
            self._stop.wait(self.get_interval_ms() / 1000)

    def _measure_self(self):
        """Сколько потребляет сам монитор и его PresentMon (CPU в % от всего процессора)."""
        n = psutil.cpu_count() or 1
        out = {"cpu": self._proc.cpu_percent(None) / n, "ram": self._proc.memory_info().rss}
        proc = self.frames.proc if self.frames else None
        if proc and proc.poll() is None:
            try:
                if self._pm is None or self._pm.pid != proc.pid:
                    self._pm = psutil.Process(proc.pid)
                    self._pm.cpu_percent(None)
                out["pm_cpu"] = self._pm.cpu_percent(None) / n
                out["pm_ram"] = self._pm.memory_info().rss
            except psutil.Error:
                self._pm = None
        return out

    def _hold(self, snap):
        """Датчики иногда пропускают опрос (особенно AMD и счётчики Windows при смене процессов).
        Тогда несколько секунд показываем последнее известное значение, а не прочерк."""
        now = time.monotonic()
        hold = max(3.0, 4 * self.get_interval_ms() / 1000)
        for sec, d in snap.items():
            for key, val in d.items():
                if val is not None:
                    self._last[(sec, key)] = (val, now)
        for (sec, key), (val, t) in self._last.items():
            d = snap.get(sec)
            if d is not None and d.get(key) is None and now - t < hold:
                d[key] = val
        return snap

    def _collect(self, pdhc, nvml, lh):
        load, vram, perf = pdhc.read() if pdhc else ({}, {}, None)

        cpu = {"name": self.cpu_name, "load": psutil.cpu_percent(None),
               "clock": self.cpu_base_mhz * perf / 100 if perf and self.cpu_base_mhz else None}
        for key, cands in LHM_CPU.items():
            fill(cpu, key, nz(key, pick(drop_zero(lh["cpu"]), *cands)))

        gpu = {}
        if self.gpu:
            g, luid = self.gpu, self.gpu["luid"]
            gpu = {"name": g["name"], "vram_total": g["vram_total"],
                   "load": min(load[luid], 100) if luid in load else None,
                   "vram_used": vram.get(luid)}
            if nvml and g["vendor"] == "NVIDIA":
                gpu.update(nvml.read(g["name"]))
            sensors = next((s for n, s in lh["gpu"].items()
                            if n.lower() in g["name"].lower() or g["name"].lower() in n.lower()), {})
            sensors = drop_zero(sensors)
            for key, cands in LHM_GPU.items():
                fill(gpu, key, nz(key, pick(sensors, *cands)))

        vm = psutil.virtual_memory()
        ram = {"used": vm.used, "total": vm.total, "load": vm.percent, "speed": self.ram_speed}
        return {"gpu": gpu, "cpu": cpu, "ram": ram}

    def get(self, cfg):
        with self.lock:
            snap = dict(self.snapshot)
        if self.frames:
            snap["fps"] = self.frames.stats(cfg["stats.seconds"], cfg["graph.seconds"])
        else:
            snap["fps"] = {"status": self.fps_status}
        return snap

    def stop(self):
        self._stop.set()
        if self.frames:
            self.frames.stop()