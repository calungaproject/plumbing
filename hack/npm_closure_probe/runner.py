"""Subprocess helpers for production pipeline scripts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

from .env import ProbeEnv


def _assert_safe_argv(argv: Sequence[str]) -> None:
    for part in argv:
        if not isinstance(part, str) or "\0" in part or "\n" in part:
            sys.exit("ERROR: invalid subprocess argument")


def run(
    cmd: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    argv = list(cmd)
    _assert_safe_argv(argv)
    print(f"+ {' '.join(argv)}", flush=True)
    proc = subprocess.run(  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use
        argv,
        env=dict(env) if env is not None else None,
        cwd=str(cwd) if cwd else None,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        sys.exit(proc.returncode)
    return proc


def run_pipeline_script(
    probe_env: ProbeEnv,
    script: Path,
    *args: str,
    check: bool = True,
    extra_env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if not script.is_file():
        sys.exit(f"ERROR: script not found: {script}")
    resolved = script.resolve()
    try:
        resolved.relative_to(probe_env.root.resolve())
    except ValueError:
        sys.exit(f"ERROR: script outside repo: {resolved}")
    try:
        shebang = script.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        shebang = ""
    env = probe_env.as_subprocess_env()
    if extra_env:
        env.update(extra_env)
    if "python" in shebang:
        cmd = ["python3", str(script), *args]
    elif "bash" in shebang:
        cmd = [probe_env.resolve_bash(), str(script), *args]
    else:
        cmd = [str(script), *args]
    return run(cmd, env=env, check=check)
