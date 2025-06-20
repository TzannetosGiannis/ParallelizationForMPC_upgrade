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
    def extract_dict(self):
        return {
            "result": self.result,
            "time_seconds": self.time_seconds,
            "data_sent_mb": self.data_sent_mb,
            "communication_rounds": self.communication_rounds
        }
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


def replace_definitions(content, replacements):
   
    for key, value in replacements.items():
        pattern = rf"^{key}\s*=\s*.*"  # Matches the variable definition line
        value_str = str(value)  # Format list properly
        replacement_line = f"{key} = {value_str}"
        content = re.sub(pattern, replacement_line, content, flags=re.MULTILINE)

    return content

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
    benchmark_name: str, benchmark_path: str, vectorized: bool, mixed: bool, protocolSets = [{'A', 'B'}, {'X', 'B'}, {'Y', 'B'}],args=None,costType="time"
) -> str:
    input_fname = os.path.join(benchmark_path, "input.py")

    with open(input_fname, "r") as f:
        input_py = f.read().strip()
    
    if not args is None:
        input_py = replace_definitions(input_py,args)

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
        protocolSets=protocolSets,
        costType=costType
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
        protocolSets=protocolsSPDZ
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
    protocolSets = [{'A', 'B'}, {'X', 'B'}, {'Y', 'B'}],
    args=None,
    costType=None
) -> BenchmarkOutput:

    set_up_spdz_compile(benchmark_name, benchmark_path, vectorized,mixed,protocolSets,args=args,costType=costType)
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


def compile_benchmark(
    benchmark_name: str, benchmark_path: str, vectorized: bool, mixed: bool = False,costType:str = None,args=None, protocol:str=None
) -> str:
    protocolSets = [{protocol}] if protocol else [{'A', 'B'}, {'X', 'B'}, {'Y', 'B'}]

    set_up_spdz_compile(benchmark_name, benchmark_path, vectorized,mixed,costType=costType,args=args,protocolSets=protocolSets)
    mpc_file = get_mpc_file_name(benchmark_name, vectorized,mixed)
    submodule_path = Backend.MP_SPDZ.submodule_path()

    print("RUNNING BENCH",benchmark_name,benchmark_path,submodule_path)    
    # Write an indicator file when running `make setup` so it only needs to run once
    setup_indicator_path = os.path.join(submodule_path, ".ran-make-setup")

    if not os.path.exists(setup_indicator_path):
        subprocess.run(["make", "setup"], cwd=submodule_path, check=True)
        with open(setup_indicator_path, "w") as _:
            pass

    # Adding compile time stats
    start_time = time()
    p = subprocess.Popen(
    ["./compile.py", mpc_file],
        cwd=submodule_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    stdout, stderr = p.communicate()
    assert p.returncode == 0, stderr
    end_time = time()
    compile_time = end_time - start_time
    print("COMPILE TIME --- %s seconds ---" % compile_time)
    return mpc_file


def run_benchmark_for_party(
    myid: str, party0_mpc_addr: str, benchmark_name: str, benchmark_path: str, protocol: str, vectorized,
    timeout:int, cmd_args= None,compile_again=True
) -> BenchmarkOutput:
    
    if compile_again == True:
        mpc_file = compile_benchmark(benchmark_name, benchmark_path, vectorized,mixed=True,costType='time',args=cmd_args, protocol=protocol)
    else:
        mpc_file = get_mpc_file_name(benchmark_name,vectorized,mixed=True)
    submodule_path = Backend.MP_SPDZ.submodule_path()
    exe_name = f"{os.path.dirname(os.path.abspath(__file__))}/../../../../backend_submodules/MP-SPDZ/Scripts/../semi-party.x"
    with subprocess.Popen(
        [
            exe_name,
            str(myid),
            mpc_file,
            "-I"
        ]+ (party0_mpc_addr.split()),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=submodule_path
    ) as party:
        try:
            party_stdout_raw, party_stderr = party.communicate(timeout)
        except subprocess.TimeoutExpired:
            party.kill()
            party_stdout_raw, party_stderr = party.communicate(timeout)

        if(party.returncode != 0):
            print("party.returncode: {}".format(party.returncode))
            return None

        return BenchmarkOutput(stdout=party_stdout_raw + party_stderr)

