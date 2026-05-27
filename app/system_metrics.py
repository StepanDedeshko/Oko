import time
from pathlib import Path

import psutil


class SystemMetricsProvider:
    """
    Сбор локальных показателей Ubuntu для нижней HUD-панели.

    Показывает:
    - время обновления;
    - память;
    - скорость сети;
    - температуру CPU, если датчики доступны.
    """

    def __init__(self):
        self.last_net = psutil.net_io_counters()
        self.last_time = time.time()

    def _format_bytes_per_second(self, value: float) -> str:
        if value >= 1024 ** 3:
            return f"{value / (1024 ** 3):.2f} ГБ/с"
        if value >= 1024 ** 2:
            return f"{value / (1024 ** 2):.1f} МБ/с"
        if value >= 1024:
            return f"{value / 1024:.1f} КБ/с"
        return f"{value:.0f} Б/с"

    def _get_network_speed(self) -> str:
        now = time.time()
        current = psutil.net_io_counters()

        elapsed = max(now - self.last_time, 0.1)

        sent_speed = (current.bytes_sent - self.last_net.bytes_sent) / elapsed
        recv_speed = (current.bytes_recv - self.last_net.bytes_recv) / elapsed

        self.last_net = current
        self.last_time = now

        return f"↓ {self._format_bytes_per_second(recv_speed)} / ↑ {self._format_bytes_per_second(sent_speed)}"

    def _get_cpu_temperature(self) -> str:
        # Основной способ через psutil.
        try:
            temps = psutil.sensors_temperatures(fahrenheit=False)

            if temps:
                preferred_names = [
                    "coretemp",
                    "k10temp",
                    "cpu_thermal",
                    "acpitz",
                    "x86_pkg_temp",
                ]

                for name in preferred_names:
                    if name in temps and temps[name]:
                        values = [item.current for item in temps[name] if item.current is not None]
                        if values:
                            return f"{max(values):.0f}°C"

                # Если имена другие, берём первую адекватную температуру.
                all_values = []
                for entries in temps.values():
                    for item in entries:
                        if item.current is not None and 0 < item.current < 120:
                            all_values.append(item.current)

                if all_values:
                    return f"{max(all_values):.0f}°C"
        except Exception:
            pass

        # Запасной способ через sysfs.
        try:
            for thermal_zone in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
                raw = thermal_zone.read_text(encoding="utf-8").strip()
                if not raw:
                    continue

                value = float(raw)
                if value > 1000:
                    value = value / 1000.0

                if 0 < value < 120:
                    return f"{value:.0f}°C"
        except Exception:
            pass

        return "н/д"

    def get_metrics(self) -> dict:
        memory = psutil.virtual_memory()

        used_gb = memory.used / (1024 ** 3)
        total_gb = memory.total / (1024 ** 3)
        percent = memory.percent

        return {
            "memory": f"{used_gb:.1f}/{total_gb:.1f} ГБ ({percent:.0f}%)",
            "network": self._get_network_speed(),
            "cpu_temp": self._get_cpu_temperature(),
        }
