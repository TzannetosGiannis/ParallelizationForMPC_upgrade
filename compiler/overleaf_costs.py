import json
import ast

def format_metric(value):
    if isinstance(value, int):
        return str(value)
    elif isinstance(value, float):
        return f"{value:.4f}"
    else:
        return 'N/A'

with open('FULL_cost_table.json', 'r') as f:
    contents = json.loads(f.read())




MOTION = contents['MOTION']
MP_SPDZ = contents['MP-SPDZ']
MOTION_PROTOCOLS = ['ArithmeticGmw', 'BooleanGmw','Bmr']
MP_SPDZ_PROTOCOLS = ['semi_A', 'semi_B', 'semi_X','semi_Y']
TOTAL_AVAIL_KEYS = ['zi_add', 'zi_and', 'zi_eq', 'zi_ge', 'zi_gt', 'zi_le', 'zi_lt', 'zi_mul', 'zi_sub', 'zi_mux', 'zi_ne', 'zi_or', 'zi_xor', 'zi_&', 'zi_|', 'zi_div', 'zi_not']
TOTAL_AVAIL_SIZES = ["1","2","5","10","25","50","100","200","500","800","1000"]

KEY_MAPPING = {
    'zi_add': 'addition',
    'zi_and': 'logical and',
    'zi_eq': 'equality',
    'zi_ge': 'greater-equal',
    'zi_gt': 'greater-than', 
    'zi_le': 'less-equal',
    'zi_lt': 'less-than',
    'zi_mul': 'multiplication',
    'zi_sub': 'subtraction',
    'zi_mux': 'MUX',
    'zi_ne': 'not-equal',
    'zi_or': 'logical or',
    'zi_xor': 'bitwise xor',
    'zi_&': 'bitwise and',
    'zi_|': 'bitwise or',
    'zi_div': 'division',
    'zi_not': 'bitwise not',
    "ArithmeticGmw_BooleanGmw": f'$ArithmeticGmw \\rightarrow BooleanGmw$',
    "ArithmeticGmw_Bmr": f'$ArithmeticGmw \\rightarrow Bmr$',
    "BooleanGmw_ArithmeticGmw": f'$BooleanGmw \\rightarrow ArithmeticGmw$',
    "BooleanGmw_Bmr": f'$BooleanGmw \\rightarrow Bmr$',
    "Bmr_ArithmeticGmw": f'$Bmr \\rightarrow ArithmeticGmw$',
    "Bmr_BooleanGmw": f'$Bmr \\rightarrow BooleanGmw$',
    "semi_AB": f'$A \\rightarrow B$',
    "semi_AX": f'$A \\rightarrow X$',
    "semi_AY": f'$A \\rightarrow Y$',
    "semi_BA": f'$B \\rightarrow A$',
    "semi_BX": f'$B \\rightarrow X$',
    "semi_BY": f'$B \\rightarrow Y$',
    "semi_XA": f'$X \\rightarrow A$',
    "semi_XB": f'$X \\rightarrow B$',
    "semi_XY": f'$X \\rightarrow Y$',
    "semi_YA": f'$Y \\rightarrow A$',
    "semi_YB": f'$Y \\rightarrow B$',
    "semi_YX": f'$Y \\rightarrow $X'
}


def generateLatexRows(tableData):
    return '\n'.join([' & '.join(row) + ' \\\\' for row in tableData])

rowsMOTION = []

for key in MOTION.keys():
    if key not in TOTAL_AVAIL_KEYS:
        break

    for size in TOTAL_AVAIL_SIZES:
        rowsMOTION.append([KEY_MAPPING[key],size])
        localDict = {}
        for MPC in MOTION_PROTOCOLS:
            if MPC in MOTION[key]:
            #     if size in MOTION[key][MPC]: 
                time = format_metric(MOTION[key][MPC][size].get('time', 'N/A'))
                dataSent = format_metric(MOTION[key][MPC][size].get('dataSent', 'N/A'))
                commRounds = format_metric(MOTION[key][MPC][size].get('commRounds', 'N/A'))
                localDict[f"{MPC}_time"] = time
                localDict[f"{MPC}_dataSent"] = dataSent
                localDict[f"{MPC}_commRounds"] = commRounds
               
        rowsMOTION[-1].extend([
            localDict.get('ArithmeticGmw_time', 'N/A'),
            localDict.get('BooleanGmw_time', 'N/A'),
            localDict.get('Bmr_time', 'N/A'),
    
            localDict.get('ArithmeticGmw_dataSent', 'N/A'),
            localDict.get('BooleanGmw_dataSent', 'N/A'),
            localDict.get('Bmr_dataSent', 'N/A'),

            localDict.get('ArithmeticGmw_commRounds', 'N/A'),
            localDict.get('BooleanGmw_commRounds', 'N/A'),
            localDict.get('Bmr_commRounds', 'N/A')
        ])        


   

# print(generateLatexRows(rowsMOTION))
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')


rowsMP_SPDZ_1 = []

for key in MP_SPDZ.keys():
    if key not in TOTAL_AVAIL_KEYS:
        break

    for size in TOTAL_AVAIL_SIZES:
        rowsMP_SPDZ_1.append([KEY_MAPPING[key],size])
        localDict = {}
        for MPC in MP_SPDZ_PROTOCOLS:
            if MPC in MP_SPDZ[key]:
                if size in MP_SPDZ[key][MPC]: 
                    time = format_metric(MP_SPDZ[key][MPC][size].get('time', 'N/A'))
                    dataSent = format_metric(MP_SPDZ[key][MPC][size].get('dataSent', 'N/A'))
                    commRounds = format_metric(MP_SPDZ[key][MPC][size].get('commRounds', 'N/A'))
                    localDict[f"{MPC}_time"] = time
                    localDict[f"{MPC}_dataSent"] = dataSent
                    localDict[f"{MPC}_commRounds"] = commRounds
                else:
                    localDict[f"{MPC}_time"] = 'N/A'
                    localDict[f"{MPC}_dataSent"] = 'N/A'
                    localDict[f"{MPC}_commRounds"] = 'N/A'

               
        rowsMP_SPDZ_1[-1].extend([
            localDict.get('semi_A_time', 'N/A'),
            localDict.get('semi_B_time', 'N/A'),
            localDict.get('semi_X_time', 'N/A'),
            localDict.get('semi_Y_time', 'N/A'),
    
        ])        

# print(generateLatexRows(rowsMP_SPDZ_1))
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')



rowsMP_SPDZ_2 = []

for key in MP_SPDZ.keys():
    if key not in TOTAL_AVAIL_KEYS:
        break

    for size in TOTAL_AVAIL_SIZES:
        rowsMP_SPDZ_2.append([KEY_MAPPING[key],size])
        localDict = {}
        for MPC in MP_SPDZ_PROTOCOLS:
            if MPC in MP_SPDZ[key]:
                if size in MP_SPDZ[key][MPC]: 
                    time = format_metric(MP_SPDZ[key][MPC][size].get('time', 'N/A'))
                    dataSent = format_metric(MP_SPDZ[key][MPC][size].get('dataSent', 'N/A'))
                    commRounds = format_metric(MP_SPDZ[key][MPC][size].get('commRounds', 'N/A'))
                    localDict[f"{MPC}_time"] = time
                    localDict[f"{MPC}_dataSent"] = dataSent
                    localDict[f"{MPC}_commRounds"] = commRounds
                else:
                    localDict[f"{MPC}_time"] = 'N/A'
                    localDict[f"{MPC}_dataSent"] = 'N/A'
                    localDict[f"{MPC}_commRounds"] = 'N/A'

               
        rowsMP_SPDZ_2[-1].extend([
            localDict.get('semi_A_dataSent', 'N/A'),
            localDict.get('semi_B_dataSent', 'N/A'),
            localDict.get('semi_X_dataSent', 'N/A'),
            localDict.get('semi_Y_dataSent', 'N/A'),

            localDict.get('semi_A_commRounds', 'N/A'),
            localDict.get('semi_B_commRounds', 'N/A'),
            localDict.get('semi_X_commRounds', 'N/A'),
            localDict.get('semi_Y_commRounds', 'N/A'),
    
        ])   



# print(generateLatexRows(rowsMP_SPDZ_2))
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')

MOTIONrowsComvertion = []

for key in MOTION.keys():
    if key  in TOTAL_AVAIL_KEYS:
        continue
    for size in TOTAL_AVAIL_SIZES:
        MOTIONrowsComvertion.append([KEY_MAPPING[key],size])
        time = format_metric(MOTION[key][size].get('time', 'N/A'))
        dataSent = format_metric(MOTION[key][size].get('dataSent', 'N/A'))
        commRounds = format_metric(MOTION[key][size].get('commRounds', 'N/A'))
        
        MOTIONrowsComvertion[-1].extend([
            time,
            dataSent,
            commRounds
        ])        

# print(generateLatexRows(MOTIONrowsComvertion))
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')
print('-----------------------------------------------------')



MP_SPDZrowsConvertion = []

for key in MP_SPDZ.keys():
    if key  in TOTAL_AVAIL_KEYS:
        continue
    for size in TOTAL_AVAIL_SIZES:
        if size in MP_SPDZ[key]:
            MP_SPDZrowsConvertion.append([KEY_MAPPING[key],size])
            time = format_metric(MP_SPDZ[key][size].get('time', 'N/A'))
            dataSent = format_metric(MP_SPDZ[key][size].get('dataSent', 'N/A'))
            commRounds = format_metric(MP_SPDZ[key][size].get('commRounds', 'N/A'))
        
            MP_SPDZrowsConvertion[-1].extend([
                time,
                dataSent,
                commRounds
            ])        

# print(generateLatexRows(MP_SPDZrowsConvertion))