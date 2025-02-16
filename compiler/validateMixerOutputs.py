import ast
import sys
import json
import traceback
import jsondiff

from compiler.ast_to_restricted_ast import ast_to_restricted_ast
from compiler.restricted_ast_to_tac_cfg import restricted_ast_to_tac_cfg
from compiler.tac_cfg_to_ssa import tac_cfg_to_ssa
from compiler.ssa_phi_to_mux import replace_phi_with_mux
from compiler.dead_code_elim import dead_code_elim
from compiler.ssa_to_loop_linear_code import ssa_to_loop_linear_code
from compiler.dep_graph import DepGraph
from compiler.type_analysis import type_check
from compiler.copy_propagation import copy_propagation
from compiler.common_subexpression_elimination import common_subexpression_elimination
from compiler.backends import Backend
from compiler import vectorize
from compiler.protocol_mixing import mix_protocols

importantTestCases = ['biometric', 'biometric_fast', 'chapterfour_figure_12', 'convex_hull', 'count_10s',
                      'count_102', 'count_123', 'cryptonets_max_pooling', 'db_cross_join_trivial', 'db_variance',
                      'histogram', 'inner_product', 'longest_102', 'longest_odd_10', 'max_dist_between_syms',
                      'max_sum_between_syms', 'minimal_points', 'mnist_relu', 'psi']
otherTestCases = ['floyd_warshall', 'inner_product', 'kmeans_iteration', 'longest_1s', 'longest_even_0', 'matrix_multiply']
costTypes = ['time', 'commRounds', 'dataSent']
backends = [Backend.MP_SPDZ, Backend.MOTION]
currentCosts = dict()
save = False
motionMix = [{'A', 'B', 'Y'}]
motionUnmix = [{'A'}, {'B'}, {'Y'}]
spdzMix = [{'A', 'B'}, {'X', 'B'}, {'Y', 'B'}]
spdzUnmix = [{'A'}, {'B'}, {'X'}, {'Y'}]
if len(sys.argv) > 1:
    if sys.argv[1] == 'overwrite':
        save = True


def getMixedConfig(filename, backend, costType, protocolSets):
    with open(filename) as f:
        text = f.read()
    try:
        ast_module = ast.parse(text, filename=filename)
        ast_node = ast_to_restricted_ast(node=ast_module, filename=filename, text=text)
    except SyntaxError as err:
        traceback.print_exception(None, value=err, tb=None)
        sys.exit(1)
    tac = restricted_ast_to_tac_cfg(ast_node)
    ssa = tac_cfg_to_ssa(tac)
    replace_phi_with_mux(ssa)
    dead_code_elim(ssa)
    linear = ssa_to_loop_linear_code(ssa)
    dep_graph = DepGraph(linear)
    vectorize.remove_infeasible_edges(linear, dep_graph)
    (linear, type_env) = type_check(linear, dep_graph)
    (linear, dep_graph) = vectorize.basic_vectorization_phase_1(linear, type_env)
    (linear, dep_graph) = vectorize.basic_vectorization_phase_2(linear)
    (linear, type_env) = type_check(linear, dep_graph)
    (linear, dep_graph, type_env) = copy_propagation(linear, dep_graph, type_env)
    (linear, dep_graph, type_env) = common_subexpression_elimination(linear, dep_graph, type_env)
    mixed_config = mix_protocols(filename=filename, type_env=type_env, body=linear.body, dep_graph=dep_graph, backend=backend, costType=costType, protocolSets=protocolSets)
    return mixed_config


for program in importantTestCases + otherTestCases:
    currentCosts[program] = dict()
    for backend in backends:
        protSetMix = spdzMix if backend == Backend.MP_SPDZ else motionMix
        protSetUnmix = spdzUnmix if backend == Backend.MP_SPDZ else motionUnmix
        strBack = str(backend)
        currentCosts[program][strBack] = dict()
        for costType in costTypes:
            currentCosts[program][strBack][costType] = dict()
            mixed = getMixedConfig(f'../benchmarks/{program}.py', backend, costType, protSetMix)
            unmixed = getMixedConfig(f'../benchmarks/{program}.py', backend, costType, protSetUnmix)
            assert mixed.total_cost <= unmixed.total_cost
            currentCosts[program][strBack][costType]['mixed'] = mixed.total_cost
            currentCosts[program][strBack][costType]['unmixed'] = unmixed.total_cost
            print(f'{strBack} {costType} {program} output')
            print(mixed)

# compare this json with the stored json
with open('mixedCostsForComparison.json', 'r') as f:
    savedCosts = json.load(f)
diff = jsondiff.diff(savedCosts, currentCosts)
if diff == dict():
    print("Tested costs are identical to saved costs")
else:
    print("DIFFERENT COSTS DETECTED:")
    print(diff)

if save:
    print('\nWriting mixedCostsForComparison.json')
    with open('mixedCostsForComparison.json', 'w') as f:
        f.write(json.dumps(currentCosts, indent=4, sort_keys=True))
