#!/usr/bin/env python3
"""Validate that a Seedance prompt covers 0 → duration without gaps.

Looks for time codes like:
  0-1.6s / 0–1.6s / [0.0-1.6] / 0s-1.6s / 0:00-0:02
Fails if:
  - file still contains [TODO placeholder beats
  - union of intervals does not cover [0, duration] (tol 0.15s)
  - opening beat (from ~0) is missing
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


TIME_RE = re.compile(
    r"(?P<a>\d+(?:[.:]\d+)?)\s*[–\-~到至]\s*(?P<b>\d+(?:[.:]\d+)?)\s*s?",
    re.IGNORECASE,
)


def parse_ts(s: str) -> float:
    s = s.strip()
    if ":" in s:
        parts = s.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return float(s)


def extract_intervals(text: str) -> list[tuple[float, float]]:
    intervals = []
    for line in text.splitlines():
        if "[TODO" in line.upper() or "TODO —" in line or "TODO -" in line:
            continue  # unfinished stub lines do not count as coverage
        for m in TIME_RE.finditer(line):
            a, b = parse_ts(m.group("a")), parse_ts(m.group("b"))
            if b < a:
                a, b = b, a
            intervals.append((a, b))
    return intervals


def covered(intervals: list[tuple[float, float]], duration: float, tol: float = 0.15):
    if not intervals:
        return False, ["no time intervals found"], []
    intervals = sorted(intervals)
    merged = [list(intervals[0])]
    for a, b in intervals[1:]:
        if a <= merged[-1][1] + tol:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    gaps = []
    if merged[0][0] > tol:
        gaps.append((0.0, merged[0][0]))
    for i in range(len(merged) - 1):
        if merged[i + 1][0] - merged[i][1] > tol:
            gaps.append((merged[i][1], merged[i + 1][0]))
    if duration - merged[-1][1] > tol:
        gaps.append((merged[-1][1], duration))
    opening_ok = merged[0][0] <= tol
    return (len(gaps) == 0 and opening_ok), gaps, merged


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", required=True, help="prompt_zh.txt or prompt_en.txt")
    p.add_argument("--duration", type=float, required=True, help="Clip duration seconds")
    p.add_argument("--tol", type=float, default=0.15)
    return p.parse_args()


def main():
    args = parse_args()
    text = Path(args.prompt).read_text(encoding="utf-8")
    # Ignore INSTRUCTIONS fences so stubs are judged on beat lines only
    body = re.sub(r"(?is)```instructions.*?```", "", text)
    body = re.sub(r"(?is)<!--.*?-->", "", body)

    todo_lines = [ln for ln in body.splitlines() if "[TODO" in ln.upper()]
    if todo_lines:
        print(f"FAIL: {args.prompt}")
        print(f"  reason: {len(todo_lines)} beat(s) still marked [TODO — not filled yet")
        print("  tip: open sheets/*.png with a VISION model and replace every [TODO] line.")
        sys.exit(1)

    intervals = extract_intervals(body)
    ok, gaps, merged = covered(intervals, args.duration, args.tol)
    if not ok:
        print(f"FAIL: {args.prompt}")
        if not intervals:
            print("  reason: no time codes like `0-1.6s` found — opening beat missing?")
            print("  tip: write beats from t=0 (e.g. fall-off-sofa) through end.")
        else:
            if gaps and gaps[0][0] == 0.0:
                print("  reason: missing OPENING beat from t=0")
            for g in gaps:
                print(f"  gap: {g[0]:.2f}s → {g[1]:.2f}s")
            print(f"  merged coverage: {merged}")
        sys.exit(1)
    print(f"OK: covers 0→{args.duration:.2f}s with {len(intervals)} beats")
    sys.exit(0)


if __name__ == "__main__":
    main()
