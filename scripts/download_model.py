#!/usr/bin/env python3
"""Pre-fetch Depth Anything V2 Small into <repo>/models/ (offline-capable).

国内网络：自动先试 huggingface.co，不通再试 hf-mirror.com；
也可 `--hf-mirror` 或环境变量 HF_ENDPOINT=https://hf-mirror.com 直接走镜像。
下载完后 models/ 文件夹可整体拷到别的电脑（离线包），无需再联网。
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
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_ID = "depth-anything/Depth-Anything-V2-Small-hf"
LOCAL_DIR = ROOT / "models" / "Depth-Anything-V2-Small-hf"
OFFICIAL = "https://huggingface.co"
DEFAULT_MIRROR = "https://hf-mirror.com"
NEEDED = ("config.json", "preprocessor_config.json", "model.safetensors")


def local_ok(d: Path = LOCAL_DIR) -> bool:
    return all((d / f).exists() and (d / f).stat().st_size > 0 for f in NEEDED)


def endpoints(prefer_mirror: bool) -> list[str]:
    env = os.environ.get("HF_ENDPOINT", "").strip().rstrip("/")
    order = []
    if env:
        order.append(env)
    if prefer_mirror:
        order.append(DEFAULT_MIRROR)
    order += [OFFICIAL, DEFAULT_MIRROR]
    seen, out = set(), []
    for e in order:
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return out


def direct_download(ep: str) -> None:
    """Plain HTTPS GET per file, following redirects (hf-mirror.com 对海外 IP 会 308 到官方，
    huggingface_hub 不跟跨域重定向；这里兜底)。"""
    import shutil
    import urllib.error
    import urllib.parse
    import urllib.request

    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    for f in NEEDED:
        dst = LOCAL_DIR / f
        if dst.exists() and dst.stat().st_size > 0:
            continue
        url = f"{ep}/{MODEL_ID}/resolve/main/{f}"
        print(f"[model]   GET {url}", flush=True)
        tmp = dst.with_suffix(dst.suffix + ".part")
        for _hop in range(5):  # Python <3.11 urllib does not follow 308
            req = urllib.request.Request(url, headers={"User-Agent": "remake-depth-breakdown"})
            try:
                with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as out:
                    shutil.copyfileobj(r, out, 1 << 20)
                break
            except urllib.error.HTTPError as e:
                loc = e.headers.get("Location")
                if e.code in (301, 302, 303, 307, 308) and loc:
                    url = urllib.parse.urljoin(url, loc)
                    print(f"[model]   → redirect {url}", flush=True)
                    continue
                raise
        else:
            raise RuntimeError("too many redirects")
        tmp.replace(dst)


def ensure_model(prefer_mirror: bool = False, quiet: bool = False) -> Path:
    """Return local model dir, downloading if needed (official → mirror)."""
    if local_ok():
        if not quiet:
            print(f"[model] already present: {LOCAL_DIR}", flush=True)
        return LOCAL_DIR
    from huggingface_hub import snapshot_download

    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "15")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
    errors = []
    for ep in endpoints(prefer_mirror):
        try:
            print(f"[model] downloading {MODEL_ID} from {ep} → {LOCAL_DIR}", flush=True)
            snapshot_download(
                repo_id=MODEL_ID,
                local_dir=str(LOCAL_DIR),
                endpoint=ep,
                allow_patterns=["*.json", "*.safetensors", "*.txt", "*.md"],
            )
            if local_ok():
                print(f"[model] OK via {ep}", flush=True)
                return LOCAL_DIR
            errors.append(f"{ep}: incomplete download")
        except Exception as e:  # network / SSL / proxy
            errors.append(f"{ep}: {type(e).__name__}: {e}")
            print(f"[model] {ep} hub-client failed ({type(e).__name__}) → direct HTTPS …", flush=True)
            try:
                direct_download(ep)
                if local_ok():
                    print(f"[model] OK via {ep} (direct)", flush=True)
                    return LOCAL_DIR
            except Exception as e2:
                errors.append(f"{ep} direct: {type(e2).__name__}: {e2}")
                print(f"[model] {ep} direct failed ({type(e2).__name__}); trying next…", flush=True)
    raise RuntimeError("model download failed on all endpoints:\n  " + "\n  ".join(errors))


def main():
    ap = argparse.ArgumentParser(description="Pre-fetch Depth Anything V2 Small into models/")
    ap.add_argument("--hf-mirror", action="store_true",
                    help=f"先走国内镜像 {DEFAULT_MIRROR}（也可设 HF_ENDPOINT）")
    args = ap.parse_args()
    try:
        d = ensure_model(prefer_mirror=args.hf_mirror)
    except Exception as e:
        print(f"[model] FAILED: {e}", file=sys.stderr)
        print("  试试：python3 scripts/download_model.py --hf-mirror\n"
              "  或从同事电脑拷整个 models/ 文件夹到本仓库根目录（离线包）", file=sys.stderr)
        sys.exit(2)
    size = sum(p.stat().st_size for p in d.rglob("*") if p.is_file()) / 1e6
    print(f"[model] ready: {d}  ({size:.0f} MB)")


if __name__ == "__main__":
    main()
