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
# backends = [Backend.MP_SPDZ]
backends = [Backend.MOTION]

opToCostSymbol = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt',
  '*': 'zi_mul', 'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '%': 'zi_rem', '<<': 'zi_shl', '-': 'zi_sub', '^': 'zi_xor',
  '>>': 'zi_shr', '-UNARY': 'UNAVAILABLE', '&': 'zi_&', '|': 'zi_|', 'Var': 'UNAVAILABLE', '/': 'zi_div', 'not': 'zi_not'}

# MP_SPDZ ==> '*': 'zi_mul' -> too slow in B. Looks like it runs out of memory during runtime
# MP_SPDZ ==> '>>': 'zi_shr' -> too slow in A. Looks like it runs out of memory during compiletime
testedOps = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt',
  'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '%': 'zi_rem', '<<': 'zi_shl', '-': 'zi_sub', '^': 'zi_xor', '&': 'zi_&', '|': 'zi_|', '/': 'zi_div', 'not': 'zi_not'}
opToCostSymbol = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt', '*': 'zi_mul',
  'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '%': 'zi_rem', '<<': 'zi_shl', '-': 'zi_sub', '^': 'zi_xor', '&': 'zi_&', '|': 'zi_|', '/': 'zi_div', 'not': 'zi_not'}
opToCostSymbol = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt', '*': 'zi_mul',
  'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '-': 'zi_sub', '^': 'zi_xor', '&': 'zi_&', '|': 'zi_|', '/': 'zi_div', 'not': 'zi_not'}
# opToCostSymbol = {'+': 'zi_add', '*': 'zi_mul', '-': 'zi_sub', '<': 'zi_lt', 'Mux': 'zi_mux'}

spdzTypes = ["A","B","X","Y"]
spdzMix = ['AB','BA','XB','BX','YB','BY']
spdzMix = []

vecSizes = [1, 2, 5, 10, 25, 50, 100, 200, 300, 500, 800, 1000]
vecSizesConv = [1, 2, 5, 10, 25, 50, 100, 200, 300, 500, 800, 1000]

# trials, loopIters, intSize = (100, 1000, 32)
trials, loopIters, intSize = (20, 20, 32)
port = 12345
conn_address = ''
server_address = '10.10.1.1'

common_prefix = f'{getcwd()}/../backend_submodules/MP-SPDZ/'
timestamp = datetime.datetime.strftime(datetime.datetime.now(), '%Y_%m_%d_%H_%M_%S')

# [TODO] test output
# opToCostSymbol = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt', '*': 'zi_mul',
#   'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '-': 'zi_sub', '^': 'zi_xor', '&': 'zi_&', '|': 'zi_|', '/': 'zi_div','not': 'zi_not'}
# opToCostSymbol = {'+': 'zi_add'}

# Accept them all in this section
# '+': 'zi_add' ALL 
# '==': 'zi_eq' NOT ARITHMETIC 
# '>': 'zi_gt'  ALL 
# '>=': 'zi_ge' NOT ARITHMETIC 
# '<': 'zi_lt'  ALL  # maybe use it ???
# '<=': 'zi_le' NOT ARITHMETIC 
# '*': 'zi_mul' ALL 
# '-': 'zi_sub' ALL 
# '!=':'zi_ne'  NOT ARITHMETIC 
# '^': 'zi_xor' NOT ARITHMETIC 
# '&': 'zi_&' NOT ARITHMETIC 
# '|': 'zi_|' NOT ARITHMETIC 
# 'not': 'zi_not' NOT ARITHMETIC 

# '/': 'zi_div' NOT ARITHMETIC
#  '%': 'zi_rem' NOT USED AND NOT IMPLEMENTED IN MOTION ?? (NEED TO CHECK) 
# '<<': 'zi_shl' NOT USED AND NOT IMPLEMENTED IN MOTION ?? (NEED TO CHECK) 
# '>>': 'zi_shr' NOT USED AND NOT IMPLEMENTED IN MOTION ?? (NEED TO CHECK) 


# STOP HERE TO REFLECT
# WE NEED TO MODIFY THOSE OR CHECK


#[TODO] NEED TO PRINT THE RESULT for the benchmarks




# backends = [Backend.MOTION]
# backends = [Backend.MP_SPDZ]
# spdzMix = []
# vecSizes = [5]
# vecSizesConv = [1]
# trials, loopIters, intSize = (1, 2, 32)
# opToCostSymbol = {'+': 'zi_add'}
# spdzTypes = ["B"]


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

    
    
    if str(backend) == 'MOTION':
        protocol_from, protocol_to = protocol = protocol.split('_')
        # Define the source and destination directories
        source_dir = "./mpc_samples/MOTION/templates"
        destination_dir = f"./test_MOTION_{iters}"

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

        # Generate the build directory
        app_path = f"/opt/mp_opa/compiler/test_MOTION_{iters}"
    
        with open(f'{app_path}/main.cpp','r') as f:
            main_code = f.read()

        main_code = main_code.replace('_vec_size',str(vecSize))
        if protocol_from == "ArithmeticGmw":
            main_code = main_code.replace("_inputA_placeHolder","A = party->In<encrypto::motion::MpcProtocol::kArithmeticGmw>(list_A,0);")
        if protocol_from == 'BooleanGmw':
            main_code = main_code.replace("_inputA_placeHolder","A = party->In<encrypto::motion::MpcProtocol::kBooleanGmw>(encrypto::motion::ToInput(list_A),0);")
        if protocol_from == "Bmr":
            main_code = main_code.replace("_inputA_placeHolder","A = party->In<encrypto::motion::MpcProtocol::kBmr>(encrypto::motion::ToInput(list_A),0);")
        
        main_code = main_code.replace("_inputB_placeHolder","")
        main_code = main_code.replace("list_B.push_back(i);","")
        main_code = main_code.replace("std::vector<std::uint32_t> list_B;","")
        main_code = main_code.replace("encrypto::motion::SecureUnsignedInteger B;","")
        main_code = main_code.replace("template_code(party, A, B);","template_code(party, A);")

        # retrieve the sample 
        with open(f'{app_path}/template_code.h','r') as f:
            code = f.read()

        code = code.replace("encrypto::motion::SecureUnsignedInteger list_A,","encrypto::motion::SecureUnsignedInteger list_A")
        code = code.replace("encrypto::motion::SecureUnsignedInteger list_B","")
        code = code.replace("_type_to_replace","encrypto::motion::SecureUnsignedInteger")
        

        code = code.replace("_operator_to_replace",f"result_C = list_A.Get().Convert<encrypto::motion::MpcProtocol::k{protocol_to}>();")
        code = code.replace("_loop_dependency","list_A = list_A + list_A;")
        code = code.replace("_iters",str(iters))
        # retrieve the sample 
        with open(f'{app_path}/template_code.h','w') as f:
            f.write(code)

        # save the main file to server side
        # Open the file in write mode and write the content
        with open(f'{app_path}/main.cpp', 'w') as f:
            f.write(main_code)

        # Tranfer the code 
        dummy_template_filename = f'MOTION_code.cpp'
        dummy_main_filename = f'MOTION_main.cpp'
        client_mixed_directory = f"client_motion_mixed_{iters}"
        # Build the code 
        sendCmd('save ' + dummy_main_filename + ' ' + main_code)
        sendCmd('save ' + dummy_template_filename + ' ' + code)
        sendCmd(f'execute sudo mkdir -p {client_mixed_directory}')
        sendCmd(f'execute sudo rm -rf ./{client_mixed_directory}/*')
        sendCmd(f'execute sudo cp mpc_samples/MOTION/templates/CMakeLists.txt ./{client_mixed_directory}/')
        sendCmd(f'execute sudo cp mpc_samples/MOTION/templates/collect_stats.cpp ./{client_mixed_directory}/')
        sendCmd(f'execute sudo cp mpc_samples/MOTION/templates/collect_stats.h ./{client_mixed_directory}/')
        sendCmd(f'execute sudo mv {dummy_template_filename} {client_mixed_directory}/template_code.h')
        sendCmd(f'execute sudo mv {dummy_main_filename} {client_mixed_directory}/main.cpp')
        

        # Compile on local version
        subprocess.run(
            ["cmake", "-S", app_path, "-B", path.join(app_path, "build")],
            check=True,
        )

        # Build
        subprocess.run(
            ["cmake", "--build", path.join(app_path, "build"),"-j8"],
            check=True,
        )

        # Compile on clients end
        client_path = f"/opt/mp_opa/compiler/{client_mixed_directory}"
        command1 = f"cmake -S {client_path} -B {path.join(client_path,'build')}"
        command2 = f"cmake --build {path.join(client_path,'build')} -j8"
        sendCmd(f"execute sudo {command1}")
        sendCmd(f"execute sudo {command2}")
        
        return f"{client_mixed_directory}"

    if str(backend) == 'MP-SPDZ':
        protocol = protocol.split('_')[1]
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

        category1 = ["zi_add","zi_mul","zi_sub","zi_div"]
        category2 = ["zi_gt","zi_lt","zi_eq","zi_ge","zi_le","zi_ne","zi_and","zi_or","zi_|","zi_&","zi_xor","zi_not","zi_mux"]
        
        # generate a working directory and move template files there
        
        # Define the source and destination directories
        source_dir = "./mpc_samples/MOTION/templates"
        destination_dir = f"./test_MOTION_{iters}"

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
        app_path = f"/opt/mp_opa/compiler/test_MOTION_{iters}"
    
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
        
        # retrieve the sample 
        with open(f'{app_path}/template_code.h','r') as f:
            code = f.read()

        code = code.replace("_iters",str(iters))

        type1 = "encrypto::motion::SecureUnsignedInteger"
        type2 = "encrypto::motion::ShareWrapper"

        operator_type1 = "result_C = list_A _operator list_B;"
       
        if symbol in category1:
            code = code.replace("_type_to_replace",type1)
            code = code.replace("_operator_to_replace",operator_type1)
            code = code.replace("_operator",operator)
            code = code.replace("_loop_dependency","list_A = result_C;")
        elif symbol in category2:

            if symbol == "zi_gt":
                code = code.replace("_type_to_replace",type2)
                code = code.replace("_operator_to_replace",operator_type1)
                code = code.replace("_operator",operator)
                if protocol == "ArithmeticGmw":
                    code = code.replace("_loop_dependency","list_A = list_A + list_B;")
                else:
                    code = code.replace("_loop_dependency","list_A = result_C.Mux(list_A.Get(),list_B.Get());")
            elif symbol == "zi_lt":
                code = code.replace("_type_to_replace",type2)
                code = code.replace("_operator_to_replace","result_C = list_B > list_A;")
                if protocol == "ArithmeticGmw":
                    code = code.replace("_loop_dependency","list_A = list_A + list_B;")
                else:
                    code = code.replace("_loop_dependency","list_A = result_C.Mux(list_A.Get(),list_B.Get());")
            elif symbol == "zi_ge":
                code = code.replace("_type_to_replace",type2)
                operation = "result_C = (list_A > list_B) | (list_A == list_B);"
                code = code.replace("_operator_to_replace",operation)
                code = code.replace("_loop_dependency","list_A = result_C.Mux(list_A.Get(),list_B.Get());")
            elif symbol == "zi_le":
                code = code.replace("_type_to_replace",type2)
                operation = "result_C = (list_B > list_A) | (list_A == list_B);"
                code = code.replace("_operator_to_replace",operation)
                code = code.replace("_loop_dependency","list_A = result_C.Mux(list_A.Get(),list_B.Get());")
            elif symbol == "zi_eq":
                code = code.replace("_type_to_replace",type2)
                if protocol == "ArithmeticGmw":
                    operation = "result_C = ~((list_A > list_B) | (list_B > list_A));"
                    code = code.replace("_loop_dependency","list_A = list_A + list_B;")
                else:
                    operation = "result_C = (list_A == list_B);"
                    code = code.replace("_loop_dependency","list_A = result_C.Mux(list_A.Get(),list_B.Get());")
                code = code.replace("_operator_to_replace",operation)
            elif symbol == "zi_ne":
                code = code.replace("_type_to_replace",type2)
                if protocol == "ArithmeticGmw":
                    operation = "result_C = ((list_A > list_B) | (list_B > list_A));"
                    code = code.replace("_loop_dependency","list_A = list_A + list_B;")
                else:
                    operation = "result_C = ~(list_A == list_B);"
                    code = code.replace("_loop_dependency","list_A = result_C.Mux(list_A.Get(),list_B.Get());")
                code = code.replace("_operator_to_replace",operation)
            elif symbol == "zi_&":
                code = code.replace("_type_to_replace",type1)
                operation = "list_A = (list_A.Get() & list_B.Get());"
                code = code.replace("_operator_to_replace",operation)
                code = code.replace("_loop_dependency", "")
            elif symbol == "zi_|":
                code = code.replace("_type_to_replace",type1)
                operation = "list_A = (list_A.Get() | list_B.Get());"
                code = code.replace("_operator_to_replace",operation)
                code = code.replace("_loop_dependency", "")
            elif symbol == "zi_and" or symbol == "zi_or" or symbol == "zi_xor":
                replace_symbols = {"zi_and":"&", "zi_or":"|","zi_xor":"^"}
                code = code.replace("_type_to_replace",type1)
                code = code.replace("encrypto::motion::SecureUnsignedInteger","encrypto::motion::ShareWrapper")
                operation = f"list_A = (list_A {replace_symbols[symbol]} list_B);"
                code = code.replace("_operator_to_replace",operation)
                code = code.replace("_loop_dependency", "")
            
                # declarations on main
                main_code = main_code.replace("encrypto::motion::SecureUnsignedInteger A;","encrypto::motion::ShareWrapper A;")
                main_code = main_code.replace("std::vector<std::uint32_t> list_A","std::vector<std::uint8_t> list_A")
                main_code = main_code.replace("encrypto::motion::SecureUnsignedInteger B;","encrypto::motion::ShareWrapper B;")
                main_code = main_code.replace("std::vector<std::uint32_t> list_B","std::vector<std::uint8_t> list_B")

                # input in 0 1
                main_code = main_code.replace("list_A.push_back(i);","list_A.push_back(0);")
                main_code = main_code.replace("list_B.push_back(i);","list_B.push_back(1);")
            
            elif symbol == "zi_not":
            
                code = code.replace("_type_to_replace",type1)
                code = code.replace("encrypto::motion::SecureUnsignedInteger","encrypto::motion::ShareWrapper")

                operation = f"result_C = ~(list_A);"
                code = code.replace("_loop_dependency","list_A = result_C;")
                code = code.replace("_operator_to_replace",operation)
                code = code.replace("encrypto::motion::ShareWrapper list_B","").replace("encrypto::motion::ShareWrapper list_A,","encrypto::motion::ShareWrapper list_A")


                # declarations on main
                main_code = main_code.replace("encrypto::motion::SecureUnsignedInteger A;","encrypto::motion::ShareWrapper A;")
                main_code = main_code.replace("std::vector<std::uint32_t> list_A","std::vector<std::uint8_t> list_A")
                main_code = main_code.replace("encrypto::motion::SecureUnsignedInteger B;","")
                main_code = main_code.replace("std::vector<std::uint32_t> list_B;","")
                main_code = main_code.replace("B = party->In<encrypto::motion::MpcProtocol::kArithmeticGmw>(list_B,1);","")
                main_code = main_code.replace("B = party->In<encrypto::motion::MpcProtocol::kBooleanGmw>(encrypto::motion::ToInput(list_B),1);","")
                main_code = main_code.replace("B = party->In<encrypto::motion::MpcProtocol::kBmr>(encrypto::motion::ToInput(list_B),1);","")
                main_code = main_code.replace("template_code(party, A, B);","template_code(party, A);")


                # input in 0 1
                main_code = main_code.replace("list_A.push_back(i);","list_A.push_back(0);")
                main_code = main_code.replace("list_B.push_back(i);","")

            elif symbol == "zi_mux":
                code = code.replace("_type_to_replace",type1)
                code = code.replace("encrypto::motion::SecureUnsignedInteger result_C;","encrypto::motion::SecureUnsignedInteger result_C; encrypto::motion::ShareWrapper comp = (list_A > list_B);")
                operation = f"list_A = comp.Mux(list_A.Get(),list_B.Get());"
                code = code.replace("_loop_dependency","")
                code = code.replace("_operator_to_replace",operation)
    
        else:
            raise Exception("Dont go here")

        # write the sample 
        with open(f'{app_path}/template_code.h','w') as f:
            f.write(code)


        # save the main file to server side
        # Open the file in write mode and write the content
        with open(f'{app_path}/main.cpp', 'w') as f:
            f.write(main_code)

        # Tranfer the code 
        dummy_template_filename = f'MOTION_code.cpp'
        dummy_main_filename = f'MOTION_main.cpp'
        client_directory = f"client_motion_{iters}"
        # Build the code 
        sendCmd('save ' + dummy_main_filename + ' ' + main_code)
        sendCmd('save ' + dummy_template_filename + ' ' + code)
        sendCmd(f'execute sudo mkdir -p {client_directory}')
        sendCmd(f'execute sudo rm -rf ./{client_directory}/*')
        sendCmd(f'execute sudo cp mpc_samples/MOTION/templates/CMakeLists.txt ./{client_directory}/')
        sendCmd(f'execute sudo cp mpc_samples/MOTION/templates/collect_stats.cpp ./{client_directory}/')
        sendCmd(f'execute sudo cp mpc_samples/MOTION/templates/collect_stats.h ./{client_directory}/')
        sendCmd(f'execute sudo mv {dummy_template_filename} {client_directory}/template_code.h')
        sendCmd(f'execute sudo mv {dummy_main_filename} {client_directory}/main.cpp')

        # Compile on local version
        subprocess.run(
            ["cmake", "-S", app_path, "-B", path.join(app_path, "build")],
            check=True,
        )

        # Build
        subprocess.run(
            ["cmake", "--build", path.join(app_path, "build"),"-j8"],
            check=True,
        )

        # Compile on clients end
        client_path = f"/opt/mp_opa/compiler/{client_directory}"
        command1 = f"cmake -S {client_path} -B {path.join(client_path,'build')}"
        command2 = f"cmake --build {path.join(client_path,'build')} -j8"
        sendCmd(f"execute sudo {command1}")
        sendCmd(f"execute sudo {command2}")
        
        return f"{client_directory}"
    
    elif str(backend) == 'MP-SPDZ':
        
        
        opToCostSymbolCategoryUnary = ['zi_rem',"zi_not"]
        opToCostSymbolCategoryLogical = ['zi_and','zi_or','zi_xor']
        spdzType = protocol.split("_")[1]
        
        if symbol in opToCostSymbolCategoryUnary:
            actualPrototype = 'protocol_unary'
        else:
            actualPrototype = 'protocol'
            
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
        
        if spdzType in {'X','Y','A'}:
            code = code.replace("_inside","")
            code = code.replace("_outside","sint")
        elif spdzType == 'B':
            additional_types = "siv32 = sbitint.get_type(32)\nsb32 = sbits.get_type(32)\n"
            code = additional_types + code
            code = code.replace("_inside","sb32")
            code = code.replace("_outside","siv32")

            if symbol == 'zi_mul':
                code = "program.options.binary = 32\n" + code 
        
        
        code = code.replace("_iters",str(iters)).replace('_vec_size',str(vecSize))
        

        
        if symbol in opToCostSymbolCategoryUnary:
            if symbol == 'zi_rem':
                basic_operation = "c = (a _operator 2)"
            elif symbol == "zi_not":
                basic_operation = "c = (a.bit_not())"
            else:
                raise Exception("Not possible to reach this place currently")
            basic_operation = basic_operation.replace('_operator',operator)
            code = code.replace('_operation',basic_operation)
        elif symbol in opToCostSymbolCategoryLogical:
            code = code.replace('sb32(i)',"sbit(0)").replace("sb32(i+1)","sbit(1)")
            code = code.replace("sbitint.get_type(32)","sbitvec")
            code = code.replace('sint',"sintbit")
            if symbol.split('_')[1] == 'or': 
                basic_operation = "c = ((a.bit_not()).bit_and(b.bit_not())).bit_not()"
            else: 
                basic_operation = "c = (a_operator(b))"
                basic_operation = basic_operation.replace('_operator',f".bit_{symbol.split('_')[1]}")
            code = code.replace('_operation',basic_operation)
        else:
            if symbol == 'zi_mux':
                code = code.replace('_operation',f"c = a.if_else(b,b)")
                if spdzType == 'B':
                    code = code.replace("a = siv32([sb32(i) ","a = sbitvec([sbit(0) ")
                else:
                    code = code.replace("a = sint([(i) ","a = sintbit([(0) ")
   
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
        app_path = f"/opt/mp_opa/compiler/test_MOTION_{iters}/build/template_code"
        client_path = f"/opt/mp_opa/compiler/{codeName}/build/template_code"
        p = subprocess.Popen(["sudo",app_path,"--my-id","0", "--parties", f"0,{server_address},23000",f"1,{conn_address},23001"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,)
        sendCmd(f'execute sudo {client_path} --my-id 1 --parties 0,{server_address},23000 1,{conn_address},23001')

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
                    finalStats[vecSize] = "Generation Error"
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
            except Exception as e:
                print(e)
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
            finalStats[vecSize] = "Execution Error"
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

    resultsDict = {"params": {"trials": trials, "loopIters": loopIters, "intSize": intSize, "MUX_IN_ALL_MOTION_OPS": True}}
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
                            printOutputToJSON(resultsDict, log=False, save=True)
                    else:
                        resultsDict[str(backend)][sym][protocol] = runBenchmark(backend, protocol, op, sym, trials, loopIters)
                        printOutputToJSON(resultsDict, log=False, save=True)

        # Compute conversion costs
        convPossibilities = spdzMix if backend == Backend.MP_SPDZ else backend.valid_protocols()
        for protocol in backend.valid_protocols():
            for conv in convPossibilities:
                if protocol == conv:
                    continue
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
                # if protocol != 'semi' and str(backend) == 'MP-SPDZ':
                #     continue
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
            for conv in convPossibilities:
                if protocol == conv:
                    continue
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
# createCostTable()
repairCostTable('partialMOTIONREDOTable.txt', useLastTable=False)
sendCmd('quit')
s.close()
