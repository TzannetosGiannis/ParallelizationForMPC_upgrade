import os, json


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
headerString = ',' + ','.join(shareTypes) + '\n'

# convert the cost table into a series of csv tables (one for each protocol)
csvString = ''
for protocol in protocols:
    csvString += protocol + headerString

    # for each operator, write which share types are present
    for op in spdzJSON.keys():
        csvString += op + ','
        if op in conversions:
            for shareType in shareTypes:
                convProts = op.split('_')[1]
                if shareType in convProts:
                    csvString += ','
                else:
                    csvString += 'x,'
        else:
            for shareType in shareTypes:
                k = protocol + '_' + shareType
                if k in spdzJSON[op].keys():
                    if len(spdzJSON[op][k]) != 0:
                        csvString += ','
                    else:
                        csvString += 'x,'
                else:
                    csvString += 'x,'
        csvString = csvString[:-1] + '\n'
    csvString += '\n\n'

print(csvString)
with open(file[:-10] + 's.csv', 'w') as f:
    f.write(csvString)
