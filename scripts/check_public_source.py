from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 25 * 1024 * 1024
FORBIDDEN_DIRS = {
    "build",
    "custom_nodes",
    "dist",
    "external",
    "launcher_logs",
    "models",
    "output",
    "temp",
    "user",
    "video_faceswap_runs",
    "watermark_runs",
}
FORBIDDEN_SUFFIXES = {
    ".7z",
    ".avi",
    ".bin",
    ".ckpt",
    ".db",
    ".dll",
    ".exe",
    ".gguf",
    ".key",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".onnx",
    ".pem",
    ".pfx",
    ".pt",
    ".pth",
    ".safetensors",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".wav",
    ".webm",
    ".zip",
}
SECRET_PATTERNS = {
    "OpenAI-style API key": re.compile(r"\bsk-[A-Za-z0-9_-]{30,}\b"),
    "GitHub personal token": re.compile(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
ALLOWED_RUNTIME_FILES = {
    "custom_nodes/example_node.py.example",
    "input/example.png",
}


def publishable_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def check_file(path: Path) -> list[str]:
    relative = path.relative_to(ROOT)
    relative_text = relative.as_posix()
    errors: list[str] = []
    top_level = relative.parts[0]
    if top_level in FORBIDDEN_DIRS and relative_text not in ALLOWED_RUNTIME_FILES:
        errors.append(f"{relative}: runtime directory must not be published")
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        errors.append(f"{relative}: generated, media, secret, or model file must not be published")
    if path.stat().st_size > MAX_FILE_BYTES:
        errors.append(f"{relative}: file exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MiB public-source limit")
    if path.stat().st_size <= 2 * 1024 * 1024:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return errors
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{relative}: possible {label}")
    return errors


def main() -> int:
    files = publishable_files()
    errors = [error for path in files for error in check_file(path)]
    if errors:
        print("Public source check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Public source check passed for {len(files)} publishable files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
