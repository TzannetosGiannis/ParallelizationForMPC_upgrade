import os, json
from math import ceil
threshold = 1e-8


# replace small numbers and negative numbers with 0
# round comm rounds up
def clean(costs, backend):
    if costs.keys():
        toRem = set()
        for i in costs.keys():
            if 'Error' in costs[i]:
                toRem.add(i)
                continue
            if backend == 'MOTION':
                costs[i]['time'] /= 1000
            for j in costs[i].keys():
                if costs[i][j] < threshold:
                    costs[i][j] = 0.0
            costs[i]['commRounds'] = ceil(costs[i]['commRounds'])
        for r in toRem:
            del costs[r]


def fixFreeOps(fileName):
    print(f'Fixing free operators and removing unavailable operators in {fileName}')
    # find target input file
    if fileName:
        if not os.path.exists(fileName):
            raise Exception("Unable to find provided file")
    else:
        files = sorted([f for f in os.listdir(".") if os.path.isfile(os.path.join(".", f))])
        for f in files:
            if f.__contains__("cost_table.txt"):
                fileName = f
    with open(fileName, 'r') as f:
        rawJSON = json.load(f)

    # process each backend
    for b in rawJSON.keys():
        if b == 'params':
            continue

        backendJSON = rawJSON[b]
        if 'UNAVAILABLE' in backendJSON.keys():
            del backendJSON['UNAVAILABLE']

        # find the set of conversions for this backend
        conversions = set()
        for op in backendJSON.keys():
            if 'zi_' not in op:
                conversions.add(op)

        # clean up the json entries and remove missing measurements
        toRem = []
        for op in backendJSON.keys():
            if op in conversions:
                clean(backendJSON[op], b)
            else:
                for protocol in backendJSON[op].keys():
                    clean(backendJSON[op][protocol], b)
                    if backendJSON[op][protocol] == dict():
                        toRem.append((op, protocol))
        for op, protocol in toRem:
            del backendJSON[op][protocol]
        toRem = []
        for op in backendJSON.keys():
            if backendJSON[op] == dict():
                toRem.append(op)
        for op in toRem:
            del backendJSON[op]

    # print to output file
    fileName = fileName[:-3] + 'json'
    with open(fileName, 'w') as f:
        print(f'\tWriting {fileName}\n')
        f.write(json.dumps(rawJSON, indent=4))
