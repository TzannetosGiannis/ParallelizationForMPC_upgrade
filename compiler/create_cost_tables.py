import datetime
from compiler.backends import Backend
import json
from os import listdir, getcwd
from os.path import isfile
import socket
import subprocess
import re
from time import sleep
import signal, sys

def parse(pattern: str,text: str) -> tuple[str, ...]:
    m = re.search(rf"^\s*{pattern}\s*$", text, re.MULTILINE)
    assert m is not None, repr(text)
    return m.groups()


# backends = [Backend.MOTION, Backend.MP_SPDZ]
backends = [Backend.MP_SPDZ]
opToCostSymbol = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt',
  '*': 'zi_mul', 'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '%': 'zi_rem', '<<': 'zi_shl', '-': 'zi_sub', '^': 'zi_xor',
  '>>': 'zi_shr', '-UNARY': 'UNAVAILABLE', '&': 'zi_&', '|': 'zi_|', 'Var': 'UNAVAILABLE', '/': 'zi_div'}

# cannotDo = {'Mux': 'zi_mux'}
remainingOps = {}
# '*': 'zi_mul' -> too slow in B. Looks like it runs out of memory during runtime
# '>>': 'zi_shr' -> too slow in A. Looks like it runs out of memory during compiletime
testedOps = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt',
  'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '%': 'zi_rem', '<<': 'zi_shl', '-': 'zi_sub', '^': 'zi_xor', '&': 'zi_&', '|': 'zi_|', '/': 'zi_div'}
opToCostSymbol = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt',
  'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '%': 'zi_rem', '<<': 'zi_shl', '-': 'zi_sub', '^': 'zi_xor', '&': 'zi_&', '|': 'zi_|', '/': 'zi_div'}
spdzTypes = ["A","B","X","Y"]
# spdzTypes = ["B2A"]
vecSizes = [1, 2, 5, 10, 25, 50, 100, 200, 300, 500, 800, 1000]
# vecSizes = [10]
# trials, loopIters, intSize = (100, 1000, 32)
trials, loopIters, intSize = (2, 100, 32)
port = 12345
conn_address = ''
server_address = '10.10.1.1'

common_prefix = f'{getcwd()}/../backend_submodules/MP-SPDZ/'
timestamp = datetime.datetime.strftime(datetime.datetime.now(), '%Y_%m_%d_%H_%M_%S')

def startSocket():
    global conn_address, server_address
    sock = socket.socket()
    sock.bind(('', port))
    sock.listen(1)
    print(f'Listening on port {port}')

    c, addr = sock.accept()
    conn_address = addr[0]
    if conn_address == '127.0.0.1':
        server_address = conn_address
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
        
        opToCostSymbolCategory = ['zi_add','zi_sub','zi_mul','zi_and','zi_or']
        opToCostSymbolCategory3 = ['zi_rem']
        
        prot = protocol.split("_")[0]
        spdzType = protocol.split("_")[1]
        
        if symbol in opToCostSymbolCategory:
            if spdzType == 'A' or spdzType == 'X' or spdzType == 'Y':
                actualPrototype = 'protocol_arithmetic'
            elif spdzType == 'B':
                actualPrototype = 'protocol_binary'
            else:
                raise TypeError("This is a type error")
        elif symbol in opToCostSymbolCategory3:
            if spdzType == 'A' or spdzType == 'X' or spdzType == 'Y':
                actualPrototype = 'protocol_3_arithmetic'
            elif spdzType == 'B':
                # Just letting this here , but anyways the execution will fail
                actualPrototype = 'protocol_binary'
            else:
                raise TypeError("This is a type error")
        else:
            if spdzType == 'A' or spdzType == 'X' or spdzType == 'Y':
                actualPrototype = 'protocol_2_arithmetic'
            elif spdzType == 'B':
                actualPrototype = 'protocol_binary'
            else:
                raise TypeError("This is a type error")
    

        
        dummy_filename = f'protocol2_{iters}.mpc'

        
        # retrieve the sample 
        with open(f'./mpc_samples/{backend}/{actualPrototype}.mpc','r') as f:
            code = f.read()
        
        if spdzType == 'X':
            X_code = 'program.use_dabit = True\n'
            code = X_code + code
        if spdzType == 'Y':
            Y_code = 'program.use_edabit(True)\n'
            code = Y_code + code
        # modify the test compoenents
        code = code.replace("_iters",str(iters)).replace('_vec_size',str(vecSize))
        

        if symbol in opToCostSymbolCategory:
            basic_operation = "c = (a _operator b)"
            basic_operation = basic_operation.replace('_operator',operator)
            code = code.replace("_operation",basic_operation)
        elif symbol in opToCostSymbolCategory3:
            basic_operation = "c[i] = (a[i] _operator 2)"
            basic_operation = basic_operation.replace('_operator',operator)
            code = code.replace('_operation',basic_operation)
        else:
            if symbol == 'zi_mux':
                if spdzType == 'B':
                    c = f'c = sb32.Array(len(a))\n       for i in range(len(a)):\n            '
                    code = code.replace('_operation',f"{c}c[i] = sb32(0).if_else(sb32(2), sb32(3))")
                else:
                    code = code.replace('_operation',"c[i] = sint(0).if_else(sint(2), sint(3))")
            elif spdzType == 'A' or spdzType == 'X' or spdzType == 'Y':
                basic_operation = "c[i] = (a[i] _operator b[i])"
                basic_operation = basic_operation.replace('_operator',operator)
                code = code.replace('_operation',basic_operation)
            else:
                basic_operation = "c = (a _operator b)"
                basic_operation = basic_operation.replace('_operator',operator)
                code = code.replace("_operation",basic_operation)

        
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
        p = subprocess.Popen([f'{common_prefix}Scripts/../{prot}-party.x','0',codeName.split(".mpc")[0], '-pn','13110','-h',server_address,'-N','2'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, )
        sendCmd(f'execute {common_prefix}Scripts/../{prot}-party.x 1 {codeName.split(".mpc")[0]} -pn 13110 -h {server_address} -N 2')
    
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
                sleep(0.01)
                codeMultiIter = genCode(backend, protocol, operator, symbol, loopIters, conv, vecSize)
                codeSingleIter = genCode(backend, protocol, operator, symbol, 1, conv, vecSize)
                success = True
                break
            except SystemExit:
                sys.exit(1)
            except Exception as e:
                failGenCount += 1
                if failGenCount > 5:
                    print(f"Skipping {protocol} {operator} {symbol} {vecSize} due to excessive generation errors")
                    print(e)
                    break
        if not success:
            continue

        # run the benchmark
        totalFails = 0
        while len(statsMultiList) < trials:
            sleep(0.01)
            try:
                statsMultiList.append(runTrial(codeMultiIter,backend,protocol))
            except SystemExit:
                sys.exit(1)
            except:
                totalFails += 1
                if totalFails > 10:
                    break
        while len(statsSingleList) < trials:
            sleep(0.01)
            try:
                statsSingleList.append(runTrial(codeSingleIter,backend,protocol))
            except SystemExit:
                sys.exit(1)
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
                            printOutputToJSON(resultsDict, log=False, save=True)
                    else:
                        resultsDict[str(backend)][sym][protocol] = runBenchmark(backend, protocol, op, sym, trials, loopIters)
                        printOutputToJSON(resultsDict, log=False, save=True)


        # [TODO] Brandon lets talk about this ==> Compute conversion costs
        # convPossibilities = spdzTypes if backend == Backend.MP_SPDZ else backend.valid_protocols()
        # for a in convPossibilities:
        #     for b in convPossibilities:
        #         if a != b:
        #             resultsDict[str(backend)][a + "2" + b] = runBenchmark(backend, a + "2" + b, None, None, trials, loopIters, conv=True)
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
                if protocol != 'semi':
                    continue
                if not sym == 'UNAVAILABLE':
                    if backend == Backend.MP_SPDZ:
                        for spdzType in spdzTypes:
                            t = protocol + '_' + spdzType
                            if t in resultsDict[str(backend)][sym].keys():
                                resultsDict[str(backend)][sym][t] = runBenchmark(backend, t, op, sym, trials, loopIters, finalStats=resultsDict[str(backend)][sym][t])
                                printOutputToJSON(resultsDict, log=False, save=True)
                            else:
                                print(f"Running missing benchmark {str(backend)} {op} {sym} {t}")
                                resultsDict[str(backend)][sym][t] = runBenchmark(backend, t, op, sym, trials, loopIters)
                                printOutputToJSON(resultsDict, log=False, save=True)
                    else:
                        if protocol in resultsDict[str(backend)][sym].keys():
                            resultsDict[str(backend)][sym][protocol] = runBenchmark(backend, protocol, op, sym, trials, loopIters, finalStats=resultsDict[str(backend)][sym][protocol])
                            printOutputToJSON(resultsDict, log=False, save=True)
                        else:
                            print(f"Running missing benchmark {str(backend)} {op} {sym} {protocol}")
                            resultsDict[str(backend)][sym][protocol] = runBenchmark(backend, protocol, op, sym, trials, loopIters)
                            printOutputToJSON(resultsDict, log=False, save=True)

        # Compute conversion costs
#        convPossibilities = spdzTypes if backend == Backend.MP_SPDZ else backend.valid_protocols()
#        for a in convPossibilities:
#            for b in convPossibilities:
#                if a != b:
#                    cType = a + "2" + b
#                    if cType in resultsDict[str(backend)].keys():
#                        runBenchmark(backend, a + "2" + b, None, None, trials, loopIters, conv=True, finalStats=resultsDict[str(backend)][cType])
#                    else:
#                        print(f"Running missing benchmark {str(backend)} {cType}")
#                        resultsDict[str(backend)][cType] = runBenchmark(backend, a + "2" + b, None, None, trials, loopIters, conv=True)
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


def signal_handler(sig, frame):
    print('Ctrl+C received. Closing socket and exiting...')
    sendCmd('quit')
    s.close()
    sys.exit(1)

# signal is used to capture ctrl+c signals and exit gracefully
signal.signal(signal.SIGINT, signal_handler)

s = startSocket()
# createCostTable()
repairCostTable()
sendCmd('quit')
s.close()
