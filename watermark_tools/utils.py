from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable, Iterable


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_command(args: Iterable[str | Path], *, cwd: Path | None = None) -> None:
    printable = " ".join(str(a) for a in args)
    proc = subprocess.run([str(a) for a in args], cwd=cwd, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {printable}")


def run_command_stream(
    args: Iterable[str | Path],
    *,
    cwd: Path | None = None,
    on_line: Callable[[str], None] | None = None,
) -> None:
    printable = " ".join(str(a) for a in args)
    proc = subprocess.Popen(
        [str(a) for a in args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        if on_line:
            on_line(line)
        else:
            print(line, flush=True)
    if proc.wait() != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {printable}")


def run_json(args: Iterable[str | Path], *, cwd: Path | None = None) -> dict:
    proc = subprocess.run(
        [str(a) for a in args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"Command failed: {' '.join(map(str, args))}")
    return json.loads(proc.stdout)


def clean_filename(value: str, default: str = "download") -> str:
    keep = []
    for char in value.strip():
        if char.isalnum() or char in "-_.()[] ":
            keep.append(char)
        else:
            keep.append("_")
    result = "".join(keep).strip(" ._")
    return result[:120] or default
