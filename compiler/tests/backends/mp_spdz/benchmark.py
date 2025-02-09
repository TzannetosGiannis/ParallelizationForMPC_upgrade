from time import time
import shutil
import os
import subprocess
import re
from typing import Optional

import compiler
from compiler.backends import Backend


class BenchmarkOutput:
    result: str
    time_seconds: float
    data_sent_mb: float
    communication_rounds:str

    def __init__(self, stdout: str) -> None:
        
        def parse(pattern: str) -> tuple[str, ...]:
            m = re.search(rf"^\s*{pattern}\s*$", stdout, re.MULTILINE)
            assert m is not None, repr(stdout)
            return m.groups()

        self.result = parse(r"MPC BENCHMARK OUTPUT (.+)")[0]
        self.time_seconds = float(parse(r"Time = (.+) seconds")[0])
        self.data_sent_mb = float(parse(r"Data sent = (.+) MB.*")[0])
        self.communication_rounds = parse(r"Data sent = .*~(\d+)\s*rounds.*")[0]

def _parse_int_pattern(pattern: str, stdout: str, mixed:bool = False) -> int:
    m = re.search(rf"^\s*{pattern}\s*$", stdout, re.MULTILINE)
    # if we compile in mixed this means that if the protocol schosen
    # is binary then we there only be bit triples and the arith (int_triples) will not
    # be in the stdout, thus we need to relaz the assertion for mixed
    if not mixed:
        assert m is not None, repr(stdout)
        return int(m.groups()[0])
    else:
        if m is None:
            return 0
        else:
            return int(m.groups()[0])


class CompileStatsArith:
    time: float
    int_triples: int
    int_opens: int
    vm_rounds: int

    def __init__(self, time: float, stdout: str) -> None:
        self.time = time
        self.int_triples = _parse_int_pattern(r"(\d+) integer triples", stdout)
        self.int_opens = _parse_int_pattern(r"(\d+) integer opens", stdout)
        self.vm_rounds = _parse_int_pattern(r"(\d+) virtual machine rounds", stdout)

class CompileStatsMixed:
    time: float
    int_triples: int
    bit_triples: int
    int_opens: int
    vm_rounds: int

    def __init__(self, time: float, stdout: str) -> None:
        self.time = time
        self.int_triples = _parse_int_pattern(r"(\d+) integer triples", stdout, mixed = True)
        self.int_opens = _parse_int_pattern(r"(\d+) integer opens", stdout, mixed = True)
        self.bit_triples = _parse_int_pattern(r"(\d+) bit triples", stdout, mixed = True)
        self.vm_rounds = _parse_int_pattern(r"(\d+) virtual machine rounds", stdout)


class CompileStatsBin:
    time: float
    bit_triples: int
    vm_rounds: int

    def __init__(self, time: float, stdout: str) -> None:
        self.time = time
        self.bit_triples = _parse_int_pattern(r"(\d+) bit triples", stdout)
        self.vm_rounds = _parse_int_pattern(r"(\d+) virtual machine rounds", stdout)


def get_mpc_file_name(benchmark_name: str, vectorized: bool,mixed:bool) -> str:
    postfix = ""
    if vectorized:
        postfix = "_vec"
    if mixed:
        postfix += "_mixed"
    return f"{benchmark_name}{postfix}"

def bmr_workaround() -> None:
    """
    Workaround to get `make semi-bmr-party.x` to succeed
    """
    from glob import glob

    submodule_path = Backend.MP_SPDZ.submodule_path()
    targets = [
        p.replace(".cpp", ".o") for p in glob("BMR/**/*.cpp", root_dir=submodule_path)
    ]
    subprocess.run(["make", "--"] + targets, cwd=submodule_path, check=True)


def set_up_spdz_compile(
    benchmark_name: str, benchmark_path: str, vectorized: bool, mixed: bool, protocolsSPDZ = [{'A', 'B'}, {'X', 'B'}, {'Y', 'B'}]
) -> str:
    input_fname = os.path.join(benchmark_path, "input.py")

    with open(input_fname, "r") as f:
        input_py = f.read().strip()

    submodule_path = Backend.MP_SPDZ.submodule_path()
    mpc_file = get_mpc_file_name(benchmark_name, vectorized,mixed)
    app_path = os.path.join(submodule_path, "Programs", "Source", f"{mpc_file}.mpc")
    
    compiler.compile(
        filename=f"{benchmark_name}.py",
        text=input_py,
        backend=Backend.MP_SPDZ,
        quiet=True,
        run_vectorization=vectorized,
        out_dir=app_path,
        overwrite_out_dir=True,
        protocol=None,
        mixing=mixed,
        protocolsSPDZ=protocolsSPDZ
    )
    
    # Copy vectorization library so compiled programs can use it
    shutil.copyfile(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "compiler",
            "backends",
            "mp_spdz",
            "library.py",
        ),
        os.path.join(submodule_path, "vectorization_library.py"),
    )
    return app_path


def _get_compile_stats_common(
    benchmark_name: str, benchmark_path: str, binary: Optional[int], vectorized: bool, mixed: bool,protocolsSPDZ = [{'A', 'B'}, {'X', 'B'}, {'Y', 'B'}]
) -> tuple[float, str]:
    set_up_spdz_compile(
        benchmark_name=benchmark_name,
        benchmark_path=benchmark_path, 
        vectorized=vectorized,
        mixed=mixed,
        protocolsSPDZ=protocolsSPDZ
    )
    mpc_file = get_mpc_file_name(benchmark_name, vectorized,mixed)
    submodule_path = Backend.MP_SPDZ.submodule_path()

    start_time = time()
    p = subprocess.Popen(
        ["./compile.py", mpc_file], # + ([] if binary is None else ["-B", str(binary)]) we dont need this anymore since we can produce B code
        cwd=submodule_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = p.communicate(timeout=600)
    assert p.returncode == 0, stderr
    end_time = time()
    compile_time = end_time - start_time
    return compile_time, stdout


def get_compile_stats_arith(
    benchmark_name: str, benchmark_path: str, vectorized: bool
) -> CompileStatsArith:
    compile_time, stdout = _get_compile_stats_common(
        benchmark_name=benchmark_name,
        benchmark_path=benchmark_path,
        binary=None,
        vectorized=vectorized,
        mixed=False
    )
    return CompileStatsArith(time=compile_time, stdout=stdout)


def get_compile_stats_mixed(
    benchmark_name: str, benchmark_path: str
) -> CompileStatsMixed:
    compile_time, stdout = _get_compile_stats_common(
        benchmark_name=benchmark_name,
        benchmark_path=benchmark_path,
        binary=None,
        vectorized=True,
        mixed=True
    )
    return CompileStatsMixed(time=compile_time, stdout=stdout)

def get_compile_stats_bin(
    benchmark_name: str, benchmark_path: str, vectorized: bool, binary: int
) -> CompileStatsBin:
    compile_time, stdout = _get_compile_stats_common(
        benchmark_name=benchmark_name,
        benchmark_path=benchmark_path,
        binary=binary,
        vectorized=vectorized,
        mixed=True,
        protocolsSPDZ=[{'B'}]
        

    )
    return CompileStatsBin(time=compile_time, stdout=stdout)

def run_benchmark(
    benchmark_name: str,
    benchmark_path: str,
    protocol: str,
    vectorized=True,
    timeout=60 * 60,
    mixed=False,
    additional_flags=[],
    protocolsSPDZ = [{'A', 'B'}, {'X', 'B'}, {'Y', 'B'}]
) -> BenchmarkOutput:

    set_up_spdz_compile(benchmark_name, benchmark_path, vectorized,mixed,protocolsSPDZ)
    mpc_file = get_mpc_file_name(benchmark_name, vectorized,mixed)
    submodule_path = Backend.MP_SPDZ.submodule_path()

    print("RUNNING BENCH",benchmark_name,benchmark_path,submodule_path)    
    # Write an indicator file when running `make setup` so it only needs to run once
    setup_indicator_path = os.path.join(submodule_path, ".ran-make-setup")

    if not os.path.exists(setup_indicator_path):
        subprocess.run(["make", "setup"], cwd=submodule_path, check=True)
        with open(setup_indicator_path, "w") as _:
            pass

    if "bmr" in protocol:
        bmr_workaround()

    # Adding compile time stats
    start_time = time()
    p = subprocess.Popen(
    ["./compile.py", mpc_file] + ([] if protocol != "semi-bin" else ["-B", str(32)]),
        cwd=submodule_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    stdout, stderr = p.communicate(timeout=600)
    assert p.returncode == 0, stderr
    end_time = time()
    compile_time = end_time - start_time
    print("COMPILE TIME --- %s seconds ---" % compile_time)
    # End of compile time status
    print("tzannnn",["Scripts/compile-run.py", "-v", "-E", protocol, mpc_file," ".join(additional_flags)])
    p = subprocess.Popen(
        ["Scripts/compile-run.py", "-v", "-E", protocol, mpc_file," ".join(additional_flags)],
        cwd=submodule_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = p.communicate(timeout=timeout)
    assert p.returncode == 0, stderr
    print(stdout)
    return BenchmarkOutput(stdout)
