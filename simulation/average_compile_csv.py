#!/usr/bin/env python3
"""Aggregate per-run rows in compile_time.csv into one row per (benchmark, size, backend).

Average is taken over the runs that finished with status=ok; error/timeout rows
are not counted toward the mean. The error column is rewritten to a
human-readable label:
  * any exception -> "EXCEPTION" (or "EXCEPTION: <Class>" if all errors share class)
  * any timeout   -> "TIMEOUT"
  * both present  -> "EXCEPTION/TIMEOUT"
  * otherwise     -> ""
"""
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean

SCRIPT_DIR = Path(__file__).resolve().parent
INPUT = SCRIPT_DIR / "results" / "compile_time.csv"
OUTPUT = SCRIPT_DIR / "results" / "compile_time_average.csv"

EXC_CLASS_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):")


def classify(rows):
    has_exc = any(r["status"] == "error" for r in rows)
    has_timeout = any(r["status"] == "timeout" for r in rows)

    if has_exc and has_timeout:
        label = "EXCEPTION/TIMEOUT"
    elif has_exc:
        exc_classes = {
            m.group(1)
            for r in rows
            if r["status"] == "error"
            for m in [EXC_CLASS_RE.match(r["error"])]
            if m
        }
        if len(exc_classes) == 1:
            label = f"EXCEPTION: {next(iter(exc_classes))}"
        else:
            label = "EXCEPTION"
    elif has_timeout:
        label = "TIMEOUT"
    else:
        label = ""

    status = Counter(r["status"] for r in rows).most_common(1)[0][0]
    return status, label


def main():
    groups = defaultdict(list)
    with INPUT.open(newline="") as f:
        for row in csv.DictReader(f):
            key = (row["benchmark"], row["size"], row["backend"])
            groups[key].append(row)

    fieldnames = [
        "benchmark",
        "size",
        "backend",
        "timestamp",
        "compile_time_seconds",
        "status",
        "error",
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key in sorted(groups):
            rows = groups[key]
            ok_times = [
                float(r["compile_time_seconds"])
                for r in rows
                if r["status"] == "ok" and r["compile_time_seconds"]
            ]
            avg = f"{fmean(ok_times):.6f}" if ok_times else ""
            status, error_label = classify(rows)
            writer.writerow(
                {
                    "benchmark": key[0],
                    "size": key[1],
                    "backend": key[2],
                    "timestamp": max(r["timestamp"] for r in rows),
                    "compile_time_seconds": avg,
                    "status": status,
                    "error": error_label,
                }
            )
    print(f"Wrote {len(groups)} grouped rows to {OUTPUT}")


if __name__ == "__main__":
    main()
