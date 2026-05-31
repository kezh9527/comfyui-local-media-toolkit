from __future__ import annotations

import json
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from aiohttp import web

from .link_resolver import download_resolved_assets, resolve_link
from .remover import parse_box, platform_cleanup_preset, remove_image_local, remove_video_local, remove_with_external_ai
from .utils import ensure_dir


ProgressCallback = Callable[[float, str], None]
MAX_JOBS = 100
JOB_TTL_SECONDS = 24 * 60 * 60


def _json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": message}, status=status)


def _parse_boxes(values) -> list[tuple[int, int, int, int]]:
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    return [parse_box(value) for value in values]


def _requires_ai(kind: str, data: dict[str, Any]) -> bool:
    if kind in {"image", "video"}:
        return data.get("engine") == "external-ai"
    if kind == "link":
        return bool(data.get("clean_platform_watermark")) and data.get("clean_engine") == "external-ai"
    return False


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._ai_executor = ThreadPoolExecutor(max_workers=1)

    def create(self, kind: str, runner: Callable[[ProgressCallback], dict[str, Any]], *, requires_ai: bool = False) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        now = time.time()
        job = {
            "id": job_id,
            "kind": kind,
            "requires_ai": requires_ai,
            "status": "queued",
            "progress": 0.0,
            "message": "Queued",
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._cleanup_locked(now)
            self._jobs[job_id] = job
        executor = self._ai_executor if requires_ai else self._executor
        executor.submit(self._run, job_id, runner)
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            self._cleanup_locked(time.time())
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError(job_id)
            return dict(job)

    def update(self, job_id: str, **values: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update(values)
            job["updated_at"] = time.time()

    def _cleanup_locked(self, now: float) -> None:
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.get("status") in {"completed", "failed"} and now - float(job.get("updated_at", now)) > JOB_TTL_SECONDS
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
        overflow = len(self._jobs) - MAX_JOBS
        if overflow <= 0:
            return
        removable = sorted(
            (
                (job.get("updated_at", job.get("created_at", now)), job_id)
                for job_id, job in self._jobs.items()
                if job.get("status") in {"completed", "failed"}
            ),
            key=lambda item: item[0],
        )
        for _, job_id in removable[:overflow]:
            self._jobs.pop(job_id, None)

    def _run(self, job_id: str, runner: Callable[[ProgressCallback], dict[str, Any]]) -> None:
        def progress(value: float, message: str) -> None:
            self.update(job_id, progress=max(0.0, min(100.0, float(value))), message=message)

        try:
            self.update(job_id, status="running", progress=1.0, message="Running")
            result = runner(progress)
            self.update(job_id, status="completed", progress=100.0, message="Done", result=result)
        except Exception as exc:
            self.update(job_id, status="failed", error=str(exc), message="Failed")


def _link_payload(result) -> dict[str, Any]:
    return {
        "ok": True,
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


def process_link_request(data: dict[str, Any], output_dir: Path, progress: ProgressCallback | None = None) -> dict[str, Any]:
    if progress:
        progress(3, "Resolving platform link")
    result = resolve_link(data["url"], data.get("parse_video_base_url"))
    if data.get("download", True):
        if progress:
            progress(15, "Downloading media")
        result = download_resolved_assets(result, output_dir / "link_downloads")
        if data.get("clean_platform_watermark"):
            cleanable = [asset for asset in result.assets if asset.path and asset.kind in {"video", "watermarked_video", "media"}]
            for index, asset in enumerate(cleanable, start=1):
                assert asset.path is not None
                clean_path = asset.path.with_name(f"{asset.path.stem}_clean.mp4")
                base = 30 + ((index - 1) / max(1, len(cleanable))) * 65
                span = 65 / max(1, len(cleanable))

                def child_progress(value: float, message: str, *, base: float = base, span: float = span) -> None:
                    if progress:
                        progress(base + value * span / 100, message)

                if data.get("clean_engine", "local") == "external-ai":
                    asset.clean_path = remove_with_external_ai(
                        asset.path,
                        clean_path,
                        detection_prompt=data.get("ai_detection_prompt", "watermark"),
                        max_bbox_percent=float(data.get("ai_max_bbox_percent", 10.0)),
                        detection_skip=int(data.get("ai_detection_skip", 3)),
                        fade_in=float(data.get("ai_fade_in", 0.5)),
                        fade_out=float(data.get("ai_fade_out", 0.5)),
                        force_format="MP4",
                        progress_callback=child_progress,
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
                        radius=int(data.get("clean_radius", preset["radius"])),
                        dilate=int(data.get("clean_dilate", preset["dilate"])),
                        limit_frames=int(data["clean_limit_frames"]) if data.get("clean_limit_frames") else None,
                        progress_callback=child_progress,
                    )
    if progress:
        progress(100, "Done")
    return _link_payload(result)


def process_image_request(data: dict[str, Any], output_dir: Path, progress: ProgressCallback | None = None) -> dict[str, Any]:
    input_path = Path(data["input"]).resolve()
    output_path = Path(data.get("output") or output_dir / f"{input_path.stem}_clean{input_path.suffix}")
    engine = data.get("engine", "local")
    if engine == "external-ai":
        result = remove_with_external_ai(
            input_path,
            output_path,
            detection_prompt=data.get("ai_detection_prompt", "watermark"),
            max_bbox_percent=float(data.get("ai_max_bbox_percent", 10.0)),
            force_format=output_path.suffix.lstrip(".").upper() if output_path.suffix else None,
            progress_callback=progress,
        )
    else:
        result = remove_image_local(
            input_path,
            output_path,
            mask_path=Path(data["mask"]).resolve() if data.get("mask") else None,
            boxes=_parse_boxes(data.get("box") or data.get("boxes")),
            auto=bool(data.get("auto")),
            smart=bool(data.get("smart")),
            radius=int(data.get("radius", 5)),
            dilate=int(data.get("dilate", 6)),
            progress_callback=progress,
        )
    return {"ok": True, "path": str(result)}


def process_video_request(data: dict[str, Any], output_dir: Path, progress: ProgressCallback | None = None) -> dict[str, Any]:
    input_path = Path(data["input"]).resolve()
    output_path = Path(data.get("output") or output_dir / f"{input_path.stem}_clean.mp4")
    engine = data.get("engine", "local")
    if engine == "external-ai":
        result = remove_with_external_ai(
            input_path,
            output_path,
            detection_prompt=data.get("ai_detection_prompt", "watermark"),
            max_bbox_percent=float(data.get("ai_max_bbox_percent", 10.0)),
            detection_skip=int(data.get("ai_detection_skip", 3)),
            fade_in=float(data.get("ai_fade_in", 0.5)),
            fade_out=float(data.get("ai_fade_out", 0.5)),
            force_format="MP4",
            progress_callback=progress,
        )
    else:
        result = remove_video_local(
            input_path,
            output_path,
            mask_path=Path(data["mask"]).resolve() if data.get("mask") else None,
            boxes=_parse_boxes(data.get("box") or data.get("boxes")),
            auto=bool(data.get("auto")),
            smart=bool(data.get("smart")),
            radius=int(data.get("radius", 5)),
            dilate=int(data.get("dilate", 6)),
            fps=float(data["fps"]) if data.get("fps") else None,
            limit_frames=int(data["limit_frames"]) if data.get("limit_frames") else None,
            progress_callback=progress,
        )
    return {"ok": True, "path": str(result)}


async def _save_upload(request: web.Request, field: str, target_dir: Path) -> Path | None:
    reader = await request.multipart()
    async for part in reader:
        if part.name != field:
            continue
        filename = part.filename or f"{field}.bin"
        target = target_dir / filename
        with target.open("wb") as handle:
            while True:
                chunk = await part.read_chunk()
                if not chunk:
                    break
                handle.write(chunk)
        return target
    return None


def create_app(output_dir: Path) -> web.Application:
    output_dir = ensure_dir(output_dir)
    app = web.Application(client_max_size=1024**3)
    app["jobs"] = JobStore()

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True, "service": "watermark_tools"})

    async def resolve_link_handler(request: web.Request) -> web.Response:
        try:
            data = await request.json()
            return web.json_response(process_link_request(data, output_dir), dumps=lambda value: json.dumps(value, ensure_ascii=False))
        except Exception as exc:
            return _json_error(str(exc), 500)

    async def image_handler(request: web.Request) -> web.Response:
        try:
            data = await request.json()
            return web.json_response(process_image_request(data, output_dir))
        except Exception as exc:
            return _json_error(str(exc), 500)

    async def image_upload_handler(request: web.Request) -> web.Response:
        run_dir = ensure_dir(output_dir / "uploads" / uuid.uuid4().hex)
        try:
            upload = await _save_upload(request, "file", run_dir)
            if upload is None:
                return _json_error("Missing multipart field: file")
            output = output_dir / f"{upload.stem}_clean{upload.suffix}"
            result = remove_image_local(upload, output, auto=True)
            return web.json_response({"ok": True, "path": str(result)})
        except Exception as exc:
            return _json_error(str(exc), 500)
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    async def video_handler(request: web.Request) -> web.Response:
        try:
            data = await request.json()
            return web.json_response(process_video_request(data, output_dir))
        except Exception as exc:
            return _json_error(str(exc), 500)

    async def create_job_handler(request: web.Request) -> web.Response:
        kind = request.match_info["kind"]
        if kind not in {"link", "image", "video"}:
            return _json_error(f"Unsupported job kind: {kind}", 404)
        try:
            data = await request.json()
            processors = {
                "link": process_link_request,
                "image": process_image_request,
                "video": process_video_request,
            }
            store: JobStore = request.app["jobs"]
            processor = processors[kind]
            job = store.create(
                f"watermark.{kind}",
                lambda progress: processor(data, output_dir, progress),
                requires_ai=_requires_ai(kind, data),
            )
            return web.json_response({"ok": True, "job": job})
        except Exception as exc:
            return _json_error(str(exc), 500)

    async def job_status_handler(request: web.Request) -> web.Response:
        try:
            store: JobStore = request.app["jobs"]
            return web.json_response({"ok": True, "job": store.get(request.match_info["job_id"])})
        except KeyError:
            return _json_error("Job not found", 404)

    app.router.add_get("/health", health)
    app.router.add_post("/api/watermark/link", resolve_link_handler)
    app.router.add_post("/api/watermark/image", image_handler)
    app.router.add_post("/api/watermark/image/upload", image_upload_handler)
    app.router.add_post("/api/watermark/video", video_handler)
    app.router.add_post("/api/jobs/watermark/{kind}", create_job_handler)
    app.router.add_get("/api/jobs/{job_id}", job_status_handler)
    return app


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


def run_server(host: str, port: int, output_dir: Path) -> None:
    app = create_app(output_dir)
    web.run_app(app, host=host, port=port)
