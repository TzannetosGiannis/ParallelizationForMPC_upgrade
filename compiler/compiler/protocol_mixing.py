# TODO: FOR MULTI-PROTOCOL CONVERSION CHAINS, RECOMPUTE CHEAPEST COST (CURRENT MODEL IS GREEDY)

# copy of vectorize.py imports
from collections import defaultdict
import functools

from .ast_shared import TypeEnv, Var, VectorizedAccess, Subscript, DataType
from .tac_cfg import DropDim, LiftExpr, Assign, BinOp, BinOpKind
from . import loop_linear_code as llc
from .dep_graph import DepGraph, DepNode, EdgeKind, DepParameter
from . import util
from .util import assert_never
from .type_analysis import collect_idx_vars

import dataclasses as dc
from dataclasses import dataclass
from typing import Iterable, Union, Optional, cast, TypeVar, Any

import z3  # type: ignore
import re
# copy of loop_linear_code.py imports
from dataclasses import dataclass
from textwrap import indent

# need importlib to get around a circular dependency in compiler.backends
import importlib
Backend = importlib.import_module("compiler.backends", "Backend")

from .ssa import (
    Atom,
    Operand,
    # Var,
    Phi,
    Assign,
    LoopBound,
    AssignLHS,
    AssignRHS,
    Constant,
    Subscript,
    SubscriptIndex,
    SubscriptIndexBinOp,
    SubscriptIndexUnaryOp,
    BinOp,
    UnaryOp,
    List,
    Tuple,
    Mux,
    Update,
    VectorizedUpdate,
    assign_rhs_accessed_vars,
)
from .loop_linear_code import (
    Function,
    Statement,
    Assign,
    TypeEnv,
    Phi,
    For,
    Return,
    VectorizedAccess,
    Constant,
    Mux,
    VectorizedUpdate,
    Subscript,
    Update
)
from .tac_cfg import LiftExpr, DropDim, assign_rhs_accessed_vars
from .ast_shared import (
    VarType,
    BinOpKind,
    Parameter,
    UnaryOpKind,
    TypeEnv,
    VectorizedAccess,
)
from .util import assert_never

from copy import deepcopy

import json
from os.path import dirname, exists

Protocol = str # Union['A', 'B', 'Y']
protocols: set[Protocol] = set()
protocolsMotion = [{'A', 'B', 'Y'}]
protocolsSPDZ = [{'A', 'B'}, {'X', 'B'}, {'Y', 'B'}]
# protocolsSPDZ = [{'A'}, {'B'}, {'X'}, {'Y'}]
transparent_ops = [LiftExpr, DropDim, VectorizedAccess, Constant] # CHECK IF THIS IS THE FULL LIST
runningSpdz = None

# conversionSymbols = {'A': {'B': 'zic_a2b', 'Y': 'zic_a2y'}, 'B': {'A': 'zic_b2a', 'Y': 'zic_b2y'}, 'Y': {'A': 'zic_y2a', 'B': 'zic_y2b'}}
# TODO CHECK IF THESE ARE ALL ZERO COST. ESPECIALLY CONSTANT and VectorizedAccess
zeroCostOps = {'LiftExpr', 'DropDim', 'Return', 'Phi', 'Constant', 'VectorizedAccess', 'Tuple', 'VectorizedUpdate', 'notUNARY'}
opToCostSymbol = {'+': 'zi_add', 'and': 'zi_and', '==': 'zi_eq', '>=': 'zi_ge', '>': 'zi_gt', '<=': 'zi_le', '<': 'zi_lt',
  '*': 'zi_mul', 'Mux': 'zi_mux', '!=': 'zi_ne', 'or': 'zi_or', '%': 'zi_rem', '<<': 'zi_shl', '-': 'zi_sub', '^': 'zi_xor',
  '>>': 'zi_shr', '-UNARY': 'UNAVAILABLE', '&': 'zi_&', '|': 'zi_|', 'Var': 'UNAVAILABLE', '/': 'zi_div'}
costTable: dict[str, dict[str, dict[str, float]]] = dict()
loopBounds: dict[str, int] = dict()
bounds: dict[Var, dict[str, tuple[int, int]]] = dict()


class Config:
    # The Config class contains the protocol assignment and variable interface for its sequence
    #  assignments is a list[Statement, Protocol, set[Protocol], cost, loop_depth, loopNestCount, list[tuple(Protocol, Protocol)]]
    #                                   ^------^  ^-----------^  ^--^  ^--------^  ^-----------^  ^-----------------------------^
    #                                    |         |              |     |           |              conversions after assignment as (from, to) pairs
    #                                    |         |              |     |           loop nest count (used for print formatting)
    #                                    |         |              |     loop depth (iteration count) of this statement
    #                                    |         |              cost to execute this statement (including conversions)
    #                                    |         conversions after assignment
    #                                    protocol used to execute operation
    assignments: list[Any]
               # mypy does not support homogenous list types. I need this to be a list type, not a tuple type to support item assignment
               # below is the correct type for lists over homogenous types:
               # list[list[Statement, Protocol, set[Protocol], float, float, int, list[tuple[Protocol, Protocol]]]]
    
    inputs: dict[Var, set[Protocol]]        # the input interface required to execute this sequence
    outputs: dict[Var, set[Protocol]]       # the output interface of this program (return value assignments)
    total_cost: float                       # the total cost (including conversions) required to execute this sequence
    protocolByVar: dict[Var, set[Protocol]] # a quick way to access the protocols of each variable
    finalStmts: list[Statement]             # used to print the return statement and the tuple if it exists
    constants: dict[Var, set[Protocol]]     # dictionary that converts constants to the required protocols
    plaintexts: dict[Var, set[Protocol]]    # dictionary that converts plaintext variables into their required protocols (these conversions should be free, but some backends don't support free plaintext->protocol conversions)
    flags: set[str]                        # the set of flags used by this program. MP-SPDZ can use the 'X' and 'Y' flags

    # sets of variables can be locked to the same set of protocols by transparent (zero-cost) operations
    lockedVarsIdx: dict[Var, int]
    lockedVarsSets: list[set[Var]]

    def __init__(self, flag: Optional[str]=None) -> None:
        self.inputs = dict()
        self.outputs = dict()
        self.assignments = []
        self.total_cost = 0.0
        self.lockedVarsIdx = dict()
        self.lockedVarsSets = []
        self.protocolByVar = dict()
        self.finalStmts = []
        self.constants = dict()
        self.plaintexts = dict()
        self.flags = set(flag) if flag else set()

    def __str__(self) -> str:
        inputs = "Input vars:\t{" + ", ".join(str(var) + ": " + (str(conv) if len(conv) else '{}') for var, conv in self.inputs.items()) + "}"
        constants = "Constants:\t{" + ", ".join(str(val) + ": " + (str(conv) if len(conv) else '{}') for val, conv in self.constants.items()) + "}"
        plaintexts = "Plaintext vars:\t{" + ", ".join(str(var) + ": " + (str(conv) if len(conv) else '{}') for var, conv in self.plaintexts.items()) + "}"
        flags = "Flags:\t\t{" + ", ".join(str(flag) for flag in self.flags) + "}"
        stmts = "\n".join("\t"*count + str(stmt) + ": " + str(assign) + " -> " + (str(conv) if len(conv) else '{}') + " for " + "{:.5f}".format(cost) + " * " + str(depth) + " = " + "{:.2f}".format(cost*depth) + (" (" + (", ".join(cd[0] + "->" + cd[1] for cd in convDict) if len(conv) else "") + ")" if len(convDict) else "") for stmt, assign, conv, cost, depth, count, convDict in self.assignments)
        finalLines = "\n".join(str(l) for l in reversed(self.finalStmts))
        outputs = "Output vars:\t{" + ", ".join(str(var) + ": " + (str(conv) if len(conv) else '{}') for var, conv in self.outputs.items()) + "}"
        return "Total cost:\t{:.5f}".format(self.total_cost) + "\n" + inputs + "\n" + constants + "\n" + plaintexts + "\n" + flags + "\n" + stmts + "\n" + finalLines + "\n" + outputs + "\n"


# helper function to sort conversion lists. This is used to make mixer output deterministic
def sortConv(conv: list[tuple[Protocol, Protocol]]) -> list[tuple[Protocol, Protocol]]:
    if len(conv) < 2:
        return conv

    lhsProts = set()
    rhsProts = set()
    for lhs, rhs in conv:
        lhsProts.add(lhs)
        rhsProts.add(rhs)

    headProtocols = lhsProts-rhsProts
    assert len(headProtocols) == 1
    remainingConvs = set(conv)
    toRet = []

    while remainingConvs:
        minConv = None
        for c in remainingConvs:
            if not minConv:
                minConv = c
            else:
                if c[0] in headProtocols and c[0] < minConv[0] or (c[0] == minConv[0] and c[1] < minConv[1]):
                    minConv = c
        assert not minConv is None
        toRet.append(minConv)
        remainingConvs.remove(minConv)
        headProtocols.add(minConv[1])
    return toRet


# Identical to Config, but every set is changed to an ordered set. This is used to make the output deterministic and
#   comparable for changes.
class OrderedConfig:
    assignments: list[Any]
    inputs: dict[Var, list[Protocol]]
    outputs: dict[Var, list[Protocol]]
    total_cost: float
    protocolByVar: dict[Var, list[Protocol]]
    finalStmts: list[Statement]
    constants: dict[Var, list[Protocol]]
    plaintexts: dict[Var, list[Protocol]]
    flags: list[str]
    lockedVarsIdx: dict[Var, int]
    lockedVarsSets: list[set[Var]]

    def __init__(self, copyConfig: Config) -> None:
        self.inputs = dict()
        self.outputs = dict()
        self.assignments = []
        self.total_cost = copyConfig.total_cost
        self.lockedVarsIdx = deepcopy(copyConfig.lockedVarsIdx)
        self.lockedVarsSets = deepcopy(copyConfig.lockedVarsSets)
        self.protocolByVar = dict()
        self.finalStmts = copyConfig.finalStmts
        self.constants = dict()
        self.plaintexts = dict()
        self.flags = sorted(list(copyConfig.flags))

        for v, s in copyConfig.inputs.items():
            self.inputs[v] = sorted(list(s))

        for v, s in copyConfig.outputs.items():
            self.outputs[v] = sorted(list(s))

        for stmt, prot, conv, cost, depth, nest, explicitConv in copyConfig.assignments:
            self.assignments.append([stmt, prot, sorted(list(conv)), cost, depth, nest, sortConv(explicitConv)])

        for v, s in copyConfig.protocolByVar.items():
            self.protocolByVar[v] = sorted(list(s))

        for v, s in copyConfig.constants.items():
            self.constants[v] = sorted(list(s))

        for v, s in copyConfig.plaintexts.items():
            self.plaintexts[v] = sorted(list(s))


    def __str__(self) -> str:
        inputs = "Input vars:\t{" + ", ".join(str(var) + ": " + (str(conv) if len(conv) else '{}') for var, conv in self.inputs.items()) + "}"
        constants = "Constants:\t{" + ", ".join(str(val) + ": " + (str(conv) if len(conv) else '{}') for val, conv in self.constants.items()) + "}"
        plaintexts = "Plaintext vars:\t{" + ", ".join(str(var) + ": " + (str(conv) if len(conv) else '{}') for var, conv in self.plaintexts.items()) + "}"
        flags = "Flags:\t\t{" + ", ".join(str(flag) for flag in self.flags) + "}"
        stmts = "\n".join("\t"*count + str(stmt) + ": " + str(assign) + " -> " + (str(conv) if len(conv) else '{}') + " for " + "{:.5f}".format(cost) + " * " + str(depth) + " = " + "{:.2f}".format(cost*depth) + (" (" + (", ".join(cd[0] + "->" + cd[1] for cd in convDict) if len(conv) else "") + ")" if len(convDict) else "") for stmt, assign, conv, cost, depth, count, convDict in self.assignments)
        finalLines = "\n".join(str(l) for l in reversed(self.finalStmts))
        outputs = "Output vars:\t{" + ", ".join(str(var) + ": " + (str(conv) if len(conv) else '{}') for var, conv in self.outputs.items()) + "}"
        return "Total cost:\t{:.5f}".format(self.total_cost) + "\n" + inputs + "\n" + constants + "\n" + plaintexts + "\n" + flags + "\n" + stmts + "\n" + finalLines + "\n" + outputs + "\n"


# get any constants from the RHS of a statement
def getRHSConstants(rhs: AssignRHS) -> list[Var]:
    if isinstance(rhs, Var):
        return []
    elif isinstance(rhs, Constant):
        return [Var(str(rhs.value))]
    elif isinstance(rhs, Subscript):
        return []
    elif isinstance(rhs, VectorizedAccess):
        return []
    elif isinstance(rhs, BinOp):
        return getRHSConstants(rhs.left) + getRHSConstants(rhs.right)
    elif isinstance(rhs, UnaryOp):
        return getRHSConstants(rhs.operand)
    elif isinstance(rhs, (List, Tuple)):
        return [var for item in rhs.items for var in getRHSConstants(item)]
    elif isinstance(rhs, Mux):
        return (
            getRHSConstants(rhs.condition)
            + getRHSConstants(rhs.false_value)
            + getRHSConstants(rhs.true_value)
        )
    elif isinstance(rhs, Update):
        return (
            getRHSConstants(rhs.array)
            + getRHSConstants(rhs.value)
        )
    elif isinstance(rhs, VectorizedUpdate):
        return (
            getRHSConstants(rhs.array)
            + getRHSConstants(rhs.value)
        )
    elif isinstance(rhs, LiftExpr):
        return getRHSConstants(rhs.expr)
    elif isinstance(rhs, DropDim):
        return getRHSConstants(rhs.array)
    else:
        assert_never(rhs)


def populateFlags(config: Config) -> None:
    replace = {'X': 'A'} if 'X' in config.flags else ({'Y': 'A'} if 'Y' in config.flags else None)
    if not replace:
        return

    # correct assignments
    for i in range(len(config.assignments)):
        val = config.assignments[i][1]
        if val in replace.keys():
            config.assignments[i][1] = replace[val]
        for k, v in replace.items():
            if k in config.assignments[i][2]:
                config.assignments[i][2].add(v)
                config.assignments[i][2].remove(k)
        for j in range(len(config.assignments[i][6])):
            for k, v in replace.items():
                if k == config.assignments[i][6][j][0]:
                    config.assignments[i][6][j] = (v, config.assignments[i][6][j][1])
                if k == config.assignments[i][6][j][1]:
                    config.assignments[i][6][j] = (config.assignments[i][6][j][0], v)

    # correct input variables
    for key in config.inputs.keys():
        for k, v in replace.items():
            if k in config.inputs[key]:
                config.inputs[key].add(v)
                config.inputs[key].remove(k)

    # correct constants
    for key in config.constants.keys():
        for k, v in replace.items():
            if k in config.constants[key]:
                config.constants[key].add(v)
                config.constants[key].remove(k)

    # correct plaintext variables
    for key in config.plaintexts.keys():
        for k, v in replace.items():
            if k in config.plaintexts[key]:
                config.plaintexts[key].add(v)
                config.plaintexts[key].remove(k)

    # correct output variables
    for key in config.outputs.keys():
        for k, v in replace.items():
            if k in config.outputs[key]:
                config.outputs[key].add(v)
                config.outputs[key].remove(k)



# function to get the required protocols for every constant
def populateConstantsAndPlaintexts(config: Config, plainVars: set[Var]) -> None:
    declared = set()
    for stmt, p, conv, _, _, _, _ in config.assignments:
        declared.add(getLHSVar(stmt))
        if isinstance(stmt, Assign):
            ps = ({p} | conv) - {'_'}
            for val in getRHSConstants(stmt.rhs):
                if val not in config.constants.keys():
                    config.constants[val] = ps
                else:
                    config.constants[val] |= ps
            for var in getRHSSimpleVars(stmt.rhs):
                if var in plainVars and var not in declared:
                    if var not in config.plaintexts.keys():
                        config.plaintexts[var] = ps if p == '_' else {p}
                    else:
                        config.plaintexts[var] |= ps if p == '_' else {p}
                    if var in config.inputs.keys():
                        assert config.inputs[var] == config.plaintexts[var]
                        del config.inputs[var]


# helper function to find the natural bounds of each tracked variable
def getNaturalBounds(nonZeroVars: set[Var], stmts: list[Statement], loop_depth: int) -> None:
    global bounds
    for stmt in stmts:
        if isinstance(stmt, llc.Return):
            continue
        if isinstance(stmt, llc.For):
            low: Union[str, int, bool, Var, Constant] = stmt.bound_low
            if isinstance(low, Constant):
                low = low.value
            else:
                low = str(low)
                assert low in loopBounds.keys()
                low = loopBounds[low]
            high: Union[str, int, bool, Var, Constant] = stmt.bound_high
            if isinstance(high, Constant):
                high = high.value
            else:
                high = str(high)
                assert high in loopBounds.keys()
                high = loopBounds[high]
            getNaturalBounds(nonZeroVars, stmt.body, loop_depth*(high-low))
        else:
            var = getLHSVar(stmt)
            if var in nonZeroVars:
                bounds[var] = dict()
                bounds[var]['this'] = (findVectorBound(stmt.lhs), loop_depth)


# create a map[Var -> subMap] where subMap = map[String -> (vector bound, loop bound)]
#   The subMap keys are: 'this'   (this variable's bounds)
#                        'input'  (the subsumption bounds if this variable appears as an input)
#                        'output' (the subsumption bounds if this variable appears as an output)
# ASSUMPTION: A GIVEN VARIABLE IS NOT DIRECTLY DROPPED MULTIPLE TIMES (TRUE ONCE COPY PROPAGATION IS IMPLEMENTED)-----------CURRENTLY DISABLED and picks first child instead
def getBounds(nonZeroVars: set[Var], dep_graph: DepGraph, stmts: list[Statement]) -> None:
    global bounds
    getNaturalBounds(nonZeroVars, stmts, 1)
    for var in nonZeroVars:
        stmt = dep_graph.var_to_assignment[var]
        assert not isinstance(stmt, DepParameter)
        count = 0
        if not 'input' in bounds[var].keys():
            curStmt = stmt
            sameKeys = set()
            inputVal = None
            while True:
                sameKeys.add(getLHSVar(curStmt))
                if 'input' in bounds[getLHSVar(curStmt)].keys():
                    inputVal = bounds[getLHSVar(curStmt)]['input']
                    break
                if isinstance(curStmt, Assign) and isinstance(curStmt.rhs, LiftExpr):
                    rhsVars = getRHSSimpleVars(curStmt.rhs)
                    assert len(rhsVars) == 1
                    rhsVar = rhsVars[0]
                    if rhsVar in dep_graph.var_to_assignment.keys():
                        temp = dep_graph.var_to_assignment[rhsVar]
                        assert not isinstance(temp, DepParameter)
                        curStmt = temp
                    else:
                        inputVal = (-1, -1)
                        break
                else:
                    inputVal = bounds[getLHSVar(curStmt)]['this']
                    break
            for inVar in sameKeys:
                if inputVal == (-1, -1):
                    bounds[inVar]['this'] = inputVal
                    bounds[inVar]['input'] = inputVal
                    bounds[inVar]['output'] = inputVal
                else:
                    bounds[inVar]['input'] = inputVal
        if not 'output' in bounds[var].keys():
            curStmt = stmt
            sameKeys = set()
            outputVal = None
            while True:
                sameKeys.add(getLHSVar(curStmt))
                if 'output' in bounds[getLHSVar(curStmt)].keys():
                    outputVal = bounds[getLHSVar(curStmt)]['output']
                    break
                count = 0
                for child in dep_graph.def_use_graph[curStmt]:
                    if isinstance(child, Assign) and isinstance(child.rhs, DropDim):
                        count += 1
                        curStmt = child
                    assert count <= 1
                if count == 0:
                    outputVal = bounds[getLHSVar(curStmt)]['this']
                    break
            for outVar in sameKeys:
                bounds[outVar]['output'] = outputVal
    return


# get the bounds for every loop in the current test case (needed for cost computation)
def getLoopBounds(filename: str, python_text: str) -> None:
    global loopBounds
    filename = dirname(__file__)+"/../../benchmarks/" + '.'.join(filename.split('.')[:-1]) + "_bounds.json"
    
    assert exists(filename)
    loopBounds_translation = json.load(open(filename))
    loopBounds = {}
    for key,value in loopBounds_translation.items():
        pattern = rf"^{key}\s*=\s*(\d+)$"  # Match 'VariableName = Value' at the start of the line
        match = re.search(pattern, python_text, re.MULTILINE)
        assert match
        extracted_match = int(match.group(1).strip())
        loopBounds[value] = extracted_match
        

# get the cost table
# ASSUMPTION: EVERYTHING IS 32 BIT
def getOpCosts(filename: str) -> None:
    global costTable
    assert exists(dirname(__file__) + filename)
    costTable = json.load(open(dirname(__file__) + filename))['32']


# get the variables the mixer needs to track. Also detect variables that are directly input/output from the program (ie the I/O interface)
def getTrackedVars(type_env: TypeEnv, stmts: list[Statement], dep_graph: DepGraph) -> tuple[set[Var], set[Var]]:
    # add inputs, outputs, and constants
    directIO = {var for var, stmt in dep_graph.var_to_assignment.items() if isinstance(stmt, DepParameter)}
    directIO.add(getLHSVar(stmts[-1]))
    stmt: Union[Phi, Assign, For, Return, DepParameter]
    for stmt in stmts:
        if isinstance(stmt, Assign) and isinstance(stmt.rhs, Constant):
            directIO.add(getLHSVar(stmt))

    prevLen = -1
    while prevLen < len(directIO):
        prevLen = len(directIO)
        toAdd = set()
        for var in directIO:
            stmt = dep_graph.var_to_assignment[var]

            # check backwards propagating outputs
            if isinstance(stmt, Assign) and (isinstance(stmt.rhs, Tuple) or isinstance(stmt.rhs, LiftExpr) or isinstance(stmt.rhs, DropDim)):
                toAdd |= set(getRHSSimpleVars(stmt.rhs))

            # check forward propagating inputs
            if not isinstance(stmt, Tuple):
                for stmt2 in dep_graph.def_use_graph.neighbors(stmt):
                    if isinstance(stmt2, Assign) and (isinstance(stmt2.rhs, LiftExpr) or isinstance(stmt2.rhs, DropDim)):
                        toAdd.add(getLHSVar(stmt2))
        if len(toAdd):
            directIO |= toAdd
    return {var for var, t in type_env.items() if t.visibility and t.visibility.value != 'plaintext'}, directIO


# copied from dep_graph.py
def collect_rhs(stmt: DepNode) -> list[llc.AssignRHS]:
    if isinstance(stmt, llc.Phi):
        return cast(list[llc.AssignRHS], stmt.rhs_vars())
    elif isinstance(stmt, llc.Assign):
        return [stmt.rhs]
    elif isinstance(stmt, DepParameter):
        return [stmt.var]
    elif isinstance(stmt, llc.For):
        if stmt.is_monolithic:
            return [
                used_var
                for substmt in stmt.body
                for used_var in collect_rhs(substmt)
            ]
        else:
            return []
    elif isinstance(stmt, llc.Return):
        return [stmt.value]
    else:
        assert_never(stmt)


# separate the code into a list of sequences based on for loops
#  these blocks will be individually optimized, then combined with merge
#  nested loops will be recursively handled
def separate_seqs(function: list[Statement]) -> list[list[Statement]]:
    seqs: list[list[Statement]] = []
    temp: list[Statement] = []
    for stmt in function:
        if isinstance(stmt, llc.For):
            if len(temp) > 0:
                seqs.append(temp)
                temp = []
            seqs.append([stmt])
        else:
            temp.append(stmt)
    if len(temp) > 0:
        seqs.append(temp)
    return seqs


# get the LHS variable from the statement
def getLHSVar(stmt1: Union[Statement, DepParameter]) -> Var:
    if isinstance(stmt1, llc.Return):
        return stmt1.value
    stmt = stmt1.lhs
    if isinstance(stmt, Subscript) or isinstance(stmt, VectorizedAccess) or isinstance(stmt, Update) or isinstance(stmt, VectorizedUpdate) or isinstance(stmt, DropDim):
        return stmt.array
    return stmt


# modified from tac_cfg.py - removed array bounds as variables
def getRHSSimpleVars(rhs: AssignRHS) -> list[Var]:
    if isinstance(rhs, Var):
        return [rhs]
    elif isinstance(rhs, Constant):
        return []
    elif isinstance(rhs, Subscript): # TODO CHECK IF CORRECT
        return [rhs.array]# + subscript_index_accessed_vars(rhs.index)
    elif isinstance(rhs, VectorizedAccess):
        return [rhs.array]
    elif isinstance(rhs, BinOp):
        return getRHSSimpleVars(rhs.left) + getRHSSimpleVars(rhs.right)
    elif isinstance(rhs, UnaryOp):
        return getRHSSimpleVars(rhs.operand)
    elif isinstance(rhs, (List, Tuple)):
        return [var for item in rhs.items for var in getRHSSimpleVars(item)]
    elif isinstance(rhs, Mux): # TODO CHECK IF CORRECT
        return (
            getRHSSimpleVars(rhs.condition)
            + getRHSSimpleVars(rhs.false_value)
            + getRHSSimpleVars(rhs.true_value)
        )
    elif isinstance(rhs, Update): # TODO CHECK IF CORRECT
        return (
            getRHSSimpleVars(rhs.array)
            + getRHSSimpleVars(rhs.value)
            #+ subscript_index_accessed_vars(rhs.index)
            #+ getRHSSimpleVars(rhs.value)
        )
    elif isinstance(rhs, VectorizedUpdate): # TODO CHECK IF CORRECT
        return (
            getRHSSimpleVars(rhs.array)
            + getRHSSimpleVars(rhs.value)
        )
    elif isinstance(rhs, LiftExpr):
        return getRHSSimpleVars(rhs.expr)
    elif isinstance(rhs, DropDim):
        return getRHSSimpleVars(rhs.array)
    else:
        assert_never(rhs)


# get the predicted cost for the given operator, protocol, and vector length
# if vectorLen <= tableMaxIndex, choose unit cost from linear interpolation
#   otherwise (vectorLen > tableMaxIndex), choose unit cost = value at tableMaxIndex
def getCost(op: str, p: Optional[str], vectorLen: int) -> float:
    prelim: Any = costTable[op]
    if p:
        if p not in prelim.keys():
            return float('inf')
        prelim = prelim[p]

    options = [int(i) for i in prelim.keys()]
    if vectorLen >= options[-1]:
        return prelim[str(options[-1])]*vectorLen

    for i in range(len(options)):
        if options[i] <= vectorLen < options[i+1]:
            break

    x = vectorLen
    x1 = options[i]
    if x1 == x:
        return prelim[str(x1)]*vectorLen
    x2 = options[i+1]
    y1 = prelim[str(x1)]
    y2 = prelim[str(x2)]

    return (y1 + (x-x1)*(y2-y1)/(x2-x1)) * vectorLen


# find the size of the vector in a VectorizedAccess
def findVectorBound(stmt: Union[VectorizedAccess, VectorizedUpdate, Var]) -> int:
    if isinstance(stmt, VectorizedUpdate):
        raise Exception(stmt)
    if isinstance(stmt, VectorizedAccess):
        toRet = 1
        for s, vectorized in zip(stmt.dim_sizes, stmt.vectorized_dims):
            size: int
            if vectorized:
                if isinstance(s, Constant):
                    size = s.value
                else:
                    s1 = str(s)
                    assert s1 in loopBounds.keys()
                    size = loopBounds[s1]
                toRet *= size
        return toRet
    return 1


# create a new Config from the previous Config and next statement
# TODO currently throws an error if a conversion is not available
def createNewConfig(conversions: set[Protocol], p: Protocol, prevConfig: Config, trackedVars: set[Var], addOutput: bool, head: Statement, requiredInputVars: set[Var], loop_depth: int, loopNestCount: int, dep_graph: DepGraph) -> Config:
    # clean conversion set
    conv = deepcopy(conversions)
    convPairs: list[tuple[str, str]] = []
    if p in conv:
        conv.remove(p)

    # create the new Config as a copy of the previous Config
    newConfig = deepcopy(prevConfig)
    newConfig.assignments = [[a[0], a[1], a[2].copy(), a[3], a[4], a[5], a[6].copy()] for a in prevConfig.assignments]
    lhsVar = getLHSVar(head)
    if p != '_' or len(conv) > 0:
        newConfig.protocolByVar[lhsVar] = (set() if p == '_' else {p}) | conv

    # edge case - skip other steps for Return or Tuple types
    assert not isinstance(head, For)
    if isinstance(head, llc.Return) or (not isinstance(head, Phi) and isinstance(head.rhs, llc.Tuple)):
        newConfig.finalStmts.append(head)
        return newConfig

    # update output dictionary
    if addOutput:
        newConfig.outputs[lhsVar] = {p} | conv

    # update input dictionary
    if not isinstance(head, llc.Return) and lhsVar in prevConfig.inputs:
        conv |= (newConfig.inputs[lhsVar] - {'_', p})
        del newConfig.inputs[lhsVar]
    for var in requiredInputVars:
        if var in trackedVars or p != '_':
            toAdd = {p}
            if not isinstance(head, Phi) and (isinstance(head.rhs, LiftExpr) or isinstance(head.rhs, DropDim)):
                toAdd |= conv
            if var not in newConfig.inputs:
                newConfig.inputs[var] = {p}
            newConfig.inputs[var] |= toAdd
            if len(newConfig.inputs[var]) > 1 and '_' in newConfig.inputs[var]:
                newConfig.inputs[var].remove('_')

    # compute cost of this operation (including output conversion(s) if applicable)
    c = 0.0
    op = type(head).__name__ if isinstance(head, llc.Return) or isinstance(head, Phi) else str(head.rhs.operator) if isinstance(head.rhs, BinOp) else str(head.rhs.operator) + 'UNARY' if isinstance(head.rhs, UnaryOp) else type(head.rhs).__name__
    assert op in zeroCostOps or op in opToCostSymbol.keys()
    vecBound = findVectorBound(head.lhs)
    if op not in zeroCostOps:
        c += getCost(opToCostSymbol[op], p.lower(), vecBound)
    for pr in conv:
        if p != '_':
            conversionSymbol = f'zic_{p.lower()}2{pr.lower()}'
            c += getCost(conversionSymbol, None, vecBound)
            assert (p, pr) not in convPairs
            convPairs.append((p, pr))

    # special handling for phi nodes: add new required conversions to back edges
    # ASSUMPTION the rhs_true node is only used for the back edge - it will never appear as a final input or output
    if isinstance(head, Phi):
        assert len(getRHSSimpleVars(head.rhs_true)) == 1
        targetStmt = dep_graph.var_to_assignment[getRHSSimpleVars(head.rhs_true)[0]]
        found = False
        for assignment in reversed(newConfig.assignments):
            if assignment[0] == targetStmt:
                found = True
                if p not in ({assignment[1]} | assignment[2]):
                    assert not isinstance(targetStmt, Return)
                    vecBound = findVectorBound(targetStmt.lhs)
                    targetLhs = getLHSVar(targetStmt)
                    assignment[2].add(p)
                    if targetLhs in newConfig.outputs.keys():
                        newConfig.outputs[targetLhs].add(p)
                    minC = float('inf')
                    minPr = '_'
                    for pr in ({assignment[1]} | assignment[2]) - {p}:
                        conversionSymbol = f'zic_{p.lower()}2{pr.lower()}'
                        curCost = getCost(conversionSymbol, None, vecBound)
                        if curCost < minC:
                            minC = curCost
                            minPr = pr
                    assignment[3] += minC
                    assert (minPr, p) not in assignment[6]
                    assignment[6].append((minPr, p))
                    newConfig.total_cost += assignment[4] * minC
                break
        if not found:
            assert getLHSVar(targetStmt) not in newConfig.inputs.keys()
            newConfig.inputs[getLHSVar(targetStmt)] = {p}

    newConfig.total_cost += c * loop_depth
    newConfig.assignments = [[head, p, conv, c, loop_depth, loopNestCount, convPairs]] + newConfig.assignments
    return newConfig


# lock a list of variables to the same protocols in the given Config
def lockSet(vars: list[Var], config: Config) -> None:
    idxs = []
    for v in vars:
        if v in config.lockedVarsIdx.keys():
            idxs.append(config.lockedVarsIdx[v])
    if len(idxs) > 1:
        idx = idxs[0]
        for merge in idxs[1:]:
            for oldVar in config.lockedVarsSets[merge]:
                config.lockedVarsIdx[oldVar] = idx
            config.lockedVarsSets[idx] |= config.lockedVarsSets[merge]
    if len(idxs) == 0:
        idxs.append(len(config.lockedVarsSets))
        config.lockedVarsSets.append(set())
    for v in vars:
        if not v in config.lockedVarsIdx.keys():
            config.lockedVarsIdx[v] = idxs[0]
            config.lockedVarsSets[idxs[0]].add(v)


# check that the total cost of this block was correctly computed
def verifyCosts(cfg: Config):
    runningTotal = 0
    infCost = True if cfg.total_cost == float('inf') else False
    for _, _, _, c, d, _, _ in cfg.assignments:
        runningTotal += c*d
        if c == float('inf'):
            if infCost:
                return
            assert False
    if abs(runningTotal - cfg.total_cost) >= 0.01:
        print(cfg)
    assert abs(runningTotal - cfg.total_cost) < 0.01

        
# find all possible mixes for the given sequence of statements
# for lift, the requested protocol(s) are converted BEFORE executing the lift operation because the lift operation has no cost and pre-converting is guaranteed to be less expensive
#  for drop, the requested protocol(s) are converted AFTER executing the drop operation because the drop operation has no cost and post-converting is guaranteed to be less expensive
# TODO ADD PHI TO LOCKED & NO COST PROTOCOLS
# TODO VERIFY ASSUMPTION THAT PHI NODES ARE NEVER THE LAST STATEMENT IN A SEQUENCE
def assign_seq(seq: list[Statement], dep_graph: DepGraph, trackedVars: set[Var], loop_depth: int, loopNestCount: int) -> list[Config]:

    # base case
    if len(seq) == 0:
        if runningSpdz:
            return [Config('X' if 'X' in protocols else ('Y' if 'Y' in protocols else None))]
        return [Config()]

    # tail recursion
    tail = assign_seq(seq[1:], dep_graph, trackedVars, loop_depth, loopNestCount)
    head = seq[0]
    uses = [*dep_graph.def_use_graph.neighbors(head)]
    uses = [use for use in uses if not isinstance(use, llc.For)]

    # find the variables that head requires as input
    #   ASSUMPTION: the rhs_true branch of phi nodes are ALWAYS declared in the future code, so remove them from this set
    requiredInputVars = {var for expr in collect_rhs(head)
                             for var in getRHSSimpleVars(expr)}
    if isinstance(head, Phi):
        assert len(getRHSSimpleVars(head.rhs_true)) == 1
        requiredInputVars.remove(getRHSSimpleVars(head.rhs_true)[0])

    assert not isinstance(head, llc.For)

    # create new Configs for each protocol (if this is a mixed operation)
    newConfigs = []
    for config in tail:
        conversions = set()
        useCount = 0

        # find necessary conversions in this block
        for stmt, protocol, _, _, _, _, _ in config.assignments:
            if stmt in uses and not isinstance(stmt, llc.Return) and not isinstance(stmt, llc.Tuple):
                useCount += 1
                if protocol != '_' and protocol not in conversions:
                    conversions.add(protocol)
        assert useCount <= len(uses)

        # add possible protocols to the new configurations. This grows exponentially with the number of statements
        ps = set()
        if isinstance(head, llc.Return):
            ps.add('_')
        if len(ps) == 0:
            for op in transparent_ops:
                assert not isinstance(head, Return)
                if not isinstance(head, Phi) and isinstance(head.rhs, op):
                    lockSet(getRHSSimpleVars(head.rhs) + [getLHSVar(head)], config)
                    locks = config.lockedVarsSets[config.lockedVarsIdx[getLHSVar(head)]]
                    for var in locks:
                        if var in config.protocolByVar.keys() and len(config.protocolByVar[var] - {'_'}) > 0:
                            conversions |= config.protocolByVar[var]
                    ps.add('_')
                    break
        if len(ps) == 0:
            ps = protocols.copy()

        # create a new config for each possible protocol
        for p in ps:
            newC = createNewConfig(conversions, p, config, trackedVars, useCount < len(uses) or isinstance(head, llc.Return), head, requiredInputVars, loop_depth, loopNestCount, dep_graph)
            verifyCosts(newC)
            if newC.total_cost < float("inf"):
                newConfigs.append(newC)
    return newConfigs


# returns true if config a subsumes config b -> if config a (with full i/o conversion) can replace b at lower cost
# TODO currently throws an error if a conversion is not available
# TODO this method of checking min conversion cost is not quite correct - it could be less expensive to chain through one of the new protocols...this is not tritival (I think it's exponential) to fix
# ASSUMPTION: IF AN INPUT PROTOCOL IS '_' (NOT YET DETERMINED), THEN IGNORE THIS CONVERSION (COST = 0) BECAUSE IT WILL NOT EFFECT SUBSUMPTION
#               EXCEPT WHEN THIS STATEMENT IS A DROP DIM ASSIGNED IN THIS BLOCK, THEN DON'T SUBSUME
# ASSUMPTION: SUBSUMPTION IGNORES ANYTHYING THAT IS DIRECTLY DERIVED FROM AN INPUT VARIABLE OR DERIVES DIRECTLY TO AN OUTPUT VARIABLE
#              BECAUSE (BY ASSUMPTION) INPUTS ARE AVAILABLE IN ALL PROTOCOLS AND THE OUTPUT PROTOCOL DOES NOT MATTER
def subsumes(a: Config, b: Config, loop_depth: int, dep_graph: DepGraph, freeConversions: set[Var], trackedVars: set[Var]) -> bool:
    
    # can't subsume if a is already more expensive than b
    costComparison = b.total_cost - a.total_cost
    if costComparison <= 0:
        return False

    # input conversion cost (b -> a)
    for var, requiredPs in a.inputs.items():
        if var not in freeConversions:
            assert var in trackedVars
            v = dep_graph.var_to_assignment[var]
            if isinstance(v, DepParameter): # I DON'T THINK THIS IS POSSIBLE OR THAT IT IS CORRECT. DISABLED FOR NOW
                assert False
                v = str(v.var)
                loopBound = loopBounds[v] if v in loopBounds.keys() else 1
            else:
                loopBound, loop_depth = bounds[var]['input']
                if loopBound == -1:
                    continue
            for requiredP in requiredPs:
                if requiredP == '_':
                    # verify assumption that the lines in Config (a) do not use the lhs of the associated statement
                    found = False
                    cannotAppearRHS = set()
                    for stmt, p, conv, _, _, _, _ in a.assignments:
                        rhsVars = getRHSSimpleVars(stmt.rhs)
                        for rhsVar in rhsVars:
                            assert rhsVar not in cannotAppearRHS
                        if var in rhsVars and p == '_' and conv == set():
                            found = True
                            lhsVar = getLHSVar(stmt)
                            cannotAppearRHS.add(lhsVar)
                            assert lhsVar in a.outputs.keys()
                            assert '_' in a.outputs[lhsVar]
                        # special case for DropDim. Do not subsume if a protocol was assigned in this block
                        if var in rhsVars and p == '_' and isinstance(stmt.rhs, DropDim):
                            return False
                    assert found
                    continue
                if requiredP not in b.inputs[var]:
                    minC = float("inf")
                    for availP in b.inputs[var]:
                        conversionSymbol = f'zic_{availP.lower()}2{requiredP.lower()}'
                        minC = min(getCost(conversionSymbol, None, loopBound), minC)
                    costComparison -= minC*loop_depth
                    if costComparison < 0:
                        return False

    # output conversion cost (a -> b)
    for var, requiredPs in b.outputs.items():
        if var not in freeConversions:
            v = dep_graph.var_to_assignment[var]
            if isinstance(v, DepParameter): # I DON'T THINK THIS IS POSSIBLE OR THAT IT IS CORRECT. DISABLED FOR NOW
                assert False
                v = str(v.var)
                loopBound = loopBounds[v] if v in loopBounds.keys() else 1
            else:
                loopBound, loop_depth = bounds[var]['output']
                if loopBound == -1:
                    continue
            for requiredP in requiredPs:
                if requiredP == '_':
                    # verify assumption that the lines in Config (b) do not assign protocols to the rhs of the associated statement
                    processed = set()
                    curSet = [var]
                    while len(curSet):
                        lhsVar = curSet.pop(0)
                        if lhsVar in processed:
                            continue
                        processed.add(lhsVar)
                        if lhsVar in dep_graph.var_to_assignment.keys():
                            toFind = dep_graph.var_to_assignment[lhsVar]
                            for stmt, p, conv, _, _, _, _ in b.assignments:
                                if stmt == toFind:
                                    assert p == '_' and conv == set()
                                    assert isinstance(toFind, Assign)
                                    curSet += getRHSSimpleVars(toFind.rhs)
                                    break
                    continue
                if requiredP not in a.outputs[var]:
                    minC = float("inf")
                    for availP in a.outputs[var]:
                        conversionSymbol = f'zic_{availP.lower()}2{requiredP.lower()}'
                        minC = min(getCost(conversionSymbol, None, loopBound), minC)
                    costComparison -= minC*loop_depth
                    if costComparison < 0:
                        return False

    if costComparison <= 0:
        return False
    return True


# driver code for subsumption
def clean_up_with_subsumption(configs: list[Config], loop_depth: int, dep_graph: DepGraph, freeConversions: set[Var], trackedVars: set[Var]) -> list[Config]:
    toRemove = []
    for i in range(len(configs)-1):
        if i in toRemove:
            continue
        for j in range(i+1, len(configs)):
            if i in toRemove or j in toRemove:
                continue
            if subsumes(configs[i], configs[j], loop_depth, dep_graph, freeConversions, trackedVars):
                toRemove.append(j)
            elif subsumes(configs[j], configs[i], loop_depth, dep_graph, freeConversions, trackedVars):
                toRemove.append(i)
    return [configs[i] for i in range(len(configs)) if i not in toRemove]


# cleans up the given Config
# POTENTIAL ISSUE: WHAT IF A LIFT STATEMENT IS NOT "FIXED" WITHIN THIS BLOCK OF CODE (ie it depends on a variable outside of this block)?
#   THIS CASE MIGHT BREAK THE CODE...I HAVE TO THINK ABOUT IT
# will only fix forward edges
def clean_locked_stmts(config: Config) -> None:
    for item in config.assignments:
        if item[1] == '_':
            lhsVar = getLHSVar(item[0])
            if isinstance(item[0], Phi):
                if len(item[2]) and '_' not in item[2]:
                    assert len(item[2]) == 1
                    item[1] = list(item[2])[0]
                    item[2] = {'_'}
                    assert len(getRHSSimpleVars(item[0].rhs_false)) == 1
                    assert len(getRHSSimpleVars(item[0].rhs_true)) == 1
                    rhsVar = getRHSSimpleVars(item[0].rhs_false)[0]
                    rhsVar2 = getRHSSimpleVars(item[0].rhs_true)[0]
                    if rhsVar in config.inputs.keys():
                        assert config.inputs[rhsVar] == {'_'}
                        config.inputs[rhsVar] = set(item[1])
                    if rhsVar2 in config.inputs.keys():
                        assert config.inputs[rhsVar2] == {'_'}
                    config.inputs[rhsVar2] = set(item[1])
            if isinstance(item[0], llc.Return):
                if lhsVar in config.protocolByVar.keys():
                    item[2] = config.protocolByVar[lhsVar]
                    if lhsVar in config.outputs.keys():
                        config.outputs[lhsVar] = item[2]
            elif lhsVar in config.lockedVarsIdx.keys():
                for var in config.lockedVarsSets[config.lockedVarsIdx[lhsVar]]:
                    if var in config.protocolByVar.keys() or var in config.inputs.keys():
                        config.protocolByVar[lhsVar] = config.protocolByVar[var] if var in config.protocolByVar.keys() else config.inputs[var]
                        item[2] |= config.protocolByVar[lhsVar]
                if lhsVar in config.outputs.keys() and len(item[2]) > 0:
                    config.outputs[lhsVar] = item[2]
            if '_' in item[2]:
                item[2] = item[2] - {'_'}


# merge two configurations
# for new conversions, if the variable is declared by a raise_dim, chain through declarations adding the conversion until a non-raise_dim is found
#   otherwise, place the conversion at the variable's declaration
def merge(c1: Config, c2: Config, dep_graph: DepGraph, trackedVars: set[Var]) -> Config:
    # print("MERGE")
    # print(c1)
    # print(c2)
    newConfig = deepcopy(c1)
    newConfig.outputs = deepcopy(c2.outputs)
    newConfig.assignments = []
    assert len(newConfig.finalStmts) == 0
    newConfig.finalStmts = c2.finalStmts
    c1Stmts, c2Stmts = set(), set()
    c1OutputsCopy = deepcopy(c1.outputs)

    for assignment in c1.assignments:
        newConfig.assignments.append([assignment[0]] + deepcopy(assignment[1:]))
        c1Stmts.add(assignment[0])

    # SPECIAL HANDLING FOR PHI NODES. CHECK IF ANY c1 INPUTS ARE DEFINED IN c2. Will add these conversions later
    backPs = dict()
    for assignment in c2.assignments:
        v = getLHSVar(assignment[0])
        if v in newConfig.inputs.keys():
            assert '_' not in newConfig.inputs[v]
            backPs[assignment[0]] = newConfig.inputs[v]
        newConfig.assignments.append([assignment[0]] + deepcopy(assignment[1:]))
        c2Stmts.add(assignment[0])
    newConfig.total_cost += c2.total_cost

    # connect c2 inputs to c1 outputs
    for var, protocols in c2.inputs.items():
        # if this variable is in the outputs of c1, then it was declared in c1 and we can resolve it
        if var in c1OutputsCopy.keys():
            newProtocols = set()
            for p in protocols:
                if p not in c1OutputsCopy[var]:
                    newProtocols.add(p)

            # if the variable from c2 never received an assignment, propagate assignment to that variable and any associated locks
            if newProtocols == {'_'}:
                protSet = c1OutputsCopy[var]
                lockedVars = {var}
                targetStmts = set()
                if var in c2.lockedVarsIdx.keys():
                    lockedVars |= c2.lockedVarsSets[c2.lockedVarsIdx[var]]

                # lookup the declarations associated with each variable. Also resolve output protocols at the same time
                for lockedVar in lockedVars:
                    targetStmts.add(dep_graph.var_to_assignment[lockedVar])
                    if lockedVar in newConfig.outputs.keys():
                        newConfig.outputs[lockedVar] = protSet

                # TODO CHECK IF IT IS CORRECT TO ONLY CHECK THE FIRST SET OF USES
                # update the target lines with any uses of the target variables
                toAdd = set()
                for line in targetStmts:
                    toAdd |= {use for use in dep_graph.def_use_graph.neighbors(line) if not isinstance(use, llc.For)}
                targetStmts |= toAdd

                # for each line in c2, update it's conversions to protSet if is one of the target statements
                for assignment in newConfig.assignments:
                    if assignment[0] in targetStmts and assignment[0] in c2Stmts:
                        assignment[2] = protSet
                # TODO IS THERE EVER A SCENARIO WHERE THIS EFFECTS COST?
            
            # assign new required conversions associated with this input-output pair
            #   if the lhs var is only used as a drop_dim, place conversion after the drop_dim
            #   if rhs is a raise_dim, chain through declarations until the "base" variable is found. Assign conversion to the base to reduce cost
            #   otherwise, place conversion at variable declaration
            #   ASSUMPTION: THE TWO CONDITIONS ABOVE DO NOT SIMULTANEOUSLY OCCUR
            #   the associated statement is guaranteed to have a rhs
            else:
                assert '_' not in newProtocols
                stmt = dep_graph.var_to_assignment[var]
                changed = False
                continueLooping = True
                first = True
                while continueLooping:
                    continueLooping = False
                    stmts = {use for use in dep_graph.def_use_graph.neighbors(stmt) if not isinstance(use, llc.For)}
                    count = 0
                    for s in stmts:
                        if not isinstance(s, Phi):
                            if isinstance(s.rhs, DropDim):
                                if not first:
                                    assert False # currently unhandled for multiple chained drop_dims
                                stmt = s
                                changed = True
                                continueLooping = True
                                first = False
                            count += 1
                    if count == 0:
                        break
                    assert not continueLooping or count == 1 # currently unhandled for multiple branches at this location

                # chain to "base" variable through raise_dims
                while not isinstance(stmt, DepParameter) and not isinstance(stmt, Phi) and not isinstance(stmt, For) and not isinstance(stmt, Return) and (isinstance(stmt.rhs, LiftExpr) or isinstance(stmt.rhs, VectorizedAccess)):
                    assert len(getRHSSimpleVars(stmt.rhs)) == 1
                    if getRHSSimpleVars(stmt.rhs)[0] not in dep_graph.var_to_assignment.keys():
                        break
                    for assignment in newConfig.assignments:
                        if stmt == assignment[0]:
                            assignment[2] |= newProtocols
                            break
                    stmt = dep_graph.var_to_assignment[getRHSSimpleVars(stmt.rhs)[0]]
                    lhsVar = getLHSVar(stmt)
                    if lhsVar in c1OutputsCopy:
                        c1OutputsCopy[lhsVar] |= newProtocols

                # if base is an input parameter, add to input Config
                if isinstance(stmt, DepParameter) and stmt.var in trackedVars:
                    if stmt.var not in newConfig.inputs.keys() or newConfig.inputs[stmt.var] == {'_'}:
                        newConfig.inputs[stmt.var] = set()
                    newConfig.inputs[stmt.var] |= newProtocols

                # otherwise, add required conversion
                else:
                    for assignment in newConfig.assignments:
                        if stmt == assignment[0]:
                            # special condition for chained drop_dim
                            if changed:
                                assert assignment[1] == '_'
                                assert isinstance(stmt, Assign)
                                variables = getRHSSimpleVars(stmt.rhs)
                                assert len(variables) == 1
                                var = variables[0]
                                assert assignment[2] == c2.inputs[var]
                                assignment[2] = c1OutputsCopy[var]
                                newProtocols = c2.inputs[var] - assignment[2]
                            assert not isinstance(stmt, Return)
                            vecBound = findVectorBound(stmt.lhs)
                            assert len(newProtocols.intersection({assignment[1]} | assignment[2])) == 0
                            for p in newProtocols:
                                if not isinstance(assignment[0], Phi) and (isinstance(assignment[0].rhs, llc.Constant) or isinstance(assignment[0].rhs, LiftExpr)):
                                    break
                                minC = float("inf")
                                minPr = '_'
                                if not isinstance(assignment[0], Phi) and isinstance(assignment[0].rhs, VectorizedAccess) and len(({assignment[1]} | assignment[2]) - {'_'}) == 0:
                                    minC = 0.0
                                    print("WARNING THIS TRIGGERED A SPECIAL CASE THAT IS NOT FULLY CHECKED")
                                # TODO THIS WAY OF PROTOCOL CHAINING IS NOT QUITE CORRECT...BUT IT'S NOT TRIVIAL TO FIX EITHER
                                for availP in ({assignment[1]} | assignment[2]) - {'_'}:
                                    conversionSymbol = f'zic_{availP.lower()}2{p.lower()}'
                                    curCost = getCost(conversionSymbol, None, vecBound)
                                    if curCost < minC:
                                        minC = curCost
                                        minPr = availP
                                assignment[3] += minC
                                assert (minPr, p) not in assignment[6]
                                assignment[6].append((minPr, p))
                                # TODO MAKE SURE IT IS CORRECT TO MULTIPLY BY LOOP DEPTH HERE
                                newConfig.total_cost += assignment[4] * minC
                            assignment[2] |= newProtocols

        # otherwise, this variable was not declared in c1, so it becomes an input to newConfig
        else:
            if var in newConfig.inputs.keys():
                newConfig.inputs[var] |= protocols
            else:
                newConfig.inputs[var] = protocols

    # connect outputs of c1 to newOutputs
    for var in c1.outputs.keys():
        uses = [*dep_graph.def_use_graph.neighbors(dep_graph.var_to_assignment[var])]
        uses = [use for use in uses if not isinstance(use, llc.For)]
        useCount = 0
        for stmt, _, _, _, _, _, _ in newConfig.assignments:
            if stmt in uses:
                useCount += 1
        assert useCount <= len(uses)
        if useCount < len(uses):
            newPs = set()
            stmt = dep_graph.var_to_assignment[var]
            for assignment in newConfig.assignments:
                if stmt == assignment[0]:
                    newPs = {assignment[1]} | assignment[2]
                    break
            if var in newConfig.outputs.keys():
                newConfig.outputs[var] |= newPs
            else:
                newConfig.outputs[var] = newPs
            if len(newConfig.outputs[var]) > 1 and '_' in newConfig.outputs[var]:
                newConfig.outputs[var].remove('_')
    assert set(newConfig.outputs.keys()).issubset(set(c1.outputs.keys()) | set(c2.outputs.keys()))

    # SPECIAL HANDLING FOR PHI NODES. Add protocols for any c1 inputs defined in c2
    for stmt, ps in backPs.items():
        for assignment in newConfig.assignments:
            if assignment[0] == stmt:
                assert not isinstance(stmt, Return)
                vecBound = findVectorBound(stmt.lhs)
                newProtocols = ps - {assignment[1]} - assignment[2]
                for p in newProtocols:
                    minC = float("inf")
                    minPr = '_'
                    # TODO THIS WAY OF PROTOCOL CHAINING IS NOT QUITE CORRECT...BUT IT'S NOT TRIVIAL TO FIX EITHER
                    for availP in ({assignment[1]} | assignment[2]) - {'_'}:
                        conversionSymbol = f'zic_{availP.lower()}2{p.lower()}'
                        curCost = getCost(conversionSymbol, None, vecBound)
                        if curCost < minC:
                            minC = curCost
                            minPr = availP
                    assignment[3] += minC
                    assert (availP, p) not in assignment[6]
                    assignment[6].append((availP, p))
                    # TODO MAKE SURE IT IS CORRECT TO MULTIPLY BY LOOP DEPTH HERE
                    newConfig.total_cost += assignment[4] * minC
                assignment[2] |= newProtocols
                v = getLHSVar(assignment[0])
                if v in newConfig.inputs.keys():
                    newConfig.inputs[v] -= ps
                    if len(newConfig.inputs[v]) == 0:
                        del newConfig.inputs[v]
                break

    # print(newConfig)
    return newConfig


# merge all pairs between configs1 and configs2
def mergeDriver(configs1: list[Config], configs2: list[Config], dep_graph: DepGraph, trackedVars: set[Var]) -> list[Config]:
    configsOut = []
    for c1 in configs1:
        for c2 in configs2:
            configsOut.append(merge(c1, c2, dep_graph, trackedVars))
    return configsOut


# run mixing
# ASSUMPTION: ALL INPUT PARAMETERS AND ALL CONSTANTS ARE AVAILABLE IN ALL PROTOCOLS
# ASSUMPTION: PROTOCOL DOES NOT MATTER FOR OUTPUT
# ASSUMPTION: ALL VECTOR CONVERSIONS ARE APPLIED TO ALL ELEMENTS
# ASSUMPTION: TUPLES ARE ONLY USED TO PACK RETURN VALUES
#   THIS IS SAFE BECAUSE OPERATIONS WILL BE APPLIED AT EVERY ELEMENT OF A VECTOR AND VECTOR CONVERSIONS ARE AMORTIZED (IT IS LESS EXPENSIVE TO CONVERT ALL ELEMENTS THAN TO INDIVIDUALLY CONVERT EACH ELEMENT)
def mix(body: list[Statement], dep_graph: DepGraph, trackedVars: set[Var], freeConversions: set[Var], loop_depth: int = 1, loopNestCount: int = 0, debug=False) -> list[Config]:
    if debug:
        print("CALL TO MIX")

    # break into sequences based on for loops
    seqs = separate_seqs(body)
    if debug:
        print("SEQS:\n" + "\n".join(str(stmt) for seq in seqs for stmt in seq + ['']))

    # create configs for each sequence (recursive for nested for loops)
    rawConfigs = []
    for seq in seqs:
        if isinstance(seq[0], llc.For) and len(seq) == 1:
            low: Any = seq[0].bound_low
            if isinstance(low, Constant):
                low = low.value
            else:
                low = str(low)
                assert low in loopBounds.keys()
                low = loopBounds[low]
            high: Any = seq[0].bound_high
            if isinstance(high, Constant):
                high = high.value
            else:
                high = str(high)
                assert high in loopBounds.keys()
                high = loopBounds[high]
            cleanedConfigs = mix(seq[0].body, dep_graph, trackedVars, freeConversions, loop_depth*(high-low), loopNestCount+1)
        else:
            initialConfigs = assign_seq(seq, dep_graph, trackedVars, loop_depth, loopNestCount)
            if debug:
                print("RAW CONFIGS:\n" + "\n".join(str(config) for config in initialConfigs))
            for config in initialConfigs:
                clean_locked_stmts(config)
            if debug:
                print("CLEANED CONFIGS:\n" + "\n".join(str(config) for config in initialConfigs))
            cleanedConfigs = clean_up_with_subsumption(initialConfigs, loop_depth, dep_graph, freeConversions, trackedVars)
            if debug:
                print("CONFIGS AFTER SUBSUMPTION:\n" + "\n".join(str(config) for config in cleanedConfigs))
        rawConfigs.append(cleanedConfigs)
        if debug:
            print()

    finalConfigs = rawConfigs[0]
    rawConfigs.pop(0)
    for nextConfigs in rawConfigs:
        finalConfigs = mergeDriver(finalConfigs, nextConfigs, dep_graph, trackedVars)
        if debug:
            print("SOME SUBSUMPTION HAPPENED HERE")
        finalConfigs = clean_up_with_subsumption(finalConfigs, loop_depth, dep_graph, freeConversions, trackedVars)

    if debug:
        print("MERGED CONFIGS:\n" + "\n".join(str(config) for config in finalConfigs))

    finalConfigs = clean_up_with_subsumption(finalConfigs, loop_depth, dep_graph, freeConversions, trackedVars)
    if debug:
        print("MERGED CONFIGS AFTER SUBSUMPTION:\n" + "\n".join(str(config) for config in finalConfigs))

    return finalConfigs


# return the number of i/o protocols in the given config and the number of conversions
def getInterfaceSize(c: Config) -> tuple[int, int]:
    i = 0
    for _, v in c.inputs.items():
        i += len(v)
    for _, v in c.constants.items():
        i += len(v)
    for _, v in c.plaintexts.items():
        i += len(v)
    for _, v in c.outputs.items():
        i += len(v)
    conv = 0
    for _, _, _, _, _, _, v in c.assignments:
        conv += len(v)
    return i, conv


# run the mixer
def mix_protocols(filename: str, type_env: TypeEnv, body: list[Statement], dep_graph: DepGraph, backend: Any, costType: str, spdzProtocol: str = 'semi', protocolSets: list[set[str]] = [], python_text: str = '' ) -> OrderedConfig:
    global protocols, runningSpdz
    # protocolSets = [{'A', 'B', 'Y'}]
    # protocolSets = [{'Y'}]
    runningSpdz = True if backend == Backend.Backend.MP_SPDZ else False
    targetCostFile = '/../Cost_Tables/'
    if not runningSpdz:
        if protocolSets == None:
            protocolSets = protocolsMotion
        targetCostFile += f'MOTION/{costType}.json'
    elif runningSpdz:
        if protocolSets == None:
            protocolSets = protocolsSPDZ
        targetCostFile += f'MP-SPDZ/{spdzProtocol}/{costType}.json'
    
    if costType not in {'time', 'dataSent', 'commRounds'}:
        raise Exception('Unknown cost type provided to protocol_mixing.py')
    getLoopBounds(filename, python_text)
    getOpCosts(targetCostFile)
    trackedVars, directIOVars = getTrackedVars(type_env, body, dep_graph)
    getBounds(trackedVars - directIOVars, dep_graph, body)
    mixed = []
    for protSet in protocolSets:
        protocols = protSet
        mixed += mix(body, dep_graph, trackedVars, directIOVars, debug=False)
    minCost, minInterface, minConversions = (float("inf"), float("inf"), float("inf"))
    if len(mixed) == 0:
        raise Exception("No valid mix found")
    best: Config
    for c in mixed:
        populateConstantsAndPlaintexts(c, {var for var, t in type_env.items() if
                                              t.visibility and t.visibility.value == 'plaintext'})
        interface, conversions = getInterfaceSize(c)
        if (c.total_cost < minCost or
                (c.total_cost == minCost and (interface < minInterface or
                                              (interface == minInterface and (conversions < minConversions or
                                                                              (conversions == minConversions and str(c) < str(best))))))):
            best = c
            minCost = c.total_cost
            minInterface = interface
            minConversions = conversions
    # populateConstantsAndPlaintexts(best, {var for var, t in type_env.items() if t.visibility and t.visibility.value == 'plaintext'})
    if runningSpdz:
        populateFlags(best)
    print(OrderedConfig(best))
    verifyCosts(best)
    return OrderedConfig(best)
