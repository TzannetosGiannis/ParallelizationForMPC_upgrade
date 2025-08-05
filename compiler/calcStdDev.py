import json
import numpy as np

with open("DETAILED_FULLResults.json", "r") as file:
    deviations = json.load(file)
with open("FULLResults.json", "r") as file:
    results = json.load(file)
print("STD DEV AVAILABLE BUT RESULTS FILE MISSING KEYS:")
for backend in deviations.keys():
    for benchmark in deviations[backend].keys():
        for dims in deviations[backend][benchmark].keys():
            if not dims in results[backend][benchmark].keys():
                print("    ", backend, benchmark, dims)
                continue
            for p in deviations[backend][benchmark][dims].keys():
                std = np.std(deviations[backend][benchmark][dims][p]["time"])
                results[backend][benchmark][dims][p]["StdDevTime"] = std

print("\nMISSING STD DEV FOR:")
for backend in results.keys():
    for benchmark in results[backend].keys():
        for dims in results[backend][benchmark].keys():
            for p in results[backend][benchmark][dims].keys():
                if (not "ERROR" in results[backend][benchmark][dims][p]) and (not "StdDevTime" in results[backend][benchmark][dims][p].keys()):
                    print("    ", backend, benchmark, dims, p)

print('\nWriting FULLResultsWithStdDev.json')
with open('FULLResultsWithStdDev.json', 'w') as f:
    f.write(json.dumps(results, indent=4, sort_keys=True))
# print(json.dumps(results, indent=4))
