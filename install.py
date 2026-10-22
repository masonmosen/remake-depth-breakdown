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


TUNA = "https://pypi.tuna.tsinghua.edu.cn/simple"
PIP_INDEX: list[str] = []  # e.g. ["-i", TUNA]; set by --pip-mirror or auto-retry


def ensure_venv(venv: Path) -> str:
    if not venv.exists():
        run([sys.executable, "-m", "venv", str(venv)])
    py = venv_python(venv)
    try:  # upgrading pip is nice-to-have; never fatal (flaky networks)
        run([py, "-m", "pip", "install", "--upgrade", "pip", *PIP_INDEX, "--timeout", "60"])
    except subprocess.CalledProcessError:
        print("[install] pip self-upgrade skipped (network) — continuing", flush=True)
    return py


def pip_install(py: str, pkgs: list[str] | None = None, req: Path | None = None):
    cmd = [py, "-m", "pip", "install", *PIP_INDEX, "--timeout", "60", "--retries", "5"]
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
    ap.add_argument(
        "--cpu",
        action="store_true",
        help="Install CPU-only torch wheel (~200MB instead of multi-GB CUDA build on Linux)",
    )
    ap.add_argument(
        "--pip-mirror",
        nargs="?",
        const=TUNA,
        default=None,
        metavar="URL",
        help=f"国内 pip 镜像（不写 URL 默认清华 {TUNA}）。不加时 pypi.org 失败也会自动改用清华镜像重试",
    )
    ap.add_argument(
        "--download-model",
        action="store_true",
        help="装完顺便把 Depth Anything V2 Small 下到 models/（可离线拷给别人）",
    )
    ap.add_argument("--hf-mirror", action="store_true", help="下载模型先走 hf-mirror.com")
    args = ap.parse_args()
    if args.pip_mirror:
        PIP_INDEX[:] = ["-i", args.pip_mirror]
    if sys.version_info < (3, 9):
        sys.exit(f"Python {sys.version.split()[0]} 太旧，需要 3.9+（macOS: 装 Xcode 命令行工具或 brew install python）")

    venv = ROOT / ".venv"
    use_venv = args.venv or venv.exists() or sys.platform == "darwin"  # macOS: always venv (no ~/Library pollution)
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
            if args.cpu:
                run([python, "-m", "pip", "install", "torch",
                     "--index-url", "https://download.pytorch.org/whl/cpu"])
            pip_install(python, req=ROOT / "requirements.txt")

    try:
        if use_venv:
            py = ensure_venv(venv)
        do_install(py)
    except subprocess.CalledProcessError as e:
        # PEP 668 externally-managed / user-site issues → auto venv retry;
        # if still failing and no mirror set, retry with Tsinghua mirror (国内网络)
        print(f"[install] pip failed ({e.returncode}); retrying inside .venv …", flush=True)
        try:
            py = ensure_venv(venv)
            do_install(py)
        except subprocess.CalledProcessError:
            if PIP_INDEX:
                raise
            print(f"[install] still failing → 改用国内镜像 {TUNA} 重试 …", flush=True)
            PIP_INDEX[:] = ["-i", TUNA]
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

    if args.download_model and not args.force_demo_only:
        dl = [py, str(ROOT / "scripts" / "download_model.py")]
        if args.hf_mirror:
            dl.append("--hf-mirror")
        run(dl)

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
