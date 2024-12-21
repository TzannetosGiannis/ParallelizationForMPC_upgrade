import datetime
from compiler.backends import Backend
from random import random, randint
import json
from os import listdir, getcwd
from os.path import isfile
import socket
import subprocess
import re

def parse(pattern: str,text: str) -> tuple[str, ...]:
    m = re.search(rf"^\s*{pattern}\s*$", text, re.MULTILINE)
    assert m is not None, repr(text)
    return m.groups()


# backends = [Backend.MOTION, Backend.MP_SPDZ]
backends = [Backend.MP_SPDZ]
# opToCostSymbol = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt',
#   '*': 'zi_mul', 'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '%': 'zi_rem', '<<': 'zi_shl', '-': 'zi_sub', '^': 'zi_xor',
#   '>>': 'zi_shr', '-UNARY': 'UNAVAILABLE', '&': 'zi_&', '|': 'zi_|', 'Var': 'UNAVAILABLE', '/': 'zi_div'}
opToCostSymbol = {'+': 'zi_add', } # 'and': 'zi_and'
# spdzTypes = ["A", "B", "X", "Y"]
spdzTypes = ["A","B"]
# vecSizes = [1, 2, 5, 10, 25, 50, 100, 200, 300, 500, 800, 1000]
vecSizes = [10]
# trials, loopIters, intSize = (100, 1000, 32)
trials, loopIters, intSize = (2, 2, 32)
port = 12345

common_prefix = f'{getcwd()}/../backend_submodules/MP-SPDZ/'

def startSocket():
    sock = socket.socket()
    sock.bind(('', port))
    sock.listen(1)
    print(f'Listening on port {port}')

    c, addr = sock.accept()
    print(f'Received connection from {addr[0]}:{addr[1]}')

    return c


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
    
    val = iters * vecSize

    if str(backend) == 'MP-SPDZ':
      
        prot = protocol.split("_")[0]
        spdzType = protocol.split("_")[1]
        dummy_filename = f'{symbol}_{spdzType}.mpc'
    
        # retrieve the sample 
        with open(f'./mpc_samples/{backend}/{symbol}_{spdzType}.mpc','r') as f:
            code = f.read()
        
        # modify the test compoenents
        code = code.replace("_iters",str(iters)).replace('_vec_size',str(vecSize))
        
        # save it to tmp file
        with open(dummy_filename, "w") as file:  # Open the file in write mode
            file.write(code)

        sendCmd('save ' + dummy_filename + ' ' + code)
        sendCmd(f'execute {common_prefix}compile.py ./{dummy_filename}')
        p = subprocess.Popen([f'{common_prefix}compile.py', f'./{dummy_filename}'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, )

    try:
        stdout, stderr = p.communicate(timeout=1000)
    except TimeoutError:
        print('Timed out')
        s.send('error'.encode())
    assert p.returncode == 0, stderr
   
    return dummy_filename


def runTrial(codeName,backend,protocol):

    # TEMP CODE FOR TESTING
    if str(backend) == 'MP-SPDZ':
        prot = protocol.split('_')[0]
        p = subprocess.Popen([f'{common_prefix}Scripts/../{prot}-party.x','0',codeName.split(".mpc")[0], '-pn','13110','-h','localhost','-N','2'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, )
        sendCmd(f'execute {common_prefix}Scripts/../{prot}-party.x 1 {codeName.split(".mpc")[0]} -pn 13110 -h localhost -N 2')
    
        try:
            stdout, stderr = p.communicate(timeout=1000)
        except TimeoutError:
            print('Timed out')
            s.send('error'.encode())
        
        assert p.returncode == 0, stderr
        # print('Output: ', stderr)
        # vals = stdout[:-1].split(' ')
        stats = {"time": float(parse(r"Time = (.+) seconds",stderr)[0]), "dataSent": float(parse(r"Data sent = (.+) MB.*",stderr)[0]), "commRounds": int(parse(r"Data sent = .*~(\d+)\s*rounds.*",stderr)[0])}
        print('Stats: ', stats)
        print('Test execution complete')

    return stats


def runBenchmark(backend, protocol, operator, symbol, trials, loopIters, conv=False, finalStats=None):
    repairMode = True
    if not finalStats:
        finalStats = dict()
        repairMode = False

    for vecSize in vecSizes:
        if repairMode and str(vecSize) in finalStats.keys():
            continue
        if repairMode:
            print(f"Missing {backend} {protocol} {operator} {symbol} {vecSize}")

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
                statsMultiList.append(runTrial(codeMultiIter,backend,protocol))
            except:
                totalFails += 1
                if totalFails > 10:
                    break
        while len(statsSingleList) < trials:
            try:
                statsSingleList.append(runTrial(codeSingleIter,backend,protocol))
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
    resultsDict = {"params": {"trials": trials, "loopIters": loopIters, "intSize": intSize}}
    for backend in backends:
        resultsDict[str(backend)] = dict()

        # Compute costs for each operator
        for op, sym in opToCostSymbol.items():
            resultsDict[str(backend)][sym] = dict()
            for protocol in backend.valid_protocols():
                if protocol != 'semi':
                    continue
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
        print("\nRepairing cost table:", tableName)
    with open(tableName) as json_data:
        resultsDict = json.load(json_data)

    for backend in backends:
        if str(backend) not in resultsDict.keys():
            resultsDict[str(backend)] = dict()

        # Compute costs for each operator
        for op, sym in opToCostSymbol.items():
            if sym not in resultsDict[str(backend)].keys():
                resultsDict[str(backend)][sym] = dict()
            for protocol in backend.valid_protocols():
                if not sym == 'UNAVAILABLE':
                    if backend == Backend.MP_SPDZ:
                        for spdzType in spdzTypes:
                            t = protocol + '_' + spdzType
                            if t in resultsDict[str(backend)][sym].keys():
                                runBenchmark(backend, t, op, sym, trials, loopIters, finalStats=resultsDict[str(backend)][sym][t])
                            else:
                                print(f"Running missing benchmark {str(backend)} {op} {sym} {t}")
                                resultsDict[str(backend)][sym][t] = runBenchmark(backend, t, op, sym, trials, loopIters)
                    else:
                        if protocol in resultsDict[str(backend)][sym].keys():
                            runBenchmark(backend, protocol, op, sym, trials, loopIters, finalStats=resultsDict[str(backend)][sym][protocol])
                        else:
                            print(f"Running missing benchmark {str(backend)} {op} {sym} {protocol}")
                            resultsDict[str(backend)][sym][protocol] = runBenchmark(backend, protocol, op, sym, trials, loopIters)

        # Compute conversion costs
        convPossibilities = spdzTypes if backend == Backend.MP_SPDZ else backend.valid_protocols()
        for a in convPossibilities:
            for b in convPossibilities:
                if a != b:
                    cType = a + "2" + b
                    if cType in resultsDict[str(backend)].keys():
                        runBenchmark(backend, a + "2" + b, None, None, trials, loopIters, conv=True, finalStats=resultsDict[str(backend)][cType])
                    else:
                        print(f"Running missing benchmark {str(backend)} {cType}")
                        resultsDict[str(backend)][cType] = runBenchmark(backend, a + "2" + b, None, None, trials, loopIters, conv=True)
    printOutputToJSON(resultsDict, log=False, save=True)


def sendCmd(cmd):
    s.send((cmd + chr(3)).encode())
    msg = ''
    while not len(msg):
        msg = s.recv(1024).decode()
    if msg != cmd.split(' ')[0]:
        if msg == 'error':
            raise Exception('Client failed to run command')
        raise Exception("Command failed for unknown reasons")


s = startSocket()
createCostTable()
# repairCostTable()
sendCmd('quit')
s.close()
