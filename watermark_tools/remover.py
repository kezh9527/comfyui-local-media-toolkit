from __future__ import annotations

import sys
import tempfile
from pathlib import Path
import re
from typing import Callable, Iterable

import cv2
import numpy as np

from .config import WATERMARK_REMOVER_AI_DIR, WATERMARK_REMOVER_AI_PYTHON, WORK_DIR, find_ffmpeg_tool
from .utils import ensure_dir, run_command, run_command_stream, run_json


Box = tuple[int, int, int, int]
ProgressCallback = Callable[[float, str], None]


def platform_cleanup_preset(platform: str, size: tuple[int, int]) -> dict:
    boxes = platform_boxes(platform, size)
    platform = platform.lower()
    if platform == "weibo":
        return {"boxes": boxes, "smart": False, "radius": 5, "dilate": 4}
    if platform == "douyin":
        return {"boxes": boxes, "smart": True, "radius": 3, "dilate": 2}
    return {"boxes": boxes, "smart": True, "radius": 3, "dilate": 2}


def parse_box(value: str) -> Box:
    parts = [int(part.strip()) for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("Box must be x,y,w,h")
    x, y, w, h = parts
    if w <= 0 or h <= 0:
        raise ValueError("Box width and height must be positive")
    return x, y, w, h


def scale_box(box: Box, source_size: tuple[int, int], target_size: tuple[int, int]) -> Box:
    x, y, w, h = box
    source_w, source_h = source_size
    target_w, target_h = target_size
    return (
        int(round(x * target_w / source_w)),
        int(round(y * target_h / source_h)),
        int(round(w * target_w / source_w)),
        int(round(h * target_h / source_h)),
    )


def platform_boxes(platform: str, size: tuple[int, int]) -> list[Box]:
    width, height = size
    presets = {
        # Top-right Weibo video account watermark, based on a 1080x1920 vertical source.
        "weibo": [((690, 100, 390, 170), (1080, 1920))],
        # Common Douyin top-right author watermark and bottom-right app/user watermark.
        "douyin": [((850, 35, 285, 90), (1280, 720)), ((995, 535, 280, 170), (1280, 720))],
    }
    boxes: list[Box] = []
    for box, source_size in presets.get(platform.lower(), []):
        boxes.append(scale_box(box, source_size, (width, height)))
    return boxes


def _load_mask(mask_path: Path, size: tuple[int, int]) -> np.ndarray:
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Could not read mask: {mask_path}")
    width, height = size
    if mask.shape[:2] != (height, width):
        mask = cv2.resize(mask, (width, height), interpolation=cv2.INTER_NEAREST)
    _, mask = cv2.threshold(mask, 10, 255, cv2.THRESH_BINARY)
    return mask


def _mask_from_boxes(shape: tuple[int, int], boxes: Iterable[Box]) -> np.ndarray:
    height, width = shape
    mask = np.zeros((height, width), dtype=np.uint8)
    for x, y, w, h in boxes:
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(width, x + w)
        y2 = min(height, y + h)
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = 255
    return mask


def _smart_mask_from_boxes(image: np.ndarray, boxes: Iterable[Box]) -> np.ndarray:
    height, width = image.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    for x, y, w, h in boxes:
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(width, x + w)
        y2 = min(height, y + h)
        if x2 <= x1 or y2 <= y1:
            continue

        roi = image[y1:y2, x1:x2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]

        bright_strokes = ((value > 155) & (saturation < 135)).astype(np.uint8) * 255
        colored_logo = ((saturation > 85) & (value > 95)).astype(np.uint8) * 255
        dark_outline = (value < 65).astype(np.uint8) * 255

        edges = cv2.Canny(gray, 35, 110)
        edge_kernel = np.ones((3, 3), np.uint8)
        edge_neighborhood = cv2.dilate(edges, edge_kernel, iterations=1)

        candidates = cv2.bitwise_or(bright_strokes, colored_logo)
        candidates = cv2.bitwise_or(candidates, cv2.bitwise_and(dark_outline, edge_neighborhood))
        candidates = cv2.bitwise_and(candidates, cv2.dilate(edge_neighborhood, edge_kernel, iterations=1))

        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(candidates, connectivity=8)
        filtered = np.zeros_like(candidates)
        roi_area = max(1, roi.shape[0] * roi.shape[1])
        for label in range(1, num_labels):
            area = stats[label, cv2.CC_STAT_AREA]
            comp_w = stats[label, cv2.CC_STAT_WIDTH]
            comp_h = stats[label, cv2.CC_STAT_HEIGHT]
            if area < 6:
                continue
            if area > roi_area * 0.28:
                continue
            if comp_w > roi.shape[1] * 0.95 and comp_h > roi.shape[0] * 0.55:
                continue
            filtered[labels == label] = 255

        stroke_kernel = np.ones((3, 3), np.uint8)
        filtered = cv2.dilate(filtered, stroke_kernel, iterations=1)
        mask[y1:y2, x1:x2] = cv2.bitwise_or(mask[y1:y2, x1:x2], filtered)
    return mask


def _auto_mask(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    bright = ((saturation < 80) & (value > 165)).astype(np.uint8) * 255
    dark = (value < 45).astype(np.uint8) * 255
    mask = cv2.bitwise_or(bright, dark)

    edge_mask = np.zeros((height, width), dtype=np.uint8)
    margin_x = max(80, width // 5)
    margin_y = max(70, height // 5)
    edge_mask[:margin_y, :] = 255
    edge_mask[-margin_y:, :] = 255
    edge_mask[:, :margin_x] = 255
    edge_mask[:, -margin_x:] = 255
    mask = cv2.bitwise_and(mask, edge_mask)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.dilate(mask, kernel, iterations=2)
    return mask


def build_mask(
    image: np.ndarray,
    *,
    mask_path: Path | None = None,
    boxes: Iterable[Box] = (),
    auto: bool = False,
    smart: bool = False,
    dilate: int = 6,
) -> np.ndarray:
    height, width = image.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    if mask_path:
        mask = cv2.bitwise_or(mask, _load_mask(mask_path, (width, height)))
    boxes = list(boxes)
    box_mask = _smart_mask_from_boxes(image, boxes) if smart else _mask_from_boxes((height, width), boxes)
    if smart and boxes and not np.any(box_mask):
        box_mask = _mask_from_boxes((height, width), boxes)
    mask = cv2.bitwise_or(mask, box_mask)
    if auto:
        mask = cv2.bitwise_or(mask, _auto_mask(image))

    if not np.any(mask):
        raise ValueError("No watermark mask was produced. Pass --mask, --box, or --auto.")

    if dilate > 0:
        kernel = np.ones((dilate, dilate), np.uint8)
        mask = cv2.dilate(mask, kernel, iterations=1)
    return mask


def remove_image_local(
    input_path: Path,
    output_path: Path,
    *,
    mask_path: Path | None = None,
    boxes: Iterable[Box] = (),
    auto: bool = False,
    smart: bool = False,
    radius: int = 5,
    dilate: int = 6,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    if progress_callback:
        progress_callback(5, "Reading image")
    image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {input_path}")
    if progress_callback:
        progress_callback(35, "Building watermark mask")
    mask = build_mask(image, mask_path=mask_path, boxes=boxes, auto=auto, smart=smart, dilate=dilate)
    if progress_callback:
        progress_callback(70, "Inpainting image")
    result = cv2.inpaint(image, mask, radius, cv2.INPAINT_TELEA)
    ensure_dir(output_path.parent)
    if not cv2.imwrite(str(output_path), result):
        raise RuntimeError(f"Could not write image: {output_path}")
    if progress_callback:
        progress_callback(100, "Done")
    return output_path


def external_ai_python(root: Path) -> Path:
    candidates = [
        WATERMARK_REMOVER_AI_PYTHON,
        root / "python" / "python.exe",
        root / ".venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return Path(sys.executable)


def remove_with_external_ai(
    input_path: Path,
    output_path: Path,
    ai_dir: Path | None = None,
    *,
    detection_prompt: str = "watermark",
    max_bbox_percent: float = 10.0,
    detection_skip: int = 3,
    fade_in: float = 0.5,
    fade_out: float = 0.5,
    force_format: str | None = None,
    overwrite: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    root = ai_dir or WATERMARK_REMOVER_AI_DIR
    if not root:
        raise RuntimeError("WATERMARK_REMOVER_AI_DIR is not configured.")
    script = root / "remwm.py"
    if not script.exists():
        raise FileNotFoundError(
            f"Could not find external AI remover script: {script}. "
            "Run setup_watermark_ai.bat from the repository root first, "
            "or set WATERMARK_REMOVER_AI_DIR."
        )
    python = external_ai_python(root)
    ensure_dir(output_path.parent if output_path.suffix else output_path)

    args: list[str | Path] = [
        python,
        script,
        input_path,
        output_path,
        "--detection-prompt",
        detection_prompt,
        "--max-bbox-percent",
        str(max_bbox_percent),
        "--detection-skip",
        str(detection_skip),
        "--fade-in",
        str(fade_in),
        "--fade-out",
        str(fade_out),
    ]
    if force_format:
        args.extend(["--force-format", force_format])
    if overwrite:
        args.append("--overwrite")

    progress_pattern = re.compile(r"overall_progress:(\d+)%")

    def on_line(line: str) -> None:
        print(line, flush=True)
        match = progress_pattern.search(line)
        if match and progress_callback:
            progress_callback(float(match.group(1)), line)

    if progress_callback:
        progress_callback(1, "Starting external AI remover")
    run_command_stream(args, cwd=root, on_line=on_line)
    if progress_callback:
        progress_callback(99, "Collecting output")

    if output_path.exists() and output_path.is_file():
        if progress_callback:
            progress_callback(100, "Done")
        return output_path

    suffix_aliases = {
        ".jpg": [".jpeg"],
        ".jpeg": [".jpg"],
    }
    for suffix in suffix_aliases.get(output_path.suffix.lower(), []):
        alias_path = output_path.with_suffix(suffix)
        if alias_path.exists() and alias_path.is_file():
            if progress_callback:
                progress_callback(100, "Done")
            return alias_path

    candidates = sorted(
        [p for p in output_path.rglob("*") if p.is_file()] if output_path.exists() and output_path.is_dir() else [],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(f"External AI remover did not create output at {output_path}")
    if progress_callback:
        progress_callback(100, "Done")
    return candidates[0]


def probe_video_fps(input_path: Path) -> float:
    ffprobe = find_ffmpeg_tool("ffprobe")
    data = run_json(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate,avg_frame_rate",
            "-of",
            "json",
            input_path,
        ]
    )
    stream = data.get("streams", [{}])[0]
    rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "25/1"
    numerator, denominator = rate.split("/")
    denominator_int = int(denominator)
    return float(numerator) / denominator_int if denominator_int else 25.0


def remove_video_local(
    input_path: Path,
    output_path: Path,
    *,
    mask_path: Path | None = None,
    boxes: Iterable[Box] = (),
    auto: bool = False,
    smart: bool = False,
    radius: int = 5,
    dilate: int = 6,
    fps: float | None = None,
    limit_frames: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> Path:
    ffmpeg = find_ffmpeg_tool("ffmpeg")
    fps_value = fps or probe_video_fps(input_path)
    ensure_dir(output_path.parent)

    ensure_dir(WORK_DIR)
    with tempfile.TemporaryDirectory(prefix="video_", dir=WORK_DIR) as temp_name:
        temp_dir = Path(temp_name)
        raw_dir = ensure_dir(temp_dir / "raw")
        processed_dir = ensure_dir(temp_dir / "processed")
        temp_video = temp_dir / "video_no_audio.mp4"

        extract_args: list[str | Path] = [ffmpeg, "-y", "-i", input_path]
        if limit_frames:
            extract_args.extend(["-frames:v", str(limit_frames)])
        extract_args.append(raw_dir / "frame_%08d.png")
        if progress_callback:
            progress_callback(3, "Extracting video frames")
        run_command(extract_args)
        raw_frames = sorted(raw_dir.glob("frame_*.png"))
        if not raw_frames:
            raise RuntimeError("No frames were extracted from the video.")
        if progress_callback:
            progress_callback(10, f"Extracted {len(raw_frames)} frames")

        for index, frame in enumerate(raw_frames, start=1):
            remove_image_local(
                frame,
                processed_dir / frame.name,
                mask_path=mask_path,
                boxes=boxes,
                auto=auto,
                smart=smart,
                radius=radius,
                dilate=dilate,
            )
            if progress_callback:
                percent = 10 + (index / len(raw_frames)) * 75
                progress_callback(percent, f"Processed {index}/{len(raw_frames)} frames")
            elif index % 25 == 0:
                print(f"processed {index}/{len(raw_frames)} frames", flush=True)

        if progress_callback:
            progress_callback(88, "Encoding processed frames")
        run_command(
            [
                ffmpeg,
                "-y",
                "-framerate",
                f"{fps_value:.6f}",
                "-i",
                processed_dir / "frame_%08d.png",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                temp_video,
            ]
        )
        if progress_callback:
            progress_callback(96, "Merging audio")
        run_command(
            [
                ffmpeg,
                "-y",
                "-i",
                temp_video,
                "-i",
                input_path,
                "-map",
                "0:v:0",
                "-map",
                "1:a?",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-shortest",
                output_path,
            ]
        )
    if progress_callback:
        progress_callback(100, "Done")
    return output_path
