#!/usr/bin/env python3
"""Compare two depth videos: side-by-side grid + flicker + correlation.
usage: compare_depth.py --a ours.mp4 --b ref.mp4 --src original.mp4 --out compare.png --times 0,1,3,7,11
"""
import argparse, json
import cv2, numpy as np
from PIL import Image, ImageDraw

def grab(p, t, size=None, gray=True):
    c = cv2.VideoCapture(p); c.set(cv2.CAP_PROP_POS_MSEC, t*1000); ok, f = c.read(); c.release()
    if not ok: return None
    if gray: f = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    else: f = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
    return cv2.resize(f, size, interpolation=cv2.INTER_AREA) if size else f

def flicker(p):
    c = cv2.VideoCapture(p); prev=None; means=[]; diffs=[]
    while True:
        ok, f = c.read()
        if not ok: break
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.float32)
        means.append(g.mean())
        if prev is not None: diffs.append(np.abs(g-prev).mean())
        prev = g
    m = np.array(means); d = np.array(diffs)
    return {"frames": len(m), "mean_luma_std": round(float(np.std(np.diff(m))),3),
            "mean_abs_frame_diff": round(float(d.mean()),3), "p95_frame_diff": round(float(np.percentile(d,95)),3)}

ap = argparse.ArgumentParser()
ap.add_argument("--a", required=True); ap.add_argument("--b", required=True); ap.add_argument("--src", required=True)
ap.add_argument("--out", required=True); ap.add_argument("--times", default="0,1,3,7,11")
a = ap.parse_args()
times = [float(x) for x in a.times.split(",")]
W, H = 270, 480
tiles = []; corr = []
for t in times:
    s = grab(a.src, t, (W,H), gray=False); x = grab(a.a, t, (W,H)); y = grab(a.b, t, (W,H))
    corr.append(round(float(np.corrcoef(x.ravel(), y.ravel())[0,1]),3))
    tiles.append((t, s, x, y))
canvas = Image.new("RGB", (W*3, H*len(times)+30*len(times)), (15,15,15))
dr = ImageDraw.Draw(canvas)
for i,(t,s,x,y) in enumerate(tiles):
    yo = i*(H+30)
    dr.text((6, yo+8), f"t={t:.1f}s   original | ours (Depth Anything V2 Small) | LibTV   corr={corr[i]}", fill=(255,255,0))
    for j, im in enumerate([s, x, y]):
        canvas.paste(Image.fromarray(im).convert("RGB"), (j*W, yo+30))
canvas.save(a.out)
print(json.dumps({"corr_per_time": dict(zip(map(str,times), corr)), "ours": flicker(a.a), "libtv": flicker(a.b)}, indent=1))
