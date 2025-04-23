import ast
import sys
import traceback
from typing import Optional

from .ast_to_restricted_ast import ast_to_restricted_ast
from .restricted_ast_to_tac_cfg import restricted_ast_to_tac_cfg
from .tac_cfg_to_ssa import tac_cfg_to_ssa
from .ssa_phi_to_mux import replace_phi_with_mux
from .dead_code_elim import dead_code_elim
from .ssa_to_loop_linear_code import ssa_to_loop_linear_code
from .dep_graph import DepGraph
from .type_analysis import type_check
from .copy_propagation import copy_propagation
from .common_subexpression_elimination import common_subexpression_elimination
from . import loop_linear_code
from .backends import Backend
from . import vectorize
from .protocol_mixing import mix_protocols


def compile(
    filename: str,
    text: str,
    backend: Optional[Backend],
    costType: str = 'time',
    quiet: bool = True,
    run_vectorization: bool = True,
    out_dir: Optional[str] = None,
    overwrite_out_dir: bool = False,
    protocol="",
    mixing: bool = False,
    protocolSets: Optional[list[set[str]]] = None,
    mixOnly = False
):
    if protocolSets == None and mixing == True:
        protocolsMotion = [{'A', 'B', 'Y'}]

        if protocol == 'ArithmeticGmw':
            protocolsMotion = [{'A'}]
            protocol = None
        if protocol == 'BooleanGmw':
            protocolsMotion = [{'B'}]
            protocol = None
        if protocol == 'Bmr':
            protocol = None
            protocolsMotion = [{'Y'}]
        
        protocolsSPDZ = [{'A', 'B'}, {'X', 'B'}, {'Y', 'B'}]
        protocolSets = protocolsSPDZ if  not (backend  is None) and backend == backend.MP_SPDZ else protocolsMotion

    try:
        ast_module = ast.parse(text, filename=filename)
        ast_node = ast_to_restricted_ast(node=ast_module, filename=filename, text=text)
    except SyntaxError as err:
        traceback.print_exception(None, value=err, tb=None)
        sys.exit(1)

    if not quiet:
        print("Restricted AST:")
        print(ast_node)
        print()

    tac = restricted_ast_to_tac_cfg(ast_node)
    if not quiet:
        print("Three-address code control flow graph:")
        print(tac)
        print()

    ssa = tac_cfg_to_ssa(tac)
    if not quiet:
        print("Static single assignment form:")
        print(ssa)
        print()

    replace_phi_with_mux(ssa)
    if not quiet:
        print("MUX static single assignment form:")
        print(ssa)
        print()

    dead_code_elim(ssa)
    if not quiet:
        print("Dead code elimination:")
        print(ssa)
        print()

    linear = ssa_to_loop_linear_code(ssa)
    if not quiet:
        print("Linear code with loops:")
        print(linear)
        print()

    dep_graph = DepGraph(linear)
    if not quiet:
        print("Dependence graph:")
        print(dep_graph)
        print()

    vectorize.remove_infeasible_edges(linear, dep_graph)
    if not quiet:
        print("Dependence graph after removal of infeasible edges:")
        print(dep_graph)
        print()

    (linear, type_env) = type_check(linear, dep_graph)
    if not quiet:
        print("Unvectorized type environment:")
        print(type_env)
        print()

    if run_vectorization:
        (linear, dep_graph) = vectorize.basic_vectorization_phase_1(linear, type_env)
        if not quiet:
            print("Basic Vectorization phase 1:")
            print(linear)
            print()

        (linear, dep_graph) = vectorize.basic_vectorization_phase_2(linear)
        if not quiet:
            print("Basic Vectorization phase 2:")
            print(linear)
            print()

        (linear, type_env) = type_check(linear, dep_graph)
        if not quiet:
            print("Vectorized type environment:")
            print(type_env)
            print()

    (linear, dep_graph, type_env) = copy_propagation(linear, dep_graph, type_env)
    if not quiet:
        print("Copy propagation:")
        print(linear)
        print()

    (linear, dep_graph, type_env) = common_subexpression_elimination(linear, dep_graph, type_env)
    if not quiet:
        print("Common subexpression elimination:")
        print(linear)
        print()

    if mixing:
        assert protocolSets is not None
        mixed_config = mix_protocols(filename, type_env, linear.body, dep_graph, backend, costType, protocolSets=protocolSets,python_text=text)
        if not quiet:
            print("Protocol Mixing Assignments:")
            print(mixed_config)
            print()
        if mixOnly:
            return mixed_config

    if backend:
        if mixing:
            backend_code = backend.render_mixed_function(linear, type_env, run_vectorization,mixed_config)
        else:
            backend_code = backend.render_function(linear, type_env, run_vectorization)
        
        if not quiet:
            print("Backend code:")
            print(backend_code)
            print()
        
        if out_dir:
            render_params = {
                "out_dir": out_dir,
                "overwrite": overwrite_out_dir,
            }
            if protocol is not None:
                if protocol not in backend.valid_protocols():
                    raise ValueError(
                        f"Invalid protocol: {protocol}. Valid protocols are: {backend.valid_protocols()}"
                    )
                render_params["protocol"] = protocol

            
            if mixing:
                backend.render_application(
                    linear, type_env, render_params, run_vectorization, True, mixed_config
                )
            else:
                backend.render_application(
                    linear, type_env, render_params, run_vectorization
                )
