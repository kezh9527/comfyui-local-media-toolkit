from __future__ import annotations

import os
import shutil
from pathlib import Path


COMFY_ROOT = Path(__file__).resolve().parents[1]
CONDA_ROOT = Path(os.environ.get("CONDA_ROOT", "D:/Miniconda3"))
CONDA_ENVS_ROOT = Path(
    os.environ.get("CONDA_ENVS_ROOT")
    or os.environ.get("CONDA_ENVS_PATH", "D:/conda_envs").split(os.pathsep)[0]
)
COMFY_ENV = CONDA_ENVS_ROOT / "comfyui"
PARSE_VIDEO_ENV = CONDA_ENVS_ROOT / "parse-video"
WATERMARK_AI_ENV = CONDA_ENVS_ROOT / "watermark-ai"
INPUT_DIR = COMFY_ROOT / "input"
OUTPUT_DIR = COMFY_ROOT / "output"
WORK_DIR = COMFY_ROOT / "watermark_runs"


def env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return Path(value).expanduser().resolve()


def find_ffmpeg_tool(name: str) -> str:
    ffmpeg_bin_dir = env_path("FFMPEG_BIN_DIR")
    candidates = [
        *((ffmpeg_bin_dir / f"{name}.exe",) if ffmpeg_bin_dir else ()),
        Path("D:/AI/ffmpeg/bin") / f"{name}.exe",
        COMFY_ENV / "Library" / "bin" / f"{name}.exe",
        CONDA_ROOT / "Library" / "bin" / f"{name}.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    exe = shutil.which(name)
    if exe:
        return exe

    raise FileNotFoundError(
        f"{name} was not found. Add ffmpeg to PATH or place it under D:/AI/ffmpeg/bin."
    )


PARSE_VIDEO_BASE_URL = os.environ.get("PARSE_VIDEO_BASE_URL", "").strip().rstrip("/")
PARSE_VIDEO_PY_SRC = env_path("PARSE_VIDEO_PY_SRC")
WATERMARK_REMOVER_AI_DIR = env_path("WATERMARK_REMOVER_AI_DIR") or COMFY_ROOT / "external" / "WatermarkRemover-AI"
WATERMARK_REMOVER_AI_PYTHON = env_path("WATERMARK_REMOVER_AI_PYTHON") or WATERMARK_AI_ENV / "python.exe"
