import os, json


def fragmentCostTable(fileName):
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
    print(f'Fragmenting {fileName} into local cost tables in Cost_Tables directory')

    # create starting folder
    if not os.path.isdir('Cost_Tables'):
        os.makedirs('Cost_Tables')

    for b in rawJSON.keys():
        # create subdirectory for each backend
        if b == 'params':
            continue
        if not os.path.isdir(f'Cost_Tables/{b}'):
            os.makedirs(f'Cost_Tables/{b}')
        backendJSON = rawJSON[b]
        if b == 'MP-SPDZ':
            # parse table to find folder structure
            protocols = set()
            measurementTypes = set()
            operators = set()
            shareTypes = set()
            conversions = set()
            for op in backendJSON.keys():
                if 'zi_' in op:
                    operators.add(op)
                    for k in backendJSON[op].keys():
                        protocol, shareType = k.split('_')
                        shareTypes.add(shareType.lower())
                        protocols.add(protocol.lower())
                        for v in backendJSON[op][k].keys():
                            measurementTypes |= set(backendJSON[op][k][v].keys())
                else:
                    protocol, conv = op.split('_')
                    operators.add('zic_' + conv[0].lower() + '2' + conv[1].lower())
                    protocols.add(protocol.lower())
                    conversions.add(conv[0].lower() + '2' + conv[1].lower())
                    for v in backendJSON[op].keys():
                        measurementTypes |= set(backendJSON[op][v].keys())

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
            for op in backendJSON.keys():
                if 'zi_' in op:
                    for k in backendJSON[op].keys():
                        protocol, shareType = k.split('_')
                        for valStr in backendJSON[op][k].keys():
                            val = int(valStr)
                            for measType in backendJSON[op][k][valStr].keys():
                                # [TODO] maybe we need the dataSent in MB ? Only god knows
                                scale_factor = 1
                                restructuredJSON[protocol][measType][intSize][op][shareType.lower()][val] = backendJSON[op][k][valStr][measType] / val * scale_factor
                else:
                    protocol, conv = op.split('_')
                    convOp = 'zic_' + conv[0].lower() + '2' + conv[1].lower()
                    for valStr in backendJSON[op].keys():
                        val = int(valStr)
                        for measType in backendJSON[op][valStr].keys():
                            restructuredJSON[protocol][measType][intSize][convOp][val] = backendJSON[op][valStr][measType] / val * scale_factor
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
                        print(f'\tWriting {fileName}')
                        f.write(json.dumps(restructuredJSON[protocol][measType], indent=4, sort_keys=True))

        elif b == 'MOTION':
            # parse table to find folder structure
            protocols = set()
            measurementTypes = set()
            operators = set()
            conversions = set()
            for op in backendJSON.keys():
                if 'zi_' in op:
                    operators.add(op)
                    for k in backendJSON[op].keys():
                        protocols.add(k.lower())
                        for v in backendJSON[op][k].keys():
                            measurementTypes |= set(backendJSON[op][k][v].keys())
                else:
                    protFrom, protTo = op.split('_')
                    protFrom = protFrom.lower()
                    protTo = protTo.lower()
                    operators.add(f'zic_{protFrom}2{protTo}')
                    protocols.add(protFrom.lower())
                    protocols.add(protTo.lower())
                    conversions.add(f'zic_{protFrom}2{protTo}')
                    for v in backendJSON[op].keys():
                        measurementTypes |= set(backendJSON[op][v].keys())

            # make folder structure and initialize split tables
            restructuredJSON = dict()
            intSize = str(rawJSON['params']['intSize'])
            for measType in measurementTypes:
                restructuredJSON[measType] = dict()
                restructuredJSON[measType][intSize] = dict()
                for op in operators:
                    restructuredJSON[measType][intSize][op] = dict()
                    if op not in conversions:
                        for protocol in protocols:
                            restructuredJSON[measType][intSize][op][protocol] = dict()

            # populate split tables
            for op in backendJSON.keys():
                if 'zi_' in op:
                    for k in backendJSON[op].keys():
                        for valStr in backendJSON[op][k].keys():
                            val = int(valStr)
                            for measType in backendJSON[op][k][valStr].keys():
                                scale_factor = 1
                                restructuredJSON[measType][intSize][op][k.lower()][val] = backendJSON[op][k][valStr][measType] / val * scale_factor
                else:
                    protFrom, protTo = op.split('_')
                    protFrom = protFrom.lower()
                    protTo = protTo.lower()
                    convOp = f'zic_{protFrom}2{protTo}'
                    for valStr in backendJSON[op].keys():
                        val = int(valStr)
                        for measType in backendJSON[op][valStr].keys():
                            scale_factor = 1
                            restructuredJSON[measType][intSize][convOp][val] = backendJSON[op][valStr][measType] / val * scale_factor

            # remove empty share types
            toRem = []
            for measType in restructuredJSON.keys():
                for intSize in restructuredJSON[measType].keys():
                    for op in restructuredJSON[measType][intSize].keys():
                        if 'zi_' in op:
                            for protocol in restructuredJSON[measType][intSize][op].keys():
                                if restructuredJSON[measType][intSize][op][protocol] == dict():
                                    toRem.append((measType, intSize, op, protocol))

            for measType, intSize, op, protocol in toRem:
                del restructuredJSON[measType][intSize][op][protocol]

            # print output files
            for measType in measurementTypes:
                fileName = f'Cost_Tables/MOTION/{measType}.json'
                with open(fileName, 'w') as f:
                    print(f'\tWriting {fileName}')
                    f.write(json.dumps(restructuredJSON[measType], indent=4, sort_keys=True).replace('arithmeticgmw', 'a').replace('booleangmw', 'b').replace('bmr', 'y'))
