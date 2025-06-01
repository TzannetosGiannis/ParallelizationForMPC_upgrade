# [TODO] maybe fix the different protocol sets ?? ?


from argparse import ArgumentParser
from dataclasses import dataclass
import os
import sys
import subprocess

import logging
import logging.handlers
import random
import json
import socket
from os.path import isfile
import datetime
import time

import compiler

from tests import context as test_context

from tests.backends.motion.benchmark import  (
    compile_benchmark as motion_compile_benchmark, 
    run_benchmark_for_party as motion_run_benchmark_for_party, 
    BenchmarkOutput as motion_BenchmarkOutput ,
    replace_definitions as motion_replace_definitions
)

from tests.backends.mp_spdz.benchmark import (
    run_benchmark_for_party as run_benchmark_for_party_spdz,
    compile_benchmark as spdz_compile
)

from utils import json_serialize, json_deserialize, StatsForInputConfig, StatsForTask, RunBenchmarkReq
from utils import GetAddressReq, GetAddressResp
from utils import read_message, write_message
from compiler.backends import Backend

NUM_ITERS = 10

GMW_PROTOCOL = "BooleanGmw"
BMR_PROTOCOL = "Bmr"

FILE_DIR = os.path.dirname(__file__)
BENCHDATA_DIR = os.path.join(FILE_DIR, "benchdata")
LAN_DIR = os.path.join(BENCHDATA_DIR, "lan")
LAN_GRAPHS_DIR = os.path.join(LAN_DIR, "graphs")
WAN_DIR = os.path.join(BENCHDATA_DIR, "wan")
WAN_GRAPHS_DIR = os.path.join(WAN_DIR, "graphs")
COMPARISON_GRAPHS_DIR = os.path.join(BENCHDATA_DIR, "comparison-graphs")
GRAPH_EXT = ".tex"

os.makedirs(BENCHDATA_DIR, exist_ok=True)
os.makedirs(LAN_DIR, exist_ok=True)
os.makedirs(LAN_GRAPHS_DIR, exist_ok=True)
os.makedirs(WAN_DIR, exist_ok=True)
os.makedirs(WAN_GRAPHS_DIR, exist_ok=True)
os.makedirs(COMPARISON_GRAPHS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler(
            "{0}.log".format(os.path.basename(__file__)),
             maxBytes=(1048576*5), backupCount=10
        )
    ])

fmt_str = "[%(asctime)s] %(levelname)s:%(name)s:%(message)s"
formatter = logging.Formatter(fmt_str)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(formatter)

log = logging.getLogger(__name__)
log.addHandler(console);

@dataclass
class InputArgs:
    label: str
    args: list[str]


random.seed(0) # Intentionally seeding with a known value, for reproducibility
def get_rand_ints(n, min=1, max=100):
    return [random.randint(min, max) for i in range(n)]

def parse_list(data):
    result = {}
    key = None
    values = []

    for item in data:
        if item.startswith("--"):
            if key is not None:
                # Store as int if only one value, otherwise as a list
                result[key] = values[0] if len(values) == 1 else values
            key = item[2:]  # Remove '--'
            values = []
        else:
            values.append(int(item))

    # Add the last key-value pair
    if key is not None:
        result[key] = values[0] if len(values) == 1 else values

    return result



def get_biometric_inputs() -> tuple[list[InputArgs], int]:
    all_args = []
    non_vec_up_to = 0 #6# Only run non-vectorized benchmark upto this index
    # for config in [[4, 4], [4, 8], [4, 16], [4, 32], [4, 64], [4, 128], [4, 256], [4, 512], [4, 1024], [4, 2048], [4, 4096]]:
    # for config in [[4, 128], [4, 4096]]:
    for config in [[4,512], [4,1024]]:
        D = config[0]
        N = config[1]
        args = [
        "--D", "{}".format(D),
        "--N", "{}".format(N),
        ]
        C = get_rand_ints(D)
        S = get_rand_ints(D * N)
        args.append("--C")
        args.extend(list(map(str, C)))
        args.append("--S")
        args.extend(list(map(str, S)))
        label = "D: {}, N: {}".format(D, N)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_biometric_fast_inputs() -> tuple[list[InputArgs], int]:
    all_args = []
    non_vec_up_to = 0 #6 # Only run non-vectorized benchmark upto this index
    # for config in [[4, 4], [4, 8], [4, 16], [4, 32], [4, 64], [4, 128], [4, 256], [4, 512], [4, 1024], [4, 2048], [4, 4096]]:
    # for config in [[4, 128], [4, 4096]]:
    # for config in [[4, 512], [4,1024]]:
    for config in [[4, 128]]:
        D = config[0]
        N = config[1]
        args = [
        "--D", "{}".format(D),
        "--N", "{}".format(N),
        ]
        C = get_rand_ints(D)
        S = get_rand_ints(D * N)
        args.append("--C")
        args.extend(list(map(str, C)))
        args.append("--S")
        args.extend(list(map(str, S)))

        two_C = [2 * C[i] for i in range(D)]
        args.append("--two_C")
        args.extend(list(map(str, two_C)))
        C_sqr_sum = sum(val * val for val in C)
        args.append("--C_sqr_sum")
        args.append(str(C_sqr_sum))
        S_sqr_sum = [sum(S[i * D + j] * S[i * D + j] for j in range(D)) for i in range(N)]
        args.append("--S_sqr_sum")
        args.extend(list(map(str, S_sqr_sum)))
        differences = [0] * N
        args.append("--differences")
        args.extend(list(map(str, differences)))

        label = "D: {}, N: {}".format(D, N)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_chapterfour_figure_12_inputs() -> tuple[list[InputArgs], int]:
    all_args = []
    non_vec_up_to = 6
    x = random.randint(1, 100)
    y = random.randint(1, 100)
    args = [
    "--x", str(x),
    "--y", str(y)
    ]
    label = "x={}, y={}".format(x, y)
    all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_convex_hull_inputs():
    all_args = []
    non_vec_up_to = 0
    #for N in [4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]:
    # for N in [32, 256]:
    for N in [32, 64, 128, 256]:
        args = [
        "--N", "{}".format(N),
        ]
        X_coords = get_rand_ints(N)
        Y_coords = get_rand_ints(N)
        result_X = [0]*N
        result_Y = [0]*N
        args.append("--X_coords")
        args.extend(list(map(str, X_coords)))
        args.append("--Y_coords")
        args.extend(list(map(str, Y_coords)))
        args.append("--result_X")
        args.extend(list(map(str, result_X)))
        args.append("--result_Y")
        args.extend(list(map(str, result_Y)))
        label = "N: {}".format(N)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_count_102_inputs():
    all_args = []
    non_vec_up_to = 0
    #for N in [8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]:
    for N in [1024, 4096]:
        args = [
        "--N", "{}".format(N),
        ]
        Seq = get_rand_ints(N, min=0, max=2)
        Syms = [1, 0, 2]
        args.append("--Seq")
        args.extend(list(map(str, Seq)))
        args.append("--Syms")
        args.extend(list(map(str, Syms)))
        label = "N: {}".format(N)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_count_10s_inputs():
    all_args = []
    non_vec_up_to = 0
    #for N in [8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]:
    for N in [1024, 4096]:
        args = [
        "--N", "{}".format(N),
        ]
        Seq = get_rand_ints(N, min=0, max=2)
        Syms = [0, 1]
        args.append("--Seq")
        args.extend(list(map(str, Seq)))
        args.append("--Syms")
        args.extend(list(map(str, Syms)))
        label = "N: {}".format(N)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_count_123_inputs():
    all_args = []
    non_vec_up_to = 0
    #for N in [8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]:
    for N in [1024, 4096]:
        args = [
        "--N", "{}".format(N),
        ]
        Seq = get_rand_ints(N, min=1, max=4)
        Syms = [1, 2, 3]
        args.append("--Seq")
        args.extend(list(map(str, Seq)))
        args.append("--Syms")
        args.extend(list(map(str, Syms)))
        label = "N: {}".format(N)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_cryptonets_max_pooling_inputs():
    all_args = []
    non_vec_up_to = 0
    #for config in [[4, 4], [8, 8], [16, 16], [32, 32], [64, 64]]:
    # for config in [[64, 64]]:
    for config in [[16, 16]]:
        rows = config[0]
        cols = config[1]
        rows_res = rows // 2
        cols_res = cols // 2

        args = [
        "--cols", str(cols),
        "--rows", str(rows),
        "--cols_res", str(cols_res),
        "--rows_res", str(rows_res)
        ]
        vals = [i + 2 for i in range(rows * cols)]
        output_size = int(cols * rows / 4)
        OUTPUT_res = [0] * output_size
        args.append("--vals")
        args.extend(list(map(str, vals)))
        args.append("--OUTPUT_res")
        args.extend(list(map(str, OUTPUT_res)))
        label = "rows: {}, cols: {}".format(rows, cols)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_db_cross_join_trivial_inputs():
    all_args = []
    non_vec_up_to = 0
    #for N in [4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]:
    for N in [32, 64]:
        Len_A = N
        Len_B = N
        args = [
        "--Len_A", str(Len_A),
        "--Len_B", str(Len_B)
        ]
        A = get_rand_ints(Len_A * 2)
        B = get_rand_ints(Len_B * 2)
        res = [0 for i in range(Len_A * Len_B * 3)]
        args.append("--A")
        args.extend(list(map(str, A)))
        args.append("--B")
        args.extend(list(map(str, B)))
        args.append("--res")
        args.extend(list(map(str, res)))
        label = "{}, {}".format(Len_A, Len_B)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_db_variance_inputs():
    all_args = []
    non_vec_up_to = 0
    #for N in [8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]:
    for N in [512, 1024, 2048, 4096]:
        args = [
        "--len", "{}".format(N),
        ]
        A = get_rand_ints(N)
        V = [0 for i in range(N)]
        args.append("--A")
        args.extend(list(map(str, A)))
        args.append("--V")
        args.extend(list(map(str, V)))
        label = "len: {}".format(N)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_histogram_inputs():
    all_args = []
    num_bins = 5
    non_vec_up_to = 0
    #for N in [8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]:
    for N in [512, 4096]:
        args = [
        "--num_bins", "{}".format(num_bins),
        "--N", "{}".format(N),
        ]
        A = get_rand_ints(N, min=0, max=num_bins-1)
        B = get_rand_ints(N)
        R = [0 for i in range(N)]
        args.append("--A")
        args.extend(list(map(str, A)))
        args.append("--B")
        args.extend(list(map(str, B)))
        args.append("--result")
        args.extend(list(map(str, R)))
        label = "N: {}".format(N)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_inner_product_inputs()-> tuple[list[InputArgs], int]:
    all_args = []
    non_vec_up_to = 0#8
    #for N in [4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]:
    for N in [512, 4096]:
        args = [
        "--N", "{}".format(N),
        ]
        A = get_rand_ints(N)
        B = get_rand_ints(N)
        args.append("--A")
        args.extend(list(map(str, A)))
        args.append("--B")
        args.extend(list(map(str, B)))
        label = "N: {}".format(N)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_kmeans_iteration_inputs():
    all_args = []
    num_bins = 5
    non_vec_up_to = 0
    #for config in [[32, 5], [32, 8], [64, 8], [128, 8], [200, 5], [256, 8]]:
    for config in [[32, 5], [256, 8]]:
        len = config[0]
        num_cluster = config[1]
        data_x = [i for i in range(len)]
        data_y = [len - i for i in range(len)]
        cluster_x = [i for i in range(num_cluster)]
        cluster_y = [i + 1 for i in range(num_cluster)]
        OUTPUT_cluster_x = [0 for i in range(num_cluster)]
        OUTPUT_cluster_y = [0 for i in range(num_cluster)]
        bestMap = [0 for i in range(len)]
        
        args = [
        "--len", str(len),
        "--num_cluster", str(num_cluster),
        ]
        args.append("--data_x")
        args.extend(list(map(str, data_x)))
        args.append("--data_y")
        args.extend(list(map(str, data_y)))
        args.append("--cluster_x")
        args.extend(list(map(str, cluster_x)))
        args.append("--cluster_y")
        args.extend(list(map(str, cluster_y)))
        args.append("--OUTPUT_cluster_x")
        args.extend(list(map(str, OUTPUT_cluster_x)))
        args.append("--OUTPUT_cluster_y")
        args.extend(list(map(str, OUTPUT_cluster_y)))
        args.append("--bestMap")
        args.extend(list(map(str, bestMap)))

        label = "len1: {}, len2: {}".format(len, num_cluster)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_longest_odd_10_inputs():
    all_args = []
    non_vec_up_to = 0
    #for N in [8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096]:
    for N in [2048]:
        args = [
        "--N", str(N),
        ]
        Seq = get_rand_ints(N, min=0, max=1)
        Syms = [0, 1]
        args.append("--Seq")
        args.extend(list(map(str, Seq)))
        args.append("--Syms")
        args.extend(list(map(str, Syms)))
        label = "N: {}".format(N)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_max_dist_between_syms_inputs():
    all_args = []
    non_vec_up_to = 0
    # for N in [8, 16, 32, 64, 128, 256, 512, 1024, 4096]:
    for N in [1024, 2048]:
        args = [
        "--N", "{}".format(N),
        ]
        Seq = get_rand_ints(N)
        some_i = random.randint(0, len(Seq)-1)
        Sym = Seq[some_i]
        args.append("--Seq")
        args.extend(list(map(str, Seq)))
        args.append("--Sym")
        args.append(str(Sym))
        label = "N: {}".format(N)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_mnist_relu_inputs()-> tuple[list[InputArgs], int]:
    all_args = []
    non_vec_up_to = 0
    #for config in [[16, 16], [16, 32], [16, 64], [16, 128], [16, 256], [16, 512], [16, 1024]]:
    for config in [[16, 512], [16, 2048]]:
        len_inner = config[0]
        len_outer = config[1]
        args = [
        "--len_inner", "{}".format(len_inner),
        "--len_outer", "{}".format(len_outer),
        ]
        input = [(i % 2) for i in range(len_inner * len_outer)]
        OUTPUT_res = [0 for i in range(len_inner * len_outer)]
        args.append("--input")
        args.extend(list(map(str, input)))
        args.append("--OUTPUT_res")
        args.extend(list(map(str, OUTPUT_res)))
        label = "{}, {}".format(len_inner, len_outer)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_psi_inputs()-> tuple[list[InputArgs], int]:
    all_args = []
    non_vec_up_to = 0
    #for config in [[16, 16], [32, 32], [64, 64], [128, 128], [256, 256], [512, 512], [1024, 1024]]:#[2048, 2084], [4096, 4096]]:
    for config in [[128, 128], [1024, 1024]]:
        SA = config[0]
        SB = config[1]
        args = [
        "--D", "{}".format(SA),
        "--R", "{}".format(SB),
        ]
        A = get_rand_ints(SA)
        B = get_rand_ints(SB)
        result = [0 for i in range(SA)]
        args.append("--A")
        args.extend(list(map(str, A)))
        args.append("--B")
        args.extend(list(map(str, B)))
        args.append("--result")
        args.extend(list(map(str, result)))
        label = "SA: {}, SB: {}".format(SA, SB)
        all_args.append(InputArgs(label, args))
    return (all_args, non_vec_up_to)

def get_inputs(name: str) -> tuple[list[InputArgs], int]:
    if name == "biometric":
        return get_biometric_inputs()
    if name == "biometric_fast":
        return get_biometric_fast_inputs()
    if name == "chapterfour_figure_12": # millionaire's problem, not interesting
        return get_chapterfour_figure_12_inputs()
    if name == "convex_hull" or name == "minimal_points":
        return get_convex_hull_inputs()
    if name == "count_102" or name == "longest_102":
        return get_count_102_inputs()
    if name == "count_10s":
        return get_count_10s_inputs()
    if name == "count_123":
        return get_count_123_inputs()
    if name == "cryptonets_max_pooling":
        return get_cryptonets_max_pooling_inputs()
    if name == "db_cross_join_trivial": # could only do up to 64
        return get_db_cross_join_trivial_inputs()
    if name == "db_variance":
        return get_db_variance_inputs()
    if name == "histogram":
        return get_histogram_inputs()
    if name == "inner_product":
        return get_inner_product_inputs()
    if name == "kmeans_iteration":
        return get_kmeans_iteration_inputs()
    if name == "longest_odd_10": # could not run for 4096 on MOTION
        return get_longest_odd_10_inputs()
    if name == "max_dist_between_syms" or name == "max_sum_between_syms":
        return get_max_dist_between_syms_inputs()
    if name == "mnist_relu":
        return get_mnist_relu_inputs()
    if name == "psi": # could not run from 2048 and 4096
        return get_psi_inputs()
    return [[], 0]


def saveToJSON(results, resultsDetailed):
    fileNames = [timestamp + '_mixerOutputs.json', timestamp + '_DETAILED_mixerOutputs.json']
    for fileName in fileNames:
        results = json.dumps(resultsDetailed if '_DETAILED_' in fileName else results, sort_keys=True, indent=4)
        print(f'Writing {fileName}')
        with open(fileName, 'w') as f:
            f.write(results)


def run_client_role_spdz(resultsDict, resultsDetailedDict):
    spdzDict = resultsDict['MP-SPDZ']
    spdzDetailedDict = resultsDetailedDict['MP-SPDZ']

    all_stats = []
    for test_case_dir in os.scandir(test_context.STAGES_DIR):
        if test_case_dir.name in test_context.SKIPPED_TESTS[None]:
            continue

        if test_case_dir.name not in spdzDict.keys():
            spdzDict[test_case_dir.name] = dict()
            spdzDetailedDict[test_case_dir.name] = dict()

        all_args, _ = get_inputs(test_case_dir.name)
        if len(all_args) == 0:
            continue

        task_stats = StatsForTask(test_case_dir.name, [])

        for args in all_args:
            argStr = str(args.label).replace(':', ' =')
            if argStr not in spdzDict[test_case_dir.name].keys():
                spdzDict[test_case_dir.name][argStr] = dict()
                spdzDetailedDict[test_case_dir.name][argStr] = dict()

            log.info("\n{} - arguments: {}".format(test_case_dir.name, args.args));
            for protocol in [None, 'A', 'B', 'X', 'Y']:
                pName = protocol if protocol else 'mixed'

                if pName not in spdzDict[test_case_dir.name][argStr].keys():
                    spdzDict[test_case_dir.name][argStr][pName] = dict()
                    spdzDetailedDict[test_case_dir.name][argStr][pName] = dict()
                if type(spdzDict[test_case_dir.name][argStr][pName]) == dict and 'compileTime' not in spdzDict[test_case_dir.name][argStr][pName].keys():
                    with open(os.path.join(test_case_dir.path, 'input.py'), 'r') as f:
                        input_py = f.read().strip()
                    argsList = parse_list(args.args)
                    if not args is None:
                        input_py = motion_replace_definitions(input_py, argsList)
                    totalTime = 0
                    timeList = []
                    try:
                        for j in range(NUM_ITERS):
                            startTime = time.perf_counter()
                            cfg = compiler.compile(
                                filename=f"{test_case_dir.name}.py",
                                text=input_py,
                                backend=Backend.MP_SPDZ,
                                quiet=True,
                                run_vectorization=True,
                                protocolSets=[{protocol}] if protocol else None,
                                mixing=True,
                                costType='time',
                                mixOnly=True)
                            endTime = time.perf_counter()
                            timeList.append(endTime - startTime)
                            totalTime += endTime - startTime
                        avgTime = totalTime / NUM_ITERS
                        spdzDict[test_case_dir.name][argStr][pName]['compileTime'] = avgTime
                        spdzDict[test_case_dir.name][argStr][pName]['predTime'] = cfg.total_cost
                        spdzDetailedDict[test_case_dir.name][argStr][pName]['compileTime'] = timeList
                    except Exception as e:
                        if str(e) == 'No valid mix found':
                            spdzDict[test_case_dir.name][argStr][pName]['compileTime'] = 'N/A'
                            spdzDict[test_case_dir.name][argStr][pName]['predTime'] = 'N/A'
                            spdzDetailedDict[test_case_dir.name][argStr][pName]['compileTime'] = ['N/A']
                        else:
                            print(e)
                            sys.exit(1)
                    saveToJSON(resultsDict, resultsDetailedDict)

        log.info("task {} DONE".format(task_stats.label))


def run_client_role_motion(resultsDict, resultsDetailedDict):
    motionDict = resultsDict['MOTION']
    motionDetailedDict = resultsDetailedDict['MOTION']
    all_stats = []
    for test_case_dir in os.scandir(test_context.STAGES_DIR):
        if test_case_dir.name in test_context.SKIPPED_TESTS[None]:
            continue

        if test_case_dir.name not in motionDict.keys():
            motionDict[test_case_dir.name] = dict()
            motionDetailedDict[test_case_dir.name] = dict()

        all_args, _ = get_inputs(test_case_dir.name)
        if len(all_args) == 0:
            continue

        task_stats = StatsForTask(test_case_dir.name, [])

        for args in all_args:
            argStr = str(args.label).replace(':', ' =')
            if argStr not in motionDict[test_case_dir.name].keys():
                motionDict[test_case_dir.name][argStr] = dict()
                motionDetailedDict[test_case_dir.name][argStr] = dict()

            log.info("\n{} - arguments: {}".format(test_case_dir.name, args.args));

            for protocol in [None, 'ArithmeticGmw', 'BooleanGmw', 'Bmr']:
                pName = protocol if protocol else 'mixed'

                if pName not in motionDict[test_case_dir.name][argStr].keys():
                    motionDict[test_case_dir.name][argStr][pName] = dict()
                    motionDetailedDict[test_case_dir.name][argStr][pName] = dict()
                if type(motionDict[test_case_dir.name][argStr][pName]) == dict and 'compileTime' not in motionDict[test_case_dir.name][argStr][pName].keys():
                    with open(os.path.join(test_case_dir.path, 'input.py'), 'r') as f:
                        input_py = f.read().strip()
                    argsList = parse_list(args.args)
                    if not args is None:
                        input_py = motion_replace_definitions(input_py, argsList)
                    totalTime = 0
                    timeList = []
                    try:
                        for j in range(NUM_ITERS):
                            startTime = time.perf_counter()
                            cfg = compiler.compile(
                                filename=f"{test_case_dir.name}.py",
                                text=input_py,
                                backend=Backend.MOTION,
                                quiet=True,
                                run_vectorization=True,
                                protocol=protocol,
                                mixing=True,
                                costType='time',
                                mixOnly=True)
                            endTime = time.perf_counter()
                            timeList.append(endTime - startTime)
                            totalTime += endTime - startTime
                        avgTime = totalTime / NUM_ITERS
                        motionDict[test_case_dir.name][argStr][pName]['compileTime'] = avgTime
                        motionDict[test_case_dir.name][argStr][pName]['predTime'] = cfg.total_cost
                        motionDetailedDict[test_case_dir.name][argStr][pName]['compileTime'] = timeList
                    except Exception as e:
                        if str(e) == 'No valid mix found':
                            motionDict[test_case_dir.name][argStr][pName]['compileTime'] = 'N/A'
                            motionDict[test_case_dir.name][argStr][pName]['predTime'] = 'N/A'
                            motionDetailedDict[test_case_dir.name][argStr][pName]['compileTime'] = ['N/A']
                        else:
                            print(e)
                            sys.exit(1)
                    
                    saveToJSON(resultsDict, resultsDetailedDict)

                
        log.info("task {} DONE".format(task_stats.label))


if __name__ == "__main__":
    parser = ArgumentParser(
        description="runs and collects benchmarks statistics for the paper. (assumes correct network config)")

    parser.add_argument('-b', '--backend', 
        help="choices for backend", 
        choices=['MOTION','MP-SPDZ'],
        required=True
    )

    parser.add_argument('-f', '--file',
        help='file storing a partial table - this file will NOT be overwritten',
        required=False
    )

    args = parser.parse_args()

    
    # read previous results (if supplied)
    timestamp = datetime.datetime.strftime(datetime.datetime.now(), '%Y_%m_%d_%H_%M_%S')
    resultsDict = dict()
    resultsDetailedDict = dict()
    if args.file:
        assert (isfile(args.file))
        assert (isfile("DETAILED_" + args.file))
        resultsDict = json.load(open(args.file))
        resultsDetailedDict = json.load(open("DETAILED_" + args.file))
    if args.backend not in resultsDict.keys():
        resultsDict[args.backend] = dict()
        resultsDetailedDict[args.backend] = dict()
    if args.backend == 'MOTION':
        run_client_role_motion(resultsDict, resultsDetailedDict)
    elif args.backend == 'MP-SPDZ':
        run_client_role_spdz(resultsDict, resultsDetailedDict)
    else:
        raise Exception("BACKEND NOT IMPLEMENTED")

    # write results to output file
    saveToJSON(resultsDict, resultsDetailedDict)
    # print(json.dumps(resultsDict, sort_keys=True, indent=4))
    # print(json.dumps(resultsDetailedDict, sort_keys=True, indent=4))
