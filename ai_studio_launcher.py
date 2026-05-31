from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import cgi
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import psutil


HOST = "127.0.0.1"
CONSOLE_PORT = 8299
COMFY_PORT = 8188
PARSE_PORT = 8000
WATERMARK_PORT = 8198
CONDA_ROOT = Path(os.environ.get("CONDA_ROOT", "D:/Miniconda3"))
CONDA_ENVS_ROOT = Path(
    os.environ.get("CONDA_ENVS_ROOT")
    or os.environ.get("CONDA_ENVS_PATH", "D:/conda_envs").split(os.pathsep)[0]
)
COMFY_ENV = CONDA_ENVS_ROOT / "comfyui"
PARSE_ENV = CONDA_ENVS_ROOT / "parse-video"
WATERMARK_AI_ENV = CONDA_ENVS_ROOT / "watermark-ai"
COMFY_PROXY_PREFIX = "/comfy-ui"
DEFAULT_CONFIG: dict[str, Any] = {
    "gpu_enabled": False,
    "autostart_parse": False,
    "autostart_watermark": False,
    "activity_cache_seconds": 5,
    "workflow_cache_seconds": 10,
}


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        if base.name.lower() == "dist" and (base.parent / "main.py").exists():
            return base.parent
        return base
    return Path(__file__).resolve().parent


ROOT = app_root()
CONFIG_PATH = ROOT / "ai_studio_config.json"
LOG_DIR = ROOT / "launcher_logs"
PROCESSES: list[subprocess.Popen] = []
PROCESS_NAMES: dict[int, str] = {}
SERVER: ThreadingHTTPServer | None = None
SHUTDOWN_EVENT = threading.Event()
CACHE_LOCK = threading.Lock()
KNOWN_NODE_TYPES_CACHE: dict[str, Any] = {"expires": 0.0, "types": set(), "source": "unavailable"}
MODEL_INDEX_CACHE: dict[str, dict[str, Any]] = {}
WORKFLOWS_CACHE: dict[str, Any] = {"expires": 0.0, "signature": None, "payload": None}
RECENT_OUTPUT_CACHE: dict[str, Any] = {"expires": 0.0, "payload": None}


def is_port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.35)
        return sock.connect_ex((HOST, port)) == 0


def load_config() -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if isinstance(raw, dict):
                config.update(raw)
        except Exception as exc:
            log_launcher_error(f"Failed to read config: {exc}")
    return normalize_config(config)


def normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    for key in ("gpu_enabled", "autostart_parse", "autostart_watermark"):
        config[key] = bool(raw.get(key, DEFAULT_CONFIG[key]))
    for key in ("activity_cache_seconds", "workflow_cache_seconds"):
        try:
            config[key] = max(1, int(raw.get(key, DEFAULT_CONFIG[key])))
        except (TypeError, ValueError):
            config[key] = DEFAULT_CONFIG[key]
    return config


def save_config(values: dict[str, Any]) -> dict[str, Any]:
    config = normalize_config({**load_config(), **values})
    with CONFIG_PATH.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return config


def config_payload() -> dict[str, Any]:
    return {"ok": True, "path": str(CONFIG_PATH), "config": load_config()}


def workflow_cache_seconds() -> int:
    return int(load_config()["workflow_cache_seconds"])


def activity_cache_seconds() -> int:
    return int(load_config()["activity_cache_seconds"])


def env() -> dict[str, str]:
    value = os.environ.copy()
    ffmpeg_bin_dir = value.get("FFMPEG_BIN_DIR", "D:\\AI\\ffmpeg\\bin")
    path_parts = [
        str(COMFY_ENV / "Library" / "cmd"),
        str(COMFY_ENV / "Library" / "bin"),
        str(PARSE_ENV / "Library" / "bin"),
        str(WATERMARK_AI_ENV / "Library" / "bin"),
        ffmpeg_bin_dir,
        value.get("PATH", ""),
    ]
    value["PATH"] = ";".join(path_parts)
    value["PARSE_VIDEO_BASE_URL"] = f"http://{HOST}:{PARSE_PORT}"
    value["WATERMARK_REMOVER_AI_DIR"] = str(ROOT / "external" / "WatermarkRemover-AI")
    value["WATERMARK_REMOVER_AI_PYTHON"] = str(WATERMARK_AI_ENV / "python.exe")
    value.setdefault("PYTHONUTF8", "1")
    return value


def python_exe() -> Path:
    candidate = COMFY_ENV / "python.exe"
    if candidate.exists():
        return candidate
    return Path(sys.executable)


def start_process(name: str, command: list[str | Path], *, cwd: Path | None = None) -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stdout = (LOG_DIR / f"{name}.log").open("ab")
    stderr = (LOG_DIR / f"{name}.err.log").open("ab")
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(
        [str(item) for item in command],
        cwd=str(cwd or ROOT),
        env=env(),
        stdout=stdout,
        stderr=stderr,
        creationflags=creationflags,
    )
    PROCESSES.append(proc)
    PROCESS_NAMES[proc.pid] = name
    return proc


def comfy_command() -> list[str | Path]:
    command: list[str | Path] = [python_exe(), "main.py"]
    if not load_config()["gpu_enabled"]:
        command.append("--cpu")
    command.extend(["--listen", HOST, "--port", str(COMFY_PORT)])
    return command


def start_comfyui() -> subprocess.Popen:
    return start_process("comfyui", comfy_command())


def start_parse_service() -> subprocess.Popen | None:
    if not is_port_open(PARSE_PORT):
        parse_exe = PARSE_ENV / "Scripts" / "parse-video-py.exe"
        if parse_exe.exists():
            return start_process("parse-video-py", [parse_exe, "serve", "--port", str(PARSE_PORT)])
        log_launcher_error(f"parse-video-py executable not found: {parse_exe}")
        return None
    return None


def start_watermark_service() -> subprocess.Popen | None:
    if not is_port_open(WATERMARK_PORT):
        return start_process(
            "watermark-service",
            [
                python_exe(),
                "-m",
                "watermark_tools.cli",
                "service",
                "--host",
                HOST,
                "--port",
                str(WATERMARK_PORT),
                "--output-dir",
                str(ROOT / "output" / "watermark_service"),
            ],
        )
    return None


def wait_for_port(port: int, timeout: float = 12.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_port_open(port):
            return True
        time.sleep(0.35)
    return is_port_open(port)


def ensure_parse_service() -> bool:
    if is_port_open(PARSE_PORT):
        return True
    start_parse_service()
    return wait_for_port(PARSE_PORT)


def ensure_watermark_service() -> bool:
    if is_port_open(WATERMARK_PORT):
        return True
    start_watermark_service()
    return wait_for_port(WATERMARK_PORT)


def start_backends() -> None:
    config = load_config()
    if config["autostart_parse"]:
        start_parse_service()
    if config["autostart_watermark"]:
        start_watermark_service()

    if not is_port_open(COMFY_PORT):
        start_comfyui()


def service_control_payload(service: str, action: str) -> dict[str, Any]:
    services = {
        "parse": ("parse-video-py", PARSE_PORT, start_parse_service),
        "watermark": ("watermark-service", WATERMARK_PORT, start_watermark_service),
    }
    if service not in services:
        return {"ok": False, "error": f"Unknown service: {service}"}
    process_name, port, starter = services[service]
    if action == "start":
        starter()
        return {"ok": wait_for_port(port), "service": service, "listening": is_port_open(port)}
    if action == "stop":
        stopped = False
        for proc in list(PROCESSES):
            if PROCESS_NAMES.get(proc.pid) == process_name and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
                stopped = True
        return {
            "ok": stopped or not is_port_open(port),
            "service": service,
            "stopped": stopped,
            "listening": is_port_open(port),
        }
    return {"ok": False, "error": f"Unknown action: {action}"}


def stop_backends() -> None:
    for proc in list(PROCESSES):
        if proc.poll() is None:
            proc.terminate()
    deadline = time.time() + 8
    for proc in list(PROCESSES):
        if proc.poll() is None:
            remaining = max(0.1, deadline - time.time())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                proc.kill()


def launcher_process_name(pid: int) -> str | None:
    if pid == os.getpid():
        return "launcher"
    if pid in PROCESS_NAMES:
        return PROCESS_NAMES[pid]
    try:
        proc = psutil.Process(pid)
        for parent in proc.parents():
            if parent.pid == os.getpid():
                return "launcher"
            if parent.pid in PROCESS_NAMES:
                return PROCESS_NAMES[parent.pid]
    except Exception:
        return None
    return None


def pid_info(pid: int) -> dict[str, Any]:
    launcher_name = launcher_process_name(pid)
    try:
        proc = psutil.Process(pid)
        return {
            "pid": pid,
            "name": proc.name(),
            "path": proc.exe(),
            "launcher_started": launcher_name is not None,
            "launcher_name": launcher_name,
        }
    except Exception:
        return {"pid": pid, "name": None, "path": None, "launcher_started": launcher_name is not None}


def ports_payload() -> dict[str, Any]:
    ports = {CONSOLE_PORT, COMFY_PORT, PARSE_PORT, WATERMARK_PORT}
    found: dict[int, dict[str, Any]] = {}
    for conn in psutil.net_connections(kind="inet"):
        if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port in ports:
            info = pid_info(conn.pid or 0)
            info.update({"port": conn.laddr.port, "address": conn.laddr.ip})
            found[conn.laddr.port] = info
    return {"ok": True, "ports": [found.get(port, {"port": port, "listening": False}) for port in sorted(ports)]}


def restart_comfy_payload() -> dict[str, Any]:
    comfy_proc = next((proc for proc in PROCESSES if PROCESS_NAMES.get(proc.pid) == "comfyui" and proc.poll() is None), None)
    if comfy_proc is None:
        port_info = next((item for item in ports_payload()["ports"] if item.get("port") == COMFY_PORT), {})
        if port_info.get("pid"):
            return {"ok": False, "needs_confirmation": True, "error": "8188 is owned by an external process", "port": port_info}
    else:
        comfy_proc.terminate()
        try:
            comfy_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            comfy_proc.kill()
            comfy_proc.wait(timeout=5)

    deadline = time.time() + 12
    while is_port_open(COMFY_PORT) and time.time() < deadline:
        time.sleep(0.5)
    if not is_port_open(COMFY_PORT):
        start_comfyui()
    deadline = time.time() + 60
    while not is_port_open(COMFY_PORT) and time.time() < deadline:
        time.sleep(1)
    return {"ok": is_port_open(COMFY_PORT), "comfy": is_port_open(COMFY_PORT)}


def read_log_tail(path: Path, limit: int = 12000) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - limit))
        return handle.read().decode("utf-8", errors="replace")


def logs_payload() -> dict[str, Any]:
    names = ["launcher", "comfyui", "parse-video-py", "watermark-service"]
    logs = {}
    for name in names:
        err = LOG_DIR / f"{name}.err.log"
        out = LOG_DIR / f"{name}.log"
        logs[name] = {"stderr": read_log_tail(err), "stdout": read_log_tail(out, 6000)}
    return {"ok": True, "logs": logs}


def size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def cleanup_directory_contents(path: Path) -> dict[str, Any]:
    root = ROOT.resolve()
    target = path.resolve()
    target.relative_to(root)
    before = size_bytes(target)
    removed = 0
    if target.exists():
        for child in target.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except FileNotFoundError:
                    pass
            removed += 1
    target.mkdir(parents=True, exist_ok=True)
    return {"path": str(target), "removed_items": removed, "freed_bytes": before - size_bytes(target)}


def cleanup_old_logs(max_age_seconds: int = 7 * 24 * 60 * 60) -> dict[str, Any]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = time.time()
    freed = 0
    removed = 0
    for path in LOG_DIR.glob("*.log"):
        try:
            if now - path.stat().st_mtime <= max_age_seconds:
                continue
            size = path.stat().st_size
            path.unlink()
            freed += size
            removed += 1
        except FileNotFoundError:
            pass
    return {"path": str(LOG_DIR), "removed_items": removed, "freed_bytes": freed}


def cleanup_temp_payload() -> dict[str, Any]:
    targets = [
        ROOT / "temp",
        ROOT / "watermark_runs",
        ROOT / "output" / "watermark_service" / "uploads",
    ]
    cleaned = [cleanup_directory_contents(path) for path in targets]
    logs = cleanup_old_logs()
    warning_path = ROOT / "output" / "watermark_tests"
    return {
        "ok": True,
        "cleaned": cleaned,
        "logs": logs,
        "freed_bytes": sum(item["freed_bytes"] for item in cleaned) + logs["freed_bytes"],
        "output_warning": {
            "path": str(warning_path),
            "bytes": size_bytes(warning_path),
            "message": "watermark_tests is not deleted automatically.",
        },
    }


def restart_all_later() -> None:
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen([sys.executable, "--delayed-start"], cwd=str(ROOT), creationflags=creationflags)
    shutdown_server()


def kill_confirmed_port(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("confirm") is not True:
        return {"ok": False, "error": "Confirmation required"}
    port = int(payload.get("port", 0) or 0)
    pid = int(payload.get("pid", 0) or 0)
    match = next((item for item in ports_payload()["ports"] if item.get("port") == port and item.get("pid") == pid), None)
    if not match:
        return {"ok": False, "error": "Port/PID no longer matches"}
    if match.get("launcher_started"):
        return {"ok": False, "error": "Refusing to kill launcher-owned process through external cleanup"}
    psutil.Process(pid).terminate()
    return {"ok": True, "port": port, "pid": pid}


def log_launcher_error(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "launcher.err.log").open("a", encoding="utf-8") as handle:
        handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        handle.write(traceback.format_exc())
        handle.write("\n")


def http_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text or "{}")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"ok": False, "error": text}
        return exc.code, data
    except Exception as exc:
        return 502, {"ok": False, "error": str(exc)}


def proxy_to_comfy(handler: BaseHTTPRequestHandler) -> None:
    parsed = urllib.parse.urlsplit(handler.path)
    if not (parsed.path == COMFY_PROXY_PREFIX or parsed.path.startswith(COMFY_PROXY_PREFIX + "/")):
        handler.send_error(404)
        return

    upstream_path = parsed.path[len(COMFY_PROXY_PREFIX):] or "/"
    upstream_url = urllib.parse.urlunsplit(
        ("http", f"{HOST}:{COMFY_PORT}", upstream_path, parsed.query, "")
    )
    length = int(handler.headers.get("Content-Length", "0") or "0")
    body = handler.rfile.read(length) if length > 0 else None
    headers = {}
    for key in ("Content-Type", "Accept", "User-Agent"):
        value = handler.headers.get(key)
        if value:
            headers[key] = value
    request = urllib.request.Request(upstream_url, data=body, method=handler.command, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
            handler.send_response(response.status)
            skip_headers = {"connection", "content-length", "transfer-encoding", "content-encoding"}
            for key, value in response.headers.items():
                if key.lower() not in skip_headers:
                    handler.send_header(key, value)
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
    except urllib.error.HTTPError as exc:
        data = exc.read()
        handler.send_response(exc.code)
        content_type = exc.headers.get("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
    except Exception as exc:
        payload = json.dumps({"ok": False, "error": f"ComfyUI proxy failed: {exc}"}, ensure_ascii=False).encode("utf-8")
        handler.send_response(502)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)


WORKFLOW_META = {
    "instantid_inpaint_cpu_min.json": {
        "title": "InstantID 局部重绘",
        "description": "CPU 最小工作流，使用 identity.png、target_pose.png 和 head_mask.png 做身份参考与局部重绘。",
        "inputs": ["identity.png", "target_pose.png", "head_mask.png"],
    }
}

MODEL_WIDGETS = {
    "CheckpointLoaderSimple": {0: "checkpoints"},
    "ControlNetLoader": {0: "controlnet"},
    "InstantIDModelLoader": {0: "instantid"},
}

INPUT_NODE_TYPES = {"LoadImage", "LoadImageMask"}
FORM_WORKFLOW = "instantid_inpaint_cpu_min.json"

WIDGET_INPUTS = {
    "CheckpointLoaderSimple": ["ckpt_name"],
    "InstantIDModelLoader": ["instantid_file"],
    "InstantIDFaceAnalysis": ["provider"],
    "ControlNetLoader": ["control_net_name"],
    "LoadImage": ["image", None],
    "LoadImageMask": ["image", "channel"],
    "CLIPTextEncode": ["text"],
    "VAEEncodeForInpaint": ["grow_mask_by"],
    "ApplyInstantIDAdvanced": ["ip_weight", "cn_strength", "start_at", "end_at", "noise", "combine_embeds"],
    "KSampler": ["seed", None, "steps", "cfg", "sampler_name", "scheduler", "denoise"],
    "SaveImage": ["filename_prefix"],
}


def safe_child(base: Path, name: str) -> Path | None:
    try:
        path = (base / name).resolve()
        path.relative_to(base.resolve())
        return path
    except (OSError, ValueError):
        return None


def workflow_files() -> list[Path]:
    if not (ROOT / "workflows").exists():
        return []
    return sorted((ROOT / "workflows").glob("*.json"), key=lambda item: item.name.lower())


def read_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def known_node_types() -> tuple[set[str], str]:
    now = time.time()
    with CACHE_LOCK:
        if KNOWN_NODE_TYPES_CACHE["expires"] > now:
            return set(KNOWN_NODE_TYPES_CACHE["types"]), str(KNOWN_NODE_TYPES_CACHE["source"])
    status, payload = http_json(f"http://{HOST}:{COMFY_PORT}/object_info")
    if status == 200 and payload:
        result = set(payload)
        source = "live"
        with CACHE_LOCK:
            KNOWN_NODE_TYPES_CACHE.update({"expires": now + workflow_cache_seconds(), "types": result, "source": source})
        return result, source
    cache = ROOT / "object_info_cache.json"
    if cache.exists():
        try:
            result = set(read_json_file(cache))
            source = "cache"
            with CACHE_LOCK:
                KNOWN_NODE_TYPES_CACHE.update({"expires": now + workflow_cache_seconds(), "types": result, "source": source})
            return result, source
        except Exception:
            pass
    result: set[str] = set()
    source = "unavailable"
    with CACHE_LOCK:
        KNOWN_NODE_TYPES_CACHE.update({"expires": now + min(5, workflow_cache_seconds()), "types": result, "source": source})
    return result, source


def model_index(folder: str) -> set[str]:
    target = ROOT / "models" / folder
    if not target.exists():
        return set()
    now = time.time()
    key = str(target)
    with CACHE_LOCK:
        cached = MODEL_INDEX_CACHE.get(key)
        if cached and cached["expires"] > now:
            return set(cached["names"])
    names = {path.name for path in target.rglob("*") if path.is_file()}
    with CACHE_LOCK:
        MODEL_INDEX_CACHE[key] = {"expires": now + workflow_cache_seconds(), "names": names}
    return names


def model_exists(folder: str, name: str) -> bool:
    return name in model_index(folder)


def diagnose_workflow(path: Path) -> dict[str, Any]:
    data = read_json_file(path)
    nodes = data.get("nodes") or []
    known_nodes, node_source = known_node_types()
    node_types = sorted({str(node.get("type", "")) for node in nodes if isinstance(node, dict) and node.get("type")})
    missing_nodes = [node_type for node_type in node_types if known_nodes and node_type not in known_nodes]

    models: list[dict[str, Any]] = []
    inputs: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type", ""))
        values = node.get("widgets_values") or []
        if not isinstance(values, list):
            values = []
        for index, folder in MODEL_WIDGETS.get(node_type, {}).items():
            if index < len(values) and isinstance(values[index], str):
                name = values[index]
                models.append({"node": node_type, "folder": folder, "name": name, "ok": model_exists(folder, name)})
        if node_type in INPUT_NODE_TYPES and values and isinstance(values[0], str):
            name = values[0]
            inputs.append({"node": node_type, "name": name, "ok": (ROOT / "input" / name).exists()})

    missing_models = [item for item in models if not item["ok"]]
    missing_inputs = [item for item in inputs if not item["ok"]]
    return {
        "ok": not missing_nodes and not missing_models and not missing_inputs,
        "node_source": node_source,
        "node_count": len(nodes),
        "node_types": node_types,
        "missing_nodes": missing_nodes,
        "models": models,
        "missing_models": missing_models,
        "inputs": inputs,
        "missing_inputs": missing_inputs,
    }


def workflow_summary(path: Path, *, include_diagnostics: bool = True) -> dict[str, Any]:
    meta = WORKFLOW_META.get(path.name, {})
    result = {
        "file": path.name,
        "path": str(path),
        "title": meta.get("title") or path.stem.replace("_", " ").title(),
        "description": meta.get("description") or "ComfyUI workflow",
        "expected_inputs": meta.get("inputs", []),
        "updated_at": path.stat().st_mtime,
    }
    if include_diagnostics:
        result["diagnostics"] = diagnose_workflow(path)
    if path.name == FORM_WORKFLOW:
        result["form_defaults"] = workflow_form_defaults(path)
    return result


def workflow_signature(paths: list[Path]) -> tuple[tuple[str, float, int], ...]:
    signature = []
    for path in paths:
        try:
            stat = path.stat()
            signature.append((path.name, stat.st_mtime, stat.st_size))
        except OSError:
            signature.append((path.name, 0.0, 0))
    return tuple(signature)


def workflows_payload() -> dict[str, Any]:
    paths = workflow_files()
    signature = workflow_signature(paths)
    now = time.time()
    with CACHE_LOCK:
        if (
            WORKFLOWS_CACHE["payload"] is not None
            and WORKFLOWS_CACHE["signature"] == signature
            and WORKFLOWS_CACHE["expires"] > now
        ):
            return dict(WORKFLOWS_CACHE["payload"])
    payload = {"ok": True, "workflows": [workflow_summary(path) for path in paths]}
    with CACHE_LOCK:
        WORKFLOWS_CACHE.update({
            "expires": now + workflow_cache_seconds(),
            "signature": signature,
            "payload": payload,
        })
    return dict(payload)


def node_by_id(data: dict[str, Any], node_id: int) -> dict[str, Any]:
    for node in data.get("nodes") or []:
        if isinstance(node, dict) and node.get("id") == node_id:
            return node
    return {}


def widget_values(data: dict[str, Any], node_id: int) -> list[Any]:
    values = node_by_id(data, node_id).get("widgets_values") or []
    return values if isinstance(values, list) else []


def workflow_form_defaults(path: Path) -> dict[str, Any]:
    if path.name != FORM_WORKFLOW or not path.exists():
        return {}
    data = read_json_file(path)
    positive = widget_values(data, 8)
    negative = widget_values(data, 9)
    instantid = widget_values(data, 11)
    sampler = widget_values(data, 12)
    return {
        "positive_prompt": positive[0] if len(positive) > 0 else "",
        "negative_prompt": negative[0] if len(negative) > 0 else "",
        "steps": sampler[2] if len(sampler) > 2 else 4,
        "cfg": sampler[3] if len(sampler) > 3 else 1.2,
        "denoise": sampler[6] if len(sampler) > 6 else 0.58,
        "seed": sampler[0] if len(sampler) > 0 else 123456789,
        "ip_weight": instantid[0] if len(instantid) > 0 else 0.62,
        "cn_strength": instantid[1] if len(instantid) > 1 else 0.78,
    }


def coerce_form_value(values: dict[str, Any], key: str, default: Any, kind: type) -> Any:
    value = values.get(key, default)
    if value == "" or value is None:
        value = default
    try:
        return kind(value)
    except (TypeError, ValueError):
        return default


def apply_instantid_form(data: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    defaults = workflow_form_defaults(ROOT / "workflows" / FORM_WORKFLOW)
    positive = node_by_id(data, 8).setdefault("widgets_values", [""])
    negative = node_by_id(data, 9).setdefault("widgets_values", [""])
    instantid = node_by_id(data, 11).setdefault("widgets_values", [0.62, 0.78, 0, 0.85, 0.35, "average"])
    sampler = node_by_id(data, 12).setdefault("widgets_values", [123456789, "randomize", 4, 1.2, "euler", "sgm_uniform", 0.58])

    positive[0] = str(values.get("positive_prompt", defaults.get("positive_prompt", "")))
    negative[0] = str(values.get("negative_prompt", defaults.get("negative_prompt", "")))
    sampler[0] = coerce_form_value(values, "seed", defaults.get("seed", 123456789), int)
    sampler[1] = "fixed"
    sampler[2] = coerce_form_value(values, "steps", defaults.get("steps", 4), int)
    sampler[3] = coerce_form_value(values, "cfg", defaults.get("cfg", 1.2), float)
    sampler[6] = coerce_form_value(values, "denoise", defaults.get("denoise", 0.58), float)
    instantid[0] = coerce_form_value(values, "ip_weight", defaults.get("ip_weight", 0.62), float)
    instantid[1] = coerce_form_value(values, "cn_strength", defaults.get("cn_strength", 0.78), float)
    return data


def workflow_to_api_prompt(data: dict[str, Any]) -> dict[str, Any]:
    links = {}
    for link in data.get("links") or []:
        if isinstance(link, list) and len(link) >= 3:
            links[link[0]] = [str(link[1]), int(link[2])]

    prompt: dict[str, Any] = {}
    for node in data.get("nodes") or []:
        if not isinstance(node, dict) or "id" not in node or "type" not in node:
            continue
        node_id = str(node["id"])
        node_type = str(node["type"])
        inputs: dict[str, Any] = {}
        for item in node.get("inputs") or []:
            if not isinstance(item, dict):
                continue
            link_id = item.get("link")
            if link_id in links:
                inputs[str(item.get("name"))] = links[link_id]

        values = node.get("widgets_values") or []
        if not isinstance(values, list):
            values = []
        for index, input_name in enumerate(WIDGET_INPUTS.get(node_type, [])):
            if input_name and index < len(values):
                inputs[input_name] = values[index]

        prompt[node_id] = {"class_type": node_type, "inputs": inputs}
    return prompt


def submit_workflow_form(path: Path, values: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    diagnostics = diagnose_workflow(path)
    if diagnostics["missing_inputs"]:
        return 400, {"ok": False, "error": "Missing required inputs", "diagnostics": diagnostics}
    data = apply_instantid_form(read_json_file(path), values)
    api_prompt = workflow_to_api_prompt(data)
    payload = {
        "client_id": "comfyai-studio-launcher",
        "prompt": api_prompt,
        "extra_data": {"extra_pnginfo": {"workflow": data}},
    }
    status, response = http_json(f"http://{HOST}:{COMFY_PORT}/prompt", method="POST", payload=payload)
    response["ok"] = 200 <= status < 300
    response["status"] = status
    return status, response


def save_workflow_input(file_name: str, input_name: str, handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    workflow = safe_child(ROOT / "workflows", file_name)
    if not workflow or not workflow.exists() or workflow.suffix.lower() != ".json":
        return {"ok": False, "status": 404, "error": "Workflow not found"}
    expected = WORKFLOW_META.get(workflow.name, {}).get("inputs", [])
    if input_name not in expected:
        return {"ok": False, "status": 400, "error": "Input is not declared for this workflow"}
    if "/" in input_name or "\\" in input_name or safe_child(ROOT / "input", input_name) is None:
        return {"ok": False, "status": 400, "error": "Invalid input filename"}

    form = cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": handler.headers.get("Content-Type", ""),
        },
    )
    item = form["file"] if "file" in form else None
    if item is None or not getattr(item, "file", None):
        return {"ok": False, "status": 400, "error": "Missing uploaded file"}

    target = ROOT / "input" / input_name
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        shutil.copyfileobj(item.file, out)
    return {
        "ok": True,
        "status": 200,
        "file": input_name,
        "path": str(target),
        "size": target.stat().st_size,
        "diagnostics": diagnose_workflow(workflow),
    }


def comfy_summary_payload() -> dict[str, Any]:
    status_code, stats = http_json(f"http://{HOST}:{COMFY_PORT}/system_stats")
    _, queue = http_json(f"http://{HOST}:{COMFY_PORT}/queue")
    pending = queue.get("queue_pending") if isinstance(queue, dict) else []
    running = queue.get("queue_running") if isinstance(queue, dict) else []
    system = stats.get("system", {}) if status_code == 200 else {}
    devices = stats.get("devices", []) if status_code == 200 else []
    return {
        "ok": status_code == 200,
        "version": system.get("comfyui_version"),
        "python": system.get("python_version"),
        "device": devices[0].get("name") if devices and isinstance(devices[0], dict) else None,
        "queue_running": len(running or []),
        "queue_pending": len(pending or []),
    }


def recent_output_files(limit: int = 10) -> list[dict[str, Any]]:
    now = time.time()
    with CACHE_LOCK:
        cached = RECENT_OUTPUT_CACHE.get("payload")
        if cached is not None and RECENT_OUTPUT_CACHE["expires"] > now:
            return list(cached)[:limit]
    output_dir = ROOT / "output"
    if not output_dir.exists():
        return []
    files = [path for path in output_dir.rglob("*") if path.is_file()]
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    result = []
    for path in files[:limit]:
        stat = path.stat()
        result.append({
            "name": path.name,
            "relative": str(path.relative_to(output_dir)),
            "path": str(path),
            "size": stat.st_size,
            "modified": stat.st_mtime,
        })
    with CACHE_LOCK:
        RECENT_OUTPUT_CACHE.update({"expires": now + activity_cache_seconds(), "payload": result})
    return result


def comfy_activity_payload() -> dict[str, Any]:
    queue_status, queue = http_json(f"http://{HOST}:{COMFY_PORT}/queue")
    history_status, history = http_json(f"http://{HOST}:{COMFY_PORT}/history?max_items=10")
    running = queue.get("queue_running") if isinstance(queue, dict) else []
    pending = queue.get("queue_pending") if isinstance(queue, dict) else []
    history_items = []
    if isinstance(history, dict):
        for prompt_id, item in history.items():
            status = item.get("status", {}) if isinstance(item, dict) else {}
            messages = status.get("messages") if isinstance(status, dict) else []
            errors = []
            if isinstance(messages, list):
                for message in messages:
                    if isinstance(message, list) and message and message[0] in {"execution_error", "execution_interrupted"}:
                        errors.append(message[1] if len(message) > 1 else message[0])
            history_items.append({
                "prompt_id": prompt_id,
                "status": status.get("status_str") if isinstance(status, dict) else None,
                "completed": status.get("completed") if isinstance(status, dict) else None,
                "errors": errors,
            })
    return {
        "ok": queue_status == 200,
        "queue": queue if isinstance(queue, dict) else {},
        "queue_running": len(running or []),
        "queue_pending": len(pending or []),
        "history_ok": history_status == 200,
        "history": history_items[:10],
        "outputs": recent_output_files(10),
    }


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ComfyAI Studio</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f8;
      --panel: #ffffff;
      --line: #d9dee3;
      --text: #18202a;
      --muted: #647080;
      --accent: #16745f;
      --warn: #b76818;
      --danger: #b3261e;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
    }
    header {
      height: 64px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 28px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    h1 { font-size: 20px; margin: 0; font-weight: 650; }
    main { max-width: 1240px; margin: 0 auto; padding: 22px; display: grid; gap: 18px; }
    .status { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .tile, section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .tile { padding: 14px 16px; display: flex; justify-content: space-between; align-items: center; }
    .tile strong { display: block; font-size: 13px; color: var(--muted); font-weight: 600; }
    .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--danger); }
    .dot.ok { background: var(--accent); }
    section { padding: 18px; }
    section h2 { margin: 0 0 14px; font-size: 17px; }
    .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
    label { display: grid; gap: 6px; color: var(--muted); font-size: 13px; }
    input, textarea, select {
      width: 100%;
      min-height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      color: var(--text);
      background: #fff;
      font: inherit;
    }
    textarea { min-height: 82px; resize: vertical; }
    .row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .check { display: inline-flex; gap: 8px; align-items: center; color: var(--text); }
    .check input { width: 16px; height: 16px; min-height: 16px; }
    button {
      border: 1px solid #12614f;
      background: var(--accent);
      color: #fff;
      min-height: 36px;
      border-radius: 6px;
      padding: 0 14px;
      font-weight: 650;
      cursor: pointer;
    }
    button.secondary { background: #fff; color: var(--accent); }
    button.warn { background: var(--warn); border-color: var(--warn); }
    .progress-wrap { margin-top: 14px; display: grid; gap: 8px; }
    progress { width: 100%; height: 16px; accent-color: var(--accent); }
    pre {
      margin: 0;
      background: #101820;
      color: #d7e8df;
      border-radius: 6px;
      padding: 12px;
      min-height: 80px;
      overflow: auto;
      white-space: pre-wrap;
    }
    .tabs { display: flex; gap: 8px; flex-wrap: wrap; }
    .tab { background: #fff; color: var(--text); border-color: var(--line); }
    .tab.active { color: #fff; background: var(--accent); border-color: var(--accent); }
    .pane { display: none; }
    .pane.active { display: block; }
    .muted { color: var(--muted); }
    .workflow-list { display: grid; gap: 10px; }
    .workflow-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      display: grid;
      gap: 10px;
    }
    .workflow-head { display: flex; justify-content: space-between; gap: 10px; align-items: start; }
    .workflow-title { font-weight: 650; }
    .badge { border-radius: 999px; padding: 2px 8px; font-size: 12px; color: #fff; background: var(--accent); white-space: nowrap; }
    .badge.warn { background: var(--warn); }
    .diag { margin: 0; padding-left: 18px; color: var(--muted); }
    .input-list { display: grid; gap: 8px; }
    .input-row {
      display: grid;
      grid-template-columns: minmax(130px, 1fr) auto;
      gap: 8px;
      align-items: center;
      padding: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
    }
    .input-row input { max-width: 240px; padding: 5px; min-height: 32px; }
    .workflow-form { display: grid; gap: 10px; border-top: 1px solid var(--line); padding-top: 10px; }
    .form-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .form-grid .wide { grid-column: span 2; }
    @media (max-width: 820px) {
      header { padding: 0 16px; }
      main { padding: 14px; }
      .status, .grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>ComfyAI Studio</h1>
    <div class="row">
      <button class="secondary" onclick="openTarget('comfy')">打开节点图引擎</button>
      <button class="secondary" onclick="openTarget('output')">打开输出目录</button>
      <button class="warn" onclick="shutdown()">退出</button>
    </div>
  </header>
  <main>
    <div class="status">
      <div class="tile"><span><strong>ComfyUI 后端</strong><span id="comfyText">检测中</span></span><i id="comfyDot" class="dot"></i></div>
      <div class="tile"><span><strong>平台链接解析</strong><span id="parseText">检测中</span></span><i id="parseDot" class="dot"></i></div>
      <div class="tile"><span><strong>去水印服务</strong><span id="wmText">检测中</span></span><i id="wmDot" class="dot"></i></div>
    </div>

    <section>
      <h2>AI 内容生成</h2>
      <p class="muted">节点图生成继续使用 ComfyUI 原生工作流和队列，本启动器负责托管和打开后端。</p>
      <div class="row">
        <button onclick="openTarget('comfy')">进入 ComfyUI</button>
        <button class="secondary" onclick="openTarget('workflows')">打开 workflows</button>
        <button class="secondary" onclick="openTarget('input')">打开 input</button>
      </div>
    </section>

    <section>
      <h2>工作流</h2>
      <div id="workflowList" class="workflow-list"></div>
    </section>

    <section>
      <h2>生成任务</h2>
      <div class="row" style="margin-bottom:12px">
        <button class="secondary" onclick="loadActivity()">刷新任务</button>
        <button class="secondary" onclick="openTarget('output')">打开输出目录</button>
      </div>
      <div id="activityPanel" class="workflow-list"></div>
    </section>

    <section>
      <h2>服务控制</h2>
      <div class="row" style="margin-bottom:12px">
        <button class="secondary" onclick="loadServices()">刷新服务</button>
        <button onclick="restartComfy()">重启 ComfyUI</button>
        <button class="warn" onclick="restartAllServices()">重启全部服务</button>
        <button class="secondary" onclick="loadLogs()">查看最近日志</button>
      </div>
      <div class="workflow-card" style="margin-bottom:12px">
        <div class="workflow-title">Local config</div>
        <div class="row">
          <label class="check"><input id="cfgGpu" type="checkbox" />Enable GPU launch</label>
          <label class="check"><input id="cfgParse" type="checkbox" />Autostart parse-video</label>
          <label class="check"><input id="cfgWatermark" type="checkbox" />Autostart watermark</label>
          <label>Activity cache seconds<input id="cfgActivityCache" value="5" /></label>
          <label>Workflow cache seconds<input id="cfgWorkflowCache" value="10" /></label>
          <button class="secondary" onclick="saveConfig()">Save config</button>
        </div>
        <div id="configMessage" class="muted"></div>
      </div>
      <div id="servicesPanel" class="workflow-list"></div>
      <pre id="logsPanel" style="margin-top:12px; display:none"></pre>
    </section>

    <section>
      <h2>去水印</h2>
      <div class="tabs">
        <button class="tab active" onclick="showPane('link')">平台链接</button>
        <button class="tab" onclick="showPane('image')">图片</button>
        <button class="tab" onclick="showPane('video')">视频</button>
      </div>

      <div id="pane-link" class="pane active">
        <div class="grid">
          <label>平台链接或分享文本<textarea id="linkUrl" placeholder="粘贴抖音、快手、微博等分享文本或链接"></textarea></label>
          <label>清理方式<select id="linkEngine"><option value="local">快速模式 OpenCV</option><option value="external-ai">高质量模式 AI</option></select></label>
          <label>膨胀像素<input id="linkDilate" value="2" /></label>
          <label>修复半径<input id="linkRadius" value="3" /></label>
        </div>
        <div class="row" style="margin-top:12px">
          <label class="check"><input id="linkDownload" type="checkbox" checked />下载视频</label>
          <label class="check"><input id="linkClean" type="checkbox" checked />自动清理平台水印</label>
          <button onclick="submitLink()">开始处理</button>
        </div>
        <div id="linkProgress" class="progress-wrap"></div>
      </div>

      <div id="pane-image" class="pane">
        <div class="grid">
          <label>输入图片路径<input id="imageInput" placeholder="input\sample.png" /></label>
          <label>输出路径<input id="imageOutput" placeholder="留空自动输出到 output" /></label>
          <label>模式<select id="imageEngine"><option value="local">快速模式 OpenCV</option><option value="external-ai">高质量模式 AI 自动识别</option></select></label>
          <label>水印框 x,y,w,h<input id="imageBox" placeholder="例如 20,20,220,80；多个用分号分隔" /></label>
          <label>修复半径<input id="imageRadius" value="5" /></label>
          <label>膨胀像素<input id="imageDilate" value="6" /></label>
        </div>
        <div class="row" style="margin-top:12px">
          <label class="check"><input id="imageAuto" type="checkbox" />自动边缘检测</label>
          <label class="check"><input id="imageSmart" type="checkbox" checked />智能笔画 mask</label>
          <button onclick="submitImage()">开始处理</button>
        </div>
        <div id="imageProgress" class="progress-wrap"></div>
      </div>

      <div id="pane-video" class="pane">
        <div class="grid">
          <label>输入视频路径<input id="videoInput" placeholder="input\sample.mp4" /></label>
          <label>输出路径<input id="videoOutput" placeholder="留空自动输出到 output" /></label>
          <label>模式<select id="videoEngine"><option value="local">快速模式 OpenCV</option><option value="external-ai">高质量模式 AI 自动识别</option></select></label>
          <label>水印框 x,y,w,h<input id="videoBox" placeholder="例如 20,20,220,80；多个用分号分隔" /></label>
          <label>AI 检测间隔<input id="videoSkip" value="10" /></label>
          <label>调试帧数限制<input id="videoLimit" placeholder="留空处理完整视频" /></label>
        </div>
        <div class="row" style="margin-top:12px">
          <label class="check"><input id="videoAuto" type="checkbox" />自动边缘检测</label>
          <label class="check"><input id="videoSmart" type="checkbox" checked />智能笔画 mask</label>
          <button onclick="submitVideo()">开始处理</button>
        </div>
        <div id="videoProgress" class="progress-wrap"></div>
      </div>
    </section>
  </main>
  <script>
    const $ = id => document.getElementById(id);
    function boxes(value) { return value.split(';').map(s => s.trim()).filter(Boolean); }
    function esc(value) {
      return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }
    function showPane(name) {
      document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.pane').forEach(p => p.classList.remove('active'));
      event.target.classList.add('active');
      $('pane-' + name).classList.add('active');
    }
    async function status() {
      const r = await fetch('/api/status'); const s = await r.json();
      setStatus('comfy', s.comfy); setStatus('parse', s.parse); setStatus('wm', s.watermark);
    }
    function setStatus(prefix, ok) {
      $(prefix + 'Dot').className = 'dot' + (ok ? ' ok' : '');
      $(prefix + 'Text').textContent = ok ? '运行中' : '未就绪';
    }
    function workflowIssues(diag) {
      if (!diag) return ['诊断不可用'];
      const issues = [];
      if (diag.missing_nodes?.length) issues.push('缺少节点：' + diag.missing_nodes.join(', '));
      if (diag.missing_models?.length) issues.push('缺少模型：' + diag.missing_models.map(m => `${m.folder}/${m.name}`).join(', '));
      if (diag.missing_inputs?.length) issues.push('缺少输入：' + diag.missing_inputs.map(i => i.name).join(', '));
      return issues.length ? issues : ['节点、模型和输入文件已就绪'];
    }
    function workflowInputRows(w) {
      const expected = w.expected_inputs || [];
      if (!expected.length) return '';
      const known = new Map((w.diagnostics?.inputs || []).map(item => [item.name, item]));
      const rows = expected.map(name => {
        const ok = known.get(name)?.ok;
        return `<div class="input-row">
          <span><strong>${name}</strong><span class="muted"> · ${ok ? '已就绪' : '缺文件'}</span></span>
          <input type="file" accept="image/*" onchange="uploadWorkflowInput('${encodeURIComponent(w.file)}','${encodeURIComponent(name)}',this)" />
        </div>`;
      }).join('');
      return `<div class="input-list">${rows}</div>`;
    }
    function workflowForm(w) {
      if (w.file !== 'instantid_inpaint_cpu_min.json') return '';
      const d = w.form_defaults || {};
      return `<form class="workflow-form" data-workflow="${esc(w.file)}" onsubmit="submitWorkflowForm(event,this)">
        <div class="form-grid">
          <label class="wide">正向 prompt<textarea name="positive_prompt">${esc(d.positive_prompt)}</textarea></label>
          <label class="wide">负向 prompt<textarea name="negative_prompt">${esc(d.negative_prompt)}</textarea></label>
          <label>steps<input name="steps" type="number" min="1" step="1" value="${esc(d.steps)}" /></label>
          <label>cfg<input name="cfg" type="number" min="0" step="0.1" value="${esc(d.cfg)}" /></label>
          <label>denoise<input name="denoise" type="number" min="0" max="1" step="0.01" value="${esc(d.denoise)}" /></label>
          <label>seed<input name="seed" type="number" step="1" value="${esc(d.seed)}" /></label>
          <label>ip_weight<input name="ip_weight" type="number" min="0" step="0.01" value="${esc(d.ip_weight)}" /></label>
          <label>cn_strength<input name="cn_strength" type="number" min="0" step="0.01" value="${esc(d.cn_strength)}" /></label>
        </div>
        <div class="row"><button type="submit">提交生成任务</button><span class="muted form-result"></span></div>
      </form>`;
    }
    async function loadWorkflows() {
      const box = $('workflowList');
      if (!box) return;
      try {
        const r = await fetch('/api/workflows');
        const data = await r.json();
        if (!data.workflows?.length) {
          box.innerHTML = '<div class="muted">workflows 目录暂无 JSON 工作流。</div>';
          return;
        }
        box.innerHTML = data.workflows.map(w => {
          const diag = w.diagnostics;
          const ok = diag?.ok;
          const issues = workflowIssues(diag).map(item => `<li>${item}</li>`).join('');
          const inputs = workflowInputRows(w);
          const form = workflowForm(w);
          return `<div class="workflow-card">
            <div class="workflow-head">
              <div><div class="workflow-title">${w.title}</div><div class="muted">${w.description}</div></div>
              <span class="badge ${ok ? '' : 'warn'}">${ok ? '可用' : '需处理'}</span>
            </div>
            <ul class="diag">${issues}</ul>
            ${inputs}
            ${form}
            <div class="row">
              <button onclick="window.location.href='/comfy?workflow=${encodeURIComponent(w.file)}'">进入节点图</button>
              <button class="secondary" onclick="openWorkflow('${encodeURIComponent(w.file)}')">打开文件</button>
            </div>
          </div>`;
        }).join('');
      } catch (error) {
        box.innerHTML = '<div class="muted">工作流诊断读取失败。</div>';
      }
    }
    function renderActivity(data) {
      const history = (data.history || []).map(item => {
        const error = item.errors?.length ? ` · 错误：${esc(JSON.stringify(item.errors[0]).slice(0, 140))}` : '';
        return `<li>${esc(item.prompt_id)} · ${esc(item.status || 'unknown')}${error}</li>`;
      }).join('') || '<li>暂无历史</li>';
      const outputs = (data.outputs || []).map(item =>
        `<li>${esc(item.relative)} <button class="secondary" onclick="openOutputFile('${encodeURIComponent(item.relative)}')">打开</button></li>`
      ).join('') || '<li>暂无输出文件</li>';
      return `<div class="workflow-card">
        <div class="workflow-head">
          <div><div class="workflow-title">队列 ${data.queue_running || 0} 运行 / ${data.queue_pending || 0} 排队</div><div class="muted">最近历史和输出</div></div>
          <span class="badge ${data.ok ? '' : 'warn'}">${data.ok ? '已连接' : '未就绪'}</span>
        </div>
        <div class="grid">
          <div><strong>最近历史</strong><ul class="diag">${history}</ul></div>
          <div><strong>最近输出</strong><ul class="diag">${outputs}</ul></div>
        </div>
      </div>`;
    }
    async function loadActivity() {
      const box = $('activityPanel');
      if (!box) return;
      try {
        const data = await fetch('/api/comfy/activity').then(r => r.json());
        box.innerHTML = renderActivity(data);
      } catch (error) {
        box.innerHTML = '<div class="muted">任务状态读取失败。</div>';
      }
    }
    async function openTarget(target) {
      if (target === 'comfy') {
        window.location.href = '/comfy';
        return;
      }
      await fetch('/api/open?target=' + encodeURIComponent(target), {method:'POST'});
    }
    async function openWorkflow(file) {
      await fetch('/api/open?target=workflow&file=' + file, {method:'POST'});
    }
    async function openOutputFile(file) {
      await fetch('/api/open?target=output-file&file=' + file, {method:'POST'});
    }
    function renderServices(data) {
      const rows = (data.ports || []).map(item => {
        if (item.listening === false) return `<li>${item.port}: 未监听</li>`;
        const owner = item.launcher_started ? `launcher:${esc(item.launcher_name || '')}` : '外部进程';
        const warn = item.launcher_started ? '' : ' · 如需清理请先确认';
        return `<li>${item.port}: PID ${item.pid || '?'} · ${esc(item.name || '')} · ${owner}${warn}</li>`;
      }).join('');
      return `<div class="workflow-card">
        <div class="workflow-title">Service actions</div>
        <div class="row">
          <button class="secondary" onclick="serviceAction('start','parse')">Start parse-video</button>
          <button class="secondary" onclick="serviceAction('stop','parse')">Stop parse-video</button>
          <button class="secondary" onclick="serviceAction('start','watermark')">Start watermark</button>
          <button class="secondary" onclick="serviceAction('stop','watermark')">Stop watermark</button>
          <button class="warn" onclick="cleanupTemp()">Clean temp files</button>
        </div>
      </div>
      <div class="workflow-card"><div class="workflow-title">端口占用</div><ul class="diag">${rows}</ul></div>`;
    }
    async function loadConfig() {
      const data = await fetch('/api/config').then(r => r.json());
      const cfg = data.config || {};
      if ($('cfgGpu')) $('cfgGpu').checked = !!cfg.gpu_enabled;
      if ($('cfgParse')) $('cfgParse').checked = !!cfg.autostart_parse;
      if ($('cfgWatermark')) $('cfgWatermark').checked = !!cfg.autostart_watermark;
      if ($('cfgActivityCache')) $('cfgActivityCache').value = cfg.activity_cache_seconds ?? 5;
      if ($('cfgWorkflowCache')) $('cfgWorkflowCache').value = cfg.workflow_cache_seconds ?? 10;
      if ($('configMessage')) $('configMessage').textContent = 'Config: ' + (data.path || '');
    }
    async function saveConfig() {
      const payload = {
        gpu_enabled: $('cfgGpu').checked,
        autostart_parse: $('cfgParse').checked,
        autostart_watermark: $('cfgWatermark').checked,
        activity_cache_seconds: Number($('cfgActivityCache').value || 5),
        workflow_cache_seconds: Number($('cfgWorkflowCache').value || 10)
      };
      const data = await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}).then(r => r.json());
      if ($('configMessage')) $('configMessage').textContent = data.ok ? 'Config saved. Restart ComfyUI to apply GPU launch changes.' : (data.error || 'Config save failed');
      loadConfig();
    }
    async function serviceAction(action, service) {
      const box = $('servicesPanel');
      box.innerHTML = `<div class="muted">${action} ${service}...</div>`;
      await fetch('/api/services/' + action, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({service})
      });
      setTimeout(() => { status(); loadServices(); }, 800);
    }
    async function cleanupTemp() {
      const box = $('servicesPanel');
      box.innerHTML = '<div class="muted">Cleaning temp files...</div>';
      const data = await fetch('/api/services/cleanup-temp', {method:'POST'}).then(r => r.json());
      box.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
      setTimeout(loadServices, 2500);
    }
    async function loadServices() {
      const box = $('servicesPanel');
      if (!box) return;
      try {
        const data = await fetch('/api/services/ports').then(r => r.json());
        box.innerHTML = renderServices(data);
      } catch (error) {
        box.innerHTML = '<div class="muted">服务状态读取失败。</div>';
      }
    }
    async function restartComfy() {
      const box = $('servicesPanel');
      box.innerHTML = '<div class="muted">正在重启 ComfyUI...</div>';
      const data = await fetch('/api/services/restart-comfy', {method:'POST'}).then(r => r.json());
      if (data.needs_confirmation) {
        box.innerHTML = `<div class="workflow-card"><strong>8188 被外部进程占用</strong><pre>${esc(JSON.stringify(data.port, null, 2))}</pre></div>`;
      } else {
        box.innerHTML = `<div class="muted">${data.ok ? 'ComfyUI 已恢复' : 'ComfyUI 重启失败'}</div>`;
      }
      setTimeout(loadServices, 1000);
    }
    async function restartAllServices() {
      await fetch('/api/services/restart-all', {method:'POST'});
      $('servicesPanel').innerHTML = '<div class="muted">正在重启全部服务，稍后自动刷新。</div>';
      setTimeout(() => location.reload(), 9000);
    }
    async function loadLogs() {
      const panel = $('logsPanel');
      const data = await fetch('/api/services/logs').then(r => r.json());
      panel.style.display = 'block';
      panel.textContent = Object.entries(data.logs || {}).map(([name, item]) =>
        `## ${name}.err.log\n${item.stderr || '(empty)'}\n## ${name}.log\n${item.stdout || '(empty)'}`
      ).join('\n\n');
    }
    async function uploadWorkflowInput(workflowFile, inputName, picker) {
      if (!picker.files || !picker.files[0]) return;
      const data = new FormData();
      data.append('file', picker.files[0]);
      picker.disabled = true;
      try {
        const url = `/api/workflows/${workflowFile}/inputs/${inputName}`;
        const response = await fetch(url, {method:'POST', body:data});
        const result = await response.json();
        if (!result.ok) alert(result.error || '输入文件复制失败');
      } catch (error) {
        alert('输入文件复制失败：' + error.message);
      } finally {
        picker.value = '';
        picker.disabled = false;
        loadWorkflows();
      }
    }
    async function submitWorkflowForm(event, form) {
      event.preventDefault();
      const result = form.querySelector('.form-result');
      const button = form.querySelector('button[type="submit"]');
      const payload = Object.fromEntries(new FormData(form).entries());
      result.textContent = '提交中...';
      button.disabled = true;
      try {
        const file = encodeURIComponent(form.dataset.workflow);
        const response = await fetch(`/api/workflows/${file}/submit`, {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify(payload)
        });
        const data = await response.json();
        if (data.ok) {
          result.textContent = `已提交：${data.prompt_id || 'queued'}`;
        } else {
          result.textContent = data.error?.message || data.error || '提交失败';
          console.warn(data);
        }
      } catch (error) {
        result.textContent = '提交失败：' + error.message;
      } finally {
        button.disabled = false;
      }
    }
    async function shutdown() {
      await fetch('/api/shutdown', {method:'POST'});
      document.body.innerHTML = '<main><section><h2>已退出</h2></section></main>';
      setTimeout(() => window.close(), 300);
    }
    function renderProgress(id, job) {
      const progress = Math.round(job.progress || 0);
      $(id).innerHTML = `<progress max="100" value="${progress}"></progress><div>${progress}% - ${job.message || job.status}</div><pre>${JSON.stringify(job.result || job.error || job, null, 2)}</pre>`;
    }
    async function startJob(kind, payload, target) {
      $(target).innerHTML = '<progress max="100" value="1"></progress><div>提交任务中</div><pre></pre>';
      const r = await fetch('/api/watermark/' + kind, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
      const data = await r.json();
      if (!data.ok) { $(target).innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>'; return; }
      const id = data.job.id;
      const timer = setInterval(async () => {
        const jr = await fetch('/api/jobs/' + id); const jd = await jr.json();
        renderProgress(target, jd.job);
        if (['completed','failed'].includes(jd.job.status)) clearInterval(timer);
      }, 1000);
    }
    function submitLink() {
      startJob('link', {
        url: $('linkUrl').value,
        download: $('linkDownload').checked,
        clean_platform_watermark: $('linkClean').checked,
        clean_engine: $('linkEngine').value,
        clean_dilate: Number($('linkDilate').value || 2),
        clean_radius: Number($('linkRadius').value || 3),
        ai_detection_prompt: 'logo text watermark',
        ai_detection_skip: 10,
        ai_max_bbox_percent: 20
      }, 'linkProgress');
    }
    function submitImage() {
      const payload = {
        input: $('imageInput').value,
        engine: $('imageEngine').value,
        box: boxes($('imageBox').value),
        auto: $('imageAuto').checked,
        smart: $('imageSmart').checked,
        radius: Number($('imageRadius').value || 5),
        dilate: Number($('imageDilate').value || 6),
        ai_detection_prompt: 'logo text watermark',
        ai_max_bbox_percent: 20
      };
      if ($('imageOutput').value) payload.output = $('imageOutput').value;
      startJob('image', payload, 'imageProgress');
    }
    function submitVideo() {
      const payload = {
        input: $('videoInput').value,
        engine: $('videoEngine').value,
        box: boxes($('videoBox').value),
        auto: $('videoAuto').checked,
        smart: $('videoSmart').checked,
        ai_detection_prompt: 'logo text watermark',
        ai_detection_skip: Number($('videoSkip').value || 10),
        ai_max_bbox_percent: 20
      };
      if ($('videoOutput').value) payload.output = $('videoOutput').value;
      if ($('videoLimit').value) payload.limit_frames = Number($('videoLimit').value);
      startJob('video', payload, 'videoProgress');
    }
    status(); loadConfig(); loadWorkflows(); loadActivity(); loadServices(); setInterval(status, 3000); setInterval(loadActivity, 5000);
  </script>
</body>
</html>
"""


def comfy_shell_html() -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ComfyAI Studio - ComfyUI</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; }}
    body {{ font: 14px/1.4 "Segoe UI", "Microsoft YaHei", Arial, sans-serif; color: #18202a; background: #f6f7f8; }}
    .bar {{
      min-height: 52px;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 0 14px;
      border-bottom: 1px solid #d9dee3;
      background: #ffffff;
      flex-wrap: wrap;
    }}
    .title {{ font-weight: 650; }}
    .spacer {{ flex: 1 1 auto; }}
    .metric {{ color: #647080; font-size: 13px; white-space: nowrap; }}
    select {{
      min-height: 32px;
      border: 1px solid #d9dee3;
      border-radius: 6px;
      padding: 0 8px;
      color: #18202a;
      background: #ffffff;
      font: inherit;
      max-width: 260px;
    }}
    button {{
      min-height: 32px;
      border: 1px solid #12614f;
      border-radius: 6px;
      padding: 0 12px;
      color: #ffffff;
      background: #16745f;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
    }}
    button.secondary {{ color: #16745f; background: #ffffff; }}
    iframe {{ width: 100%; height: calc(100% - 52px); border: 0; display: block; background: #ffffff; }}
  </style>
</head>
<body>
  <div class="bar">
    <button onclick="window.location.href='/'">返回首页</button>
    <span class="title">ComfyUI 节点图引擎</span>
    <button class="secondary" onclick="document.getElementById('comfyFrame').contentWindow.location.reload()">刷新</button>
    <button class="secondary" onclick="fetch('/api/open?target=comfy', {{method:'POST'}})">外部打开</button>
    <span id="queueMetric" class="metric">队列读取中</span>
    <select id="workflowSelect" onchange="selectWorkflow()">
      <option value="">工作流</option>
    </select>
    <button class="secondary" onclick="openSelectedWorkflow()">打开文件</button>
    <button class="secondary" onclick="fetch('/api/open?target=input', {{method:'POST'}})">input</button>
    <button class="secondary" onclick="fetch('/api/open?target=output', {{method:'POST'}})">output</button>
  </div>
  <iframe id="comfyFrame" src="{COMFY_PROXY_PREFIX}/" title="ComfyUI"></iframe>
  <script>
    const params = new URLSearchParams(location.search);
    const selectedWorkflow = params.get('workflow') || '';
    let workflows = [];
    let workflowLoadStarted = false;
    async function refreshShell() {{
      try {{
        const summary = await fetch('/api/comfy/summary').then(r => r.json());
        document.getElementById('queueMetric').textContent =
          summary.ok ? `队列 ${{summary.queue_running || 0}} / ${{summary.queue_pending || 0}} · ${{summary.device || 'device'}}` : 'ComfyUI 未就绪';
      }} catch (error) {{
        document.getElementById('queueMetric').textContent = '队列读取失败';
      }}
    }}
    async function loadWorkflowSelect() {{
      try {{
        const data = await fetch('/api/workflows').then(r => r.json());
        workflows = data.workflows || [];
        const select = document.getElementById('workflowSelect');
        select.innerHTML = '<option value="">工作流</option>' + workflows.map(item =>
          `<option value="${{item.file}}">${{item.diagnostics?.ok ? '✓' : '!'}} ${{item.title}}</option>`
        ).join('');
        if (selectedWorkflow) select.value = selectedWorkflow;
      }} catch (error) {{}}
    }}
    function selectWorkflow() {{
      const file = document.getElementById('workflowSelect').value;
      if (file) history.replaceState(null, '', '/comfy?workflow=' + encodeURIComponent(file));
    }}
    async function openSelectedWorkflow() {{
      const file = document.getElementById('workflowSelect').value || selectedWorkflow;
      if (file) await fetch('/api/open?target=workflow&file=' + encodeURIComponent(file), {{method:'POST'}});
    }}
    function waitForComfyApp(frameWindow, timeoutMs = 30000) {{
      const started = Date.now();
      return new Promise((resolve, reject) => {{
        const timer = setInterval(() => {{
          const app = frameWindow.comfyAPI?.app?.app;
          const canvasReady = app?.canvas && app?.canvasEl?.width && app?.canvasEl?.height;
          if (app?.loadGraphData && app?.graph && canvasReady) {{
            clearInterval(timer);
            resolve(app);
            return;
          }}
          if (Date.now() - started > timeoutMs) {{
            clearInterval(timer);
            reject(new Error('ComfyUI frontend did not become ready'));
          }}
        }}, 250);
      }});
    }}
    async function loadSelectedWorkflowIntoFrame() {{
      if (!selectedWorkflow) return;
      if (workflowLoadStarted) return;
      workflowLoadStarted = true;
      const frame = document.getElementById('comfyFrame');
      try {{
        const workflow = await fetch('/api/workflows/' + encodeURIComponent(selectedWorkflow) + '/raw').then(r => {{
          if (!r.ok) throw new Error('workflow fetch failed');
          return r.json();
        }});
        const app = await waitForComfyApp(frame.contentWindow);
        await new Promise(resolve => setTimeout(resolve, 3000));
        await app.loadGraphData(workflow, true, false, null, {{
          skipAssetScans: true,
          deferWarnings: true,
          silentAssetErrors: true
        }});
        app.graph?.setDirtyCanvas?.(true, true);
        document.getElementById('queueMetric').textContent = '已加载 ' + selectedWorkflow;
      }} catch (error) {{
        document.getElementById('queueMetric').textContent = '工作流加载失败：' + error.message;
        workflowLoadStarted = false;
      }}
    }}
    document.getElementById('comfyFrame').addEventListener('load', loadSelectedWorkflowIntoFrame);
    setTimeout(loadSelectedWorkflowIntoFrame, 1000);
    refreshShell();
    loadWorkflowSelect();
    setInterval(refreshShell, 3000);
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "ComfyAIStudio/1.0"

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        if self.path == COMFY_PROXY_PREFIX or self.path.startswith(COMFY_PROXY_PREFIX + "/"):
            proxy_to_comfy(self)
            return
        if self.path == "/" or self.path.startswith("/?"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/comfy" or self.path.startswith("/comfy?"):
            self._send(200, comfy_shell_html().encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/api/status":
            self._json(200, {"ok": True, "comfy": is_port_open(COMFY_PORT), "parse": is_port_open(PARSE_PORT), "watermark": is_port_open(WATERMARK_PORT)})
            return
        if self.path == "/api/config":
            self._json(200, config_payload())
            return
        if self.path == "/api/workflows":
            self._json(200, workflows_payload())
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/workflows/") and parsed.path.endswith("/raw"):
            file_name = urllib.parse.unquote(parsed.path[len("/api/workflows/"):-len("/raw")]).strip("/")
            workflow = safe_child(ROOT / "workflows", file_name)
            if not workflow or not workflow.exists() or workflow.suffix.lower() != ".json":
                self._json(404, {"ok": False, "error": "Workflow not found"})
                return
            self._send(200, workflow.read_bytes(), "application/json; charset=utf-8")
            return
        if parsed.path.startswith("/api/workflows/") and parsed.path.endswith("/form"):
            file_name = urllib.parse.unquote(parsed.path[len("/api/workflows/"):-len("/form")]).strip("/")
            workflow = safe_child(ROOT / "workflows", file_name)
            if not workflow or not workflow.exists() or workflow.name != FORM_WORKFLOW:
                self._json(404, {"ok": False, "error": "Workflow form not found"})
                return
            self._json(200, {"ok": True, "file": workflow.name, "defaults": workflow_form_defaults(workflow)})
            return
        if self.path == "/api/comfy/summary":
            self._json(200, comfy_summary_payload())
            return
        if self.path == "/api/comfy/activity":
            self._json(200, comfy_activity_payload())
            return
        if self.path == "/api/services/ports":
            self._json(200, ports_payload())
            return
        if self.path == "/api/services/logs":
            self._json(200, logs_payload())
            return
        if self.path.startswith("/api/jobs/"):
            job_id = self.path.rsplit("/", 1)[-1]
            status, payload = http_json(f"http://{HOST}:{WATERMARK_PORT}/api/jobs/{job_id}")
            self._json(status, payload)
            return
        self._json(404, {"ok": False, "error": "Not found"})

    def do_POST(self) -> None:
        if self.path == COMFY_PROXY_PREFIX or self.path.startswith(COMFY_PROXY_PREFIX + "/"):
            proxy_to_comfy(self)
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/workflows/") and "/inputs/" in parsed.path:
            rest = parsed.path[len("/api/workflows/"):]
            workflow_part, input_part = rest.split("/inputs/", 1)
            payload = save_workflow_input(
                urllib.parse.unquote(workflow_part).strip("/"),
                urllib.parse.unquote(input_part).strip("/"),
                self,
            )
            status = int(payload.pop("status", 200))
            self._json(status, payload)
            return
        if parsed.path.startswith("/api/workflows/") and parsed.path.endswith("/submit"):
            file_name = urllib.parse.unquote(parsed.path[len("/api/workflows/"):-len("/submit")]).strip("/")
            workflow = safe_child(ROOT / "workflows", file_name)
            if not workflow or not workflow.exists() or workflow.name != FORM_WORKFLOW:
                self._json(404, {"ok": False, "error": "Workflow form not found"})
                return
            status, payload = submit_workflow_form(workflow, self._read_json())
            self._json(status, payload)
            return
        if self.path == "/api/config":
            try:
                self._json(200, {"ok": True, "path": str(CONFIG_PATH), "config": save_config(self._read_json())})
            except Exception as exc:
                self._json(500, {"ok": False, "error": str(exc)})
            return
        if self.path == "/api/services/restart-comfy":
            self._json(200, restart_comfy_payload())
            return
        if self.path == "/api/services/restart-all":
            self._json(200, {"ok": True, "restarting": True})
            threading.Thread(target=restart_all_later, daemon=True).start()
            return
        if self.path == "/api/services/kill-port":
            self._json(200, kill_confirmed_port(self._read_json()))
            return
        if self.path in {"/api/services/start", "/api/services/stop"}:
            action = self.path.rsplit("/", 1)[-1]
            service = str(self._read_json().get("service", ""))
            self._json(200, service_control_payload(service, action))
            return
        if self.path == "/api/services/cleanup-temp":
            try:
                self._json(200, cleanup_temp_payload())
            except Exception as exc:
                self._json(500, {"ok": False, "error": str(exc)})
            return
        if self.path.startswith("/api/watermark/"):
            kind = self.path.rsplit("/", 1)[-1]
            if kind == "link":
                ensure_parse_service()
            if not ensure_watermark_service():
                self._json(503, {"ok": False, "error": "watermark-service did not start"})
                return
            status, payload = http_json(
                f"http://{HOST}:{WATERMARK_PORT}/api/jobs/watermark/{kind}",
                method="POST",
                payload=self._read_json(),
            )
            self._json(status, payload)
            return
        if self.path.startswith("/api/open"):
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            target = query.get("target", ["comfy"])[0]
            folders = {
                "output": ROOT / "output",
                "input": ROOT / "input",
                "workflows": ROOT / "workflows",
            }
            if target == "workflow":
                file_name = query.get("file", [""])[0]
                workflow = safe_child(ROOT / "workflows", file_name)
                if workflow and workflow.exists() and os.name == "nt":
                    subprocess.Popen(["explorer", "/select,", str(workflow)])
                elif workflow and workflow.exists():
                    webbrowser.open(str(workflow.parent))
            elif target == "output-file":
                file_name = query.get("file", [""])[0]
                output_file = safe_child(ROOT / "output", file_name)
                if output_file and output_file.exists() and output_file.is_file() and os.name == "nt":
                    subprocess.Popen(["explorer", "/select,", str(output_file)])
                elif output_file and output_file.exists() and output_file.is_file():
                    webbrowser.open(str(output_file))
            elif target in folders:
                folder = folders[target]
                folder.mkdir(parents=True, exist_ok=True)
                if os.name == "nt":
                    os.startfile(str(folder))  # type: ignore[attr-defined]
                else:
                    webbrowser.open(str(folder))
            else:
                webbrowser.open(f"http://{HOST}:{COMFY_PORT}")
            self._json(200, {"ok": True})
            return
        if self.path == "/api/shutdown":
            self._json(200, {"ok": True})
            threading.Thread(target=shutdown_server, daemon=True).start()
            return
        self._json(404, {"ok": False, "error": "Not found"})

    def log_message(self, format: str, *args: Any) -> None:
        return


def shutdown_server() -> None:
    time.sleep(0.3)
    stop_backends()
    if SERVER:
        SERVER.shutdown()
        SERVER.server_close()
    SHUTDOWN_EVENT.set()


def serve_console() -> None:
    if SERVER:
        SERVER.serve_forever()


def run_webview(url: str) -> None:
    import webview

    webview.create_window(
        "ComfyAI Studio",
        url,
        width=1240,
        height=860,
        min_size=(920, 640),
        text_select=True,
    )
    webview.start(debug=False)


def run_browser_fallback(url: str) -> None:
    webbrowser.open(url)
    SHUTDOWN_EVENT.wait()


def main() -> None:
    global SERVER
    if "--delayed-start" in sys.argv:
        time.sleep(4)
    start_backends()
    SERVER = ThreadingHTTPServer((HOST, CONSOLE_PORT), Handler)
    url = f"http://{HOST}:{CONSOLE_PORT}"

    try:
        if "--browser" in sys.argv:
            webbrowser.open(url)
            SERVER.serve_forever()
            return

        server_thread = threading.Thread(target=serve_console, daemon=True)
        server_thread.start()
        try:
            run_webview(url)
        except Exception:
            log_launcher_error("WebView startup failed; falling back to the default browser.")
            run_browser_fallback(url)
    finally:
        SHUTDOWN_EVENT.set()
        if SERVER:
            try:
                SERVER.shutdown()
                SERVER.server_close()
            except Exception:
                pass
        stop_backends()


if __name__ == "__main__":
    main()
