from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import OUTPUT_DIR
from .link_resolver import download_resolved_assets, resolve_link
from .remover import platform_cleanup_preset, parse_box, remove_image_local, remove_video_local, remove_with_external_ai
from .utils import ensure_dir


def _boxes(values: list[str] | None):
    return [parse_box(value) for value in values or []]


def cmd_link(args: argparse.Namespace) -> None:
    result = resolve_link(args.url, args.parse_video_base_url)
    if args.download:
        result = download_resolved_assets(result, Path(args.output_dir))
        if args.clean_platform_watermark:
            for asset in result.assets:
                if asset.path is None:
                    continue
                if asset.kind not in {"video", "watermarked_video", "media"}:
                    continue
                clean_path = asset.path.with_name(f"{asset.path.stem}_clean.mp4")
                if args.clean_engine == "external-ai":
                    asset.clean_path = remove_with_external_ai(
                        asset.path,
                        clean_path,
                        detection_prompt=args.ai_detection_prompt,
                        max_bbox_percent=args.ai_max_bbox_percent,
                        detection_skip=args.ai_detection_skip,
                        fade_in=args.ai_fade_in,
                        fade_out=args.ai_fade_out,
                        force_format="MP4",
                    )
                else:
                    preset = platform_cleanup_preset(result.platform, _video_size(asset.path))
                    boxes = preset["boxes"]
                    if not boxes:
                        continue
                    asset.clean_path = remove_video_local(
                        asset.path,
                        clean_path,
                        boxes=boxes,
                        smart=bool(preset["smart"]),
                        radius=args.clean_radius if args.clean_radius is not None else int(preset["radius"]),
                        dilate=args.clean_dilate if args.clean_dilate is not None else int(preset["dilate"]),
                        limit_frames=args.clean_limit_frames,
                    )

    payload = {
        "platform": result.platform,
        "title": result.title,
        "assets": [
            {
                "kind": asset.kind,
                "url": asset.url,
                "path": str(asset.path) if asset.path else None,
                "clean_path": str(asset.clean_path) if asset.clean_path else None,
            }
            for asset in result.assets
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _video_size(path: Path) -> tuple[int, int]:
    import json
    import subprocess

    from .config import find_ffmpeg_tool

    data = subprocess.check_output(
        [
            find_ffmpeg_tool("ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    stream = json.loads(data)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def cmd_image(args: argparse.Namespace) -> None:
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve() if args.output else OUTPUT_DIR / f"{input_path.stem}_clean{input_path.suffix}"

    if args.engine == "external-ai":
        result = remove_with_external_ai(
            input_path,
            output_path,
            detection_prompt=args.ai_detection_prompt,
            max_bbox_percent=args.ai_max_bbox_percent,
            force_format=Path(output_path).suffix.lstrip(".").upper() if Path(output_path).suffix else None,
        )
    else:
        result = remove_image_local(
            input_path,
            output_path,
            mask_path=Path(args.mask).resolve() if args.mask else None,
            boxes=_boxes(args.box),
            auto=args.auto,
            smart=args.smart,
            radius=args.radius,
            dilate=args.dilate,
        )
    print(result)


def cmd_video(args: argparse.Namespace) -> None:
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve() if args.output else OUTPUT_DIR / f"{input_path.stem}_clean.mp4"

    if args.engine == "external-ai":
        result = remove_with_external_ai(
            input_path,
            output_path,
            detection_prompt=args.ai_detection_prompt,
            max_bbox_percent=args.ai_max_bbox_percent,
            detection_skip=args.ai_detection_skip,
            fade_in=args.ai_fade_in,
            fade_out=args.ai_fade_out,
            force_format="MP4",
        )
    else:
        result = remove_video_local(
            input_path,
            output_path,
            mask_path=Path(args.mask).resolve() if args.mask else None,
            boxes=_boxes(args.box),
            auto=args.auto,
            smart=args.smart,
            radius=args.radius,
            dilate=args.dilate,
            fps=args.fps,
            limit_frames=args.limit_frames,
        )
    print(result)


def cmd_service(args: argparse.Namespace) -> None:
    from .server import run_server

    ensure_dir(Path(args.output_dir))
    run_server(args.host, args.port, Path(args.output_dir))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone watermark tools for images, videos, and platform links.")
    sub = parser.add_subparsers(dest="command", required=True)

    link = sub.add_parser("link", help="Resolve and optionally download an authorized platform link.")
    link.add_argument("url")
    link.add_argument("--parse-video-base-url", default=None)
    link.add_argument("--output-dir", default=str(OUTPUT_DIR / "link_downloads"))
    link.add_argument("--download", action="store_true")
    link.add_argument("--clean-platform-watermark", action="store_true", help="After downloading, auto-clean known platform watermarks and keep the original.")
    link.add_argument("--clean-engine", choices=("local", "external-ai"), default="local", help="Cleaning engine used with --clean-platform-watermark.")
    link.add_argument("--clean-dilate", type=int)
    link.add_argument("--clean-radius", type=int)
    link.add_argument("--clean-limit-frames", type=int)
    link.add_argument("--ai-detection-prompt", default="watermark")
    link.add_argument("--ai-max-bbox-percent", type=float, default=10.0)
    link.add_argument("--ai-detection-skip", type=int, default=3)
    link.add_argument("--ai-fade-in", type=float, default=0.5)
    link.add_argument("--ai-fade-out", type=float, default=0.5)
    link.set_defaults(func=cmd_link)

    image = sub.add_parser("image", help="Remove watermark from an image.")
    image.add_argument("input")
    image.add_argument("--output")
    image.add_argument("--engine", choices=("local", "external-ai"), default="local")
    image.add_argument("--ai-detection-prompt", default="watermark")
    image.add_argument("--ai-max-bbox-percent", type=float, default=10.0)
    image.add_argument("--mask", help="Black/white mask image. White pixels are inpainted.")
    image.add_argument("--box", action="append", help="Watermark rectangle as x,y,w,h. Can be repeated.")
    image.add_argument("--auto", action="store_true", help="Try to auto-detect high-contrast edge watermarks.")
    image.add_argument("--smart", action="store_true", help="Use boxes as search areas and mask only likely watermark strokes.")
    image.add_argument("--radius", type=int, default=5)
    image.add_argument("--dilate", type=int, default=6)
    image.set_defaults(func=cmd_image)

    video = sub.add_parser("video", help="Remove watermark from an MP4/MOV/MKV video.")
    video.add_argument("input")
    video.add_argument("--output")
    video.add_argument("--engine", choices=("local", "external-ai"), default="local")
    video.add_argument("--ai-detection-prompt", default="watermark")
    video.add_argument("--ai-max-bbox-percent", type=float, default=10.0)
    video.add_argument("--ai-detection-skip", type=int, default=3)
    video.add_argument("--ai-fade-in", type=float, default=0.5)
    video.add_argument("--ai-fade-out", type=float, default=0.5)
    video.add_argument("--mask", help="Black/white mask image applied to every frame.")
    video.add_argument("--box", action="append", help="Watermark rectangle as x,y,w,h. Can be repeated.")
    video.add_argument("--auto", action="store_true", help="Try to auto-detect high-contrast edge watermarks.")
    video.add_argument("--smart", action="store_true", help="Use boxes as search areas and mask only likely watermark strokes.")
    video.add_argument("--radius", type=int, default=5)
    video.add_argument("--dilate", type=int, default=6)
    video.add_argument("--fps", type=float)
    video.add_argument("--limit-frames", type=int, help="Debug only: process the first N frames.")
    video.set_defaults(func=cmd_video)

    service = sub.add_parser("service", help="Start an aiohttp API service.")
    service.add_argument("--host", default="127.0.0.1")
    service.add_argument("--port", type=int, default=8198)
    service.add_argument("--output-dir", default=str(OUTPUT_DIR / "watermark_service"))
    service.set_defaults(func=cmd_service)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
