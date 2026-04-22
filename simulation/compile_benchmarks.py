#!/usr/bin/env python3
"""Time the full compile pipeline (mixed-protocol, ILP path) for MOTION and MP-SPDZ
backends across every (benchmark, size) tuple that paper_benchmarks.py currently
enables, writing one row per run to a resume-safe CSV.

Mirrors the shape of Silph's ``simulation/compile_benchmarks.py`` so that the two
output files are directly comparable.
"""
import argparse
import csv
import os
import signal
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPILER_DIR = REPO_ROOT / "compiler"
sys.path.insert(0, str(COMPILER_DIR))

import paper_benchmarks  # noqa: E402  (path-hacked above)
from tests import context as test_context  # noqa: E402
from tests.backends.motion.benchmark import (  # noqa: E402
    compile_benchmark as motion_compile_benchmark,
)
from tests.backends.mp_spdz.benchmark import (  # noqa: E402
    compile_benchmark as spdz_compile,
)
from compiler.backends import Backend  # noqa: E402

RUNS_PER_CONFIG = 10
DEFAULT_TIMEOUT_SECONDS = 600
BACKENDS = ("motion", "mp_spdz")


class CompileTimeout(Exception):
    pass


def _alarm_handler(signum, frame):
    raise CompileTimeout()


def _install_timeout(seconds):
    signal.signal(signal.SIGALRM, _alarm_handler)
    signal.alarm(seconds)


def _clear_timeout():
    signal.alarm(0)


def iter_jobs():
    """Yield (benchmark_name, benchmark_path, size_label, input_args_list, backend)
    tuples in a deterministic order."""
    skipped_all = set(test_context.SKIPPED_TESTS[None])
    skipped_motion = set(test_context.SKIPPED_TESTS.get(Backend.MOTION, []))
    skipped_spdz = set(test_context.SKIPPED_TESTS.get(Backend.MP_SPDZ, []))

    for entry in sorted(os.scandir(test_context.STAGES_DIR), key=lambda e: e.name):
        if not entry.is_dir() or entry.name in skipped_all:
            continue
        all_args, _ = paper_benchmarks.get_inputs(entry.name)
        if not all_args:
            continue
        for input_args in all_args:
            for backend in BACKENDS:
                if backend == "motion" and entry.name in skipped_motion:
                    continue
                if backend == "mp_spdz" and entry.name in skipped_spdz:
                    continue
                yield entry.name, entry.path, input_args.label, input_args.args, backend


def run_compile(backend, benchmark_name, benchmark_path, cmd_args, timeout_seconds):
    parsed = paper_benchmarks.parse_list(cmd_args)
    start = time.perf_counter()
    try:
        _install_timeout(timeout_seconds)
        if backend == "motion":
            motion_compile_benchmark(
                benchmark_name=benchmark_name,
                benchmark_path=benchmark_path,
                protocol=None,
                vectorized=True,
                mixed=True,
                costType="time",
                args=parsed,
            )
        else:
            spdz_compile(
                benchmark_name=benchmark_name,
                benchmark_path=benchmark_path,
                vectorized=True,
                mixed=True,
                costType="time",
                args=parsed,
                protocol=None,
            )
    except CompileTimeout:
        return None, f"compile exceeded {timeout_seconds}s"
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        msg = msg.replace("\n", " ")[:500]
        return "error", msg
    finally:
        _clear_timeout()
    elapsed = time.perf_counter() - start
    return elapsed, ""


def load_seen(output_path):
    seen = set()
    if not output_path.exists():
        return seen
    with output_path.open(newline="") as f:
        for row in csv.DictReader(f):
            key = (
                row.get("benchmark"),
                row.get("size"),
                row.get("backend"),
                row.get("run"),
            )
            if all(v is not None for v in key):
                seen.add(key)
    return seen


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Compile every (benchmark, size) with each backend 10 times and "
            "record wallclock compile time. Default output: "
            "simulation/results/compile_time.csv."
        )
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "simulation" / "results" / "compile_time.csv"),
        help="Path to output CSV file.",
    )
    parser.add_argument(
        "--log-file",
        default=str(REPO_ROOT / "simulation" / "results" / "compile_time.log"),
        help="Path to detailed log file (appended across runs).",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Max seconds per compile before SIGALRM kills it.",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    log_path = Path(args.log_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "benchmark",
        "size",
        "backend",
        "run",
        "timestamp",
        "compile_time_seconds",
        "status",
        "error",
    ]
    seen = load_seen(output_path)
    write_header = not output_path.exists()

    with output_path.open("a", newline="") as csvfile, log_path.open("a") as log_file:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
            csvfile.flush()

        for benchmark, path, size_label, input_args, backend in iter_jobs():
            for run in range(1, RUNS_PER_CONFIG + 1):
                key = (benchmark, size_label, backend, str(run))
                if key in seen:
                    log_file.write(
                        f"[skip] {benchmark} [{size_label}] {backend} run {run} already recorded\n"
                    )
                    log_file.flush()
                    continue

                timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                header = (
                    f"[{timestamp}] {benchmark} [{size_label}] {backend} "
                    f"run {run}/{RUNS_PER_CONFIG}"
                )
                log_file.write(f"{header} START\n")
                log_file.flush()

                result, err = run_compile(
                    backend, benchmark, path, input_args, args.timeout_seconds
                )

                if result is None:
                    row = {
                        "benchmark": benchmark,
                        "size": size_label,
                        "backend": backend,
                        "run": run,
                        "timestamp": timestamp,
                        "compile_time_seconds": "",
                        "status": "timeout",
                        "error": err,
                    }
                elif result == "error":
                    row = {
                        "benchmark": benchmark,
                        "size": size_label,
                        "backend": backend,
                        "run": run,
                        "timestamp": timestamp,
                        "compile_time_seconds": "",
                        "status": "error",
                        "error": err,
                    }
                else:
                    row = {
                        "benchmark": benchmark,
                        "size": size_label,
                        "backend": backend,
                        "run": run,
                        "timestamp": timestamp,
                        "compile_time_seconds": f"{result:.6f}",
                        "status": "ok",
                        "error": "",
                    }

                writer.writerow(row)
                csvfile.flush()
                log_file.write(
                    f"{header} END status={row['status']} "
                    f"time={row['compile_time_seconds']} error={row['error']!r}\n"
                )
                log_file.flush()

    print(f"Results written to {output_path}")
    print(f"Detailed log written to {log_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
