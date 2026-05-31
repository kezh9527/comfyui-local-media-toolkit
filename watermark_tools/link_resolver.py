from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import requests

from .config import OUTPUT_DIR, PARSE_VIDEO_BASE_URL, PARSE_VIDEO_PY_SRC
from .downloader import download_url
from .utils import clean_filename, ensure_dir


@dataclass
class LinkAsset:
    kind: str
    url: str
    path: Path | None = None
    clean_path: Path | None = None


@dataclass
class LinkResolveResult:
    platform: str
    title: str
    raw: dict[str, Any] = field(default_factory=dict)
    assets: list[LinkAsset] = field(default_factory=list)


PLATFORM_PATTERNS = {
    "douyin": ("douyin.com", "iesdouyin.com", "amemv.com"),
    "kuaishou": ("kuaishou.com", "gifshow.com", "chenzhongtech.com"),
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
    "bilibili": ("bilibili.com", "b23.tv"),
    "weibo": ("weibo.com", "weibo.cn"),
    "pipix": ("pipix.com", "pipixia.com"),
    "tiktok": ("tiktok.com", "vm.tiktok.com"),
    "youtube": ("youtube.com", "youtu.be"),
    "acfun": ("acfun.cn",),
}

URL_RE = re.compile(r"https?://[^\s，。]+")


def detect_platform(url: str) -> str:
    url = extract_first_url(url)
    host = urlparse(url).netloc.lower()
    for platform, needles in PLATFORM_PATTERNS.items():
        if any(needle in host for needle in needles):
            return platform
    return "direct" if urlparse(url).scheme in {"http", "https"} else "unknown"


def extract_first_url(value: str) -> str:
    match = URL_RE.search(value)
    if match:
        return match.group(0).rstrip(".,;，。；")
    return value.strip()


def _first_string(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _collect_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            urls.append(value)
    elif isinstance(value, list):
        for item in value:
            urls.extend(_collect_urls(item))
    elif isinstance(value, dict):
        for item in value.values():
            urls.extend(_collect_urls(item))
    return urls


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(item) for item in value]
    if hasattr(value, "__dict__"):
        return _plain(vars(value))
    return value


def _run_async(coro_factory):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())

    box: dict[str, Any] = {}

    def target() -> None:
        try:
            box["value"] = asyncio.run(coro_factory())
        except BaseException as exc:
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _unwrap_parse_video_response(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload
    for key in ("data", "result", "item"):
        nested = data.get(key)
        if isinstance(nested, dict):
            data = nested
    return data


def _result_from_payload(url: str, payload: dict[str, Any]) -> LinkResolveResult:
    data = _unwrap_parse_video_response(payload)

    title = _first_string(data, ("title", "desc", "description", "nickname")) or detect_platform(url)
    platform = _first_string(data, ("platform", "source")) or detect_platform(url)
    result = LinkResolveResult(platform=platform, title=title, raw=payload)

    video_url = _first_string(
        data,
        ("video_url", "videoUrl", "play_addr", "playAddr", "download_url", "downloadUrl", "url"),
    )
    if video_url:
        result.assets.append(LinkAsset(kind="video", url=video_url))

    for key in ("images", "image_urls", "imageUrls", "pics", "pic_urls"):
        for image_url in _collect_urls(data.get(key)):
            result.assets.append(LinkAsset(kind="image", url=image_url))

    for live_url in _collect_urls(data.get("image_live_photos")):
        result.assets.append(LinkAsset(kind="live_photo", url=live_url))

    music_url = _first_string(data, ("music_url", "musicUrl", "audio_url", "audioUrl"))
    if music_url:
        result.assets.append(LinkAsset(kind="audio", url=music_url))

    if not result.assets:
        for candidate in _collect_urls(data):
            kind = "image" if any(ext in candidate.lower() for ext in (".jpg", ".jpeg", ".png", ".webp")) else "video"
            result.assets.append(LinkAsset(kind=kind, url=candidate))

    return result


def resolve_with_parse_video_py(url: str) -> LinkResolveResult:
    if PARSE_VIDEO_PY_SRC:
        src = str(PARSE_VIDEO_PY_SRC)
        if src not in sys.path:
            sys.path.insert(0, src)

    try:
        from parse_video_py import parse_video_share_url
    except Exception as exc:
        raise RuntimeError(
            "parse-video-py is not importable. Install it in this environment, set PARSE_VIDEO_PY_SRC, "
            "or start an HTTP resolver and set PARSE_VIDEO_BASE_URL."
        ) from exc

    payload = _plain(_run_async(lambda: parse_video_share_url(url)))
    if not isinstance(payload, dict):
        raise RuntimeError(f"parse-video-py returned unsupported data: {type(payload).__name__}")
    return _result_from_payload(url, payload)


def resolve_with_parse_video(url: str, base_url: str | None = None) -> LinkResolveResult:
    base = (base_url or PARSE_VIDEO_BASE_URL).strip().rstrip("/")
    if not base:
        raise RuntimeError(
            "PARSE_VIDEO_BASE_URL is not configured. Start parse-video and set this env var."
        )

    endpoint = f"{base}/video/share/url/parse?url={quote(url, safe='')}"
    response = requests.get(endpoint, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    payload = response.json()
    return _result_from_payload(url, payload)


def resolve_douyin_web(url: str) -> LinkResolveResult:
    clean_input_url = extract_first_url(url)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Mobile/15E148 aweme_26.0.0"
        ),
        "Referer": "https://www.iesdouyin.com/",
    }
    first = requests.get(clean_input_url, timeout=30, headers=headers, allow_redirects=False)
    page_url = first.headers.get("location", clean_input_url)
    page = requests.get(page_url, timeout=30, headers=headers)
    page.raise_for_status()
    text = page.text

    video_id = ""
    id_match = re.search(r"/video/(\d+)", page_url) or re.search(r'"aweme_id":"(\d+)"', text)
    if id_match:
        video_id = id_match.group(1)

    desc = "douyin"
    desc_match = re.search(r'"desc":"(.*?)"', text)
    if desc_match:
        try:
            desc = json.loads(f'"{desc_match.group(1)}"')
        except json.JSONDecodeError:
            desc = desc_match.group(1)

    playwm_match = re.search(
        r"https:\\u002F\\u002Faweme\.snssdk\.com\\u002Faweme\\u002Fv1\\u002Fplaywm\\u002F\?video_id=[^\"\\]+",
        text,
    )
    if not playwm_match:
        raise RuntimeError("Douyin fallback could not find playwm URL in page HTML.")

    watermarked_url = playwm_match.group(0).replace("\\u002F", "/")
    no_watermark_url = watermarked_url.replace("/playwm/", "/play/")

    result = LinkResolveResult(platform="douyin", title=desc or video_id or "douyin", raw={"page_url": page_url})
    result.assets.append(LinkAsset(kind="video", url=no_watermark_url))
    result.assets.append(LinkAsset(kind="watermarked_video", url=watermarked_url))
    return result


def resolve_direct_url(url: str) -> LinkResolveResult:
    url = extract_first_url(url)
    return LinkResolveResult(
        platform=detect_platform(url),
        title=Path(urlparse(url).path).stem or "direct",
        assets=[LinkAsset(kind="media", url=url)],
    )


def resolve_link(url: str, base_url: str | None = None) -> LinkResolveResult:
    url = extract_first_url(url)
    platform = detect_platform(url)
    if platform == "direct" and Path(urlparse(url).path).suffix.lower() in {
        ".mp4",
        ".mov",
        ".mkv",
        ".avi",
        ".webm",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        }:
        return resolve_direct_url(url)
    if base_url or PARSE_VIDEO_BASE_URL:
        try:
            result = resolve_with_parse_video(url, base_url)
            if result.assets:
                return result
        except Exception:
            if platform != "douyin":
                raise
        if platform == "douyin":
            return resolve_douyin_web(url)
        return result
    try:
        result = resolve_with_parse_video_py(url)
        if result.assets:
            return result
    except Exception:
        if platform != "douyin":
            raise
    if platform == "douyin":
        return resolve_douyin_web(url)
    return result


def download_resolved_assets(result: LinkResolveResult, output_dir: Path | None = None) -> LinkResolveResult:
    base = ensure_dir(output_dir or OUTPUT_DIR / "link_downloads")
    stem = clean_filename(result.title, result.platform)
    counters: dict[str, int] = {}

    for asset in result.assets:
        counters[asset.kind] = counters.get(asset.kind, 0) + 1
        suffix = "" if counters[asset.kind] == 1 else f"_{counters[asset.kind]}"
        asset.path = download_url(asset.url, base, f"{stem}_{asset.kind}{suffix}")

    return result
