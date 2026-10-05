"""
MIA Self-Modification — shared paths and the core write-protection boundary.

Everything in PROTECTED_PATHS is MIA's own source and safety state. While a tool
runs (inside `untrusted()`), a Python audit hook refuses any in-process attempt to
write, move or delete those paths — so this holds even for code MIA wrote itself,
not just for the tools that check paths explicitly.
"""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

SELFMOD_DIR = DATA_DIR / "self_mod"
BACKUPS_DIR = SELFMOD_DIR / "backups"
TRASH_DIR = SELFMOD_DIR / "trash"
STAGING_DIR = SELFMOD_DIR / "staging"
ACTION_LOG = SELFMOD_DIR / "actions.jsonl"
APPROVALS_FILE = SELFMOD_DIR / "approvals.json"

DYNAMIC_TOOLS_DIR = DATA_DIR / "dynamic_tools"
SKILLS_DIR = DATA_DIR / "skills"

PROTECTED_PATHS = [
    PROJECT_ROOT / "server",
    PROJECT_ROOT / "frontend",
    PROJECT_ROOT / "scripts",
    PROJECT_ROOT / "mia.py",
    PROJECT_ROOT / ".env",
    PROJECT_ROOT / ".git",
    SELFMOD_DIR,  # logs, backups, trash and approvals — MIA must not be able to rewrite its own audit trail
    DATA_DIR / "bin",  # helper programs MIA runs with your credentials (e.g. the `ant` CLI)
]


def _norm(path) -> str:
    path = os.fspath(path)
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    return os.path.normcase(os.path.abspath(path))


_PROTECTED = [_norm(p) for p in PROTECTED_PATHS]


def _under(path_str: str, root: str) -> bool:
    return path_str == root or path_str.startswith(root.rstrip(os.sep) + os.sep)


def is_protected(path) -> bool:
    """True if `path` (or what it resolves to through links/junctions) is part of MIA's core."""
    candidates = {_norm(path)}
    try:
        candidates.add(os.path.normcase(os.path.realpath(os.fspath(path))))
    except (OSError, ValueError, TypeError):
        pass
    return any(_under(c, root) for c in candidates for root in _PROTECTED)


def is_inside(path, folder) -> bool:
    return _under(_norm(path), _norm(folder))


# ── Enforcement context ───────────────────────────────────────

_untrusted = ContextVar("mia_untrusted", default=False)
_trusted = ContextVar("mia_trusted", default=False)
_always_enforce = False
_hook_installed = False


@contextmanager
def untrusted():
    """Run tool code with core write-protection enforced."""
    token = _untrusted.set(True)
    try:
        yield
    finally:
        _untrusted.reset(token)


@contextmanager
def trusted():
    """Let MIA's own safety machinery (journal, approvals, trash) write to data/self_mod."""
    token = _trusted.set(True)
    try:
        yield
    finally:
        _trusted.reset(token)


_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC

# audit event → indexes of the path arguments that must not be protected
_PATH_EVENTS = {
    "os.remove": (0,),
    "os.rmdir": (0,),
    "os.mkdir": (0,),
    "os.truncate": (0,),
    "os.chmod": (0,),
    "os.rename": (0, 1),   # also raised by os.replace
    "os.link": (0, 1),
    "os.symlink": (0, 1),  # blocks pointing a link/junction at core files
    "shutil.rmtree": (0,),
    "shutil.copyfile": (1,),
    "shutil.copytree": (1,),
}


def _deny(path):
    raise PermissionError(f"MIA core is read-only: {os.fspath(path)}")


def _is_path(value) -> bool:
    return isinstance(value, (str, bytes, os.PathLike))


_in_hook = ContextVar("mia_in_audit_hook", default=False)


def _audit_hook(event, args):
    if not (_always_enforce or _untrusted.get()) or _trusted.get() or _in_hook.get():
        return
    if event != "open" and event not in _PATH_EVENTS:
        return
    token = _in_hook.set(True)  # path resolution below must not re-enter the hook
    try:
        _check_event(event, args)
    finally:
        _in_hook.reset(token)


def _check_event(event, args):
    if event == "open":
        path, mode, flags = args
        if not _is_path(path):
            return
        writing = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
            isinstance(flags, int) and flags & _WRITE_FLAGS
        )
        if writing and is_protected(path):
            _deny(path)
    elif event in _PATH_EVENTS:
        for index in _PATH_EVENTS[event]:
            if index < len(args) and _is_path(args[index]) and is_protected(args[index]):
                _deny(args[index])


def install_audit_hook(always_enforce: bool = False):
    """Install the core write-protection hook (process-wide, cannot be removed once added)."""
    global _hook_installed, _always_enforce
    if always_enforce:
        _always_enforce = True
    if _hook_installed:
        return
    import sys
    sys.addaudithook(_audit_hook)
    _hook_installed = True
