import os, json
from math import ceil
muxDepOps = {"zi_gt", "zi_lt", "zi_eq", "zi_ge", "zi_le", "zi_ne"}


def fixDepCosts(costs, muxCosts, addCosts):
    for op in costs.keys():
        if not op.startswith('zi_'):
            protocol = op.split('_')[0]
            for vecSize in costs[op].keys():
                for costType in costs[op][vecSize].keys():
                    costs[op][vecSize][costType] -= addCosts[protocol][vecSize][costType]
                    if costs[op][vecSize][costType] < 0:
                        costs[op][vecSize][costType] = 0.0

        elif op in muxDepOps:
            for protocol in costs[op].keys():
                for vecSize in costs[op][protocol].keys():
                    for costType in costs[op][protocol][vecSize].keys():
                        costs[op][protocol][vecSize][costType] -= addCosts[protocol][vecSize][costType] if protocol == 'ArithmeticGmw' else muxCosts[protocol][vecSize][costType]
                        if costs[op][protocol][vecSize][costType] < 0:
                            costs[op][protocol][vecSize][costType] = 0.0


def fixMotionOps(fileName):
    print(f'Fixing MOTION costs in {fileName} (MUX costs were included in some operators to force loop dependence for measurements)')
    # find target input file
    fileName = fileName.replace('.txt', '.json')
    if not os.path.exists(fileName):
        raise Exception("Unable to find provided file")
    with open(fileName, 'r') as f:
        rawJSON = json.load(f)

    backendJSON = rawJSON['MOTION']

    fixDepCosts(backendJSON, backendJSON['zi_mux'], backendJSON['zi_add'])

    # print to output file
    with open(fileName, 'w') as f:
        print(f'\tWriting {fileName}\n')
        f.write(json.dumps(rawJSON, indent=4))
