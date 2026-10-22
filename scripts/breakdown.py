#!/usr/bin/env python3
"""Scene detect + per-second timeline skeleton + contact sheet PNGs.

Descriptions are LEFT EMPTY for a vision-capable agent to fill.
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
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--outdir", required=True, help="Output folder (writes timeline.csv, breakdown.md, sheets/)")
    p.add_argument("--start", type=float, default=None)
    p.add_argument("--end", type=float, default=None)
    p.add_argument("--cols", type=int, default=4, help="Contact sheet columns")
    p.add_argument("--thumb-w", type=int, default=320)
    return p.parse_args()


def detect_scenes(path: str, start: float | None, end: float | None):
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector

        video = open_video(path)
        sm = SceneManager()
        sm.add_detector(ContentDetector(threshold=27.0))
        sm.detect_scenes(video)
        scenes = sm.get_scene_list()
        cuts = []
        for a, b in scenes:
            t0 = a.get_seconds()
            t1 = b.get_seconds()
            if start is not None and t1 <= start:
                continue
            if end is not None and t0 >= end:
                continue
            cuts.append((max(t0, start or 0.0), min(t1, end) if end is not None else t1))
        return cuts
    except Exception as e:
        print(f"[breakdown] scenedetect unavailable ({e}); using 1s pseudo-cuts")
        return []


def change_candidates(path: str, fps: float, top: int = 12, min_gap: float = 0.4):
    """Soft transitions (wipes, occlusion, outfit swaps) that ContentDetector misses.

    Per-frame mean abs diff on 64px gray thumbnails; returns peak times (s)
    above mean+2*std. Candidates only — a vision model must confirm.
    """
    cap = cv2.VideoCapture(path)
    prev = None
    diffs = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.resize(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), (36, 64)).astype(np.float32)
        diffs.append(0.0 if prev is None else float(np.abs(g - prev).mean()))
        prev = g
    cap.release()
    if len(diffs) < 3:
        return []
    d = np.array(diffs)
    thr = d.mean() + 2 * d.std()
    idx = [i for i in np.argsort(-d) if d[i] > thr]
    picked = []
    for i in idx:
        t = i / fps
        if all(abs(t - p) >= min_gap for p in picked):
            picked.append(t)
        if len(picked) >= top:
            break
    return sorted(round(t, 2) for t in picked)


def video_meta(path: str):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise SystemExit(f"Cannot open {path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 25.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from extract_depth import probe_timing
        fps, n = probe_timing(path, fps, n)
    except Exception:
        pass
    dur = n / fps if n else 0.0
    return fps, n, w, h, dur


def grab_frame(path: str, t: float):
    cap = cv2.VideoCapture(path)
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def make_sheets(path: str, times: list[float], outdir: Path, cols: int, thumb_w: int):
    outdir.mkdir(parents=True, exist_ok=True)
    thumbs = []
    for t in times:
        fr = grab_frame(path, t)
        if fr is None:
            continue
        h, w = fr.shape[:2]
        scale = thumb_w / float(w)
        th = max(1, int(round(h * scale)))
        im = Image.fromarray(fr).resize((thumb_w, th), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(im)
        label = f"{t:.1f}s"
        draw.rectangle([4, 4, 4 + 8 * len(label), 22], fill=(0, 0, 0))
        draw.text((6, 6), label, fill=(255, 255, 0))
        thumbs.append((t, im))

    if not thumbs:
        return []

    paths = []
    # chunk into sheets of up to cols*3
    per_sheet = cols * 3
    for si in range(0, len(thumbs), per_sheet):
        chunk = thumbs[si : si + per_sheet]
        tw = chunk[0][1].width
        th = chunk[0][1].height
        rows = (len(chunk) + cols - 1) // cols
        canvas = Image.new("RGB", (cols * tw, rows * th), (20, 20, 20))
        for i, (_, im) in enumerate(chunk):
            r, c = divmod(i, cols)
            canvas.paste(im, (c * tw, r * th))
        sp = outdir / f"sheet_{si // per_sheet + 1:02d}.png"
        canvas.save(sp)
        paths.append(str(sp))
    return paths


def main():
    args = parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    sheets_dir = out / "sheets"
    fps, n, w, h, dur = video_meta(args.input)
    start = args.start if args.start is not None else 0.0
    end = args.end if args.end is not None else dur
    end = min(end, dur) if dur else end
    duration = max(0.0, end - start)

    scenes = detect_scenes(args.input, start, end)
    if len(scenes) <= 1:
        scenes = []
    pseudo = not scenes
    candidates = [t for t in change_candidates(args.input, fps) if start <= t <= end]
    if not scenes:
        # 1-second pseudo scenes
        t = start
        while t < end - 1e-6:
            scenes.append((t, min(t + 1.0, end)))
            t += 1.0

    # per-second skeleton
    seconds = []
    t = start
    while t < end - 1e-6:
        seconds.append(round(t, 3))
        t += 1.0

    # contact sheet sample points: every 0.5s plus scene midpoints
    sample = set()
    for s in seconds:
        sample.add(round(s, 2))
        if s + 0.5 < end:
            sample.add(round(s + 0.5, 2))
    for a, b in scenes:
        sample.add(round((a + b) / 2.0, 2))
    for c in candidates:
        sample.add(round(c, 2))
    sample_times = sorted(x for x in sample if start <= x <= end)

    sheet_paths = make_sheets(args.input, sample_times, sheets_dir, args.cols, args.thumb_w)

    csv_path = out / "timeline.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        wri = csv.writer(f)
        wri.writerow(
            [
                "t_start",
                "t_end",
                "shot_id",
                "camera",
                "action",
                "wardrobe",
                "props",
                "transition",
                "notes",
            ]
        )
        for i, (a, b) in enumerate(scenes, 1):
            wri.writerow([f"{a:.3f}", f"{b:.3f}", f"S{i:02d}", "", "", "", "", "", ""])

    # also per-second rows file for agents
    sec_csv = out / "per_second.csv"
    with sec_csv.open("w", newline="", encoding="utf-8") as f:
        wri = csv.writer(f)
        wri.writerow(["t", "action", "wardrobe", "props", "transition", "notes"])
        for s in seconds:
            wri.writerow([f"{s:.3f}", "", "", "", "", ""])

    md = out / "breakdown.md"
    lines = [
        f"# 拉片骨架 · {Path(args.input).name}",
        "",
        f"- 时长: **{duration:.2f}s** (window {start:.2f}→{end:.2f})",
        f"- 分辨率: {w}×{h} @ {fps:.2f} fps",
        f"- 场景切点: {len(scenes)}"
        + ("（未检测到硬切，下表为 1 秒网格，不是真实镜头）" if pseudo else ""),
        "- 软转场/变化候选（遮挡、擦除、换装等，需看图确认）: "
        + (", ".join(f"{c:.2f}s" for c in candidates) or "无"),
        f"- 缩略图拼图: {len(sheet_paths)} 张 → `sheets/`",
        "",
        "## 重要",
        "",
        "本文件只有**时间轴骨架**。动作 / 服装 / 道具描述列为空，",
        "**必须由能看图的模型**对照 `sheets/*.png` 填写，再写入 `prompt_zh.txt` / `prompt_en.txt`。",
        "纯文本模型请停止并提示用户切换视觉模型。",
        "",
        "## 场景表",
        "",
        "| shot | t_start | t_end | camera | action | wardrobe | props | transition |",
        "|------|---------|-------|--------|--------|----------|-------|------------|",
    ]
    for i, (a, b) in enumerate(scenes, 1):
        lines.append(f"| S{i:02d} | {a:.2f} | {b:.2f} |  |  |  |  |  |")
    lines += [
        "",
        "## 每秒时间点（待填）",
        "",
    ]
    for s in seconds:
        lines.append(f"- `{s:05.1f}s` — ")
    lines += [
        "",
        "## 拼图",
        "",
    ]
    for sp in sheet_paths:
        lines.append(f"- `{Path(sp).name}`")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    meta = {
        "duration_sec": round(duration, 4),
        "start": start,
        "end": end,
        "fps": fps,
        "size": [w, h],
        "scenes": len(scenes),
        "scenes_are_pseudo_1s_grid": pseudo,
        "change_candidates_sec": candidates,
        "seconds": seconds,
        "sheets": sheet_paths,
        "timeline_csv": str(csv_path),
        "per_second_csv": str(sec_csv),
        "breakdown_md": str(md),
    }
    (out / "breakdown_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"ok": True, **{k: meta[k] for k in ("duration_sec", "scenes", "sheets")}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
