"""Список показателей. Отсюда строятся и настройки, и оверлей:
чтобы добавить новый показатель, достаточно одной строки здесь + значения в sensors.py."""

GIB = 2 ** 30


def num(key, pattern):
    def get(d):
        v = d.get(key)
        return None if v is None else pattern.format(v)
    return get


def used_total(used_key, total_key):
    def get(d):
        u, t = d.get(used_key), d.get(total_key)
        if u is None or not t:
            return None
        return f"{u / GIB:.1f} / {t / GIB:.0f} ГБ"
    return get


PCT = "{:.0f} %"
TEMP = "{:.0f} °C"
MHZ = "{:.0f} МГц"
WATT = "{:.0f} Вт"

# (ключ, подпись, функция-форматтер, включён по умолчанию)
METRICS = {
    "gpu": [
        ("load", "Загрузка", num("load", PCT), True),
        ("temp", "Температура", num("temp", TEMP), True),
        ("clock", "Частота", num("clock", MHZ), True),
        ("voltage", "Напряжение", num("voltage", "{:.3f} В"), False),
        ("power", "Потребление", num("power", WATT), True),
        ("fan_rpm", "Обороты вент.", num("fan_rpm", "{:.0f} об/мин"), False),
        ("fan_pct", "Обороты вент. в %", num("fan_pct", PCT), False),
        ("hotspot", "Температура Hotspot", num("hotspot", TEMP), False),
        ("mem_temp", "Температура памяти", num("mem_temp", TEMP), False),
        ("mem_clock", "Память GPU", num("mem_clock", MHZ), True),
        ("vram", "Видеопамять", used_total("vram_used", "vram_total"), True),
    ],
    "cpu": [
        ("load", "Загрузка", num("load", PCT), True),
        ("temp", "Температура", num("temp", TEMP), True),
        ("clock", "Частота", num("clock", MHZ), True),
        ("power", "Потребление", num("power", WATT), True),
    ],
    "ram": [
        ("used", "Использовано", used_total("used", "total"), True),
        ("load", "Загрузка", num("load", PCT), True),
        ("speed", "Скорость", num("speed", MHZ), True),
    ],
}

SECTION_TITLES = {"gpu": "Видеокарта", "cpu": "Процессор", "ram": "ОЗУ"}
