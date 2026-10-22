#!/usr/bin/env python3
"""Extract a grayscale depth video from a reference clip.

Primary: Depth Anything V2 Small via HuggingFace transformers.
Fallback (offline / download fail): OpenCV luminosity proxy labeled DEMO ONLY.

Near = white, far = black. No audio. Temporal median smooth.
"""
from __future__ import annotations

# --- auto-use bundled .venv (install.py may have created it) ---
import os as _os, sys as _sys
from pathlib import Path as _P
_VENV = _P(__file__).resolve().parent.parent / ".venv"
_VPY = _VENV / ("Scripts/python.exe" if _os.name == "nt" else "bin/python")
if _VPY.exists() and _P(_sys.prefix).resolve() != _VENV.resolve() and not _os.environ.get("RDB_NO_VENV_REEXEC"):
    _os.environ["RDB_NO_VENV_REEXEC"] = "1"
    _os.execv(str(_VPY), [str(_VPY), *_sys.argv])
# ---------------------------------------------------------------

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

MODEL_ID = "depth-anything/Depth-Anything-V2-Small-hf"
BACKEND_REAL = "depth-anything-v2-small"
BACKEND_DEMO = "demo-luminosity-proxy"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract depth video for remake reference")
    p.add_argument("--input", required=True, help="Source video path")
    p.add_argument("--output", required=True, help="Output depth mp4 path")
    p.add_argument("--start", type=float, default=None, help="Start seconds (inclusive)")
    p.add_argument("--end", type=float, default=None, help="End seconds (exclusive)")
    p.add_argument("--max-side", type=int, default=720, help="Max long-side pixels (0=keep)")
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "cuda", "mps"])
    p.add_argument(
        "--split-max",
        type=float,
        default=0,
        help="If >0, also emit segment files of at most this many seconds",
    )
    p.add_argument(
        "--force-demo",
        action="store_true",
        help="Skip model download; use DEMO luminosity proxy",
    )
    p.add_argument(
        "--require-real",
        action="store_true",
        help="Exit non-zero instead of falling back to DEMO proxy",
    )
    p.add_argument("--meta", default=None, help="Optional JSON sidecar path")
    return p.parse_args()


def resolve_device(name: str):
    import torch

    if name == "cpu":
        return torch.device("cpu")
    if name == "cuda":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if name == "mps":
        ok = getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
        return torch.device("mps" if ok else "cpu")
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def open_capture(path: str):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(f"Cannot open video: {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps, n = probe_timing(path, fps, n)
    return cap, fps, w, h, n


def probe_timing(path: str, cv_fps: float, cv_n: int):
    """Return (fps, nframes) robust to bad container avg_frame_rate.

    OpenCV reports avg_frame_rate, which some phone/app exports get wrong
    (e.g. 23.685 for a true 24 fps clip) → depth drifts vs original.
    Prefer ffprobe r_frame_rate when it agrees with frame count/duration.
    """
    import shutil, subprocess
    ff = shutil.which("ffprobe")
    if not ff:
        return cv_fps, cv_n
    try:
        out = subprocess.run(
            [ff, "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=r_frame_rate,nb_frames:format=duration", "-of", "json", path],
            capture_output=True, text=True, timeout=30,
        ).stdout
        j = json.loads(out)
        st = j["streams"][0]
        num, den = st["r_frame_rate"].split("/")
        r = float(num) / float(den)
        n = int(st.get("nb_frames") or cv_n or 0)
        dur = float(j["format"]["duration"])
        if r > 0 and 1 <= r <= 240:
            if n and dur and abs(n / r - dur) <= max(2.0 / r, 0.1):
                return r, n
            if n and dur:
                return n / dur, n
            return r, n
    except Exception:
        pass
    return cv_fps, cv_n


def target_size(w: int, h: int, max_side: int) -> tuple[int, int]:
    if not max_side or max(w, h) <= max_side:
        return w, h
    scale = max_side / float(max(w, h))
    return max(2, int(round(w * scale))), max(2, int(round(h * scale)))


def load_model(device, force_demo: bool):
    if force_demo:
        return None, None, BACKEND_DEMO, "forced --force-demo"
    try:
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        print(f"[depth] loading {MODEL_ID} on {device} …", flush=True)
        processor = AutoImageProcessor.from_pretrained(MODEL_ID)
        model = AutoModelForDepthEstimation.from_pretrained(MODEL_ID)
        model.eval().to(device)
        return processor, model, BACKEND_REAL, None
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(
            "[depth] WARNING: Depth Anything load failed — falling back to "
            f"DEMO luminosity proxy.\n         reason: {msg}\n"
            "         Re-run with network + `pip install -r requirements.txt` "
            "for real depth.",
            flush=True,
        )
        return None, None, BACKEND_DEMO, msg


def infer_real(processor, model, device, frame_bgr: np.ndarray) -> np.ndarray:
    import torch

    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    inputs = processor(images=rgb, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        pred = model(**inputs).predicted_depth
    h, w = frame_bgr.shape[:2]
    depth = torch.nn.functional.interpolate(
        pred[None], size=(h, w), mode="bicubic", align_corners=False
    )[0, 0]
    return depth.detach().float().cpu().numpy()


def infer_demo(frame_bgr: np.ndarray) -> np.ndarray:
    """DEMO ONLY: brightness-as-depth proxy (near≈bright). Not metric depth."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    # Invert a bit of center-weight so faces/foreground often read nearer
    h, w = gray.shape
    yy, xx = np.ogrid[:h, :w]
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    dist = np.sqrt(((yy - cy) / max(h, 1)) ** 2 + ((xx - cx) / max(w, 1)) ** 2)
    weight = 1.0 - 0.35 * np.clip(dist / 0.75, 0, 1)
    return gray * weight


def normalize_stack(stack: np.ndarray) -> np.ndarray:
    """Temporal median (k=3) then percentile stretch → uint8 near=white."""
    if len(stack) == 0:
        return stack.astype(np.uint8)
    stack = stack.astype(np.float32)
    smoothed = stack.copy()
    if len(stack) >= 3:
        for i in range(1, len(stack) - 1):
            smoothed[i] = np.median(stack[i - 1 : i + 2], axis=0)
    flat = smoothed.reshape(-1)
    if flat.size > 4_000_000:
        flat = flat[:: flat.size // 4_000_000 + 1]
    lo, hi = np.percentile(flat, 1), np.percentile(flat, 99)
    if hi <= lo:
        hi = lo + 1.0
    u8 = np.clip((smoothed - lo) / (hi - lo), 0, 1) * 255.0
    return u8.astype(np.uint8)


def write_video(frames_u8: list[np.ndarray], path: str, fps: float, tw: int, th: int):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Try mp4v then avc1
    for fourcc in ("mp4v", "avc1", "XVID"):
        writer = cv2.VideoWriter(
            path, cv2.VideoWriter_fourcc(*fourcc), fps, (tw, th), isColor=False
        )
        if writer.isOpened():
            break
        writer.release()
    else:
        raise SystemExit(f"Cannot open VideoWriter for {path}")
    for f in frames_u8:
        if f.shape[1] != tw or f.shape[0] != th:
            f = cv2.resize(f, (tw, th), interpolation=cv2.INTER_AREA)
        # stamp DEMO banner on first/last few frames if needed handled upstream
        writer.write(f)
    writer.release()


def stamp_demo(frame: np.ndarray) -> np.ndarray:
    out = frame.copy()
    cv2.putText(
        out,
        "DEMO ONLY — not Depth Anything",
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        255,
        2,
        cv2.LINE_AA,
    )
    return out


def extract(args) -> dict:
    cap, fps, w, h, n = open_capture(args.input)
    tw, th = target_size(w, h, args.max_side)
    start = 0.0 if args.start is None else max(0.0, args.start)
    end = None if args.end is None else max(start, args.end)

    if start > 0:
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)

    device = None
    processor = model = None
    backend = BACKEND_DEMO
    fail_reason = None
    if not args.force_demo:
        try:
            import torch  # noqa: F401

            device = resolve_device(args.device)
            processor, model, backend, fail_reason = load_model(device, False)
        except Exception as e:
            backend = BACKEND_DEMO
            fail_reason = f"{type(e).__name__}: {e}"
            print(f"[depth] torch unavailable → DEMO: {fail_reason}", flush=True)
    else:
        fail_reason = "forced --force-demo"

    if backend != BACKEND_REAL and getattr(args, "require_real", False):
        raise SystemExit(
            "[depth] FATAL: --require-real set but Depth Anything V2 unavailable: "
            f"{fail_reason}"
        )

    depths = []
    raw_frames = 0
    t = start
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = start + raw_frames / fps
        if end is not None and t >= end:
            break
        if (tw, th) != (w, h):
            frame = cv2.resize(frame, (tw, th), interpolation=cv2.INTER_AREA)
        if backend == BACKEND_REAL:
            d = infer_real(processor, model, device, frame)
        else:
            d = infer_demo(frame)
        depths.append(d.astype(np.float16))
        raw_frames += 1
        if raw_frames % 30 == 0:
            print(f"[depth] {raw_frames} frames @ t={t:.2f}s ({backend})", flush=True)
    cap.release()

    if not depths:
        raise SystemExit("No frames read — check --start/--end and input path")

    u8 = normalize_stack(np.stack(depths))
    frames = [u8[i] for i in range(len(u8))]
    if backend == BACKEND_DEMO:
        frames = [stamp_demo(f) for f in frames]

    write_video(frames, args.output, fps, tw, th)
    duration = len(frames) / fps
    meta = {
        "input": str(Path(args.input).resolve()),
        "output": str(Path(args.output).resolve()),
        "backend": backend,
        "demo_fallback_reason": fail_reason,
        "fps": fps,
        "frames": len(frames),
        "duration_sec": round(duration, 4),
        "size": [tw, th],
        "start": start,
        "end": end,
        "near": "white",
        "far": "black",
        "audio": False,
        "model_id": MODEL_ID if backend == BACKEND_REAL else None,
    }

    segments = []
    if args.split_max and args.split_max > 0 and duration > args.split_max:
        nseg = int(math.ceil(duration / args.split_max))
        out_p = Path(args.output)
        for i in range(nseg):
            a = int(round(i * args.split_max * fps))
            b = int(round(min(duration, (i + 1) * args.split_max) * fps))
            a = max(0, min(a, len(frames)))
            b = max(a, min(b, len(frames)))
            seg_path = str(out_p.with_name(f"{out_p.stem}_seg{i+1:02d}{out_p.suffix}"))
            write_video(frames[a:b], seg_path, fps, tw, th)
            segments.append(
                {
                    "path": seg_path,
                    "start_sec": round(a / fps, 3),
                    "end_sec": round(b / fps, 3),
                    "frames": b - a,
                }
            )
            print(f"[depth] segment → {seg_path}", flush=True)
        meta["segments"] = segments

    meta_path = args.meta or str(Path(args.output).with_suffix(".json"))
    Path(meta_path).write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "backend": backend, "output": args.output, "frames": len(frames)}, ensure_ascii=False))
    return meta


def main():
    args = parse_args()
    extract(args)


if __name__ == "__main__":
    main()
