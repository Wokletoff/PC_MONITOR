# PC Мониторинг

```
pip install -r requirements.txt
python main.py            # настройки + оверлей
python main.py --hidden   # сразу в трей
```

Опциональные компоненты (кладутся рядом с main.py):

- **FPS / frametime / latency**: `PresentMon-*.exe` из https://github.com/GameTechDev/PresentMon/releases
  (можно в папку `tools/`). Нужен запуск от администратора.
- **Температура и потребление CPU, напряжение, hotspot, обороты вентиляторов**:
  содержимое архива LibreHardwareMonitor в папку `lhm/` (нужен `LibreHardwareMonitorLib.dll`
  и его зависимости) + `pip install pythonnet`. Нужен запуск от администратора.

Без них работают: загрузка CPU/GPU, частота CPU, ОЗУ, VRAM, а для NVIDIA ещё температура,
частоты, потребление и обороты в %.

Оверлей виден в оконном и borderless-режимах. В эксклюзивном полноэкранном режиме обычное окно
поверх игры не отображается.
