import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib import request

import cv2
import numpy as np
from insightface.app import FaceAnalysis
from PIL import Image, ImageDraw, ImageFilter


COMFY_ROOT = Path(__file__).resolve().parent
INPUT_DIR = COMFY_ROOT / "input"
OUTPUT_DIR = COMFY_ROOT / "output"
WORK_DIR = COMFY_ROOT / "video_faceswap_runs"
SERVER = "http://127.0.0.1:8188"


def run(cmd):
    print(" ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def get_json(url):
    with request.urlopen(url, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ensure_comfy_running():
    try:
        get_json(f"{SERVER}/system_stats")
        return None
    except Exception:
        pass

    log = COMFY_ROOT / "video_faceswap_comfy.log"
    err = COMFY_ROOT / "video_faceswap_comfy.err.log"
    env = os.environ.copy()
    comfy_env = Path("D:/conda_envs/comfyui")
    env["PATH"] = str(comfy_env / "Library" / "cmd") + os.pathsep + str(comfy_env / "Library" / "bin") + os.pathsep + env.get("PATH", "")
    proc = subprocess.Popen(
        [sys.executable, "main.py", "--cpu", "--listen", "127.0.0.1", "--port", "8188"],
        cwd=COMFY_ROOT,
        stdout=log.open("w", encoding="utf-8"),
        stderr=err.open("w", encoding="utf-8"),
        env=env,
    )

    for _ in range(90):
        time.sleep(1)
        try:
            get_json(f"{SERVER}/system_stats")
            return proc
        except Exception:
            continue
    raise RuntimeError(f"ComfyUI did not start. Check {err}")


def resize_to_max(src, dst, max_side):
    img = Image.open(src).convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        nw = max(8, int(round(w * scale / 8) * 8))
        nh = max(8, int(round(h * scale / 8) * 8))
        img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    img.save(dst)


def build_detector():
    app = FaceAnalysis(name="antelopev2", root=str(COMFY_ROOT / "models" / "insightface"), providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))
    return app


def face_box(detector, image_path, previous=None):
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        return previous
    faces = detector.get(bgr)
    if not faces:
        return previous
    faces = sorted(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
    return faces[0].bbox.astype(float)


def make_head_mask(image_path, mask_path, detector, previous_box, expand=0.72, feather=22):
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    box = face_box(detector, image_path, previous_box)

    if box is None:
        cx, cy = w * 0.5, h * 0.28
        bw, bh = w * 0.28, h * 0.22
        box = np.array([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], dtype=float)

    x1, y1, x2, y2 = box
    bw = max(1.0, x2 - x1)
    bh = max(1.0, y2 - y1)
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2

    # More room above the detection box catches hair and the head contour,
    # while keeping the suit/background mostly untouched.
    mx = bw * expand
    top = bh * (expand + 0.55)
    bottom = bh * (expand * 0.55)
    left = max(0, cx - bw / 2 - mx)
    right = min(w, cx + bw / 2 + mx)
    upper = max(0, cy - bh / 2 - top)
    lower = min(h, cy + bh / 2 + bottom)

    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((left, upper, right, lower), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=feather))
    Image.merge("RGB", (mask, mask, mask)).save(mask_path)
    return box


def make_prompt(args, target_name, identity_name, mask_name, prefix, seed):
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": args.checkpoint}},
        "2": {"class_type": "InstantIDModelLoader", "inputs": {"instantid_file": "ip-adapter.bin"}},
        "3": {"class_type": "InstantIDFaceAnalysis", "inputs": {"provider": "CPU"}},
        "4": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "instantid_controlnet.safetensors"}},
        "5": {"class_type": "LoadImage", "inputs": {"image": identity_name}},
        "6": {"class_type": "LoadImage", "inputs": {"image": target_name}},
        "7": {"class_type": "LoadImageMask", "inputs": {"image": mask_name, "channel": "red"}},
        "8": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["1", 1],
                "text": "natural realistic mirror selfie, same body pose, same suit, same phone, same bathroom, same warm low light, seamless face and hair replacement, realistic skin texture",
            },
        },
        "9": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["1", 1],
                "text": "pasted face, face swap artifact, distorted eyes, warped mouth, waxy skin, over-smoothed, duplicate face, changed clothes, changed hand, changed phone, changed background, watermark, text",
            },
        },
        "10": {
            "class_type": "VAEEncodeForInpaint",
            "inputs": {"pixels": ["6", 0], "vae": ["1", 2], "mask": ["7", 0], "grow_mask_by": args.grow_mask_by},
        },
        "11": {
            "class_type": "ApplyInstantIDAdvanced",
            "inputs": {
                "instantid": ["2", 0],
                "insightface": ["3", 0],
                "control_net": ["4", 0],
                "image": ["5", 0],
                "model": ["1", 0],
                "positive": ["8", 0],
                "negative": ["9", 0],
                "ip_weight": args.ip_weight,
                "cn_strength": args.cn_strength,
                "start_at": 0.0,
                "end_at": 0.85,
                "noise": args.noise,
                "combine_embeds": "average",
                "image_kps": ["6", 0],
                "mask": ["7", 0],
            },
        },
        "12": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["11", 0],
                "positive": ["11", 1],
                "negative": ["11", 2],
                "latent_image": ["10", 0],
                "seed": seed,
                "steps": args.steps,
                "cfg": args.cfg,
                "sampler_name": args.sampler,
                "scheduler": args.scheduler,
                "denoise": args.denoise,
            },
        },
        "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["1", 2]}},
        "14": {"class_type": "SaveImage", "inputs": {"images": ["13", 0], "filename_prefix": prefix}},
    }


def queue_and_wait(prompt):
    client_id = str(uuid.uuid4())
    result = post_json(f"{SERVER}/prompt", {"prompt": prompt, "client_id": client_id})
    prompt_id = result["prompt_id"]

    while True:
        time.sleep(2)
        history = get_json(f"{SERVER}/history/{prompt_id}")
        if prompt_id in history:
            item = history[prompt_id]
            if item.get("status", {}).get("status_str") == "error":
                raise RuntimeError(json.dumps(item.get("status"), ensure_ascii=False, indent=2))
            outputs = item.get("outputs", {})
            images = outputs.get("14", {}).get("images", [])
            if not images:
                raise RuntimeError("ComfyUI finished without SaveImage output.")
            image = images[0]
            return OUTPUT_DIR / image.get("subfolder", "") / image["filename"]


def frame_count(path):
    return len(list(Path(path).glob("frame_*.png")))


def parse_args():
    parser = argparse.ArgumentParser(description="Frame-by-frame ComfyUI InstantID video face swap with original audio preserved.")
    parser.add_argument("--video", required=True, help="Target video path. The target pose/body/background are preserved.")
    parser.add_argument("--identity", required=True, help="Identity reference image path.")
    parser.add_argument("--out", default=str(COMFY_ROOT / "output" / "video_faceswap_result.mp4"))
    parser.add_argument("--fps", type=float, default=2.0, help="Processing FPS. Use 2 for CPU preview; use original FPS only on a fast GPU.")
    parser.add_argument("--max-side", type=int, default=640, help="Resize extracted frames so the longest side is at most this value.")
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--cfg", type=float, default=1.2)
    parser.add_argument("--denoise", type=float, default=0.56)
    parser.add_argument("--ip-weight", type=float, default=0.62)
    parser.add_argument("--cn-strength", type=float, default=0.78)
    parser.add_argument("--noise", type=float, default=0.35)
    parser.add_argument("--grow-mask-by", type=int, default=12)
    parser.add_argument("--mask-feather", type=int, default=22)
    parser.add_argument("--mask-expand", type=float, default=0.72)
    parser.add_argument("--sampler", default="euler")
    parser.add_argument("--scheduler", default="sgm_uniform")
    parser.add_argument("--checkpoint", default="sdxl_lightning_4step.safetensors")
    parser.add_argument("--limit-frames", type=int, default=0, help="Optional quick test limit.")
    parser.add_argument("--keep-work", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    video = Path(args.video).resolve()
    identity = Path(args.identity).resolve()
    out = Path(args.out).resolve()
    if not video.exists():
        raise FileNotFoundError(video)
    if not identity.exists():
        raise FileNotFoundError(identity)

    ensure_comfy_running()

    run_id = time.strftime("%Y%m%d_%H%M%S")
    run_dir = WORK_DIR / run_id
    raw_dir = run_dir / "raw_frames"
    resized_dir = run_dir / "resized_frames"
    mask_dir = run_dir / "masks"
    swapped_dir = run_dir / "swapped_frames"
    for d in [raw_dir, resized_dir, mask_dir, swapped_dir, INPUT_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg") or str(Path("D:/conda_envs/comfyui") / "Library" / "bin" / "ffmpeg.exe")
    extract_filter = f"fps={args.fps}"
    run([ffmpeg, "-y", "-i", video, "-vf", extract_filter, raw_dir / "frame_%06d.png"])

    raw_frames = sorted(raw_dir.glob("frame_*.png"))
    if args.limit_frames:
        raw_frames = raw_frames[: args.limit_frames]
    if not raw_frames:
        raise RuntimeError("No frames extracted.")

    identity_input = f"vfs_{run_id}_identity.png"
    resize_to_max(identity, INPUT_DIR / identity_input, args.max_side)

    detector = build_detector()
    previous_box = None

    for idx, raw in enumerate(raw_frames, start=1):
        target_local = resized_dir / raw.name
        mask_local = mask_dir / raw.name
        resize_to_max(raw, target_local, args.max_side)
        previous_box = make_head_mask(target_local, mask_local, detector, previous_box, args.mask_expand, args.mask_feather)

        target_input = f"vfs_{run_id}_target_{idx:06d}.png"
        mask_input = f"vfs_{run_id}_mask_{idx:06d}.png"
        shutil.copy2(target_local, INPUT_DIR / target_input)
        shutil.copy2(mask_local, INPUT_DIR / mask_input)

        prefix = f"video_faceswap/{run_id}/frame_{idx:06d}"
        seed = 123456789 + idx
        prompt = make_prompt(args, target_input, identity_input, mask_input, prefix, seed)

        print(f"[{idx}/{len(raw_frames)}] swapping {raw.name}", flush=True)
        generated = queue_and_wait(prompt)
        dest = swapped_dir / f"frame_{idx:06d}.png"
        shutil.copy2(generated, dest)

    out.parent.mkdir(parents=True, exist_ok=True)
    run([
        ffmpeg,
        "-y",
        "-framerate",
        str(args.fps),
        "-i",
        swapped_dir / "frame_%06d.png",
        "-i",
        video,
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        out,
    ])

    print(f"Done: {out}", flush=True)
    if not args.keep_work:
        print(f"Intermediate files kept for inspection: {run_dir}", flush=True)


if __name__ == "__main__":
    main()
