from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from .utils import clean_filename, ensure_dir


VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_DOWNLOAD_BYTES = int(os.environ.get("WATERMARK_MAX_DOWNLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))


def extension_from_response(url: str, response: requests.Response, fallback: str = ".mp4") -> str:
    path_ext = Path(unquote(urlparse(url).path)).suffix.lower()
    if path_ext in VIDEO_EXTS | IMAGE_EXTS:
        return path_ext

    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
    guessed = mimetypes.guess_extension(content_type) if content_type else None
    if guessed:
        if guessed == ".jpe":
            return ".jpg"
        return guessed
    return fallback


def download_url(url: str, output_dir: Path, filename: str | None = None, *, max_bytes: int = MAX_DOWNLOAD_BYTES) -> Path:
    ensure_dir(output_dir)
    host = urlparse(url).netloc.lower()
    referer = ""
    if "weibocdn.com" in host or "sinaimg.cn" in host:
        referer = "https://weibo.com/"
    elif "bilivideo.com" in host:
        referer = "https://www.bilibili.com/"
    elif "kwimgs.com" in host or "yximgs.com" in host:
        referer = "https://v.kuaishou.com/"
    elif "douyin" in host or "snssdk.com" in host or "zjcdn.com" in host:
        referer = "https://www.iesdouyin.com/"

    headers = {"User-Agent": "Mozilla/5.0"}
    if referer:
        headers["Referer"] = referer

    with requests.get(url, stream=True, timeout=60, headers=headers) as response:
        response.raise_for_status()
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > max_bytes:
            raise RuntimeError(f"Download is too large: {int(content_length)} bytes exceeds {max_bytes} bytes.")
        ext = extension_from_response(url, response)
        if filename:
            target_name = filename
            if not Path(target_name).suffix:
                target_name += ext
        else:
            url_name = Path(unquote(urlparse(url).path)).name
            target_name = clean_filename(url_name, "download")
            if not Path(target_name).suffix:
                target_name += ext

        target = output_dir / target_name
        index = 1
        while target.exists():
            target = output_dir / f"{Path(target_name).stem}_{index}{Path(target_name).suffix}"
            index += 1

        try:
            with target.open("wb") as handle:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        downloaded += len(chunk)
                        if downloaded > max_bytes:
                            raise RuntimeError(f"Download exceeded size limit: {downloaded} bytes exceeds {max_bytes} bytes.")
                        handle.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
    return target
