#!/usr/bin/env python3
"""Generate a 2s synthetic clip and run extract_depth + breakdown. CPU OK."""
from __future__ import annotations

# --- auto-use bundled .venv (install.py may have created it) ---
import os as _os, sys as _sys
from pathlib import Path as _P
_VENV = _P(__file__).resolve().parent / ".venv"
_VPY = _VENV / ("Scripts/python.exe" if _os.name == "nt" else "bin/python")
if _VPY.exists() and _P(_sys.prefix).resolve() != _VENV.resolve() and not _os.environ.get("RDB_NO_VENV_REEXEC"):
    _os.environ["RDB_NO_VENV_REEXEC"] = "1"
    _os.execv(str(_VPY), [str(_VPY), *_sys.argv])
# ---------------------------------------------------------------

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"


def make_bars(path: Path, seconds: float = 2.0, fps: float = 10.0, size=(320, 180)):
    w, h = size
    n = int(seconds * fps)
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h), isColor=True
    )
    if not writer.isOpened():
        raise SystemExit("VideoWriter failed")
    for i in range(n):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        # moving color bar + circle (gives depth proxy signal)
        x = int((i / max(n - 1, 1)) * (w - 40)) + 20
        frame[:, :] = (30, 30, 30)
        cv2.rectangle(frame, (0, 0), (w // 3, h), (0, 0, 200), -1)
        cv2.rectangle(frame, (w // 3, 0), (2 * w // 3, h), (0, 200, 0), -1)
        cv2.rectangle(frame, (2 * w // 3, 0), (w, h), (200, 0, 0), -1)
        cv2.circle(frame, (x, h // 2), 18, (255, 255, 255), -1)
        writer.write(frame)
    writer.release()


def main():
    out_root = ROOT / "out" / "_selfcheck"
    out_root.mkdir(parents=True, exist_ok=True)
    src = out_root / "bars.mp4"
    make_bars(src)
    print(f"[selfcheck] wrote {src}")

    depth = out_root / "depth.mp4"
    # Prefer real model; allow DEMO fallback so offline CI still passes
    cmd = [
        sys.executable,
        str(SCRIPTS / "extract_depth.py"),
        "--input",
        str(src),
        "--output",
        str(depth),
        "--max-side",
        "320",
        "--device",
        "cpu",
        "--meta",
        str(out_root / "depth.json"),
    ]
    # If env REMOTE_DEPTH=0 or no network expected, force demo
    import os

    if os.environ.get("SELFCHECK_FORCE_DEMO", "1") == "1":
        cmd.append("--force-demo")
        print("[selfcheck] SELFCHECK_FORCE_DEMO=1 → demo proxy (set 0 to try real model)")
    else:
        cmd.append("--require-real")
        print("[selfcheck] SELFCHECK_FORCE_DEMO=0 → REAL Depth Anything V2 required")

    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit("extract_depth failed")
    if not depth.exists() or depth.stat().st_size < 100:
        raise SystemExit("depth.mp4 missing/empty")

    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "breakdown.py"),
            "--input",
            str(src),
            "--outdir",
            str(out_root),
        ]
    )
    if r.returncode != 0:
        raise SystemExit("breakdown failed")

    need = [
        out_root / "breakdown.md",
        out_root / "timeline.csv",
        out_root / "per_second.csv",
    ]
    for p in need:
        if not p.exists():
            raise SystemExit(f"missing {p}")
    sheets = list((out_root / "sheets").glob("*.png"))
    if not sheets:
        raise SystemExit("no contact sheets")

    meta = json.loads((out_root / "depth.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {
                "ok": True,
                "backend": meta.get("backend"),
                "depth": str(depth),
                "sheets": len(sheets),
            },
            ensure_ascii=False,
        )
    )
    print("selfcheck PASSED")


if __name__ == "__main__":
    main()
