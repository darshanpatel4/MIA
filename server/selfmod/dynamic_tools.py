"""
MIA Self-Modification — dynamic tools: abilities MIA writes for itself in data/dynamic_tools/.

Layout per tool:
  data/dynamic_tools/<name>/tool.py        — functions registered with @tool
  data/dynamic_tools/<name>/test_tool.py   — tests, run in a separate process before install
  data/dynamic_tools/<name>/manifest.json  — description, version, reason, timestamps

The static checks below are guard rails that catch the obvious ways generated code could
delete things or escape the core write-protection. They are not a sandbox.
"""

import ast
import importlib.util
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time

from server.plugins import TOOL_REGISTRY
from server.selfmod import paths
from server.selfmod.paths import trusted, untrusted

MODULE_PREFIX = "mia_dynamic_"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
TEST_TIMEOUT = 60

# Whole modules generated code may not import (process spawning, threads that escape the
# protection context, raw memory access, import machinery).
BLOCKED_MODULES = {
    "subprocess", "multiprocessing", "threading", "_thread", "concurrent", "asyncio", "ctypes",
    "importlib", "builtins", "gc", "code", "codeop", "runpy", "pty", "signal", "winreg", "_winapi",
    "msvcrt", "send2trash",
}
BLOCKED_CALLS = {"eval", "exec", "compile", "__import__", "globals", "locals", "vars", "breakpoint",
                 "getattr", "setattr", "delattr"}
# Attributes blocked on specific modules (catches `os.remove(...)` and `from os import remove`).
BLOCKED_MODULE_ATTRS = {
    "os": {"system", "popen", "startfile", "remove", "unlink", "rmdir", "removedirs", "rename", "renames",
           "replace", "kill", "killpg", "fork", "forkpty", "execv", "execve", "execl", "execle", "execlp",
           "execlpe", "execvp", "execvpe", "spawnl", "spawnle", "spawnv", "spawnve", "posix_spawn", "symlink", "link"},
    "shutil": {"rmtree", "move"},
    "sys": {"modules", "_getframe", "addaudithook", "settrace", "setprofile"},
}
# Attributes blocked on anything (deletion methods and introspection escape hatches).
BLOCKED_ATTRS = {
    "unlink", "rmdir", "rmtree", "removedirs", "__globals__", "__builtins__", "__subclasses__", "__code__",
    "__closure__", "__loader__", "__spec__", "f_globals", "f_locals", "f_back", "gi_frame", "cr_frame", "tb_frame",
}
ALLOWED_SERVER_IMPORTS = {"server.plugins", "server.selfmod.api"}


# ── Static checks ────────────────────────────────────────────

def _check_imports(node, aliases: dict, errors: list, extra_allowed: set):
    if isinstance(node, ast.Import):
        for alias in node.names:
            _check_module(alias.name, errors, extra_allowed)
            aliases[alias.asname or alias.name.split(".")[0]] = alias.name
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        if node.level:
            errors.append(f"line {node.lineno}: relative imports aren't allowed")
            return
        if module == "server":
            for alias in node.names:
                _check_module(f"server.{alias.name}", errors, extra_allowed)
        else:
            _check_module(module, errors, extra_allowed)
        blocked = BLOCKED_MODULE_ATTRS.get(module.split(".")[0], set())
        for alias in node.names:
            if alias.name in blocked or alias.name == "*" and blocked:
                errors.append(f"line {node.lineno}: `from {module} import {alias.name}` isn't allowed")


def _check_module(name: str, errors: list, extra_allowed: set):
    root = name.split(".")[0]
    if name in extra_allowed:
        return
    if root in BLOCKED_MODULES:
        errors.append(f"import of `{name}` isn't allowed in dynamic tools")
    elif root == "server" and name not in ALLOWED_SERVER_IMPORTS:
        errors.append(f"import of `{name}` isn't allowed — dynamic tools may only use "
                      "`server.plugins` (for @tool) and `server.selfmod.api` (to call other tools)")
    elif root.startswith(MODULE_PREFIX):
        errors.append(f"import of `{name}` isn't allowed — call other tools via server.selfmod.api.call_tool")


def check_code(code: str, filename: str, extra_allowed: set = frozenset()) -> list[str]:
    try:
        tree = ast.parse(code, filename=filename)
    except SyntaxError as e:
        return [f"{filename}: syntax error on line {e.lineno}: {e.msg}"]

    errors: list[str] = []
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _check_imports(node, aliases, errors, extra_allowed)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            errors.append(f"line {node.lineno}: calling `{node.func.id}()` isn't allowed")
        elif isinstance(node, ast.Attribute):
            if node.attr in BLOCKED_ATTRS:
                errors.append(f"line {node.lineno}: `.{node.attr}` isn't allowed — use the delete_file tool "
                              "via server.selfmod.api.call_tool so deletions get approved")
            elif isinstance(node.value, ast.Name):
                module = aliases.get(node.value.id, node.value.id).split(".")[0]
                if node.attr in BLOCKED_MODULE_ATTRS.get(module, set()):
                    errors.append(f"line {node.lineno}: `{module}.{node.attr}` isn't allowed")
        elif isinstance(node, ast.Name) and node.id in ("__builtins__", "__loader__", "__spec__"):
            errors.append(f"line {node.lineno}: `{node.id}` isn't allowed")
    return [f"{filename}: {e}" for e in errors]


def _declared_tool_names(code: str) -> list[str]:
    names = []
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tool":
            for kw in node.keywords:
                if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                    names.append(kw.value.value)
            if node.args and isinstance(node.args[0], ast.Constant):
                names.append(node.args[0].value)
    return names


def validate(name: str, code: str, test_code: str) -> list[str]:
    """Return a list of problems; empty means the code may be tested."""
    if not NAME_RE.match(name or ""):
        return ["tool_name must be 3-41 chars: lowercase letters, digits, underscores, starting with a letter"]
    errors = check_code(code, "tool.py") + check_code(test_code, "test_tool.py", extra_allowed={"tool"})
    if errors:
        return errors

    declared = _declared_tool_names(code)
    if not declared:
        errors.append("tool.py must register at least one function with @tool(name=\"...\", ...)")
    module_name = MODULE_PREFIX + name
    for tool_name in declared:
        existing = TOOL_REGISTRY.get(tool_name)
        if existing and existing["function"].__module__ != module_name:
            errors.append(f"tool name `{tool_name}` is already used by {existing['function'].__module__}; pick another name")
    return errors


# ── Testing ──────────────────────────────────────────────────

def run_tests(name: str, code: str, test_code: str) -> tuple[bool, str]:
    """Run test_tool.py against tool.py in a fresh process with core write-protection always on."""
    stage = paths.STAGING_DIR / f"{name}-{secrets.token_hex(3)}"
    with trusted():
        stage.mkdir(parents=True, exist_ok=True)
        (stage / "tool.py").write_text(code, encoding="utf-8")
        (stage / "test_tool.py").write_text(test_code, encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "server.selfmod.test_runner", str(stage)],
            cwd=str(paths.PROJECT_ROOT),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=TEST_TIMEOUT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        output = (proc.stdout + "\n" + proc.stderr).strip()
        return proc.returncode == 0, output[-3000:]
    except subprocess.TimeoutExpired:
        return False, f"Tests timed out after {TEST_TIMEOUT}s."
    finally:
        with trusted():
            shutil.rmtree(stage, ignore_errors=True)


# ── Install / load ───────────────────────────────────────────

def tool_dir(name: str):
    return paths.DYNAMIC_TOOLS_DIR / name


def read_manifest(name: str) -> dict:
    try:
        return json.loads((tool_dir(name) / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def install(name: str, code: str, test_code: str, description: str, reason: str) -> str:
    """Write a (validated, tested) tool to disk and hot-load it."""
    folder = tool_dir(name)
    manifest = read_manifest(name)
    now = time.time()
    manifest.update({
        "name": name,
        "description": description,
        "version": manifest.get("version", 0) + 1,
        "reason": reason,
        "created_at": manifest.get("created_at", now),
        "updated_at": now,
    })
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "tool.py").write_text(code, encoding="utf-8")
    (folder / "test_tool.py").write_text(test_code, encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    try:
        registered = load(name)
    except Exception as e:
        return f"❌ Saved '{name}' v{manifest['version']} but it failed to load: {e}"
    return (f"✅ Dynamic tool '{name}' v{manifest['version']} installed. "
            f"New tools available now: {', '.join(registered)}")


def registered_tools(name: str) -> list[str]:
    module_name = MODULE_PREFIX + name
    return [k for k, v in TOOL_REGISTRY.items() if v["function"].__module__ == module_name]


def unload(name: str):
    for tool_name in registered_tools(name):
        del TOOL_REGISTRY[tool_name]
    sys.modules.pop(MODULE_PREFIX + name, None)


def load(name: str) -> list[str]:
    """(Re)load one dynamic tool module. Returns the tool names it registered."""
    module_name = MODULE_PREFIX + name
    path = tool_dir(name) / "tool.py"
    previous = dict(TOOL_REGISTRY)
    unload(name)

    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        with untrusted():  # module-level code runs with core protection on
            spec.loader.exec_module(module)
        registered = registered_tools(name)
        clashes = [t for t in registered if t in previous and previous[t]["function"].__module__ != module_name]
        if clashes:
            raise ValueError(f"tool name(s) already taken: {', '.join(clashes)}")
        if not registered:
            raise ValueError("no @tool functions were registered")
        return registered
    except Exception:
        TOOL_REGISTRY.clear()
        TOOL_REGISTRY.update(previous)
        sys.modules.pop(module_name, None)
        raise


def installed_names() -> list[str]:
    if not paths.DYNAMIC_TOOLS_DIR.exists():
        return []
    return sorted(p.name for p in paths.DYNAMIC_TOOLS_DIR.iterdir() if (p / "tool.py").is_file())


def load_all():
    for name in installed_names():
        try:
            tools = load(name)
            print(f"  🧩 Dynamic tool '{name}' loaded ({', '.join(tools)})")
        except Exception as e:
            print(f"  ⚠️ Dynamic tool '{name}' failed to load: {e}")


def reload_all():
    for module_name in [m for m in list(sys.modules) if m.startswith(MODULE_PREFIX)]:
        unload(module_name[len(MODULE_PREFIX):])
    load_all()
