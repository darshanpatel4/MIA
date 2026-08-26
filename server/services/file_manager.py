"""
MIA File Manager — Remote file browsing, upload, and download.
"""

import os
import shutil
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import Optional


class FileManager:
    """File browsing and management service."""

    # Directories that should never be listed/modified
    BLOCKED_PATHS = [
        "C:\\Windows\\System32",
        "C:\\Windows\\SysWOW64",
    ]

    def list_directory(self, dir_path: str) -> dict:
        """List directory contents with metadata."""
        try:
            path = Path(dir_path)
            if not path.exists():
                return {"error": f"Directory not found: {dir_path}"}
            if not path.is_dir():
                return {"error": f"Not a directory: {dir_path}"}

            items = []
            for item in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                try:
                    stat = item.stat()
                    entry = {
                        "name": item.name,
                        "path": str(item),
                        "is_dir": item.is_dir(),
                        "size": stat.st_size if item.is_file() else None,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "extension": item.suffix.lower() if item.is_file() else None,
                    }
                    if item.is_dir():
                        try:
                            entry["children_count"] = sum(1 for _ in item.iterdir())
                        except PermissionError:
                            entry["children_count"] = -1
                    items.append(entry)
                except (PermissionError, OSError):
                    items.append({
                        "name": item.name,
                        "path": str(item),
                        "is_dir": item.is_dir(),
                        "error": "Permission denied",
                    })

            return {
                "path": str(path),
                "parent": str(path.parent),
                "items": items,
                "count": len(items),
            }

        except PermissionError:
            return {"error": f"Permission denied: {dir_path}"}
        except Exception as e:
            return {"error": str(e)}

    def get_file_info(self, file_path: str) -> dict:
        """Get detailed file information."""
        try:
            path = Path(file_path)
            if not path.exists():
                return {"error": "File not found"}

            stat = path.stat()
            mime_type, _ = mimetypes.guess_type(str(path))

            return {
                "name": path.name,
                "path": str(path),
                "is_dir": path.is_dir(),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "extension": path.suffix,
                "mime_type": mime_type,
                "readable": os.access(str(path), os.R_OK),
                "writable": os.access(str(path), os.W_OK),
            }
        except Exception as e:
            return {"error": str(e)}

    def create_directory(self, dir_path: str) -> dict:
        """Create a directory."""
        try:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            return {"success": True, "message": f"Created: {dir_path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete(self, file_path: str) -> dict:
        """Delete a file or directory."""
        try:
            path = Path(file_path)
            # Safety check
            abs_path = str(path.resolve())
            for blocked in self.BLOCKED_PATHS:
                if abs_path.startswith(blocked):
                    return {"success": False, "error": "Cannot delete system files"}

            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
            else:
                return {"success": False, "error": "Path not found"}

            return {"success": True, "message": f"Deleted: {file_path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def rename(self, old_path: str, new_name: str) -> dict:
        """Rename a file or directory."""
        try:
            path = Path(old_path)
            new_path = path.parent / new_name
            path.rename(new_path)
            return {"success": True, "new_path": str(new_path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_drives(self) -> list:
        """Get available drives on Windows."""
        drives = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                try:
                    usage = shutil.disk_usage(drive)
                    drives.append({
                        "letter": letter,
                        "path": drive,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": round(usage.used / usage.total * 100, 1) if usage.total > 0 else 0,
                    })
                except Exception:
                    drives.append({"letter": letter, "path": drive})
        return drives

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format bytes to human-readable size."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


# Global instance
file_manager = FileManager()
