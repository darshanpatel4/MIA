"""
MIA Process Manager — View and manage running processes.
"""

import psutil
from typing import Optional


class ProcessManager:
    """Manage system processes."""

    def list_processes(self, sort_by: str = "memory", limit: int = 50, search: Optional[str] = None) -> list:
        """Get running processes with details."""
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "username", "create_time"]):
            try:
                info = proc.info
                if search and search.lower() not in (info.get("name") or "").lower():
                    continue
                processes.append({
                    "pid": info.get("pid"),
                    "name": info.get("name", "Unknown"),
                    "cpu": round(info.get("cpu_percent", 0) or 0, 1),
                    "memory": round(info.get("memory_percent", 0) or 0, 1),
                    "status": info.get("status", "unknown"),
                    "user": info.get("username", ""),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort
        sort_keys = {
            "memory": lambda x: x["memory"],
            "cpu": lambda x: x["cpu"],
            "name": lambda x: x["name"].lower(),
            "pid": lambda x: x["pid"],
        }
        key_fn = sort_keys.get(sort_by, sort_keys["memory"])
        processes.sort(key=key_fn, reverse=(sort_by in ("memory", "cpu")))

        return processes[:limit]

    def kill_process(self, pid: int) -> dict:
        """Kill a process by PID."""
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            proc.terminate()
            return {"success": True, "message": f"Terminated: {name} (PID {pid})"}
        except psutil.NoSuchProcess:
            return {"success": False, "error": f"Process {pid} not found"}
        except psutil.AccessDenied:
            return {"success": False, "error": f"Access denied for PID {pid}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_process_details(self, pid: int) -> dict:
        """Get detailed info about a specific process."""
        try:
            proc = psutil.Process(pid)
            with proc.oneshot():
                return {
                    "pid": proc.pid,
                    "name": proc.name(),
                    "exe": proc.exe(),
                    "cwd": proc.cwd(),
                    "status": proc.status(),
                    "cpu_percent": proc.cpu_percent(),
                    "memory_percent": round(proc.memory_percent(), 2),
                    "memory_rss": proc.memory_info().rss,
                    "threads": proc.num_threads(),
                    "username": proc.username(),
                    "cmdline": " ".join(proc.cmdline()),
                }
        except Exception as e:
            return {"error": str(e)}


# Global instance
process_manager = ProcessManager()
