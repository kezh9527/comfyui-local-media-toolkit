# Watermark Tools

Standalone CLI and localhost API utilities for authorized image and video
cleanup. They do not modify ComfyUI core files.

Read [../docs/RESPONSIBLE_USE.md](../docs/RESPONSIBLE_USE.md) before use. Only
process media you own or are authorized to edit. Platform-link integration must
also comply with the applicable platform terms.

## Features

- Local OpenCV image inpainting with boxes, masks, or edge-based detection.
- Local video cleanup with original audio preservation.
- Optional platform-link resolution through a separately installed
  `parse-video-py` service.
- Optional adapter for `D-Ogi/WatermarkRemover-AI`.
- Localhost-only aiohttp service for UI integration.

## Environment

Run commands from the repository root. The examples below use reusable
PowerShell variables:

```powershell
$repo = (Get-Location).Path
$python = "D:\conda_envs\comfyui\python.exe"
```

Set `CONDA_ENVS_ROOT`, `CONDA_ROOT`, and `FFMPEG_BIN_DIR` when your tools live
elsewhere.

## Local Image Cleanup

```powershell
& $python -m watermark_tools.cli image "$repo\input\sample.png" `
  --box 20,20,220,80 `
  --output "$repo\output\sample_clean.png"
```

Use `--smart --dilate 2` to limit changes to likely watermark strokes inside a
box, `--mask <path>` for a black-and-white mask, or `--auto` for edge-based
detection.

## Local Video Cleanup

```powershell
& $python -m watermark_tools.cli video "$repo\input\sample.mp4" `
  --box 20,20,220,80 `
  --smart `
  --output "$repo\output\sample_clean.mp4"
```

Add `--limit-frames 10` for a quick smoke test.

## Optional Platform-Link Resolver

```powershell
.\setup_parse_video_py.bat
.\start_parse_video_py.bat
$env:PARSE_VIDEO_BASE_URL = "http://127.0.0.1:8000"
& $python -m watermark_tools.cli link "https://..." --download
```

The setup helper installs `wujunwei928/parse-video-py` into an isolated Conda
environment. It is downloaded at setup time and is not included in this source
repository.

## Optional External AI Cleanup

```powershell
.\setup_watermark_ai.bat
& $python -m watermark_tools.cli image "$repo\input\sample.png" --engine external-ai
```

The optional setup helper downloads `D-Ogi/WatermarkRemover-AI` under
`external/`, which is intentionally ignored by Git. Its first run may download
additional model weights.

## Localhost API

```powershell
.\start_watermark_service.bat
```

Endpoints:

- `GET /health`
- `POST /api/watermark/link`
- `POST /api/watermark/image`
- `POST /api/watermark/video`
- `GET /api/jobs/{id}`

See [../docs/USAGE.zh-CN.md](../docs/USAGE.zh-CN.md) for a complete Chinese
guide and request examples.
