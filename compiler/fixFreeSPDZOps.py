import os, json
from math import ceil

threshold = 1e-5

# replace small numbers and negative numbers with 0
# round comm rounds up
# remove operators with {}
def clean(costs):
    if costs.keys():
        for i in costs.keys():
            for j in costs[i].keys():
                if costs[i][j] < threshold:
                    costs[i][j] = 0.0
            costs[i]['commRounds'] = ceil(costs[i]['commRounds'])


# find target input file
file = ""
if file == "":
    files = [f for f in os.listdir(".") if os.path.isfile(os.path.join(".", f))]
    for f in files:
        if f.__contains__("cost_table.txt"):
            file = f
with open(file, 'r') as f:
    rawJSON = json.load(f)
spdzJSON = rawJSON['MP-SPDZ']
if 'UNAVAILABLE' in spdzJSON.keys():
    del spdzJSON['UNAVAILABLE']

# find the set of protocols and share types in the cost table
protocols = set()
shareTypes = set()
conversions = set()
for op in spdzJSON.keys():
    if 'zi_' in op:
        for protocol in spdzJSON[op].keys():
            x = protocol.split('_')
            protocols.add(x[0])
            shareTypes.add(x[1])
    else:
        conversions.add(op)
protocols = sorted(list(protocols))
shareTypes = sorted(list(shareTypes))

# clean up the json entries and remove missing measurements
toRem = []
for op in spdzJSON.keys():
    if op in conversions:
        clean(spdzJSON[op])
    else:

        for protocol in spdzJSON[op].keys():
            if spdzJSON[op][protocol] == dict():
                toRem.append((op, protocol))
            else:
                clean(spdzJSON[op][protocol])
for op, protocol in toRem:
    del spdzJSON[op][protocol]
toRem = []
for op in spdzJSON.keys():
    if spdzJSON[op] == dict():
        toRem.append(op)
for op in toRem:
    del spdzJSON[op]

# print to output file
with open(file[:-3] + 'json', 'w') as f:
    f.write(json.dumps(rawJSON, indent=4))
