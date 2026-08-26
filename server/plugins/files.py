import os
import glob
import shutil
from pathlib import Path
from server.plugins import tool

@tool(
    name="read_file",
    description="Read the contents of a text file.",
    parameters={
        "file_path": {"type": "string", "description": "Path to the file to read"}
    },
    required=["file_path"]
)
def read_file(file_path: str, max_chars: int = 10000) -> str:
    """Read the contents of a file."""
    try:
        path = Path(file_path)
        if not path.exists():
            return f"❌ File not found: {file_path}"
        if not path.is_file():
            return f"❌ Not a file: {file_path}"

        size = path.stat().st_size
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)

        if size > max_chars:
            return f"📄 {file_path} ({size} bytes, showing first {max_chars} chars):\n\n{content}\n\n... [truncated]"
        return f"📄 {file_path}:\n\n{content}"

    except Exception as e:
        return f"❌ Error reading file: {str(e)}"

@tool(
    name="write_file",
    description="Write content to a file. Creates it if it doesn't exist.",
    parameters={
        "file_path": {"type": "string", "description": "Path to the file"},
        "content": {"type": "string", "description": "Content to write"}
    },
    required=["file_path", "content"]
)
def write_file(file_path: str, content: str) -> str:
    """Write content to a file (creates it if it doesn't exist)."""
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"✅ Written {len(content)} chars to {file_path}"
    except Exception as e:
        return f"❌ Error writing file: {str(e)}"

@tool(
    name="list_directory",
    description="List files and folders in a directory.",
    parameters={
        "dir_path": {"type": "string", "description": "Path to the directory. Default: current directory", "default": "."}
    },
    required=[]
)
def list_directory(dir_path: str = ".") -> str:
    """List files and folders in a directory."""
    try:
        path = Path(dir_path)
        if not path.exists():
            return f"❌ Directory not found: {dir_path}"
        if not path.is_dir():
            return f"❌ Not a directory: {dir_path}"

        items = []
        for item in sorted(path.iterdir()):
            if item.is_dir():
                count = sum(1 for _ in item.iterdir()) if os.access(str(item), os.R_OK) else "?"
                items.append(f"📁 {item.name}/ ({count} items)")
            else:
                size = item.stat().st_size
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                elif size < 1024 * 1024 * 1024:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                else:
                    size_str = f"{size / (1024 * 1024 * 1024):.1f} GB"
                items.append(f"📄 {item.name} ({size_str})")

        if not items:
            return f"📁 {dir_path} is empty."

        return f"📁 {dir_path}:\n" + "\n".join(items)

    except PermissionError:
        return f"❌ Permission denied: {dir_path}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

@tool(
    name="delete_file",
    description="Delete a file or directory. Use with caution!",
    parameters={
        "file_path": {"type": "string", "description": "Path to delete"}
    },
    required=["file_path"]
)
def delete_file(file_path: str) -> str:
    """Delete a file or directory."""
    try:
        path = Path(file_path)
        if not path.exists():
            return f"❌ Not found: {file_path}"
        if path.is_file():
            path.unlink()
            return f"✅ Deleted file: {file_path}"
        elif path.is_dir():
            shutil.rmtree(path)
            return f"✅ Deleted directory: {file_path}"
    except Exception as e:
        return f"❌ Error deleting: {str(e)}"

@tool(
    name="move_file",
    description="Move or rename a file/directory.",
    parameters={
        "source": {"type": "string", "description": "Source path"},
        "destination": {"type": "string", "description": "Destination path"}
    },
    required=["source", "destination"]
)
def move_file(source: str, destination: str) -> str:
    """Move or rename a file/directory."""
    try:
        shutil.move(source, destination)
        return f"✅ Moved {source} → {destination}"
    except Exception as e:
        return f"❌ Error moving: {str(e)}"

@tool(
    name="search_files",
    description="Search for files matching a glob pattern.",
    parameters={
        "pattern": {"type": "string", "description": "Glob pattern (e.g., '*.pdf')"},
        "search_path": {"type": "string", "description": "Directory to search in", "default": "C:\\Users"}
    },
    required=["pattern"]
)
def search_files(pattern: str, search_path: str = "C:\\Users") -> str:
    """Search for files matching a pattern."""
    try:
        results = []
        for match in glob.iglob(os.path.join(search_path, "**", pattern), recursive=True):
            results.append(match)
            if len(results) >= 50:
                break

        if not results:
            return f"🔍 No files matching '{pattern}' found in {search_path}"

        return f"🔍 Found {len(results)} files:\n" + "\n".join(f"  📄 {r}" for r in results)

    except Exception as e:
        return f"❌ Error searching: {str(e)}"
