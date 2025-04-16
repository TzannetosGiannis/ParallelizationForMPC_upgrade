#!/usr/bin/env python3
import argparse

import compiler
from compiler.backends import Backend


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=argparse.FileType("r"))
    parser.add_argument(
        "--out-dir",
        help="If provided, render a sample application into this directory.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output directory",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Avoid printing output of compiler stages",
    )
    parser.add_argument(
        "--protocol",
        help="Protocol to use when running benchmarks",
    )
    parser.add_argument(
        "--backend",
        type=Backend,
        choices=list(Backend),
        help="The MPC backend to target",
    )
    parser.add_argument(
        "--mixing",
        action="store_true",
        help="Run protocol mixing algorithm to find optimal assignments",
    )
    parser.add_argument(
        "--costType",
        choices=['time', 'dataSent', 'commRounds'],
        help="Type of cost model to use for mixing",
    )


    args = parser.parse_args()
     # Ensure that --costType is explicitly provided if --mixing is used
    if args.mixing and args.costType is None:
        parser.error("--costType must be specified when using --mixing")

    return args


if __name__ == "__main__":
    args = parse_args()
    compiler.compile(
        args.input.name,
        args.input.read(),
        args.backend,
        'time' if args.costType is None else args.costType,
        args.quiet,
        True,  # Only output vectorized code when invoked from the command line
        args.out_dir,
        args.overwrite,
        args.protocol,
        args.mixing,
    )
