"""Entry point for a Supercías build that WMI starts on Windows.

`supercias_financials._spawn_via_wmi` starts the build through the WMI service
so it belongs to none of the server's job objects (see the comment above
`_WINDOWS_DETACHED_FLAGS` there). A process WMI creates inherits the WMI
service's environment instead of the server's and has no stdout of ours, so
this module first restores the variables the build reads from a JSON file,
deleting it as soon as it is read because it can hold a proxy URL with
credentials. It then sends stdout and stderr to the build log and runs the
build exactly as `python -m helpers.supercias_financials_build` would.

Usage: python -m helpers.supercias_detached_launch ENV_FILE LOG_FILE
"""

from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path

_BUILD_MODULE = "helpers.supercias_financials_build"


def main(argv: list[str] | None = None) -> None:
    env_file, log_file = (Path(arg) for arg in (sys.argv[1:3] if argv is None else argv))
    try:
        os.environ.update(json.loads(env_file.read_text(encoding="utf-8")))
    finally:
        env_file.unlink(missing_ok=True)
    # Held open for the life of the build; line-buffered so a log read while
    # it runs (or after it is killed) shows its last stage.
    log = open(log_file, "w", encoding="utf-8", errors="replace", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stderr = log
    runpy.run_module(_BUILD_MODULE, run_name="__main__")


if __name__ == "__main__":
    main()
