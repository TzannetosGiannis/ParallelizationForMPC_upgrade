import sys, os
from fixFreeOps import fixFreeOps
from showMissingOps import showMissingOps
from fragmentCostTable import fragmentCostTable
from fixMotionCosts import fixMotionOps


if len(sys.argv) > 1:
    fileName = sys.argv[1]
    if not os.path.exists(fileName):
        raise Exception("Unable to find provided file")
else:
    files = sorted([f for f in os.listdir(".") if os.path.isfile(os.path.join(".", f))])
    for f in files:
        if f.__contains__("cost_table.txt"):
            fileName = f

print(f'Processing cost table: {fileName}\n')
fixFreeOps(fileName)
fixMotionOps(fileName)
showMissingOps(fileName)
fragmentCostTable(fileName)
