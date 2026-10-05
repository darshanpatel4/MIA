"""
Runs a staged dynamic tool's tests: `python -m server.selfmod.test_runner <stage_dir>`.

Executed in its own process with core write-protection permanently on. Supports plain
top-level asserts and pytest-style `test_*` functions.
"""

import sys
import runpy
import traceback
from pathlib import Path

from server.selfmod import paths


def main(stage_dir: str) -> int:
    paths.install_audit_hook(always_enforce=True)
    sys.path.insert(0, stage_dir)

    namespace = runpy.run_path(str(Path(stage_dir) / "test_tool.py"), run_name="__main__")
    tests = [(name, fn) for name, fn in namespace.items() if name.startswith("test_") and callable(fn)]

    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()

    if failed:
        print(f"❌ {failed} of {len(tests)} test(s) failed")
        return 1
    print(f"✅ Tests passed ({len(tests)} test function(s) + top-level asserts)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
