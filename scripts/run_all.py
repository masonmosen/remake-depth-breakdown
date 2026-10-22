#!/usr/bin/env python3
"""One-shot: depth + audio + breakdown + prompt stubs → out/<stem>/."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent


def run(cmd: list[str]):
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(r.returncode)


def stub_prompt(lang: str, duration: float, stem: str) -> str:
    # Build empty beat skeleton every ~1s so validate can see structure after fill
    beats = []
    t = 0.0
    while t < duration - 1e-6:
        nxt = min(t + 1.0, duration)
        beats.append(f"{t:.1f}-{nxt:.1f}s: [TODO — fill from contact sheets]")
        t = nxt
    if lang == "zh":
        header = f"""# Seedance 提示词（中文）· {stem}
# 时长 {duration:.2f}s · 从 t=0 写起，禁止跳过开场动作

```instructions
你是视觉拉片助手。请打开同目录 sheets/*.png 与 breakdown.md。
用中文把每个时间段的：镜头、人物动作、服装、道具、转场 写进下方 beats。
规则：
1. 必须从 0.0s 开场写起（含掉沙发/起身等首个动作），禁止直接从中段开始。
2. 时间轴连续覆盖 0→{duration:.2f}s，间隙 <0.15s。
3. 不要编造原片没有的字幕/Logo。
4. 写完后运行: python scripts/validate_prompt.py --prompt <本文件> --duration {duration:.2f}
若你是纯文本模型、看不到图片：停止，并明确告诉用户需要切换视觉模型。
本技能不依赖 Grok Bot / LibTV MCP / 特定云账号。
```

"""
    else:
        header = f"""# Seedance prompt (EN) · {stem}
# Duration {duration:.2f}s · start at t=0; do not skip the opening beat

```instructions
You are a vision breakdown assistant. Open sheets/*.png and breakdown.md.
Fill each beat: camera, action, wardrobe, props, transition.
Rules:
1. Start at 0.0s (include fall-from-sofa / first motion). Never begin mid-clip.
2. Cover 0→{duration:.2f}s continuously (gaps <0.15s).
3. No invented subtitles/logos.
4. Validate: python scripts/validate_prompt.py --prompt <this file> --duration {duration:.2f}
If you are a text-only model and cannot see images: STOP and tell the user to switch to a vision model.
This skill does not depend on Grok Bot / LibTV MCP / any cloud account.
```

"""
    return header + "\n".join(beats) + "\n"


def parse_args():
    p = argparse.ArgumentParser(description="复刻拉片工坊 one-shot pipeline")
    p.add_argument("--input", required=True, help="Reference video")
    p.add_argument("--outdir", default=None, help="Default: out/<stem>/")
    p.add_argument("--start", type=float, default=None)
    p.add_argument("--end", type=float, default=None)
    p.add_argument("--max-side", type=int, default=720)
    p.add_argument("--device", default="auto")
    p.add_argument("--split-max", type=float, default=15.0, help="Depth segment length; 0=off")
    p.add_argument("--force-demo", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    src = Path(args.input).resolve()
    if not src.exists():
        raise SystemExit(f"input not found: {src}")
    stem = src.stem
    out = Path(args.outdir) if args.outdir else (ROOT / "out" / stem)
    out.mkdir(parents=True, exist_ok=True)

    depth_mp4 = out / "depth.mp4"
    audio_m4a = out / "ref_audio.m4a"

    depth_cmd = [
        sys.executable,
        str(SCRIPTS / "extract_depth.py"),
        "--input",
        str(src),
        "--output",
        str(depth_mp4),
        "--max-side",
        str(args.max_side),
        "--device",
        args.device,
        "--meta",
        str(out / "depth.json"),
    ]
    if args.start is not None:
        depth_cmd += ["--start", str(args.start)]
    if args.end is not None:
        depth_cmd += ["--end", str(args.end)]
    if args.split_max and args.split_max > 0:
        depth_cmd += ["--split-max", str(args.split_max)]
    if args.force_demo:
        depth_cmd.append("--force-demo")
    run(depth_cmd)

    audio_cmd = [
        sys.executable,
        str(SCRIPTS / "extract_audio.py"),
        "--input",
        str(src),
        "--output",
        str(audio_m4a),
    ]
    if args.start is not None:
        audio_cmd += ["--start", str(args.start)]
    if args.end is not None:
        audio_cmd += ["--end", str(args.end)]
    run(audio_cmd)

    run(
        [
            sys.executable,
            str(SCRIPTS / "breakdown.py"),
            "--input",
            str(src),
            "--outdir",
            str(out),
            *(["--start", str(args.start)] if args.start is not None else []),
            *(["--end", str(args.end)] if args.end is not None else []),
        ]
    )

    bmeta = json.loads((out / "breakdown_meta.json").read_text(encoding="utf-8"))
    duration = float(bmeta.get("duration_sec") or 0)
    depth_meta = {}
    if (out / "depth.json").exists():
        depth_meta = json.loads((out / "depth.json").read_text(encoding="utf-8"))

    zh = out / "prompt_zh.txt"
    en = out / "prompt_en.txt"
    zh.write_text(stub_prompt("zh", duration, stem), encoding="utf-8")
    en.write_text(stub_prompt("en", duration, stem), encoding="utf-8")

    manifest = {
        "skill": "复刻拉片工坊",
        "id": "remake-depth-breakdown",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input": str(src),
        "outdir": str(out.resolve()),
        "duration_sec": duration,
        "artifacts": {
            "depth_mp4": str(depth_mp4),
            "ref_audio_m4a": str(audio_m4a),
            "breakdown_md": str(out / "breakdown.md"),
            "timeline_csv": str(out / "timeline.csv"),
            "per_second_csv": str(out / "per_second.csv"),
            "sheets_dir": str(out / "sheets"),
            "prompt_zh": str(zh),
            "prompt_en": str(en),
            "depth_json": str(out / "depth.json"),
        },
        "depth_backend": depth_meta.get("backend"),
        "next_steps": [
            "If your model can SEE images: open sheets/*.png, fill prompt_zh.txt and prompt_en.txt from t=0.",
            f"python scripts/validate_prompt.py --prompt {zh} --duration {duration:.2f}",
            "Paid LibTV/Seedance generation is OUT OF SCOPE — see docs/libtv-manual.md for manual upload.",
        ],
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\n=== 复刻拉片工坊 done ===")
    print(f"outdir: {out}")
    print(f"depth backend: {manifest['depth_backend']}")
    print(f"duration: {duration:.2f}s")
    print("NEXT: vision model fills prompts → validate_prompt.py")
    print(json.dumps({"ok": True, "outdir": str(out), "backend": manifest["depth_backend"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
