import os
from typing import Optional

from compiler.backends import Backend

TESTS_DIR = os.path.dirname(__file__)

STAGES_DIR = os.path.join(TESTS_DIR, "stages")

BACKEND: Optional[Backend] = None

SKIPPED_TESTS = {
    # Skipped in all backends
    None: [
        # These benchmarks will always be skipped (they're essentially pseudocode)
        "biometric_vectorized",
        # The following tests cause issues since they don't loop from 0
        "longest_1s",
        "longest_even_0",
        # The following benchmarks are disabled because they take too long to run
        "kmeans_iteration",

        "histogram",
        # "biometric_fast",
        # "chapterfour_figure_12",
    ],
    # Skipped only in MOTION
    Backend.MOTION: [
        # "convex_hull",
        # "biometric",
        # "biometric_fast",
        # "chapterfour_figure_12",
        # "count_123",
        # "minimal_points",
        # "inner_product",
        # "db_cross_join_trivial",
        # "psi",
        # "count_10s",
        # "longest_102",
        # "db_variance",
        # "histogram",
        # "count_102",
        # "mnist_relu",
        # "max_sum_between_syms",
        # "cryptonets_max_pooling",
        # "max_dist_between_syms",
        # "longest_odd_10"
    ],
    # Skipped only in SPDZ
    Backend.MP_SPDZ: [
        # AssertionError: assert all(array.vectorized_dims)
        "histogram", # it doesnt compile
        # "convex_hull", 
        # "biometric",
        # "biometric_fast",
        # "chapterfour_figure_12",
        # "count_123", 
        # "minimal_points", 
        # "inner_product",
        # "db_cross_join_trivial",
        # "psi", 
        # "count_10s",
        # "longest_102",
        # "db_variance",
        # "count_102",
        # "mnist_relu", 
        # "max_sum_between_syms",
        # "cryptonets_max_pooling", 
        # "max_dist_between_syms",
        # "longest_odd_10" 
    ],
}
