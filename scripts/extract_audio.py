#!/usr/bin/env python3
"""Extract reference audio (AAC/M4A) with ffmpeg for Seedance mixed mode."""
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
import shutil
import subprocess
import sys
from pathlib import Path


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise SystemExit(
            "ffmpeg not found on PATH. Install system ffmpeg, or: pip install imageio-ffmpeg"
        )


def parse_args():
    p = argparse.ArgumentParser(description="Extract audio track to m4a/aac")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True, help="Output .m4a path")
    p.add_argument("--start", type=float, default=None)
    p.add_argument("--end", type=float, default=None)
    return p.parse_args()


def main():
    args = parse_args()
    ff = find_ffmpeg()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error"]
    if args.start is not None:
        cmd += ["-ss", str(args.start)]
    cmd += ["-i", args.input]
    if args.end is not None:
        # duration from start
        start = args.start or 0.0
        cmd += ["-t", str(max(0.0, args.end - start))]
    cmd += ["-vn", "-acodec", "aac", "-b:a", "192k", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        # silent / no audio stream
        print(
            f"[audio] ffmpeg failed (maybe no audio stream): {r.stderr.strip()}",
            file=sys.stderr,
        )
        # write a short silent aac so pipeline still has a file
        silence = [
            ff,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            "1",
            "-acodec",
            "aac",
            str(out),
        ]
        r2 = subprocess.run(silence, capture_output=True, text=True)
        if r2.returncode != 0:
            raise SystemExit(f"audio extract failed: {r.stderr or r2.stderr}")
        meta = {"output": str(out.resolve()), "silent_placeholder": True}
    else:
        meta = {"output": str(out.resolve()), "silent_placeholder": False}
    print(json.dumps({"ok": True, **meta}, ensure_ascii=False))


if __name__ == "__main__":
    main()
