import datetime
from compiler.backends import Backend
import json
from os import listdir, getcwd, makedirs, path
import shutil
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


#backends = [Backend.MOTION, Backend.MP_SPDZ]
backends = [Backend.MP_SPDZ]

opToCostSymbol = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt',
  '*': 'zi_mul', 'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '%': 'zi_rem', '<<': 'zi_shl', '-': 'zi_sub', '^': 'zi_xor',
  '>>': 'zi_shr', '-UNARY': 'UNAVAILABLE', '&': 'zi_&', '|': 'zi_|', 'Var': 'UNAVAILABLE', '/': 'zi_div','not': 'zi_not'}

# MP_SPDZ ==> '*': 'zi_mul' -> too slow in B. Looks like it runs out of memory during runtime
# MP_SPDZ ==> '>>': 'zi_shr' -> too slow in A. Looks like it runs out of memory during compiletime
testedOps = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt',
  'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '%': 'zi_rem', '<<': 'zi_shl', '-': 'zi_sub', '^': 'zi_xor', '&': 'zi_&', '|': 'zi_|', '/': 'zi_div','not': 'zi_not'}
opToCostSymbol = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt', '*': 'zi_mul',
  'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '%': 'zi_rem', '<<': 'zi_shl', '-': 'zi_sub', '^': 'zi_xor', '&': 'zi_&', '|': 'zi_|', '/': 'zi_div','not': 'zi_not'}
#opToCostSymbol = {'*': 'zi_mul', 'and': 'zi_and', 'or': 'zi_or', '^': 'zi_xor','not': 'zi_not'}

spdzTypes = ["A","B","X","Y"]
spdzMix = ['AB','BA','XB','BX','YB','BY']

vecSizes = [1, 2, 5, 10, 25, 50, 100, 200, 300, 500, 800, 1000]
vecSizesConv = [1, 2, 5, 10, 25, 50, 100, 200, 300, 500]
# trials, loopIters, intSize = (100, 1000, 32)
trials, loopIters, intSize = (20, 20, 32)
port = 12345
conn_address = ''
server_address = '10.10.1.1'

common_prefix = f'{getcwd()}/../backend_submodules/MP-SPDZ/'
timestamp = datetime.datetime.strftime(datetime.datetime.now(), '%Y_%m_%d_%H_%M_%S')

# '+': 'zi_add' ALL
# '==': 'zi_eq' NOT ARITHMETIC
# '&': 'zi_&' NOT ARITHMETIC
# '|': 'zi_|' NOT ARITHMETIC
# '/': 'zi_div' NOT AT ALL
# '>=': 'zi_ge' NOT AT ALL ==>  error: no match for ‘operator>=’ (operand types are ‘encrypto::motion::ShareWrapper’ and ‘encrypto::motion::ShareWrapper’)
# '<=': 'zi_le' NOT AT ALL ==>  error: no match for ‘operator<=’ (operand types are ‘encrypto::motion::ShareWrapper’ and ‘encrypto::motion::ShareWrapper’)
# '>': 'zi_gt'  NOT BOOLEAN AND BMR ==> what():  GreaterThan operation is only supported for arithmetic GMW shares
# '<': 'zi_lt'  NOT AT ALL ==>  error: no match for ‘operator<’ (operand types are ‘encrypto::motion::ShareWrapper’ and ‘encrypto::motion::ShareWrapper’)
# '*': 'zi_mul' ALL
# '-': 'zi_sub' ALL
# '!=': 'zi_ne' NOT AT ALL ==> error: return type of ‘encrypto::motion::ShareWrapper encrypto::motion::ShareWrapper::operator==(const encrypto::motion::ShareWrapper&) const’ is not ‘bool’
#  '%': 'zi_rem' NOT AT ALL
# '<<': 'zi_shl' NOT AT ALL ==>  error: no match for ‘operator<<’ (operand types are ‘encrypto::motion::SecureUnsignedInteger’ and ‘encrypto::motion::SecureUnsignedInteger’)
# '^': 'zi_xor' NOT ARITHMETIC
# ,'>>': 'zi_shr' NOT AT ALL ==>  error: no match for ‘operator>>’ (operand types are ‘encrypto::motion::ShareWrapper’ and ‘encrypto::motion::ShareWrapper’)


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



def genCodeConv(backend,protocol,iters,vecSize):

    protocol = protocol.split('_')[1]
    if str(backend) == 'MP-SPDZ':

        dummy_filename = f'protocol_mixed_{iters}.mpc'

        # retrieve the sample 
        with open(f'./mpc_samples/{backend}/convert.mpc','r') as f:
            code = f.read()

        if  'X' in protocol:
            X_code = 'program.use_dabit = True\n'
            code = X_code + code
        if  'Y' in protocol:
            Y_code = 'program.use_edabit(True)\n'
            code = Y_code + code
        # modify the test compoenents
        code = code.replace("_iters",str(iters)).replace('_vec_size',str(vecSize))

        if protocol[0] == 'B':
            code = code.replace('_isArith','sb32').replace('_siv32','siv32')
            code = code.replace('_operation','c[i] = sint(a[i])').replace('_init','sint')
        else:
            code = code.replace('_isArith','sint').replace('_siv32','')
            code = code.replace('_operation','c[i] = sb32(a[i])').replace('_init','sb32')

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
        

def genCode(backend, protocol, operator, symbol, iters, conv, vecSize):
    # TEMP CODE FOR TESTING
    val = iters * vecSize
    if str(backend) == 'MOTION': 

        category1 = ["zi_add","zi_mul","zi_sub"]
        
        # generate a working directory and move template files there
        
        # Define the source and destination directories
        source_dir = "./mpc_samples/MOTION/templates"
        destination_dir = f"./dummy_MOTION_{iters}"

        # Delete the destination directory if it exists
        if path.exists(destination_dir):
            shutil.rmtree(destination_dir)
        # Create the new directory if it doesn't exist
        makedirs(destination_dir, exist_ok=True)

        # Move all files and subdirectories from source to destination
        for item in listdir(source_dir):
            source_item = path.join(source_dir, item)
            destination_item = path.join(destination_dir, item)
            shutil.copy2(source_item, destination_item)
        
        # Construct the proper template

        # Generate the build directory
        app_path = f"/opt/ParallelizationForMPC_upgrade/compiler/dummy_MOTION_{iters}"
    
        with open(f'{app_path}/main.cpp','r') as f:
            main_code = f.read()

        main_code = main_code.replace('_vec_size',str(vecSize))
        if protocol == "ArithmeticGmw":
            main_code = main_code.replace("_inputA_placeHolder","A = party->In<encrypto::motion::MpcProtocol::kArithmeticGmw>(list_A,0);")
            main_code = main_code.replace("_inputB_placeHolder","B = party->In<encrypto::motion::MpcProtocol::kArithmeticGmw>(list_B,1);")
        if protocol == 'BooleanGmw':
            main_code = main_code.replace("_inputA_placeHolder","A = party->In<encrypto::motion::MpcProtocol::kBooleanGmw>(encrypto::motion::ToInput(list_A),0);")
            main_code = main_code.replace("_inputB_placeHolder","B = party->In<encrypto::motion::MpcProtocol::kBooleanGmw>(encrypto::motion::ToInput(list_B),1);")
        if protocol == "Bmr":
            main_code = main_code.replace("_inputA_placeHolder","A = party->In<encrypto::motion::MpcProtocol::kBmr>(encrypto::motion::ToInput(list_A),0);")
            main_code = main_code.replace("_inputB_placeHolder","B = party->In<encrypto::motion::MpcProtocol::kBmr>(encrypto::motion::ToInput(list_B),1);")
 
        if symbol in category1:
            main_code = main_code.replace("_output_type",".As<std::uint32_t>()")
        else:
            main_code = main_code.replace("_output_type","")
        # save the main file to server side
        # Open the file in write mode and write the content
        with open(f'{app_path}/main.cpp', 'w') as f:
            f.write(main_code)

        # retrieve the sample 
        with open(f'{app_path}/template_code.h','r') as f:
            code = f.read()

        code = code.replace("_iters",str(iters))

        type1 = "encrypto::motion::SecureUnsignedInteger"
        type2 = "encrypto::motion::ShareWrapper"

        operator_type1 = "result_C = list_A _operator list_B;"
        operator_type2 = "result_C = encrypto::motion::ShareWrapper(list_A.Get()) _operator encrypto::motion::ShareWrapper(list_B.Get());"
       
        if symbol in category1:
            code = code.replace("_type_to_replace",type1)
            code = code.replace("_operator_to_replace",operator_type1)
            code = code.replace("_operator",operator)
        else:
            code = code.replace("_type_to_replace",type2)
            code = code.replace("_operator_to_replace",operator_type2)
            code = code.replace("_operator",operator)

        # retrieve the sample 
        with open(f'{app_path}/template_code.h','w') as f:
            f.write(code)


        # Tranfer the code 
        dummy_template_filename = f'MOTION_code.cpp'
        dummy_main_filename = f'MOTION_main.cpp'

        # Build the code 
        sendCmd('save ' + dummy_main_filename + ' ' + main_code)
        sendCmd('save ' + dummy_template_filename + ' ' + code)
        sendCmd(f'execute sudo mkdir -p client_motion_{iters}')
        sendCmd(f'execute sudo rm -rf ./client_motion_{iters}/*')
        sendCmd(f'execute sudo cp mpc_samples/MOTION/templates/CMakeLists.txt ./client_motion_{iters}/')
        sendCmd(f'execute sudo cp mpc_samples/MOTION/templates/collect_stats.cpp ./client_motion_{iters}/')
        sendCmd(f'execute sudo cp mpc_samples/MOTION/templates/collect_stats.h ./client_motion_{iters}/')
        sendCmd(f'execute sudo mv {dummy_template_filename} client_motion_{iters}/template_code.h')
        sendCmd(f'execute sudo mv {dummy_main_filename} client_motion_{iters}/main.cpp')

        # Compile on local version
        subprocess.run(
            ["cmake", "-S", app_path, "-B", path.join(app_path, "build")],
            check=True,
        )

        # Build
        subprocess.run(
            ["cmake", "--build", path.join(app_path, "build")],
            check=True,
        )

        # Compile on clients end
        client_path = f"/opt/ParallelizationForMPC_upgrade/compiler/client_motion_{iters}"
        command1 = f"cmake -S {client_path} -B {path.join(client_path,'build')}"
        command2 = f"cmake --build {path.join(client_path,'build')}"
        sendCmd(f"execute sudo {command1}")
        sendCmd(f"execute sudo {command2}")
        
        return f"client_motion_{iters}"
    
    elif str(backend) == 'MP-SPDZ':
        
        

        opToCostSymbolCategory = ['zi_add','zi_sub','zi_mul']
        opToCostSymbolCategory3 = ['zi_rem']
        opToCostSymbolCategory4 = ['zi_and','zi_or','zi_xor','zi_not']
       
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
        if symbol.split('_')[1] == 'not':
            code = code.replace("b = ([sint(i+1) for i in range(_vec_size)])","")
            code = code.replace("b = siv32([sb32(i+1) for i in range(_vec_size)])","")
            code = code.replace("zi_prot(a, b,","zi_prot(a,")

        code = code.replace("_iters",str(iters)).replace('_vec_size',str(vecSize))
        

        if symbol in opToCostSymbolCategory:
            basic_operation = "c = (a _operator b)"
            basic_operation = basic_operation.replace('_operator',operator)
            code = code.replace("_operation",basic_operation)
        elif symbol in opToCostSymbolCategory3:
            basic_operation = "c[i] = (a[i] _operator 2)"
            basic_operation = basic_operation.replace('_operator',operator)
            code = code.replace('_operation',basic_operation)
        elif symbol in opToCostSymbolCategory4:
            if spdzType == 'A' or spdzType == 'X' or spdzType == 'Y':
                code = code.replace("sint.Array(len(a))","sintbit.Array(len(a))")
                if symbol.split('_')[1] == 'or': 
                    basic_operation = "c[i] = ((a[i].bit_not()).bit_and(b[i].bit_not())).bit_not()"
                else: 
                    basic_operation = "c[i] = (a[i]_operator(b[i]))" if symbol.split('_')[1] != 'not' else "c[i] = (a[i]_operator())"
                    basic_operation = basic_operation.replace('_operator',f".bit_{symbol.split('_')[1]}")
                code = code.replace('_operation',basic_operation)
                code = code.replace('sint(i)',"sintbit(0)").replace("sint(i+1)","sintbit(1)")
            else:
                if symbol.split('_')[1] == 'or': 
                    basic_operation = "c = ((a.bit_not()).bit_and(b.bit_not())).bit_not()"
                else:
                    basic_operation = "c = (a_operator(b))" if symbol.split('_')[1] != 'not' else "c = (a_operator())"
                    basic_operation = basic_operation.replace('_operator',f".bit_{symbol.split('_')[1]}")
                code = code.replace('_operation',basic_operation)
                code = code.replace('sb32(i)',"sbit(0)").replace("sb32(i+1)","sbit(1)")
                code = code.replace("sbitint.get_type(32)","sbitvec")
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
    if str(backend) == 'MOTION':
        nameComponents = codeName.split("_")
        iters = nameComponents[len(nameComponents)-1]
        app_path = f"/opt/ParallelizationForMPC_upgrade/compiler/dummy_MOTION_{iters}/build/template_code"
        client_path = f"/opt/ParallelizationForMPC_upgrade/compiler/{codeName}/build/template_code"
        p = subprocess.Popen([app_path,"--my-id","0", "--parties", "0,127.0.0.1,23000","1,127.0.0.1,23001"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,)
        sendCmd(f'execute sudo {client_path} --my-id 1 --parties 0,127.0.0.1,23000 1,127.0.0.1,23001')

        try:
            stdout, stderr = p.communicate(timeout=1000)
        except TimeoutError:
            print('Timed out')
            s.send('error'.encode())
        
        assert p.returncode == 0, stderr
        # print('Output: ', stderr)

        circuit_eval_pattern = r"Circuit Evaluation\s+([\d.]+) ms"
        sent_pattern = r"Sent:\s+([\d.]+)\s+MiB"
        message_pattern = r"Sent:\s+[\d.]+\s+MiB in (\d+) messages"

        # Find all matches for Circuit Evaluation in the log
        circuit_eval = float((re.findall(circuit_eval_pattern, stderr))[0])
        circuit_sent = float((re.findall(sent_pattern, stderr))[0])
        circuit_message = int((re.findall(message_pattern, stderr))[0])
        print(circuit_message)

        stats = {
            "time": circuit_eval,
            "dataSent":circuit_sent,
            'commRounds':circuit_message
        }

        print('Stats: ', stats)
        print('Test execution complete')

       


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
    
    v = vecSizesConv if conv else vecSizes
    for vecSize in v:
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
                if conv:
                    codeMultiIter = genCodeConv(backend, protocol, loopIters, vecSize)
                    codeSingleIter = genCodeConv(backend, protocol, 1, vecSize)
                else:
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
                if protocol != 'semi' and str(backend) == 'MP-SPDZ':
                    continue
                # if protocol == "ArithmeticGmw" or protocol == "Bmr":
                #     print("Continue from ",protocol)
                    # continue
                if not sym == 'UNAVAILABLE':
                    if backend == Backend.MP_SPDZ:
                        for spdzType in spdzTypes:
                            t = protocol + '_' + spdzType
                            resultsDict[str(backend)][sym][t] = runBenchmark(backend, t, op, sym, trials, loopIters)
                            printOutputToJSON(resultsDict, log=False, save=True)
                    else:
                        resultsDict[str(backend)][sym][protocol] = runBenchmark(backend, protocol, op, sym, trials, loopIters)
                        printOutputToJSON(resultsDict, log=False, save=True)

        # Compute conversion costs
        convPossibilities = spdzMix if backend == Backend.MP_SPDZ else backend.valid_protocols()
        # above line needs to be modified for MOTION
        for protocol in backend.valid_protocols():
            if protocol != 'semi' and str(backend) == 'MP-SPDZ':
                continue
            for conv in convPossibilities:
                resultsDict[str(backend)][f"{protocol}_{conv}"] = runBenchmark(backend,f"{protocol}_{conv}", None, None, trials, loopIters, conv=True)
                printOutputToJSON(resultsDict, log=False, save=True)
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
                if protocol != 'semi' and str(backend) == 'MP-SPDZ':
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
        convPossibilities = spdzMix if backend == Backend.MP_SPDZ else backend.valid_protocols()
        for protocol in backend.valid_protocols():
            if protocol != 'semi' and str(backend) == 'MP-SPDZ':
                continue
            for conv in convPossibilities:
                conv = f"{protocol}_{conv}"
                if conv in resultsDict[str(backend)].keys():
                    resultsDict[str(backend)][conv] = runBenchmark(backend, conv, None, None, trials, loopIters, conv=True, finalStats=resultsDict[str(backend)][conv])
                    printOutputToJSON(resultsDict, log=False, save=True)
                else:
                    resultsDict[str(backend)][conv] = runBenchmark(backend, conv, None, None, trials, loopIters, conv=True)
                    printOutputToJSON(resultsDict, log=False, save=True)
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
createCostTable()
# repairCostTable()
sendCmd('quit')
s.close()
