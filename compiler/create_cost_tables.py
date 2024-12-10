import datetime

from compiler.backends import Backend
from random import random, randint
import json


backends = [Backend.MOTION, Backend.MP_SPDZ]
opToCostSymbol = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt',
  '*': 'zi_mul', 'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '%': 'zi_rem', '<<': 'zi_shl', '-': 'zi_sub', '^': 'zi_xor',
  '>>': 'zi_shr', '-UNARY': 'UNAVAILABLE', '&': 'zi_&', '|': 'zi_|', 'Var': 'UNAVAILABLE', '/': 'zi_div'}
spdzTypes = ["A", "B", "X", "Y"]
vecSizes = [1, 2, 5, 10, 25, 50, 100, 200, 300, 500, 800, 1000]


def averageStats(statsList):
    n = len(statsList)
    sumStat = statsList[0]
    for stat in statsList[1:]:
        for k,v in stat.items():
            sumStat[k] += v
    for k,v in sumStat.items():
        sumStat[k] /= n
    return sumStat


def genCode(backend, protocol, operator, symbol, iters, conv, vecSize):
    # TEMP CODE FOR TESTING
    return iters*vecSize


def runTrial(code):
    # TEMP CODE FOR TESTING
    return {"time": random()*2*code, "dataSent": randint(1,20*code), "commRounds": randint(1,200*code)}


def runBenchmark(backend, protocol, operator, symbol, trials, loopIters, conv=False):
    finalStats = dict()
    for vecSize in vecSizes:
        statsList = []
        codeMultiIter = genCode(backend, protocol, operator, symbol, loopIters, conv, vecSize)
        codeSingleIter = genCode(backend, protocol, operator, symbol, 1, conv, vecSize)
        for i in range(trials):
            statMultiIter = runTrial(codeMultiIter)
            statSingleIter = runTrial(codeSingleIter)
            for k, v in statSingleIter.items():
                statMultiIter[k] -= v
                statMultiIter[k] /= (loopIters - 1)
            statsList.append(statMultiIter)
        finalStats[vecSize] = averageStats(statsList)
    return finalStats


def printOutputToJSON(outputDict, log=False, save=True):
    jsonData = json.dumps(outputDict, indent=2)
    if log:
        print(jsonData)
    if save:
        timestamp = datetime.datetime.strftime(datetime.datetime.now(), '%Y_%m_%d_%H_%M_%S')
        with open(timestamp + "_cost_table.txt", "w") as text_file:
            print(f'Wrote json data to "{timestamp}_cost_table.txt"')
            text_file.write(jsonData)


def createCostTables():
    trials, loopIters, intSize = (1000, 100, 32)
    resultsDict = {"params": {"trials": trials, "loopIters": loopIters, "intSize": intSize}}
    for backend in backends:
        resultsDict[str(backend)] = dict()

        # Compute costs for each operator
        for op, sym in opToCostSymbol.items():
            resultsDict[str(backend)][sym] = dict()
            for protocol in backend.valid_protocols():
                if not sym == 'UNAVAILABLE':
                    if backend == Backend.MP_SPDZ:
                        for spdzType in spdzTypes:
                            t = protocol + '_' + spdzType
                            resultsDict[str(backend)][sym][t] = runBenchmark(backend, t, op, sym, trials, loopIters)
                    else:
                        resultsDict[str(backend)][sym][protocol] = runBenchmark(backend, protocol, op, sym, trials, loopIters)

        # Compute conversion costs
        convPossibilities = spdzTypes if backend == Backend.MP_SPDZ else backend.valid_protocols()
        for a in convPossibilities:
            for b in convPossibilities:
                if a != b:
                    resultsDict[str(backend)][a + "2" + b] = runBenchmark(backend, a + "2" + b, None, None, trials, loopIters, conv=True)
    printOutputToJSON(resultsDict, log=False, save=True)

createCostTables()
