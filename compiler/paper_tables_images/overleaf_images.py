import json
import ast
import matplotlib.pyplot as plt
import re
import numpy as np
import copy
from pathlib import Path

with open('../FULLResultsWithStdDev.json', 'r') as f:
    contents = json.loads(f.read())

with open('../mixerOutputs.json', 'r') as f:
    contents2 = json.loads(f.read())

keyList1 = [
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

keyList2 = [

        {"key":'convex_hull',"label":'Convex Hull (N)', 'dims': [],'motionYlim':80, 'spdzYlim': 12},
        {"key":'db_variance',"label":'Database Variance (N)', 'dims': [],'motionYlim':80, 'spdzYlim': 0.5}, 
        {"key":'minimal_points',"label":'Minimal Points (N)', 'dims': [],'motionYlim':70, 'spdzYlim':12},
               
]

def extract_dimensions(keyList, backend):
    """
    Extracts dimensions from the contents of the JSON file and appends them to the keyList.
    This function is called to populate the dimensions for each benchmark in keyList.
    """
   
    for i in range(len(keyList)):
            elem = keyList[i]
            keys = list(contents[backend][elem['key']].keys())
            for key in keys:
                keyList[i]['dims'].append({"key":key, "label": format_entry(key)})
            keyList[i]['dims'] = sorted(keyList[i]['dims'], key=lambda x: x['label'])

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

def extract_info_motion(keyList):
    for i in range(len(keyList)):
        elem = keyList[i]
        lines = [{
            "label":  "N/A",
            "ArithmeticGMW": "N/A",
            "ArithmeticGMWSTD": "N/A",
            "ArighmeticGMWPRED": "N/A",
            "BooleanGmw": "N/A",
            "BooleanGmwSTD": "N/A",
            "BooleanGmwPRED": "N/A",
            "Bmr": "N/A",
            "BmrSTD": "N/A",
            "BmrPRED": "N/A",
            "mixed": "N/A",
            "mixedSTD": "N/A",
            "mixedPRED": "N/A",
            "mixType": "N/A"
        }]
        for dim in elem['dims']:
            lines[-1]["label"] = (",".join([str(x) for x in dim['label']]))

            ArithmeticGMW = not (type(contents['MOTION'][elem['key']][dim['key']]['ArithmeticGmw']) == str )
            lines[-1]["ArithmeticGMW"] = f"{contents['MOTION'][elem['key']][dim['key']]['ArithmeticGmw']['time']:.2f}" if ArithmeticGMW else "N/A"
            lines[-1]['ArithmeticGMWSTD'] = (f"{contents['MOTION'][elem['key']][dim['key']]['ArithmeticGmw']['StdDevTime']:.2f}") if ArithmeticGMW else "N/A"
            lines[-1]['ArighmeticGMWPRED'] = (f"{contents2['MOTION'][elem['key']][dim['key']]['ArithmeticGmw']['predTime']:.2f}") if ArithmeticGMW else "N/A"
            lines[-1]['BooleanGmw'] = (f"{contents['MOTION'][elem['key']][dim['key']]['BooleanGmw']['time']:.2f}")
            lines[-1]['BooleanGmwSTD'] = (f"{contents['MOTION'][elem['key']][dim['key']]['BooleanGmw']['StdDevTime']:.2f}")
            lines[-1]['BooleanGmwPRED'] = (f"{contents2['MOTION'][elem['key']][dim['key']]['BooleanGmw']['predTime']:.2f}")
            lines[-1]["Bmr"] = (f"{contents['MOTION'][elem['key']][dim['key']]['Bmr']['time']:.2f}")
            lines[-1]["BmrSTD"] = (f"{contents['MOTION'][elem['key']][dim['key']]['Bmr']['StdDevTime']:.2f}")
            lines[-1]["BmrPRED"] = (f"{contents2['MOTION'][elem['key']][dim['key']]['Bmr']['predTime']:.2f}")
            lines[-1]["mixed"] = f"{contents['MOTION'][elem['key']][dim['key']]['mixed']['time']:.2f}"
            lines[-1]["mixedSTD"] = f"{contents['MOTION'][elem['key']][dim['key']]['mixed']['StdDevTime']:.2f}"
            lines[-1]["mixedPRED"] = f"{contents2['MOTION'][elem['key']][dim['key']]['mixed']['predTime']:.2f}"
            lines[-1]["mixType"] = ",".join(ast.literal_eval(contents['MOTION'][elem['key']][dim['key']]['mixed']['mixType']))
            lines.append({
                "label":  "N/A",
                "ArithmeticGMW": "N/A",
                "ArithmeticGMWSTD": "N/A",
                "ArighmeticGMWPRED": "N/A",
                "BooleanGmw": "N/A",
                "BooleanGmwSTD": "N/A",
                "BooleanGmwPRED": "N/A",
                "Bmr": "N/A",
                "BmrSTD": "N/A",
                "BmrPRED": "N/A",
                "mixed": "N/A",
                "mixedSTD": "N/A",
                "mixedPRED": "N/A",
                "mixType": "N/A"
            })
        lines.pop()
        keyList[i]['lines'] = lines


def extract_info_spdz(keyList):
    for i in range(len(keyList)):
        elem = keyList[i]
        lines = [{
            "label":  "N/A",
            "A": "N/A",
            "A_STD": "N/A",
            'A_pred': "N/A",
            "B": "N/A",
            "B_STD": "N/A",
            'B_pred': "N/A",
            "X": "N/A",
            "X_STD": "N/A",
            'X_pred': "N/A",
            "Y": "N/A",
            "Y_STD": "N/A",
            'Y_pred': "N/A",
            "mixed": "N/A",
            "mixedSTD": "N/A",
            'mixed_pred': "N/A",
            "mixType": "N/A"
        }]
        for dim in elem['dims']:
            lines[-1]["label"] = (",".join([str(x) for x in dim['label']]))

            lines[-1]["A"] = f"{contents['MP-SPDZ'][elem['key']][dim['key']]['A']['time']:.2f}"
            lines[-1]["A_STD"] = f"{contents['MP-SPDZ'][elem['key']][dim['key']]['A']['StdDevTime']:.2f}"     
            lines[-1]['A_pred'] = (f"{contents2['MP-SPDZ'][elem['key']][dim['key']]['A']['predTime']:.2f}")
            B = not (type(contents['MP-SPDZ'][elem['key']][dim['key']]['B']) == str )
            lines[-1]['B'] = (f"{contents['MP-SPDZ'][elem['key']][dim['key']]['B']['time']:.2f}") if B else "N/A"
            lines[-1]['B_STD'] = (f"{contents['MP-SPDZ'][elem['key']][dim['key']]['B']['StdDevTime']:.2f}") if B else "N/A"
            lines[-1]['B_pred'] = (f"{contents2['MP-SPDZ'][elem['key']][dim['key']]['B']['predTime']:.2f}") if B else "N/A"
            lines[-1]["X"] = (f"{contents['MP-SPDZ'][elem['key']][dim['key']]['X']['time']:.2f}")
            lines[-1]["X_STD"] = (f"{contents['MP-SPDZ'][elem['key']][dim['key']]['X']['StdDevTime']:.2f}")

            lines[-1]["Y"] = (f"{contents['MP-SPDZ'][elem['key']][dim['key']]['Y']['time']:.2f}")
            lines[-1]["Y_STD"] = (f"{contents['MP-SPDZ'][elem['key']][dim['key']]['Y']['StdDevTime']:.2f}")
            lines[-1]['X_pred'] = (f"{contents2['MP-SPDZ'][elem['key']][dim['key']]['X']['predTime']:.2f}")
            lines[-1]["mixed"] = f"{contents['MP-SPDZ'][elem['key']][dim['key']]['mixed']['time']:.2f}"
            lines[-1]["mixedSTD"] = f"{contents['MP-SPDZ'][elem['key']][dim['key']]['mixed']['StdDevTime']:.2f}"
            lines[-1]['mixed_pred'] = f"{contents2['MP-SPDZ'][elem['key']][dim['key']]['mixed']['predTime']:.2f}"
            lines[-1]["mixType"] = ",".join(ast.literal_eval(contents['MP-SPDZ'][elem['key']][dim['key']]['mixed']['mixType']))
            lines.append({
                "label":  "N/A",
                "A": "N/A",
                "A_STD": "N/A",
                'A_pred': "N/A",
                "B": "N/A",
                "B_STD": "N/A",
                'B_pred': "N/A",
                "X": "N/A",
                "X_STD": "N/A",
                'X_pred': "N/A",
                "Y": "N/A",
                "Y_STD": "N/A",
                'Y_pred': "N/A",
                "mixed": "N/A",
                "mixedSTD": "N/A",
                'mixed_pred': "N/A",
                "mixType": "N/A"
            })
        
        lines.pop()
        keyList[i]['lines'] = lines

        # Pick last dim for each benchmark
    

def generate_chart_1_motion():
    
    keyList = copy.deepcopy(keyList1)
    extract_dimensions(keyList, 'MOTION')
    extract_info_motion(keyList)

    # Pick last dim for each benchmark
    labels = []
    arith_gmw = []
    arith_gmw_std = []
    bool_gmw = []
    bool_gmw_std = []
    bmr = []
    bmr_std = []
    mixed = []
    mixed_std = []
    mixed_type = []

    for entry in keyList:
        labels.append(re.sub(r"\s*\(.*\)", "", entry['label']))
        last = entry['lines'][-1]
        labels[-1] += f" ({last['label']})"
        def val_or_nan(x):
            try:
                return float(x)
            except:
                return np.nan
        arith_gmw.append(val_or_nan(last['ArithmeticGMW']))
        arith_gmw_std.append(val_or_nan(last['ArithmeticGMWSTD']))
        bool_gmw.append(val_or_nan(last['BooleanGmw']))
        bool_gmw_std.append(val_or_nan(last['BooleanGmwSTD']))
        bmr.append(val_or_nan(last['Bmr']))
        bmr_std.append(val_or_nan(last['BmrSTD']))
        mixed.append(val_or_nan(last['mixed']))
        mixed_std.append(val_or_nan(last['mixedSTD']))
        mixed_type.append(last['mixType'])

    labels = np.array(labels)
    arith_gmw = np.array(arith_gmw)
    arith_gmw_std = np.array(arith_gmw_std)
    bool_gmw = np.array(bool_gmw)
    bool_gmw_std = np.array(bool_gmw_std)
    bmr = np.array(bmr)
    bmr_std = np.array(bmr_std)
    mixed = np.array(mixed)
    mixed_std = np.array(mixed_std)

    # Calculate improvement vs best of Arithmetic, Boolean, BMR
    improvement = []
    for a, g, b, m in zip(arith_gmw, bool_gmw, bmr, mixed):
        if np.isnan(m) or m == 0:
            improvement.append(np.nan)
        else:
            best = np.nanmin([a, g, b])
            improvement.append(best / m  if best > 0 else np.nan)
    improvement = np.array(improvement)



    # Bars
    plt.figure(figsize=(16, 6))
    x = np.arange(len(labels))
    bar_w = 0.2
    offsets = (-1.5*bar_w, -0.5*bar_w, 0.5*bar_w, 1.5*bar_w)

    ax = plt.gca()
    ax.bar(x + offsets[0], arith_gmw, width=bar_w, label="Arithmetic GMW (A)", color='#e59e00',capsize=6)
    ax.set_ylim(0, 400)  # symmetric around 0

    # Add yellow X at 0 for NaN values
    for xi, yi in zip(x + offsets[0], arith_gmw):
        if np.isnan(yi):
            ax.plot(xi, 8, marker="x", color="#e59e00", markersize=10, mew=2)
        else:
            ax.plot(xi, 10, marker="o", color="#e59e00", markersize=10, mew=2)
 

    ax.bar(x + offsets[1], bool_gmw,  width=bar_w, label="Boolean GMW (B)",  color='#9400d4',capsize=6)

     # Add yellow X at 0 for NaN values
    for xi, yi in zip(x + offsets[1], bool_gmw):
        if np.isnan(yi):
            ax.plot(xi, 8, marker="x", color="#9400d4", markersize=10, mew=2)
        else:
            ax.plot(xi, 10, marker="o", color="#9400d4", markersize=10, mew=2)
    ax.bar(x + offsets[2], bmr,       width=bar_w, label="BMR (Y)",color='#58b5e8',capsize=6)

     # Add yellow X at 0 for NaN values
    for xi, yi in zip(x + offsets[2], bmr):
        if np.isnan(yi):
            ax.plot(xi, 8, marker="x", color="#58b5e8", markersize=10, mew=2)
        else:
            ax.plot(xi, 10, marker="o", color="#58b5e8", markersize=10, mew=2)
    
    ax.bar(x + offsets[3], mixed,     width=bar_w, label="Mixed",        color='#019e73',capsize=6)

   

    for xi, yi, label in zip(x + offsets[3], mixed, mixed_type):
        if not np.isnan(yi):
            ax.text(
                xi, yi, label,
                ha="center", va="bottom", fontsize=10, fontweight="bold", color="black"
            )

    ax.set_ylabel("Time (sec)")
    ax.set_xticks(x, labels, rotation=35, ha="right")
    ax.set_title("MOTION Circuit Evaluation Time.")

    # # Legends
    bars_legend = ax.legend(loc="upper left", ncol=1, frameon=False,fontsize=14)
    # lines_legend = ax2.legend(loc="upper center", frameon=False)
    ax.add_artist(bars_legend)

    plt.tight_layout()
    out_path = Path("./motion_circuit_evaluation_time.pdf")
    plt.savefig(out_path, dpi=300)
    out_path.as_posix()


def generate_chart_1_spdz():
    
    keyList = copy.deepcopy(keyList1)      
    extract_dimensions(keyList, 'MP-SPDZ')
    extract_info_spdz(keyList)
  
    # Pick last dim for each benchmark
    labels = []
    A = []
    A_STD = []
    B = []
    B_STD = []
    X = []
    X_STD = []
    Y = []
    Y_STD = []
    mixed = []
    mixed_std = []
    mixed_type = []

    for entry in keyList:
        labels.append(re.sub(r"\s*\(.*\)", "", entry['label']))
        last = entry['lines'][-1]
        labels[-1] += f" ({last['label']})"
        def val_or_nan(x):
            try:
                return float(x)
            except:
                return np.nan
        A.append(val_or_nan(last['A']))
        A_STD.append(val_or_nan(last['A_STD']))
        B.append(val_or_nan(last['B']))
        B_STD.append(val_or_nan(last['B_STD']))
        X.append(val_or_nan(last['X']))
        X_STD.append(val_or_nan(last['X_STD']))
        Y.append(val_or_nan(last['Y']))
        Y_STD.append(val_or_nan(last['Y_STD']))
        mixed.append(val_or_nan(last['mixed']))
        mixed_std.append(val_or_nan(last['mixedSTD']))
        mixed_type.append(last['mixType'])

    labels = np.array(labels)
    A = np.array(A)
    A_STD = np.array(A_STD)
    B = np.array(B)
    B_STD = np.array(B_STD)
    X = np.array(X)
    X_STD = np.array(X_STD)
    Y = np.array(Y)
    Y_STD = np.array(Y_STD)
    mixed = np.array(mixed)
    mixed_std = np.array(mixed_std)

    # Calculate improvement vs best of Arithmetic, Boolean, BMR
    improvement = []
    for a, b, x, y, m in zip(A, B, X, Y, mixed):
        if np.isnan(m) or m == 0:
            improvement.append(np.nan)
        else:
            best = np.nanmin([a, b, x , y])
            improvement.append(( best / m ) if best > 0 else np.nan)
    improvement = np.array(improvement)



    # Bars
    plt.figure(figsize=(16, 6))
    x = np.arange(len(labels))
    bar_w = 0.2
    # offsets = (-1.5*bar_w, -0.5*bar_w, 0.5*bar_w, 1.5*bar_w, 2.5*bar_w)
    offsets = (-1.5*bar_w, -0.5*bar_w, 0.5*bar_w, 1.5*bar_w)
    ax = plt.gca()
    # ax.bar(x + offsets[0], A, width=bar_w, label="A", color='#e59e00')
    ax.bar(x + offsets[0], B,  width=bar_w, label="B",  color='#9400d4',capsize=6)

       # Add yellow X at 0 for NaN values
    for xi, yi in zip(x + offsets[0], B):
        if np.isnan(yi):
            ax.plot(xi, 0.1, marker="x", color="#9400d4", markersize=10, mew=2)
        else:
            ax.plot(xi,0.1, marker="o", color="#9400d4", markersize=10, mew=2)
 
    ax.bar(x + offsets[1], X,       width=bar_w, label="X",          color='#58b5e8',capsize=6 )
    i = -1
    for xi, yi in zip(x + offsets[1], X):
        i+=1
        if np.isnan(yi):
            ax.plot(xi, 0.1, marker="x", color="#58b5e8", markersize=10, mew=2)
        else:
            if i == 7 or i == 4:
                continue
            ax.plot(xi, 0.1, marker="o", color="#58b5e8", markersize=10, mew=2)
    
    ax.bar(x + offsets[2], Y,       width=bar_w, label="Y",          color='#FFb5e8',capsize=6)
    i = -1
    for xi, yi in zip(x + offsets[2], Y):
        i+=1
        if np.isnan(yi):
            ax.plot(xi, 0.1, marker="x", color="#FFb5e8", markersize=10, mew=2)
        else:
            if i == 7 or i == 4:
                continue
            ax.plot(xi, 0.1, marker="o", color="#FFb5e8", markersize=10, mew=2)
    ax.bar(x + offsets[3], mixed,     width=bar_w, label="Mixed",        color='#019e73',capsize=6)

    for xi, yi, label in zip(x + offsets[3], mixed, mixed_type):
        if not np.isnan(yi):
            ax.text(
                xi, yi, label,
                ha="center", va="bottom", fontsize=10, fontweight="bold", color="black"
            )
    

    ax.set_ylabel("Time (sec)")
    ax.set_xticks(x, labels, rotation=35, ha="right")
    ax.set_title("MP-SPDZ Circuit Evaluation Time.")
    # ax.set_yscale("log")
    ax.set_ylim(0,5)  # symmetric around 0
    
    # Legends
    bars_legend = ax.legend(loc="upper left", ncol=1, frameon=False,fontsize=14)
    ax.add_artist(bars_legend)

    plt.tight_layout()
    out_path = Path("./spdz_circuit_evaluation_time.pdf")
    plt.savefig(out_path, dpi=300)
    out_path.as_posix()


def generate_chart_2_motion_specific():
   
    keyList = copy.deepcopy(keyList2)    
    extract_dimensions(keyList, 'MOTION')
    extract_info_motion(keyList)

    for entry in keyList:
        
        labels = []
        arith_gmw = []
        arith_gmw_std = []
        bool_gmw = []
        bool_gmw_std = []
        bmr = []
        bmr_std = []
        mixed = []
        mixed_std = []
        mixed_type = []
        print(f"Processing key: {entry['key']}")
        for line in entry['lines']:
            labels.append(re.sub(r"\s*\(.*\)", "", entry['label']))
            last = line
            labels[-1] += f" ({last['label']})"
            def val_or_nan(x):
                try:
                    return float(x)
                except:
                    return np.nan
            arith_gmw.append(val_or_nan(last['ArithmeticGMW']))
            arith_gmw_std.append(val_or_nan(last['ArithmeticGMWSTD']))
            bool_gmw.append(val_or_nan(last['BooleanGmw']))
            bool_gmw_std.append(val_or_nan(last['BooleanGmwSTD']))
            bmr.append(val_or_nan(last['Bmr']))
            bmr_std.append(val_or_nan(last['BmrSTD']))
            mixed.append(val_or_nan(last['mixed']))
            mixed_std.append(val_or_nan(last['mixedSTD']))
            mixed_type.append(last['mixType'])
            # Pick last dim for each benchmark
       

        labels = np.array(labels)
        arith_gmw = np.array(arith_gmw)
        arith_gmw_std = np.array(arith_gmw_std)
        bool_gmw = np.array(bool_gmw)
        bool_gmw_std = np.array(bool_gmw_std)
        bmr = np.array(bmr)
        bmr_std = np.array(bmr_std)
        mixed = np.array(mixed)
        mixed_std = np.array(mixed_std)


        # Calculate improvement vs best of Arithmetic, Boolean, BMR
        improvement = []
        for a, g, b, m in zip(arith_gmw, bool_gmw, bmr, mixed):
            if np.isnan(m) or m == 0:
                improvement.append(np.nan)
            else:
                best = np.nanmin([a, g, b])
                improvement.append(best / m  if best > 0 else np.nan)
        improvement = np.array(improvement)



        # Bars
        plt.figure(figsize=(16, 6))
        x = np.arange(len(labels))
        bar_w = 0.2
        offsets = (-1.5*bar_w, -0.5*bar_w, 0.5*bar_w, 1.5*bar_w)

        ax = plt.gca()
        ax.bar(x + offsets[0], arith_gmw, width=bar_w, label="Arithmetic GMW (A)", color='#e59e00', yerr=arith_gmw_std, capsize=6)

        ax = plt.gca()
        ax.set_ylim(0, entry["motionYlim"]) 

        # Add yellow X at 0 for NaN values
        for xi, yi in zip(x + offsets[0], arith_gmw):
            if np.isnan(yi):
                ax.plot(xi+0.05, 2, marker="x", color="#e59e00", markersize=10, mew=2)
            else:
                ax.plot(xi + 0.05, 2, marker="o", color="#e59e00", markersize=10, mew=2)
                # ax.text(
                #     xi, yi, f"{yi:.2f}",  # format to 2 decimals, adjust as you like
                #     ha="center", va="bottom", fontsize=8, color="black", rotation=90
                # )

        ax.bar(x + offsets[1], bool_gmw,  width=bar_w, label="Boolean GMW (B)",  color='#9400d4', capsize=6)
        ax.bar(x + offsets[2], bmr,       width=bar_w, label="BMR (Y)",          color='#58b5e8', capsize=6)
        ax.bar(x + offsets[3], mixed,     width=bar_w, label="Mixed",        color='#019e73', capsize=6)

        for xi, yi, label in zip(x + offsets[3], mixed, mixed_type):
            if not np.isnan(yi):
                ax.text(
                    xi, yi, label,
                    ha="center", va="bottom", fontsize=10, fontweight="bold", color="black"
                )


        ax.set_ylabel("Time (sec)")
        ax.set_xticks(x, labels, rotation=35, ha="right")
        ax.set_title(f"MOTION {re.sub(r"\s*\(.*\)", "", entry['label'])} Circuit Evaluation Time.")

       
        # Legends
        bars_legend = ax.legend(loc="upper left", ncol=2, frameon=False,fontsize=14)
        ax.add_artist(bars_legend)

        plt.tight_layout()
        out_path = Path(f"./motion_specific_{re.sub(r"\s*\(.*\)", "", entry['label'])}.pdf")
        plt.savefig(out_path, dpi=300)
        out_path.as_posix()


def generate_chart_2_spdz_specific():
    keyList = copy.deepcopy(keyList2)
    extract_dimensions(keyList, 'MP-SPDZ')
    extract_info_spdz(keyList)

    for entry in keyList:
        
        labels = []
        A = []
        A_STD = []
        B = []
        B_STD = []
        X = []
        X_STD = []
        Y = []
        Y_STD = []
        mixed = []
        mixed_type = []
        print(f"Processing key: {entry['key']}")
        for line in entry['lines']:
            labels.append(re.sub(r"\s*\(.*\)", "", entry['label']))
            last = line
            labels[-1] += f" ({last['label']})"
            def val_or_nan(x):
                try:
                    return float(x)
                except:
                    return np.nan
            A.append(val_or_nan(last['A']))
            A_STD.append(val_or_nan(last['A_STD']))
            B.append(val_or_nan(last['B']))
            B_STD.append(val_or_nan(last['B_STD']))
            X.append(val_or_nan(last['X']))
            X_STD.append(val_or_nan(last['X_STD']))
            Y.append(val_or_nan(last['Y']))
            Y_STD.append(val_or_nan(last['Y_STD']))
            mixed.append(val_or_nan(last['mixed']))
            mixed_std = val_or_nan(last['mixedSTD'])
            mixed_type.append(last['mixType'])
       

        labels = np.array(labels)
        A = np.array(A)
        A_STD = np.array(A_STD)
        B = np.array(B)
        B_STD = np.array(B_STD)
        X = np.array(X)
        X_STD = np.array(X_STD)
        Y = np.array(Y)
        Y_STD = np.array(Y_STD)
        mixed = np.array(mixed)
        mixed_std = np.array(mixed_std)

        # Calculate improvement vs best of Arithmetic, Boolean, BMR
        improvement = []
        for a, b, x, y, m in zip(A, B, X,Y, mixed):
            if np.isnan(m) or m == 0:
                improvement.append(np.nan)
            else:
                best = np.nanmin([a, b, x , y])
                improvement.append((best / m ) if best > 0 else np.nan)
        improvement = np.array(improvement)



        # Bars
        plt.figure(figsize=(16, 6))
        x = np.arange(len(labels))
        bar_w = 0.2
        offsets = (-1.5*bar_w, -0.5*bar_w, 0.5*bar_w, 1.5*bar_w)

        ax = plt.gca()
        ax.set_ylim(0, entry["spdzYlim"])
        ax.bar(x + offsets[0], B,  width=bar_w, label="B",  color='#9400d4', capsize=6)
        ax.bar(x + offsets[1], X,       width=bar_w, label="X",          color='#58b5e8', capsize=6)
        ax.bar(x + offsets[2], Y,       width=bar_w, label="Y",          color='#FFb5e8',  capsize=6)
        ax.bar(x + offsets[3], mixed,     width=bar_w, label="Mixed",        color='#019e73',  capsize=6)

        for xi, yi, label in zip(x + offsets[3], mixed, mixed_type):
            if not np.isnan(yi):
                ax.text(
                    xi, yi, label,
                    ha="center", va="bottom", fontsize=10, fontweight="bold", color="black"
                )
        ax.set_ylabel("Time (sec)")
        ax.set_xticks(x, labels, rotation=35, ha="right")
        ax.set_title(f"MP-SPDZ {re.sub(r"\s*\(.*\)", "", entry['label'])} Circuit Evaluation Time.")

        # Legends
        bars_legend = ax.legend(loc="upper left", ncol=2, frameon=False,fontsize=14)
        ax.add_artist(bars_legend)

        plt.tight_layout()
        # print(key)
        out_path = Path(f"./spdz_specific_{re.sub(r"\s*\(.*\)", "", entry['label'])}.pdf")
        plt.savefig(out_path, dpi=300)
        out_path.as_posix()


def generate_chart_3_act_vs_pred_motion():
    
    keyList = copy.deepcopy(keyList1)  
    extract_dimensions(keyList, 'MOTION')
    extract_info_motion(keyList)
 
    # Pick last dim for each benchmark
    labels = []
    arith_gmw = []
    arith_gmw_std = []
    arith_gmw_pred = []
    bool_gmw = []
    bool_gmw_std = []
    bool_gmw_pred = []
    bmr = []
    bmr_std = []
    bmr_pred = []
    mixed = []
    mixed_std = []
    mixed_pred = []

    for entry in keyList:
        labels.append(re.sub(r"\s*\(.*\)", "", entry['label']))
        last = entry['lines'][-1]
        labels[-1] += f" ({last['label']})"
        def val_or_nan(x):
            try:
                return float(x)
            except:
                return np.nan
        arith_gmw.append(val_or_nan(last['ArithmeticGMW']))
        arith_gmw_std.append(val_or_nan(last['ArithmeticGMWSTD']))
        arith_gmw_pred.append(val_or_nan(last['ArighmeticGMWPRED']))
        bool_gmw.append(val_or_nan(last['BooleanGmw']))
        bool_gmw_std.append(val_or_nan(last['BooleanGmwSTD']))
        bool_gmw_pred.append(val_or_nan(last['BooleanGmwPRED']))
        bmr.append(val_or_nan(last['Bmr']))
        bmr_std.append(val_or_nan(last['BmrSTD']))
        bmr_pred.append(val_or_nan(last['BmrPRED']))
        mixed.append(val_or_nan(last['mixed']))
        mixed_std.append(val_or_nan(last['mixedSTD']))
        mixed_pred.append(val_or_nan(last['mixedPRED']))

    labels = np.array(labels)
    arith_gmw = np.array(arith_gmw)
    arith_gmw_std = np.array(arith_gmw_std)
    arith_gmw_pred = np.array(arith_gmw_pred)
    bool_gmw = np.array(bool_gmw)
    bool_gmw_std = np.array(bool_gmw_std)
    bool_gmw_pred = np.array(bool_gmw_pred)
    bmr = np.array(bmr)
    bmr_std = np.array(bmr_std)
    bmr_pred = np.array(bmr_pred)
    mixed = np.array(mixed)
    mixed_std = np.array(mixed_std)
    mixed_pred = np.array(mixed_pred)

    # Calculate improvement vs best of Arithmetic, Boolean, BMR
    improvement = []
    for a, g, b, m in zip(arith_gmw, bool_gmw, bmr, mixed):
        if np.isnan(m) or m == 0:
            improvement.append(np.nan)
        else:
            best = np.nanmin([a, g, b])
            improvement.append(best / m  if best > 0 else np.nan)
    improvement = np.array(improvement)


    plt.figure(figsize=(16, 6))
    x = np.arange(len(labels))
    bar_w = 0.2
    offsets = (-0.5*bar_w, 0.5*bar_w)
    ax = plt.gca()
    
    ax.bar(x + offsets[0], mixed, width=bar_w,  label="Mixed actual",color='#019e73')
    ax.bar(x + offsets[1], mixed_pred, width=bar_w, label="Mixed prediction", color='#e59e00')

    ax.set_ylabel("Time (sec)")
    ax.set_xticks(x, labels, rotation=35, ha="right")
    ax.set_title("MOTION Circuit Evaluation Prediction vs Actual runtime (Seconds).")

    ax.legend(loc="upper left", frameon=False)  # Add legend her,fontsize=12e
    # Second axis for percentage error
   
    # Legends
    bars_legend = ax.legend(loc="upper left", frameon=False,fontsize=14)
    ax.add_artist(bars_legend)
    plt.tight_layout()
    out_path = Path("./motion_pred_vs_actual.pdf")
    plt.savefig(out_path, dpi=300)
    out_path.as_posix()

def generate_chart_3_act_vs_pred_spdz():
    
    keyList = copy.deepcopy(keyList1)    
    extract_dimensions(keyList, 'MP-SPDZ')
    extract_info_spdz(keyList)
    
    labels = []
    A = []
    A_STD = []
    A_pred = []
    B = []
    B_STD = []
    B_pred = []
    X = []
    X_STD = []
    X_pred = []
    Y = []
    Y_STD = []
    Y_pred = []
    mixed = []
    mixed_std = []
    mixed_pred = []

    for entry in keyList:
        labels.append(re.sub(r"\s*\(.*\)", "", entry['label']))
        last = entry['lines'][-1]
        labels[-1] += f" ({last['label']})"
        def val_or_nan(x):
            try:
                return float(x)
            except:
                return np.nan
        A.append(val_or_nan(last['A']))
        A_STD.append(val_or_nan(last['A_STD']))
        A_pred.append(val_or_nan(last['A_pred']))
        B.append(val_or_nan(last['B']))
        B_STD.append(val_or_nan(last['B_STD']))
        B_pred.append(val_or_nan(last['B_pred']))
        X.append(val_or_nan(last['X']))
        X_STD.append(val_or_nan(last['X_STD']))
        X_pred.append(val_or_nan(last['X_pred']))
        Y.append(val_or_nan(last['Y']))
        Y_STD.append(val_or_nan(last['Y_STD']))
        Y_pred.append(val_or_nan(last['Y_pred']))
        mixed.append(val_or_nan(last['mixed']))
        mixed_std.append(val_or_nan(last['mixedSTD']))
        mixed_pred.append(val_or_nan(last['mixed_pred']))

    labels = np.array(labels)
    A = np.array(A)
    A_STD = np.array(A_STD)
    A_pred = np.array(A_pred)
    B = np.array(B)
    B_STD = np.array(B_STD)
    B_pred = np.array(B_pred)
    X = np.array(X)
    X_STD = np.array(X_STD)
    X_pred = np.array(X_pred)
    Y = np.array(Y)
    Y_STD = np.array(Y_STD)
    Y_pred = np.array(Y_pred)
    mixed = np.array(mixed)
    mixed_std = np.array(mixed_std)
    mixed_pred = np.array(mixed_pred)

    # Calculate improvement vs best of Arithmetic, Boolean, BMR
    improvement = []
    for a, b, x, y, m in zip(A, B, X,Y, mixed):
        if np.isnan(m) or m == 0:
            improvement.append(np.nan)
        else:
            best = np.nanmin([a, b, x , y])
            improvement.append((best / m ) if best > 0 else np.nan)
    improvement = np.array(improvement)



    plt.figure(figsize=(16, 6))
    x = np.arange(len(labels))
    bar_w = 0.2
    offsets = ( -0.5*bar_w, 0.5*bar_w)
   
    ax = plt.gca()
    ax.bar(x + offsets[0], mixed,width=bar_w,  label="Mixed actual",color='#019e73')
    ax.bar(x + offsets[1], mixed_pred,width=bar_w, label="Mixed prediction", color='#e59e00')

    ax.set_ylabel("Time (sec)")
    ax.set_xticks(x, labels, rotation=35, ha="right")
    ax.set_title("MP-SPDZ Circuit Evaluation Prediction vs Actual runtime (Seconds).")

    # Legends
    bars_legend = ax.legend(loc="upper left", frameon=False,fontsize=14)
    ax.add_artist(bars_legend)


    plt.tight_layout()
    out_path = Path("./spdz_pred_vs_actual.pdf")
    plt.savefig(out_path, dpi=300)
    out_path.as_posix()


# generate_chart_1_motion()
generate_chart_1_spdz()
# generate_chart_2_motion_specific()
# generate_chart_2_spdz_specific()
# generate_chart_3_act_vs_pred_motion()
# generate_chart_3_act_vs_pred_spdz()