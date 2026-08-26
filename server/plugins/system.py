import platform
from datetime import datetime
import psutil
from server.plugins import tool

@tool(
    name="get_system_info",
    description="Get CPU, RAM, disk, network, and OS information.",
    parameters={},
    required=[]
)
def get_system_info() -> str:
    """Get comprehensive system information."""
    try:
        cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
        mem = psutil.virtual_memory()
        disk_info = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_info.append(
                    f"  {part.device}: {usage.used / (1024**3):.1f}/{usage.total / (1024**3):.1f} GB ({usage.percent}%)"
                )
            except PermissionError:
                continue

        net = psutil.net_io_counters()
        boot = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot

        return (
            f"💻 **System Information**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"**OS:** {platform.system()} {platform.release()} ({platform.version()})\n"
            f"**CPU:** {psutil.cpu_count()} cores, {sum(cpu_percent)/len(cpu_percent):.1f}% avg\n"
            f"  Per-core: {', '.join(f'{p:.0f}%' for p in cpu_percent)}\n"
            f"**RAM:** {mem.used / (1024**3):.1f}/{mem.total / (1024**3):.1f} GB ({mem.percent}%)\n"
            f"**Disks:**\n{''.join(disk_info) if disk_info else '  No disk info'}\n"
            f"**Network:** ↑{net.bytes_sent / (1024**2):.0f} MB ↓{net.bytes_recv / (1024**2):.0f} MB\n"
            f"**Uptime:** {str(uptime).split('.')[0]}\n"
            f"**Boot:** {boot.strftime('%Y-%m-%d %H:%M')}"
        )
    except Exception as e:
        return f"❌ Error getting system info: {str(e)}"

@tool(
    name="list_processes",
    description="List running processes sorted by resource usage.",
    parameters={
        "sort_by": {"type": "string", "description": "Sort by 'memory', 'cpu', or 'name'", "default": "memory"},
        "limit": {"type": "integer", "description": "Number of processes to show", "default": 20}
    },
    required=[]
)
def list_processes(sort_by: str = "memory", limit: int = 20) -> str:
    """List running processes sorted by resource usage."""
    try:
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                info = proc.info
                processes.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        # Sort
        key_map = {
            "memory": lambda x: x.get("memory_percent", 0) or 0,
            "cpu": lambda x: x.get("cpu_percent", 0) or 0,
            "name": lambda x: (x.get("name") or "").lower(),
        }
        sort_key = key_map.get(sort_by, key_map["memory"])
        processes.sort(key=sort_key, reverse=(sort_by != "name"))

        lines = [f"{'PID':<8} {'Name':<30} {'CPU%':<8} {'MEM%':<8} {'Status'}"]
        lines.append("─" * 70)
        for p in processes[:limit]:
            lines.append(
                f"{p.get('pid', '?'):<8} "
                f"{(p.get('name') or 'unknown')[:28]:<30} "
                f"{p.get('cpu_percent', 0) or 0:<8.1f} "
                f"{p.get('memory_percent', 0) or 0:<8.1f} "
                f"{p.get('status', '?')}"
            )

        return f"⚙️ **Top {limit} Processes** (by {sort_by}):\n```\n" + "\n".join(lines) + "\n```"

    except Exception as e:
        return f"❌ Error listing processes: {str(e)}"

@tool(
    name="kill_process",
    description="Kill a process by PID or name.",
    parameters={
        "identifier": {"type": "string", "description": "Process PID or name"}
    },
    required=["identifier"]
)
def kill_process(identifier: str) -> str:
    """Kill a process by PID or name."""
    try:
        # Try as PID first
        try:
            pid = int(identifier)
            proc = psutil.Process(pid)
            name = proc.name()
            proc.terminate()
            return f"✅ Terminated process: {name} (PID {pid})"
        except ValueError:
            pass

        # Search by name
        killed = []
        for proc in psutil.process_iter(["pid", "name"]):
            if proc.info["name"] and identifier.lower() in proc.info["name"].lower():
                try:
                    proc.terminate()
                    killed.append(f"{proc.info['name']} (PID {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        if killed:
            return f"✅ Terminated {len(killed)} process(es):\n" + "\n".join(f"  • {k}" for k in killed)
        return f"❌ No process found matching '{identifier}'"

    except Exception as e:
        return f"❌ Error killing process: {str(e)}"
