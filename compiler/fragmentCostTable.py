import os, json, sys


# find target input file
file = ""
if file == "":
    files = [f for f in os.listdir(".") if os.path.isfile(os.path.join(".", f))]
    for f in files:
        if f.__contains__("cost_table.json"):
            file = f
with open(file, 'r') as f:
    rawJSON = json.load(f)
spdzJSON = rawJSON['MP-SPDZ']

# create starting folders
if not os.path.isdir('Cost_Tables'):
    os.makedirs('Cost_Tables')
if not os.path.isdir('Cost_Tables/MP-SPDZ'):
    os.makedirs('Cost_Tables/MP-SPDZ')

# parse table to find folder structure
protocols = set()
measurementTypes = set()
operators = set()
shareTypes = set()
conversions = set()
for op in spdzJSON.keys():
    if 'zi_' in op:
        operators.add(op)
        for k in spdzJSON[op].keys():
            protocol, shareType = k.split('_')
            shareTypes.add(shareType.lower())
            protocols.add(protocol)
            for v in spdzJSON[op][k].keys():
                measurementTypes |= set(spdzJSON[op][k][v].keys())
    else:
        protocol, conv = op.split('_')
        operators.add('zic_' + conv[0].lower() + '2' + conv[1].lower())
        protocols.add(protocol)
        conversions.add(conv[0].lower() + '2' + conv[1].lower())
        for v in spdzJSON[op].keys():
            measurementTypes |= set(spdzJSON[op][v].keys())

# make folder structure and initialize split tables
restructuredJSON = dict()
intSize = str(rawJSON['params']['intSize'])
for protocol in protocols:
    restructuredJSON[protocol] = dict()
    if not os.path.isdir(f'Cost_Tables/MP-SPDZ/{protocol}'):
        os.makedirs(f'Cost_Tables/MP-SPDZ/{protocol}')
    for measType in measurementTypes:
        restructuredJSON[protocol][measType] = dict()
        restructuredJSON[protocol][measType][intSize] = dict()
        for op in operators:
            restructuredJSON[protocol][measType][intSize][op] = dict()
            if op.split('_')[1] not in conversions:
                for shareType in shareTypes:
                    restructuredJSON[protocol][measType][intSize][op][shareType] = dict()

# populate split tables
for op in spdzJSON.keys():
    if 'zi_' in op:
        for k in spdzJSON[op].keys():
            protocol, shareType = k.split('_')
            for valStr in spdzJSON[op][k].keys():
                val = int(valStr)
                for measType in spdzJSON[op][k][valStr].keys():
                    restructuredJSON[protocol][measType][intSize][op][shareType.lower()][valStr] = spdzJSON[op][k][valStr][measType] / val * 1000
    else:
        protocol, conv = op.split('_')
        convOp = 'zic_' + conv[0].lower() + '2' + conv[1].lower()
        for valStr in spdzJSON[op].keys():
            val = int(valStr)
            for measType in spdzJSON[op][valStr].keys():
                restructuredJSON[protocol][measType][intSize][convOp][valStr] = spdzJSON[op][valStr][measType] / val * 1000
        convA = conv[0]
        convB = conv[1]

# remove empty share types
toRem = []
for protocol in restructuredJSON.keys():
    for measType in restructuredJSON[protocol].keys():
        for intSize in restructuredJSON[protocol][measType].keys():
            for op in restructuredJSON[protocol][measType][intSize].keys():
                if 'zi_' in op:
                    for shareType in restructuredJSON[protocol][measType][intSize][op].keys():
                        if restructuredJSON[protocol][measType][intSize][op][shareType] == dict():
                            toRem.append((protocol, measType, intSize, op, shareType))

for protocol, measType, intSize, op, shareType in toRem:
    del restructuredJSON[protocol][measType][intSize][op][shareType]

# print output files
for protocol in protocols:
    for measType in measurementTypes:
        fileName = f'Cost_Tables/MP-SPDZ/{protocol}/{measType}.json'
        with open(fileName, 'w') as f:
            print(f'Writing {fileName}')
            f.write(json.dumps(restructuredJSON[protocol][measType], indent=4, sort_keys=True))
