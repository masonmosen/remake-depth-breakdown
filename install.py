#!/usr/bin/env python3
"""Install deps for 复刻拉片工坊. Optional/auto venv. Checks ffmpeg."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(cmd, **kw):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.check_call(cmd, **kw)


def check_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


def venv_python(venv: Path) -> str:
    if os.name == "nt":
        return str(venv / "Scripts" / "python.exe")
    return str(venv / "bin" / "python")


def ensure_venv(venv: Path) -> str:
    if not venv.exists():
        run([sys.executable, "-m", "venv", str(venv)])
    py = venv_python(venv)
    run([py, "-m", "pip", "install", "--upgrade", "pip"])
    return py


def pip_install(py: str, pkgs: list[str] | None = None, req: Path | None = None):
    cmd = [py, "-m", "pip", "install"]
    if req is not None:
        cmd += ["-r", str(req)]
    else:
        cmd += list(pkgs or [])
    run(cmd)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--venv", action="store_true", help="Create .venv and install into it")
    ap.add_argument(
        "--force-demo-only",
        action="store_true",
        help="Skip torch/transformers (light install for offline selfcheck)",
    )
    args = ap.parse_args()

    venv = ROOT / ".venv"
    use_venv = args.venv or venv.exists()
    py = sys.executable

    def do_install(python: str):
        if args.force_demo_only:
            pkgs = [
                "opencv-python",
                "numpy",
                "pillow",
                "scenedetect",
                "imageio-ffmpeg",
            ]
            pip_install(python, pkgs=pkgs)
        else:
            pip_install(python, req=ROOT / "requirements.txt")

    try:
        if use_venv:
            py = ensure_venv(venv)
        do_install(py)
    except subprocess.CalledProcessError as e:
        # PEP 668 externally-managed-environment → auto venv retry
        print(
            f"[install] pip failed ({e.returncode}); retrying inside .venv …",
            flush=True,
        )
        py = ensure_venv(venv)
        do_install(py)

    ff = check_ffmpeg()
    print("\n=== install status ===")
    print(f"python: {py}")
    if ff:
        print(f"ffmpeg: {ff}  OK")
    else:
        print("ffmpeg: MISSING")
        print("  macOS: brew install ffmpeg")
        print("  Ubuntu: sudo apt install ffmpeg")
        print("  or: pip install imageio-ffmpeg")
        sys.exit(1)

    print(
        "\nNext:\n"
        f"  {py} selfcheck.py\n"
        f"  {py} scripts/run_all.py --input /path/to/ref.mp4\n"
        "\nBoundaries:\n"
        "  • depth / audio / cuts / sheets = local, any chat model\n"
        "  • filling Seedance prompts = needs a VISION model\n"
        "  • LibTV/Seedance paid gen = OUT OF SCOPE (docs/libtv-manual.md)\n"
    )
    # helper shim note
    print(f"Tip: prefer `{py}` for all subsequent commands (or activate .venv).")


if __name__ == "__main__":
    main()
