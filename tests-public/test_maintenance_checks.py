from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import check_public_source  # noqa: E402
from watermark_tools import config as watermark_config  # noqa: E402


class PublicSourceCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.work_dir = check_public_source.ROOT / "temp" / "unit-public-source-check"
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def write_file(self, name: str, text: str) -> Path:
        path = self.work_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_runtime_directory_is_rejected(self) -> None:
        errors = check_public_source.check_file(self.write_file("runtime.txt", "local output"))

        self.assertTrue(any("runtime directory must not be published" in error for error in errors))

    def test_forbidden_model_suffix_is_rejected(self) -> None:
        errors = check_public_source.check_file(self.write_file("weights.safetensors", "not real weights"))

        self.assertTrue(any("generated, media, secret, or model file" in error for error in errors))

    def test_secret_pattern_is_rejected_without_storing_a_real_token(self) -> None:
        fake_key = "sk-" + ("A" * 32)
        errors = check_public_source.check_file(self.write_file("secret.txt", f"token={fake_key}"))

        self.assertTrue(any("possible OpenAI-style API key" in error for error in errors))


class MissingDependencyErrorTests(unittest.TestCase):
    def test_missing_ffmpeg_message_includes_recovery_hint(self) -> None:
        missing_root = check_public_source.ROOT / "temp" / "unit-missing-ffmpeg"
        with (
            patch.dict(os.environ, {"FFMPEG_BIN_DIR": str(missing_root / "ffmpeg-bin"), "PATH": ""}),
            patch.object(watermark_config, "COMFY_ENV", missing_root / "comfyui"),
            patch.object(watermark_config, "CONDA_ROOT", missing_root / "conda"),
            patch.object(Path, "exists", return_value=False),
            patch.object(watermark_config.shutil, "which", return_value=None),
        ):
            with self.assertRaises(FileNotFoundError) as raised:
                watermark_config.find_ffmpeg_tool("ffmpeg")

        message = str(raised.exception)
        self.assertIn("FFMPEG_BIN_DIR", message)
        self.assertIn("ffmpeg.exe", message)
        self.assertIn("ffprobe.exe", message)


if __name__ == "__main__":
    unittest.main()
