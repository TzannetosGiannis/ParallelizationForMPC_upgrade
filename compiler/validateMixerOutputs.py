import ast
import sys
import json
import traceback
import jsondiff
import time

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
                      'inner_product', 'longest_102', 'longest_odd_10', 'max_dist_between_syms',
                      'max_sum_between_syms', 'minimal_points', 'mnist_relu', 'psi']
otherTestCases = ['histogram', 'inner_product', 'kmeans_iteration', 'longest_1s', 'longest_even_0', 'matrix_multiply']
# 'floyd_warshall' does not fit restrictions for arrays
# 'histogram' may not run correctly in spdz
costTypes = ['time', 'commRounds', 'dataSent']
backends = [Backend.MP_SPDZ, Backend.MOTION]
currentCosts = dict()
currentMixes = dict()
currentBackendMixes = dict()
save = False
motionMix = [{'A', 'B', 'Y'}]
motionUnmix = [{'A'}, {'B'}, {'Y'}]
spdzMix = [{'A', 'B'}, {'X', 'B'}, {'Y', 'B'}]
spdzUnmix = [{'A'}, {'B'}, {'X'}, {'Y'}]
if len(sys.argv) > 1:
    if sys.argv[1] == 'overwrite':
        save = True


def getMixedConfig(filename, backend, costType, protocolSets):
    startTime = time.perf_counter()

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
    mixed_config = mix_protocols(filename=filename, type_env=type_env, body=linear.body, dep_graph=dep_graph, backend=backend, costType=costType, protocolSets=protocolSets, python_text=text)
    try:
        backend_code = backend.render_mixed_function(linear, type_env, True, mixed_config)
    except Exception as e:
        print("ERROR IN VECTORIZATION", e)
        backend_code = f"ERROR: {e}"
    endTime = time.perf_counter()
    print("COMPILE TIME:", endTime - startTime)
    return mixed_config, backend_code, endTime - startTime


for program in importantTestCases + otherTestCases:
    currentCosts[program] = dict()
    currentMixes[program] = dict()
    currentBackendMixes[program] = dict()
    for backend in backends:
        protSetMix = spdzMix if backend == Backend.MP_SPDZ else motionMix
        protSetUnmix = spdzUnmix if backend == Backend.MP_SPDZ else motionUnmix
        strBack = str(backend)
        currentCosts[program][strBack] = dict()
        currentMixes[program][strBack] = dict()
        currentBackendMixes[program][strBack] = dict()
        for costType in costTypes:
            currentCosts[program][strBack][costType] = dict()
            currentMixes[program][strBack][costType] = dict()
            currentBackendMixes[program][strBack][costType] = dict()
            mixed, mixedBackend, compileMixedTime = getMixedConfig(f'../benchmarks/{program}.py', backend, costType, protSetMix)
            for prot in protSetUnmix:
                assert len(prot) == 1
                protStr = list(prot)[0]
                try:
                    unmixed, unmixedBackend, compileProtTime = getMixedConfig(f'../benchmarks/{program}.py', backend, costType, [prot])
                    assert mixed.total_cost <= unmixed.total_cost
                    currentCosts[program][strBack][costType][protStr] = unmixed.total_cost
                    currentMixes[program][strBack][costType][protStr] = str(unmixed)
                    currentBackendMixes[program][strBack][costType][protStr] = str(unmixedBackend)
                except Exception as e:
                    if str(e) == "No valid mix found":
                        currentCosts[program][strBack][costType][protStr] = 'N/A'
                        currentMixes[program][strBack][costType][protStr] = 'N/A'
                        currentBackendMixes[program][strBack][costType][protStr] = 'N/A'
                    else:
                        sys.exit()
            currentCosts[program][strBack][costType]['mixed'] = mixed.total_cost
            currentMixes[program][strBack][costType]['mixed'] = str(mixed)
            currentBackendMixes[program][strBack][costType]['mixed'] = str(mixedBackend)
            print(f'{strBack} {costType} {program} output')
            print(mixed)
            # print(mixedBackend)

# compare this json with the stored json
with open('mixedCostsForComparison.json', 'r') as f:
    savedCosts = json.load(f)
diffCost = jsondiff.diff(savedCosts, currentCosts)
with open('previousMixResults.json', 'r') as f:
    savedMixes = json.load(f)
diffMix = jsondiff.diff(savedMixes, currentMixes)
with open('previousBackendResults.json', 'r') as f:
    savedBackends = json.load(f)
diffBackend = jsondiff.diff(savedBackends, currentBackendMixes)
if diffCost == dict():
    print("Tested costs are identical to saved costs")
else:
    print("DIFFERENT COSTS DETECTED:")
    toRem = []
    for k, v in diffCost.items():
        if type(toRem) != str:
            toRem.append((k, v))
    for k, v in toRem:
        del diffCost[k]
        diffCost[str(k).replace('$', '')] = v
    print(json.dumps(diffCost, indent=4, sort_keys=True))
print()
if diffMix == dict():
    print("Tested mixes are identical to saved mixes")
else:
    print("DIFFERENT MIXES DETECTED:")
    toRem = []
    for k, v in diffMix.items():
        if type(toRem) != str:
            toRem.append((k, v))
    for k, v in toRem:
        del diffMix[k]
        diffMix[str(k).replace('$', '')] = v
    print(json.dumps(diffMix, indent=4, sort_keys=True))
print()
if diffBackend == dict():
    print("Tested mixes are identical to saved mixes")
else:
    print("DIFFERENT BACKENDS DETECTED:")
    toRem = []
    for k, v in diffBackend.items():
        if type(toRem) != str:
            toRem.append((k, v))
    for k, v in toRem:
        del diffBackend[k]
        diffBackend[str(k).replace('$', '')] = v
    print(json.dumps(diffBackend, indent=4, sort_keys=True))

if save:
    print('\nWriting mixedCostsForComparison.json')
    with open('mixedCostsForComparison.json', 'w') as f:
        f.write(json.dumps(currentCosts, indent=4, sort_keys=True))

    print('Writing previousMixResults.json')
    with open('previousMixResults.json', 'w') as f:
        f.write(json.dumps(currentMixes, indent=4, sort_keys=True))

    print('Writing previousBackendResults.json')
    with open('previousBackendResults.json', 'w') as f:
        f.write(json.dumps(currentBackendMixes, indent=4, sort_keys=True))
