import json
import ast
with open('FULLResults.json', 'r') as f:
    contents = json.loads(f.read())

def format_mix_type_subscript(s):
    elems = ast.literal_eval(s)  # safely parse string list to Python list
    joined = ','.join(elems)
    return f"_{{{joined}}}"


def generate_multirow_line(entry):
    label = entry['label']
    rowspan = len(entry['dims'])
    return f"\\multirow{{{rowspan}}}{{*}}{{{label}}}"

keyList = [
    {"key":'biometric',"label":'Biometric Matching (D,N)', 'dims': []},
    {"key":'convex_hull',"label":'Convex Hull (N)', 'dims': []},
    {"key":'count_102',"label":'Count 102 (N)', 'dims': []},
    {"key":'count_10s',"label":'Count 10 (N)', 'dims': []},
    {"key":'cryptonets_max_pooling',"label":'Cryptonets Max Pooling (R,C)', 'dims': []},
    {"key":'db_cross_join_trivial',"label":'Database Join (A,B)', 'dims': []},
    {"key":'db_variance',"label":'Database Variance (N)', 'dims': []},
    {"key":'inner_product',"label":'Inner Product (N)', 'dims': []},
    {"key":'longest_102',"label":'Longest 102 (N)', 'dims': []},
    {"key":'max_dist_between_syms',"label":'Max Distance b/w Symbols (N)', 'dims': []},
    {"key":'minimal_points',"label":'Minimal Points (N)', 'dims': []},
    {"key":'mnist_relu',"label":'MNIST ReLU (O,I)', 'dims': []},
    {"key":'psi',"label":'Private Set Intersection (A,B)', 'dims': []},
    
]


def format_entry(entry):
    if '=' in entry:
        # Split by comma, then by '=', take only the values
        parts = entry.split(',')
        values = [int(p.split('=')[1].strip()) for p in parts]
        return values
    else:
        # For entries like '16, 512' or '32, 32'
        parts = entry.split(',')
        values = [int(p) for p in parts]
        return values
    
for i in range(len(keyList)):
    elem = keyList[i]
    keys = list(contents['MOTION'][elem['key']].keys())
    for key in keys:
        keyList[i]['dims'].append({"key":key, "label": format_entry(key)})
    keyList[i]['dims'] = sorted(keyList[i]['dims'], key=lambda x: x['label'])

for elem in keyList:
    multi_line_key = generate_multirow_line(elem)
    lines = [[]]
    for dim in elem['dims']:
        lines[-1].append(",".join([str(x) for x in dim['label']]))

        ArithmeticGMW = not (type(contents['MOTION'][elem['key']][dim['key']]['ArithmeticGmw']) == str )
        lines[-1].append(f"{contents['MOTION'][elem['key']][dim['key']]['ArithmeticGmw']['time']:.2f}" if ArithmeticGMW else "N/A")
        lines[-1].append(f"{contents['MOTION'][elem['key']][dim['key']]['BooleanGmw']['time']:.2f}")
        lines[-1].append(f"{contents['MOTION'][elem['key']][dim['key']]['Bmr']['time']:.2f}")

        mixedElems = ast.literal_eval(contents['MOTION'][elem['key']][dim['key']]['mixed']['mixType'])
        isMixed = "\ding{51}" if (len(mixedElems) > 1) else "\ding{55}"
        lines[-1].append(isMixed)
        lines[-1].append((',').join(mixedElems))
        lines[-1].append(f"{contents['MOTION'][elem['key']][dim['key']]['mixed']['time']:.2f}")
        lines.append([])
    lines.pop()
    assigned_Benchmark = False
    
    for line in lines:
        if not assigned_Benchmark:
            print(f"{multi_line_key} & ", end='')
            assigned_Benchmark = True
        else:
            print(f" & ", end='')
        print(" & ".join(line) + r' \\')
    print("\cline{1-8}")


print('----------------------------------------------------')


keyList = [
    {"key":'biometric',"label":'Biometric Matching', 'dims': []},
    {"key":'convex_hull',"label":'Convex Hull', 'dims': []},
    {"key":'count_102',"label":'Count 102', 'dims': []},
    {"key":'count_10s',"label":'Count 10', 'dims': []},
    {"key":'cryptonets_max_pooling',"label":'Cryptonets Max Pooling', 'dims': []},
    {"key":'db_cross_join_trivial',"label":'Database Join', 'dims': []},
    {"key":'db_variance',"label":'Database Variance', 'dims': []},
    {"key":'inner_product',"label":'Inner Product', 'dims': []},
    {"key":'longest_102',"label":'Longest 102', 'dims': []},
    {"key":'max_dist_between_syms',"label":'Max Distance b/w Symbols', 'dims': []},
    {"key":'minimal_points',"label":'Minimal Points', 'dims': []},
    {"key":'mnist_relu',"label":'MNIST ReLU', 'dims': []},
    {"key":'psi',"label":'Private Set Intersection', 'dims': []},
    
]

for i in range(len(keyList)):
    elem = keyList[i]
    keys = list(contents['MP-SPDZ'][elem['key']].keys())
    for key in keys:
        keyList[i]['dims'].append({"key":key, "label": format_entry(key)})
    keyList[i]['dims'] = sorted(keyList[i]['dims'], key=lambda x: x['label'])


for elem in keyList:
    multi_line_key = generate_multirow_line(elem)
    lines = [[]]
    for dim in elem['dims']:
        lines[-1].append(",".join([str(x) for x in dim['label']]))

        lines[-1].append(f"{contents['MP-SPDZ'][elem['key']][dim['key']]['A']['time']:.2f}")
        B = not (type(contents['MP-SPDZ'][elem['key']][dim['key']]['B']) == str )
        lines[-1].append(f"{contents['MP-SPDZ'][elem['key']][dim['key']]['B']['time']:.2f}" if B else "N/A")
        lines[-1].append(f"{contents['MP-SPDZ'][elem['key']][dim['key']]['X']['time']:.2f}")
        lines[-1].append(f"{contents['MP-SPDZ'][elem['key']][dim['key']]['Y']['time']:.2f}")

        mixedElems = ast.literal_eval(contents['MP-SPDZ'][elem['key']][dim['key']]['mixed']['mixType'])
        isMixed = "\ding{51}" if (len(mixedElems) > 1) else "\ding{55}"
        lines[-1].append(isMixed)
        lines[-1].append((',').join(mixedElems))
        lines[-1].append(f"{contents['MP-SPDZ'][elem['key']][dim['key']]['mixed']['time']:.2f}")
        lines.append([])
    lines.pop()
    assigned_Benchmark = False
    
    for line in lines:
        if not assigned_Benchmark:
            print(f"{multi_line_key} & ", end='')
            assigned_Benchmark = True
        else:
            print(f" & ", end='')
        print(" & ".join(line) + r' \\')
    print("\cline{1-9}")


print('----------------------------------------------------')


