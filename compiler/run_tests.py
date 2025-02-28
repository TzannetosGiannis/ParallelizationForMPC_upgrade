#!/usr/bin/env python3

from argparse import ArgumentParser

from tests import run_tests, regenerate_stages
from tests import context as test_context
from compiler.backends import Backend

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Regenerate test output to match the current compiler output",
    )
    parser.add_argument(
        "--mixing",
        action="store_true",
        help="Notifies the compiler to generate the mixed compiler output",
    )

    parser.add_argument(
        "--scallar",
        action="store_false",
        help="Notifies the compiler to not run vectorization",
    )
    parser.add_argument(
        "--test-backend",
        type=Backend,
        choices=list(Backend),
        help="Test that the example apps compile and run with the given backend",
    )

    parser.add_argument(
        "--costType",
        choices=["time", "dataSent", "commRounds"],
        help="Specifies the type of cost when mixing is enabled. Required if --mixing is used.",
    )


    args = parser.parse_args()

    test_context.BACKEND = args.test_backend

    # Ensure that --costType is explicitly provided if --mixing is used
    if args.mixing and args.costType is None:
        parser.error("--costType must be specified when using --mixing")

    if args.regenerate:
        regenerate_stages(args.mixing,args.scallar,args.costType)
    else:
        run_tests()
