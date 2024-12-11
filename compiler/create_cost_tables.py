import datetime

from compiler.backends import Backend
from random import random, randint
import json
from os import listdir
from os.path import isfile, join


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
    if random() < 0.2:
        raise Exception("Random fail genCode")
    return iters*vecSize


def runTrial(code):
    # TEMP CODE FOR TESTING
    if random() < 0.02:
        raise Exception("Random fail runTrial")
    return {"time": random()*2*code, "dataSent": randint(1,20*code), "commRounds": randint(1,200*code)}


def runBenchmark(backend, protocol, operator, symbol, trials, loopIters, conv=False):
    finalStats = dict()
    for vecSize in vecSizes:
        statsMultiList = []
        statsSingleList = []

        # generate backend code for this benchmark
        failGenCount = 0
        success = False
        while True:
            try:
                codeMultiIter = genCode(backend, protocol, operator, symbol, loopIters, conv, vecSize)
                codeSingleIter = genCode(backend, protocol, operator, symbol, 1, conv, vecSize)
                success = True
                break
            except:
                failGenCount += 1
                if failGenCount > 5:
                    print(f"Skipping {protocol} {operator} {symbol} {vecSize} due to excessive generation errors")
                    break
        if not success:
            continue

        # run the benchmark
        totalFails = 0
        while len(statsMultiList) < trials:
            try:
                statsMultiList.append(runTrial(codeMultiIter))
            except:
                totalFails += 1
                if totalFails > 10:
                    break
        while len(statsSingleList) < trials:
            try:
                statsSingleList.append(runTrial(codeSingleIter))
            except:
                totalFails += 1
                if totalFails > 10:
                    break
        if len(statsMultiList) < trials or len(statsSingleList) < trials:
            print(f"Skipping {protocol} {operator} {symbol} {vecSize} due to excessive execution errors")
            continue

        # Compute average statistics for this benchmark
        statSingle = averageStats(statsSingleList)
        statMulti = averageStats(statsMultiList)
        for k, v in statSingle.items():
            statMulti[k] -= v
            statMulti[k] /= (loopIters - 1)
        finalStats[vecSize] = statMulti
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


def createCostTable():
    trials, loopIters, intSize = (100, 1000, 32)
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


def repairCostTable(tableName="", useLastTable=True):
    if useLastTable:
        fileNames = sorted([f for f in listdir() if isfile(f) and f.__contains__('cost_table.txt')])
        if not len(fileNames):
            print("No cost tables found to repair")
            return
        tableName = fileNames[-1]
    with open(tableName) as json_data:
        resultsDict = json.load(json_data)
    pass

# createCostTable()
repairCostTable()
