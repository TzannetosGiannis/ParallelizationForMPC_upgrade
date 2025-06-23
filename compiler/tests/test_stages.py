import ast
import json
import os
import sys
import subprocess
import unittest

import compiler
from compiler.backends import Backend

from . import context as test_context
from .backends import run_benchmark


class StagesTestCase(unittest.TestCase):
    maxDiff = None
    # [TODO] fix the tests for the pytest function to incorporate the 
    # changes of files named mixed_code
    def test_stages(self):
        if test_context.BACKEND:
            self.skipTest("Only verifying output of example applications")

        for test_case_dir in os.scandir(test_context.STAGES_DIR):
            if test_case_dir.name in test_context.SKIPPED_TESTS[None]:
                continue

            print(f"Testing {test_case_dir.name}...")

            stages = dict()

            for stage_file in os.scandir(test_case_dir.path):
                if stage_file.is_file():
                    with open(stage_file.path, "r") as f:
                        stages[stage_file.name] = f.read().strip()

            node = ast.parse(stages["input.py"])

            node = compiler.ast_to_restricted_ast(node, "input.py", stages["input.py"])
            self.assertEqual(str(node), stages["restricted_ast.py"])

            cfg = compiler.restricted_ast_to_tac_cfg(node)
            self.assertEqual(str(cfg), stages["tac_cfg.txt"])

            ssa = compiler.tac_cfg_to_ssa(cfg)
            self.assertEqual(str(ssa), stages["ssa.txt"])

            compiler.replace_phi_with_mux(ssa)
            self.assertEqual(str(ssa), stages["ssa_mux.txt"])

            compiler.dead_code_elim(ssa)
            self.assertEqual(str(ssa), stages["dead_code_elim.txt"])

            loop_linear = compiler.ssa_to_loop_linear_code(ssa)
            self.assertEqual(str(loop_linear), stages["loop_linear.txt"])

            dep_graph = compiler.DepGraph(loop_linear)
            self.assertEqual(str(dep_graph), stages["dep_graph.txt"])

            compiler.vectorize.remove_infeasible_edges(loop_linear, dep_graph)
            self.assertEqual(
                str(dep_graph), stages["dep_graph_remove_infeasible_edges.txt"]
            )

            (loop_linear, type_env) = compiler.type_check(loop_linear, dep_graph)
            self.assertEqual(str(loop_linear), stages["unvectorized_linear.txt"])
            self.assertEqual(str(type_env), stages["unvectorized_type_env.txt"])

            (loop_linear, dep_graph) = compiler.vectorize.basic_vectorization_phase_1(
                loop_linear, type_env
            )
            self.assertEqual(str(loop_linear), stages["bv_phase_1.txt"])
            self.assertEqual(str(dep_graph), stages["bv_phase_1_dep_graph.txt"])

            (
                loop_linear,
                dep_graph,
            ) = compiler.vectorize.basic_vectorization_phase_2(loop_linear)
            self.assertEqual(str(loop_linear), stages["bv_phase_2.txt"])
            self.assertEqual(str(dep_graph), stages["bv_phase_2_dep_graph.txt"])

            (loop_linear, type_env) = compiler.type_check(loop_linear, dep_graph)
            self.assertEqual(str(loop_linear), stages["vectorized_linear.txt"])
            self.assertEqual(str(type_env), stages["vectorized_type_env.txt"])

            (loop_linear, dep_graph, type_env) = compiler.copy_propagation(
                loop_linear, dep_graph, type_env
            )
            self.assertEqual(str(loop_linear), stages["copy_prop_linear.txt"])

            (loop_linear, dep_graph, type_env) = compiler.common_subexpression_elimination(
                loop_linear, dep_graph, type_env
            )
            self.assertEqual(str(loop_linear), stages["copy_subexp_linear.txt"])
            

            for backend in Backend:
                backend_code = backend.render_function(loop_linear, type_env, True)
                self.assertEqual(
                    str(backend_code), stages[f"{backend}_code.txt".lower()]
                )

    def test_example_apps(self):
        if test_context.BACKEND is None:
            self.skipTest("Skipping example application compilation")

        for test_case_dir in os.scandir(test_context.STAGES_DIR):
            name = test_case_dir.name
            if name in (
                test_context.SKIPPED_TESTS[None]
                + test_context.SKIPPED_TESTS[test_context.BACKEND]
            ):
                continue
            print(f"Testing {name}...")
            expected_output = get_test_case_expected_output(test_case_dir.path)
            
            for protocol in test_context.BACKEND.valid_protocols():
                if protocol == "ArithmeticGmw" :
                    continue
                print(f"    Protocol {protocol}...")

                for vectorized in [True]:
                    output = run_benchmark(
                        test_context.BACKEND,
                        name,
                        test_case_dir.path,
                        protocol,
                        vectorized,
                    )
                    assert output
                    party0, party1 = output
                    self.assertEqual(party0.strip(), party1.strip())
                    self.assertEqual(party0.strip(), expected_output.strip())
                    self.assertEqual(party1.strip(), expected_output.strip())

            if str(test_context.BACKEND) == 'MOTION' and "--mixing" in sys.argv:
                # read the stages testcase for the input protocol
                # at this step assume that the input variables have the same protocol

                costType = sys.argv.index('--costType') + 1
                output = run_benchmark(
                    test_context.BACKEND,
                    name,
                    test_case_dir.path,
                    None,
                    True, # for vectorization
                    mixed=True,
                    costType=sys.argv[costType]
                
                )
                assert output
                party0, party1 = output
                self.assertEqual(party0.strip(), party1.strip())
                self.assertEqual(party0.strip(), expected_output.strip())
                self.assertEqual(party1.strip(), expected_output.strip())
            elif str(test_context.BACKEND) == 'MP-SPDZ' and "--mixing" in sys.argv:
                # In case of mpsdz we dont need to specify protocol input as it is part
                # of compilation steps
                costType = sys.argv.index('--costType') + 1
                for protocol in test_context.BACKEND.valid_protocols():
                    print(f"Testing {name}... {protocol} mixed")
                    output = run_benchmark(
                        test_context.BACKEND,
                        name,
                        test_case_dir.path,
                        protocol,
                        True, # for vectorization
                        mixed=True,
                        costType=sys.argv[costType]    
                    )
                    assert output
                    party0, party1 = output
                    self.assertEqual(party0.strip(), party1.strip())
                    self.assertEqual(party0.strip(), expected_output.strip())
                    self.assertEqual(party1.strip(), expected_output.strip())
            
            


def get_test_case_expected_output(test_case_dir: str) -> str:
    """
    Run the benchmark file in a Python interpreter to get the expected output
    for the test inputs.
    """

    input_fname = os.path.join(test_case_dir, "input.py")
    proc = subprocess.run(
        [sys.executable, input_fname],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    return proc.stdout


def regenerate_stages(mixing = False,vectorization = True,costType = 'time'):
    for test_case_dir in os.scandir(test_context.STAGES_DIR):
        if test_case_dir.name in test_context.SKIPPED_TESTS[None]:
            continue

        print(f"Regenerating {test_case_dir.name}...")
        with open(os.path.join(test_case_dir, "input.py"), "r") as f:
            input_text = f.read()

        node = ast.parse(input_text)

        node = compiler.ast_to_restricted_ast(node, "input.py", input_text)
        with open(os.path.join(test_case_dir, "restricted_ast.py"), "w") as f:
            f.write(f"{node}\n")

        cfg = compiler.restricted_ast_to_tac_cfg(node)
        with open(os.path.join(test_case_dir, "tac_cfg.txt"), "w") as f:
            f.write(f"{cfg}\n")

        ssa = compiler.tac_cfg_to_ssa(cfg)
        with open(os.path.join(test_case_dir, "ssa.txt"), "w") as f:
            f.write(f"{ssa}\n")

        compiler.replace_phi_with_mux(ssa)
        with open(os.path.join(test_case_dir, "ssa_mux.txt"), "w") as f:
            f.write(f"{ssa}\n")

        compiler.dead_code_elim(ssa)
        with open(os.path.join(test_case_dir, "dead_code_elim.txt"), "w") as f:
            f.write(f"{ssa}\n")

        loop_linear = compiler.ssa_to_loop_linear_code(ssa)
        with open(os.path.join(test_case_dir, "loop_linear.txt"), "w") as f:
            f.write(f"{loop_linear}\n")

        dep_graph = compiler.DepGraph(loop_linear)
        with open(os.path.join(test_case_dir, "dep_graph.txt"), "w") as f:
            f.write(f"{dep_graph}\n")

        if vectorization:
            compiler.vectorize.remove_infeasible_edges(loop_linear, dep_graph)
            with open(
                os.path.join(test_case_dir, "dep_graph_remove_infeasible_edges.txt"), "w"
            ) as f:
                f.write(f"{dep_graph}\n")

            (loop_linear, type_env) = compiler.type_check(loop_linear, dep_graph)
            with open(os.path.join(test_case_dir, "unvectorized_linear.txt"), "w") as f:
                f.write(f"{loop_linear}\n")
            with open(os.path.join(test_case_dir, "unvectorized_type_env.txt"), "w") as f:
                f.write(f"{type_env}\n")

            (loop_linear, dep_graph) = compiler.vectorize.basic_vectorization_phase_1(
                loop_linear, type_env
            )
            with open(os.path.join(test_case_dir, "bv_phase_1.txt"), "w") as f:
                f.write(f"{loop_linear}\n")
            with open(os.path.join(test_case_dir, "bv_phase_1_dep_graph.txt"), "w") as f:
                f.write(f"{dep_graph}\n")

            (
                loop_linear,
                dep_graph,
            ) = compiler.vectorize.basic_vectorization_phase_2(loop_linear)
            with open(os.path.join(test_case_dir, "bv_phase_2.txt"), "w") as f:
                f.write(f"{loop_linear}\n")
            with open(os.path.join(test_case_dir, "bv_phase_2_dep_graph.txt"), "w") as f:
                f.write(f"{dep_graph}\n")

        (loop_linear, type_env) = compiler.type_check(loop_linear, dep_graph)
        with open(os.path.join(test_case_dir, f"vectorized_linear{'' if vectorization else '_scallar'}.txt"), "w") as f:
            f.write(f"{loop_linear}\n")
        with open(os.path.join(test_case_dir, f"vectorized_type_env{'' if vectorization else '_scallar'}.txt"), "w") as f:
            f.write(f"{type_env}\n")

        (loop_linear, dep_graph, type_env) = compiler.copy_propagation(
            loop_linear, dep_graph, type_env
        )
        with open(os.path.join(test_case_dir, f"copy_prop_linear{'' if vectorization else '_scallar'}.txt"), "w") as f:
            f.write(f"{loop_linear}\n")

        (loop_linear, dep_graph, type_env) = compiler.common_subexpression_elimination(
            loop_linear, dep_graph, type_env
        )
        with open(os.path.join(test_case_dir, f"copy_subexp_linear{'' if vectorization else '_scallar'}.txt"), "w") as f:
            f.write(f"{loop_linear}\n")

        for backend in Backend:
            
            if mixing:
                
                mixed_config = compiler.mix_protocols(f"{test_case_dir.name}.py", type_env, loop_linear.body, dep_graph,  backend,costType,python_text=input_text)
                
                # Convert the dictionary to the desired format
                result = {}
                for var, values in mixed_config.inputs.items():
                    # Construct the new key as name_rename_subscript
                    key = f"{var.name}_{var.rename_subscript}"
                    # Convert the set of values to a list
                    result[key] = list(values)

                
                backend_code = backend.render_mixed_function(loop_linear, type_env, True,mixed_config)
            else:
                backend_code = backend.render_function(loop_linear, type_env, True)
            
            code_name = str(backend)
            if mixing:
                code_name += f"_mixed_{costType}"
            
            if not vectorization:
                code_name += "_scallar"

            with open(
                os.path.join(test_case_dir, f"{code_name}_code.txt".lower()), "w"
            ) as f:
                f.write(f"{backend_code}\n")
