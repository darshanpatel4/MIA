"""
MIA System Monitor — Real-time system stats via WebSocket.
"""

import asyncio
import time
import platform
from datetime import datetime

import psutil


class SystemMonitor:
    """Provides real-time system monitoring data."""

    def __init__(self):
        self._clients: set = set()
        self.is_monitoring = False

    def get_snapshot(self) -> dict:
        """Get a single snapshot of system stats."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0, percpu=True)
            cpu_freq = psutil.cpu_freq()
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            net = psutil.net_io_counters()
            boot = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot

            # Disk usage per partition
            disks = []
            for part in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disks.append({
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent,
                    })
                except (PermissionError, OSError):
                    continue

            # Battery info
            battery = None
            try:
                bat = psutil.sensors_battery()
                if bat:
                    battery = {
                        "percent": bat.percent,
                        "plugged": bat.power_plugged,
                        "secs_left": bat.secsleft if bat.secsleft != psutil.POWER_TIME_UNLIMITED else -1,
                    }
            except Exception:
                pass

            return {
                "timestamp": time.time(),
                "cpu": {
                    "percent_total": sum(cpu_percent) / len(cpu_percent) if cpu_percent else 0,
                    "percent_per_core": cpu_percent,
                    "cores": psutil.cpu_count(),
                    "freq_current": cpu_freq.current if cpu_freq else 0,
                    "freq_max": cpu_freq.max if cpu_freq else 0,
                },
                "memory": {
                    "total": mem.total,
                    "used": mem.used,
                    "available": mem.available,
                    "percent": mem.percent,
                },
                "swap": {
                    "total": swap.total,
                    "used": swap.used,
                    "percent": swap.percent,
                },
                "disks": disks,
                "network": {
                    "bytes_sent": net.bytes_sent,
                    "bytes_recv": net.bytes_recv,
                    "packets_sent": net.packets_sent,
                    "packets_recv": net.packets_recv,
                },
                "battery": battery,
                "uptime": str(uptime).split(".")[0],
                "os": f"{platform.system()} {platform.release()}",
            }

        except Exception as e:
            return {"error": str(e)}

    async def start_monitoring(self, websocket, interval: float = 1.0):
        """Stream system stats to a WebSocket client."""
        self._clients.add(websocket)
        self.is_monitoring = True

        prev_net = psutil.net_io_counters()
        prev_time = time.time()

        try:
            while websocket in self._clients:
                snapshot = self.get_snapshot()

                # Calculate network speed
                cur_net = psutil.net_io_counters()
                cur_time = time.time()
                dt = cur_time - prev_time
                if dt > 0:
                    snapshot["network"]["upload_speed"] = (cur_net.bytes_sent - prev_net.bytes_sent) / dt
                    snapshot["network"]["download_speed"] = (cur_net.bytes_recv - prev_net.bytes_recv) / dt
                prev_net = cur_net
                prev_time = cur_time

                try:
                    await websocket.send_json(snapshot)
                except Exception:
                    break

                await asyncio.sleep(interval)

        except Exception as e:
            print(f"  Monitor error: {e}")
        finally:
            self._clients.discard(websocket)
            if not self._clients:
                self.is_monitoring = False

    def stop_monitoring(self, websocket=None):
        """Stop monitoring for a client."""
        if websocket:
            self._clients.discard(websocket)
        else:
            self._clients.clear()
        if not self._clients:
            self.is_monitoring = False


# Global instance
system_monitor = SystemMonitor()
