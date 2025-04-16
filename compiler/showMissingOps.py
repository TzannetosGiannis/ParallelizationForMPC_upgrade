import os, json


def showMissingOps(fileName):
    # find target input file
    if fileName:
        fileName = fileName.replace('.txt', '.json')
        if not os.path.exists(fileName):
            raise Exception("Unable to find provided file")
    else:
        files = sorted([f for f in os.listdir(".") if os.path.isfile(os.path.join(".", f))])
        for f in files:
            if f.__contains__("cost_table.json"):
                fileName = f
    with open(fileName, 'r') as f:
        rawJSON = json.load(f)
    print(f'Identifying missing operators in {fileName}')

    # process each backend
    csvString = ''
    for b in rawJSON.keys():
        if b == 'params':
            continue
        backendJSON = rawJSON[b]
        if 'UNAVAILABLE' in backendJSON.keys():
            del backendJSON['UNAVAILABLE']

        # find the set of protocols and share types in the cost table
        protocols = {'MOTION'} if b == 'MOTION' else set()
        shareTypes = set()
        conversions = set()
        for op in backendJSON.keys():
            if 'zi_' in op:
                for protocol in backendJSON[op].keys():
                    if b == 'MOTION':
                        shareTypes.add(protocol)
                    else:
                        x = protocol.split('_')
                        protocols.add(x[0])
                        shareTypes.add(x[1])
            else:
                conversions.add(op)
        protocols = sorted(list(protocols))
        shareTypes = sorted(list(shareTypes))
        headerString = ',' + ','.join(shareTypes) + '\n'

        # convert the cost table into a series of csv tables (one for each protocol)
        for protocol in protocols:
            csvString += ('' if b == 'MOTION' else b + '_') + protocol + headerString

            # for each operator, write which share types are present
            for op in backendJSON.keys():
                csvString += op + ','
                if op in conversions:
                    for shareType in shareTypes:
                        convProts = op if b == 'MOTION' else op.split('_')[1]
                        if shareType in convProts:
                            csvString += ','
                        else:
                            csvString += 'x,'
                else:
                    for shareType in shareTypes:
                        k = ('' if b == 'MOTION' else protocol + '_') + shareType
                        if k in backendJSON[op].keys():
                            if len(backendJSON[op][k]) != 0:
                                csvString += ','
                            else:
                                csvString += 'x,'
                        else:
                            csvString += 'x,'
                csvString = csvString[:-1] + '\n'
            csvString += '\n\n'

    fileName = fileName[:-11] + 's.csv'
    with open(fileName, 'w') as f:
        print(f'\tWriting {fileName}\n')
        f.write(csvString)
