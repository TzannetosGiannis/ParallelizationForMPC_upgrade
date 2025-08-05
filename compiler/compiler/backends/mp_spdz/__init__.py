from textwrap import indent
from typing import Any, Optional, Union
import dataclasses as dc

from ...util import assert_never
from ...loop_linear_code import (
    Parameter,
    Function,
    Statement,
    Phi,
    Assign,
    For,
    Return,
    Update,
    VectorizedAccess,
    VectorizedUpdate,
    Var,
    BinOp,
    BinOpKind,
    SubscriptIndexBinOp,
    List,
    Tuple,
    Mux,
    UnaryOp,
    UnaryOpKind,
    Subscript,
    SubscriptIndex,
    SubscriptIndexBinOp,
    SubscriptIndexUnaryOp,
    Atom,
    LiftExpr,
    DropDim,
    LoopBound,
)
from ...type_analysis import TypeEnv, Constant, DataType
from ...protocol_mixing import OrderedConfig,Config

UpdatelessAssignRHS = Union[
    Atom, Subscript, BinOp, UnaryOp, List, Tuple, Mux, LiftExpr, DropDim
]


VALID_PROTOCOLS = [
    # "mascot",
    # "lowgear",
    # "highgear",
    # "spdz2k",
    # "tiny",
    # "tinier",
    # "semi-bmr",
    # "cowgear",
    # "chaigear",
    "semi",
    # "hemi",
    # "temi",
    # "soho",
    # "semi2k",
    # "semi-bin",
    # "yao-gc",
    # "yao-bmr",
    # "shamir",
    # "rep3",
    # "ps",
    # "sy",
    # "brain",
    # "ccd",
    # "atlas",
    # "rep4",
    # "dealer",
]

# when we find a convertion inside a for loop we need to have initialized before entering
# thuse we use this list to move the declaration on top of the programme
global_declarations = []

def convert_vector(key,new_key,convertion_from_with_type,default_space=""):
    
    if new_key.endswith("_B"):
        convertion = f"for _random_iter in range(0,len({key})):\n"
        convertion += f"  {default_space}{new_key}[_random_iter] = {convertion_from_with_type}\n" 
        convertion += f"{new_key} = siv32({new_key})"
    else:
        convertion = f"{new_key} = [elem for elem in sint({key})]\n"
    return convertion

def render_var(var: Var, var_mappings: dict[Var, str]) -> str:
    try:
        return var_mappings[var]
    except KeyError:
        return str(var).replace("!", "_")

# safe modify dictionary that keeps variables and allocated protocol
def modify_stmt_details_dict(stmt_details_dict,key,field,value):
    if stmt_details_dict[key][field] is None:
        stmt_details_dict[key][field] = value

# iterate throught the strings associated with the current code line and replace with the correct protocol
# if we have a line in B and the rendered is in A we can find it here and replace it with the B 
def replace_variables_in_protocol(stmt_details_dict,assigned_value,protocol_to_be_replaced):
    for k in stmt_details_dict:
        if k in assigned_value and f"_{k}" not in assigned_value:
            # if the key exists and is not part of other key
            # replace with the representation of the correct protocol_to_be_replaced
            if stmt_details_dict[k][protocol_to_be_replaced] is not None:
                assigned_value = assigned_value.replace(k,stmt_details_dict[k][protocol_to_be_replaced])
    return assigned_value
                    

def render_vec_indices(v: VectorizedAccess, var_mappings: dict[Var, str]) -> str:
    return (
        "["
        + ", ".join(
            [
                "None" if vectorized else render_var(var, var_mappings)
                for vectorized, var in zip(v.vectorized_dims, v.idx_vars)
            ]
        )
        + "]"
    )


def render_array_shape(shape: tuple[LoopBound, ...], simdify: bool = False) -> str:
    return (
        "["
        + ", ".join([render_atom(dim_size, False, dict(), simdify) for dim_size in shape])
        + "]"
    )


def normalize_vectorized_access(v: VectorizedAccess) -> VectorizedAccess:
    array = v.array
    while isinstance(array, VectorizedAccess):
        if all(array.vectorized_dims):
            array = array.array
        else:
            array = Var("(TODO: fix this case)")
    return dc.replace(v, array=array)


def render_vectorized_access(v: VectorizedAccess, var_mappings: dict[Var, str], simdify: bool = False) -> str:
    v = normalize_vectorized_access(v)
    array = render_var(v.array, var_mappings)
    shape = render_array_shape(v.dim_sizes)
    indices = render_vec_indices(v, var_mappings)
    if simdify:
        return f"_v.vectorized_access_simd({array}, {shape}, {indices})"
    else:
        return f"_v.vectorized_access({array}, {shape}, {indices})"
    

def render_vectorized_assign(lhs: VectorizedAccess, rhs: UpdatelessAssignRHS) -> str:
    lhs = normalize_vectorized_access(lhs)
    array = render_var(lhs.array, dict())
    value = render_assign_rhs(rhs, dict())

    if isinstance(rhs, LiftExpr): 
        return f"{array} = {value}"
    shape = render_array_shape(lhs.dim_sizes)
    indices = render_vec_indices(lhs, dict())
    return f"_v.vectorized_assign({array}, {shape}, {indices}, {value})"


def render_constant(c: Constant, make_shared: bool) -> str:
    v = c.value
    if make_shared:
        if isinstance(v, bool):
            return f"_v.sbool({v})"
        elif isinstance(v, int):
            return f"sint({v})"
        else:
            assert_never(v)
    else:
        return str(v)


def render_atom(atom: Atom, make_shared: bool, var_mappings: dict[Var, str], simdify: bool = False) -> str:
    if isinstance(atom, Var):
        return render_var(atom, var_mappings)
    elif isinstance(atom, Constant):
        return render_constant(atom, make_shared)
    elif isinstance(atom, VectorizedAccess):
        return render_vectorized_access(atom, var_mappings, simdify)
    else:
        assert_never(atom)


def render_bin_op(left: str, op: BinOpKind, right: str) -> str:
    if op in (BinOpKind.AND, BinOpKind.BIT_AND):
        return f"{left}.bit_and({right})"
    elif op == BinOpKind.OR:
        return f"OR({left}, {right})"
    elif op == BinOpKind.DIV:
        return f"_v.div({left}, {right})"
    else:
        return f"({left} {op} {right})"


def render_unary_op_kind(op: UnaryOpKind, operand: str) -> str:
    if op is UnaryOpKind.NEGATE:
        return f"-{operand}"
    elif op is UnaryOpKind.NOT:
        return f"{operand}.bit_not()"
    else:
        assert_never(op)


def render_subscript_index(index: SubscriptIndex, var_mappings: dict[Var, str]) -> str:
    if isinstance(index, (Var, Constant)):
        return render_atom(index, False, var_mappings)
    elif isinstance(index, SubscriptIndexBinOp):
        left = render_subscript_index(index.left, var_mappings)
        right = render_subscript_index(index.right, var_mappings)
        return render_bin_op(left, index.operator, right)
    elif isinstance(index, SubscriptIndexUnaryOp):
        operand = render_subscript_index(index.operand, var_mappings)
        expr = render_unary_op_kind(index.operator, operand)
        return f"({expr})"
    else:
        assert_never(index)


def render_lift_expr(lift: LiftExpr) -> str:
    assert not isinstance(lift.expr, (Update, VectorizedUpdate))
    expr = render_assign_rhs(
        lift.expr,
        {var: f"indices[{index}]" for index, (var, _) in enumerate(lift.dims)},
    )
    dim_sizes = ", ".join(render_atom(size, False, dict()) for (_, size) in lift.dims)
    #return f"_v.lift(lambda indices: {expr}, [{dim_sizes}]).get_vector()"
    return f"_v.lift(lambda indices: {expr}, [{dim_sizes}])" 


def render_assign_rhs(
    arhs: UpdatelessAssignRHS,
    var_mappings: dict[Var, str],
    simdify: bool = False
) -> str:
    if isinstance(arhs, BinOp):
        left = render_assign_rhs(arhs.left, var_mappings,simdify=True)
        right = render_assign_rhs(arhs.right, var_mappings,simdify=True)
        return render_bin_op(left, arhs.operator, right)
    elif isinstance(arhs, (Var, Constant, VectorizedAccess)):
        return render_atom(arhs, True, var_mappings, simdify)
    elif isinstance(arhs, List):
        items_list = [render_atom(item, True, var_mappings) for item in arhs.items]
        items = ", ".join(items_list)
        return f"[{items}]"
    elif isinstance(arhs, Tuple):
        items = "".join(
            render_atom(item, True, var_mappings, simdify) + "," for item in arhs.items
        )
        return f"({items})"
    elif isinstance(arhs, Mux):
        condition = render_assign_rhs(arhs.condition, var_mappings)
        true_value = render_assign_rhs(arhs.true_value, var_mappings)
        false_value = render_assign_rhs(arhs.false_value, var_mappings)
        return f"{condition}.if_else({true_value}, {false_value})"
    elif isinstance(arhs, UnaryOp):
        operand = render_assign_rhs(arhs.operand, var_mappings,simdify=True)
        expr = render_unary_op_kind(arhs.operator, operand)
        return f"({expr})"
    elif isinstance(arhs, Subscript):
        array = render_assign_rhs(arhs.array, var_mappings, simdify)
        index = render_subscript_index(arhs.index, var_mappings)
        return f"({array}[{index}])"
    elif isinstance(arhs, LiftExpr):
        return render_lift_expr(arhs)
    elif isinstance(arhs, DropDim):
        if isinstance(arhs.array, VectorizedAccess):
            assert all(arhs.array.vectorized_dims)
            array_var = arhs.array.array
        else:
            array_var = arhs.array
        array = render_var(array_var, var_mappings)
        shape = render_array_shape(arhs.dims)
        return f"_v.drop_dim({array}, {shape})"
    else:
        return assert_never(arhs)


def render_loop_exit_phi(loop: For) -> str:
    return "\n".join(
        render_statement(Assign(lhs=phi.lhs, rhs=phi.rhs_true), None)
        for phi in loop.body
        if isinstance(phi, Phi)
    )


def render_statement(stmt: Statement, containing_loop: Optional[For]) -> str:
    if isinstance(stmt, Phi):
        assert containing_loop
        assert isinstance(containing_loop.bound_low, Constant)
        assert containing_loop.bound_low.value == 0
        loop_counter = render_var(containing_loop.counter, dict())
        phi_assign_false = render_statement(
            Assign(lhs=stmt.lhs, rhs=stmt.rhs_false), None
        )
        phi_assign_true = render_statement(
            Assign(lhs=stmt.lhs, rhs=stmt.rhs_true), None
        )
        return (
            f"# Set ϕ value\n"
            + f"if {loop_counter} == 0:\n"
            + f"    {phi_assign_false}\n"
            + f"else:\n"
            + f"    {phi_assign_true}"
        )
    elif isinstance(stmt, Assign):
        lhs = render_atom(stmt.lhs, False, dict())
        if isinstance(stmt.rhs, Update):
            array = render_var(stmt.rhs.array, dict())
            index = render_subscript_index(stmt.rhs.index, dict())
            value = render_atom(stmt.rhs.value, True, dict())
            return f"{array}[{index}] = {value}; {lhs} = {array}"
        elif isinstance(stmt.rhs, VectorizedUpdate):
            rhs_array_access = VectorizedAccess(
                array=stmt.rhs.array,
                dim_sizes=stmt.rhs.dim_sizes,
                vectorized_dims=stmt.rhs.vectorized_dims,
                idx_vars=stmt.rhs.idx_vars,
            )
            assign1 = render_vectorized_assign(
                lhs=rhs_array_access,
                rhs=stmt.rhs.value,
            )
            assign2 = render_statement(
                Assign(lhs=stmt.lhs, rhs=rhs_array_access), containing_loop
            )
            return f"{assign1}; {assign2}"
        elif isinstance(stmt.lhs, VectorizedAccess):
            # TODO: Cludgy fix for SPDZ vectorized MUX, 2 lines
            if isinstance(stmt.rhs,Mux):
                return render_iterative_mux(stmt.lhs, stmt.rhs)
            return render_vectorized_assign(stmt.lhs, stmt.rhs)
        else:
            rhs = render_assign_rhs(stmt.rhs, dict())
            return f"{lhs} = {rhs}"
    elif isinstance(stmt, For):
        counter = render_var(stmt.counter, dict())
        bound_low = render_atom(stmt.bound_low, False, dict())
        bound_high = render_atom(stmt.bound_high, False, dict())
        body = indent(render_statements(stmt.body, stmt), "    ")
        exit_phi = render_loop_exit_phi(stmt)
        return (
            f"for {counter} in range({bound_low}, {bound_high}):\n"
            + f"{body}\n"
            + "# Loop exit ϕ values\n"
            + exit_phi
        )
    elif isinstance(stmt, Return):
        value = render_var(stmt.value, dict())
        return f"return {value}"
    else:
        assert_never(stmt)

def apply(protocol,someArg,convert=False):
    if someArg.startswith("sint("):
        someArg = someArg.replace("sint(","")[:-1]

    # if the protocol is a dropdim do not convert as you dont know the dims
    if someArg.startswith("_v.drop_dim"):
        return someArg
    if protocol == "B" and someArg.startswith("_v.sbool"):
        if protocol == 'A':
            if "False" in someArg:
                return "sintbit(0)"
            else:
                return "sintbit(1)"
        elif protocol == 'B':
            if "False" in someArg:
                return "sbit(0)"
            else:
                return "sbit(1)"
        else:
            assert_never

    if protocol == "B" and convert == True:
        return f"_v.convertion_check({someArg})"
    if protocol == "B" and convert == False:
        return f"siv32({someArg})"
    elif protocol == "A":
        return f"sint({someArg})"
    else:
        assert_never(protocol)

def render_mixed_statement(stmt: Statement, containing_loop: Optional[For],convertion_dict,stmt_details_dict) -> str:
    
    if isinstance(stmt, Phi):
        # mixer always operates on vectorized but here the type can be also Var which has no array
        # thus we add the check for the pytest to pass
        if not hasattr(stmt.lhs,'array'):
            raise Exception("mixed version requires vectors")

        key = render_var(stmt.lhs.array,dict())
        convertion_to = list(convertion_dict[str(stmt.lhs)]['to'])
        convertion_from = list(convertion_dict[str(stmt.lhs)]['from'])
        if hasattr(stmt.rhs_false, 'array'):
            falsy = render_var(stmt.rhs_false.array,dict())
        else:
            falsy = render_var(stmt.rhs_false,dict())
        if hasattr(stmt.rhs_true, 'array'):
            truthy = render_var(stmt.rhs_true.array,dict())
        else:
            truthy = render_var(stmt.rhs_true,dict())
        
        if len(convertion_to) == 0 and len(convertion_from) == 1:
            modify_stmt_details_dict(stmt_details_dict,key,convertion_from[0],key)
            modify_stmt_details_dict(stmt_details_dict,falsy,convertion_from[0],falsy)
            modify_stmt_details_dict(stmt_details_dict,truthy,convertion_from[0],truthy)
               
        assert containing_loop
        assert isinstance(containing_loop.bound_low, Constant)
        assert containing_loop.bound_low.value == 0
        loop_counter = render_var(containing_loop.counter, dict())
        
        phi_assign_false = render_mixed_statement(
            Assign(lhs=stmt.lhs, rhs=stmt.rhs_false), None,convertion_dict,stmt_details_dict
        )
        phi_assign_true = render_mixed_statement(
            Assign(lhs=stmt.lhs, rhs=stmt.rhs_true), None,convertion_dict,stmt_details_dict
        )
        return (
            f"# Set ϕ value\n"
            + f"if {loop_counter} == 0:\n"
            + f"    {phi_assign_false}\n"
            + f"else:\n"
            + f"    {phi_assign_true}"
        )
    elif isinstance(stmt, Assign):
        lhs = render_atom(stmt.lhs, False, dict())
        if isinstance(stmt.rhs, Update):
            array = render_var(stmt.rhs.array, dict())
            index = render_subscript_index(stmt.rhs.index, dict())
            value = render_atom(stmt.rhs.value, True, dict())
            return f"{array}[{index}] = {value}; {lhs} = {array}"
        elif isinstance(stmt.rhs, VectorizedUpdate):
            rhs_array_access = VectorizedAccess(
                array=stmt.rhs.array,
                dim_sizes=stmt.rhs.dim_sizes,
                vectorized_dims=stmt.rhs.vectorized_dims,
                idx_vars=stmt.rhs.idx_vars,
            )
            assign1 = render_vectorized_assign(
                lhs=rhs_array_access,
                rhs=stmt.rhs.value,
            )
            assign2 = render_mixed_statement(
                Assign(lhs=stmt.lhs, rhs=rhs_array_access), containing_loop,convertion_dict,stmt_details_dict
            )
            # mixer always operates on vectorized but here the type can be also Var whic has no array
            # thus we add the check for the pytest to pass
            if not hasattr(stmt.lhs,'array'):
                raise Exception("mixed version requires vectors")
            
            key = render_var(stmt.lhs.array,dict())
            convertion_tuple = list(convertion_dict[str(stmt.lhs)]["convertion_tuple"])
            convertion =""
            if len(convertion_tuple) == 1:
                # mixer always operates on vectorized but here the type can be also Var which has no array
                # thus we add the check for the pytest to pass
                if isinstance(stmt.lhs,Var):
                    raise Exception("mixed version requires vectors")
                
                convertion_tuple = convertion_tuple[0]
                modify_stmt_details_dict(stmt_details_dict,key,convertion_tuple[0],key)
                new_key = f"{key}_{convertion_tuple[1]}"
                modify_stmt_details_dict(stmt_details_dict,key,convertion_tuple[1],new_key)
                current_declaration = stmt_details_dict[key]['declaration'].replace(key,new_key)
                convertion = ";\n" + current_declaration + "\n"
                convertion += convert_vector(key,new_key,apply(convertion_tuple[1],f'{key}[_random_iter]',True))
            return f"{assign1}; {assign2}{convertion}"
        elif isinstance(stmt.lhs, VectorizedAccess):
            # TODO: Cludgy fix for SPDZ vectorized MUX, 2 lines
            if isinstance(stmt.rhs,Mux):
                initial_mux = render_iterative_mux(stmt.lhs, stmt.rhs)
                stmt_key = render_var(stmt.lhs.array,dict())
                convertion_to = list(convertion_dict[str(stmt.lhs)]['to'])
                convertion_from = list(convertion_dict[str(stmt.lhs)]['from'])
                if len(convertion_to) == 0 and len(convertion_from) == 1:
                    modify_stmt_details_dict(stmt_details_dict,stmt_key,convertion_from[0],stmt_key)
                    initial_mux = replace_variables_in_protocol(stmt_details_dict,initial_mux,convertion_from[0])
                    return initial_mux
                elif len(convertion_to) == 1 and len(convertion_from) == 1:
                    modify_stmt_details_dict(stmt_details_dict,stmt_key,convertion_from[0],stmt_key)
                    initial_mux = replace_variables_in_protocol(stmt_details_dict,initial_mux,convertion_from[0])
                    new_key = f"{stmt_key}_{convertion_to[0]}"
                    convertor = 'sint' if convertion_to[0] == 'A' else "siv32"
                    convertion_key = render_var(stmt.lhs.idx_vars[0],dict())
                    if convertion_key == 'i_1':
                        if convertor == 'sint':
                            converted_mux = f"{new_key} = [elem for elem in {convertor}({stmt_key})]"     
                        else:
                            converted_mux = f"{new_key} = [{convertor}({stmt_key}[_random_iter]) for _random_iter in range(len({stmt_key}))]" 
                    else:
                        converted_mux = f"{new_key}[{convertion_key}] = {convertor}({stmt_key}[{convertion_key}])" 

                    modify_stmt_details_dict(stmt_details_dict,stmt_key,convertion_to[0],new_key)
                    current_declaration = stmt_details_dict[stmt_key]['declaration'].replace(stmt_key,new_key)
                    global_declarations.append(current_declaration)
                    return f"{initial_mux};{converted_mux}"
            
            key = render_var(stmt.lhs.array,dict())
            convertion_to = list(convertion_dict[str(stmt.lhs)]['to'])
            # the protocol to be converted is irelevant
            # we want it as the from case
            # P _
            if len(convertion_to) == 0:
                initial_access = render_vectorized_assign(stmt.lhs, stmt.rhs)
                stmt_details_dict[key][convertion_dict[str(stmt.lhs)]['from']] = key
                
                # convert
                if convertion_dict[str(stmt.lhs)]['from'] == 'B':
                    initial_access = initial_access.replace('sint','siv32')

                initial_access = replace_variables_in_protocol(stmt_details_dict,initial_access,convertion_dict[str(stmt.lhs)]['from'])
                return initial_access
            
            # already in the correct protocol
            elif len(convertion_to) == 1 and len(convertion_dict[str(stmt.lhs)]['convertion_tuple']) == 0:
                stmt_details_dict[key][convertion_to[0]] = key
                assigned_value = render_vectorized_assign(stmt.lhs, stmt.rhs)
                assigned_value = replace_variables_in_protocol(stmt_details_dict,assigned_value,convertion_to[0])
                if convertion_to[0] == 'B':
                    assigned_value = assigned_value.replace("sint","siv32")   
                return assigned_value
            else:
                # _ {'A','B'} _
                # exactly one explicit convertion identified
                if (len(convertion_dict[str(stmt.lhs)]['convertion_tuple'])  == 1):
                    basic_stmt = render_vectorized_assign(stmt.lhs, stmt.rhs)
                    modify_stmt_details_dict(stmt_details_dict,key,convertion_dict[str(stmt.lhs)]['convertion_tuple'][0][0],key)
                    basic_stmt = replace_variables_in_protocol(stmt_details_dict,basic_stmt,convertion_dict[str(stmt.lhs)]['convertion_tuple'][0][0])
                    ordering = convertion_dict[str(stmt.lhs)]['convertion_tuple'][0]
                    if ordering[0] == 'B':
                        basic_stmt = basic_stmt.replace('sint','sb32')
                    modify_stmt_details_dict(stmt_details_dict,key,ordering[0],key)
                    
                    new_key = f"{key}_{ordering[1]}"
                    current_declaration = stmt_details_dict[key]['declaration'].replace(key,new_key)
                    global_declarations.append(current_declaration)
                    render_key = render_var(stmt.lhs.idx_vars[0],dict())
                    
                    if render_key == 'i_1':
                        convertion = basic_stmt +"\n" 
                        convertion += convert_vector(key,new_key,apply(ordering[1],f'{key}[_random_iter]',True))
                    else:
                        convertion = basic_stmt +";" 
                        convertion += f"{new_key}[{render_key}] = {apply(ordering[1],f'{key}[{render_key}]',True)}" 

                    # store the variable to the stmt details dict to use it when using protocol 2 for the lhs (1 -> 2)
                    modify_stmt_details_dict(stmt_details_dict,key,ordering[1],new_key)
                    
                    
                else:
                    # example _ {A,B} _
                    basic_stmt = render_vectorized_assign(stmt.lhs, stmt.rhs)
                    key = render_var(stmt.lhs.array,dict())
                    
                    # identify if it is a lift
                    if isinstance(stmt.rhs,LiftExpr):
                        assert not isinstance(stmt.rhs.expr,Var)
                        assert not isinstance(stmt.rhs.expr,Constant)
                        assert not isinstance(stmt.rhs.expr,BinOp)
                        assert not isinstance(stmt.rhs.expr,UnaryOp)
                        assert not isinstance(stmt.rhs.expr,Tuple)
                        assert not isinstance(stmt.rhs.expr,List)
                        assert not isinstance(stmt.rhs.expr,Mux)
                        assert not isinstance(stmt.rhs.expr,LiftExpr)
                        lift_key = render_var(stmt.rhs.expr.array,dict())
                        # identify either A or B
                        # store both the actual and converted
                        if stmt_details_dict[lift_key]['A'] == lift_key:
                            modify_stmt_details_dict(stmt_details_dict,key,'A',key)
                            new_key = f"{key}_B"
                            modify_stmt_details_dict(stmt_details_dict,key,'B',new_key)
                            stmt_B = f";{new_key} = {basic_stmt.split(' = ')[1].replace(lift_key,f'{lift_key}_B')}"
                            return f"{basic_stmt}{stmt_B}"
                        else:
                            modify_stmt_details_dict(stmt_details_dict,key,'B',key)
                            new_key = f"{key}_A"
                            modify_stmt_details_dict(stmt_details_dict,key,'A',new_key)
                            stmt_A = f";{new_key} = {basic_stmt.split(' = ')[1].replace(lift_key,f'{lift_key}_A')}"
                            return f"{basic_stmt}{stmt_A}"
                    
                return convertion
        else:
            # simple not vectorized assign is here
            rhs = render_assign_rhs(stmt.rhs, dict()) 
            if str(stmt.lhs) not in convertion_dict:
                return f"{lhs} = {rhs}"
            
            # initialize the dict
            stmt_details_dict[render_var(stmt.lhs,dict())] = {
                'A': None,
                'B': None
            }

            # Pr _ _
            # means that we need it in Pr
            if len(list(convertion_dict[str(stmt.lhs)]['to'])) == 0:
                stmt_from = list(convertion_dict[str(stmt.lhs)]['from'])[0]
                
                # store the key for future reference in protocol Pr
                modify_stmt_details_dict(stmt_details_dict,render_var(stmt.lhs,dict()),stmt_from,render_var(stmt.lhs,dict()))
                mixed_stmt = f"{lhs} = {rhs}"
                mixed_stmt = replace_variables_in_protocol(stmt_details_dict,mixed_stmt,stmt_from)
                # render atom induces the basic types 
                # so we need to convert if the type is B
                if stmt_from == 'B' and "sint" in mixed_stmt:
                    mixed_stmt = mixed_stmt.replace('sint',"siv32")
                return mixed_stmt
            elif len(list(convertion_dict[str(stmt.lhs)]['to'])) == 1:
                # we want cases Pr1 Pr _
                to = list(convertion_dict[str(stmt.lhs)]['to'])[0]
                modify_stmt_details_dict(stmt_details_dict,render_var(stmt.lhs,dict()),to,render_var(stmt.lhs,dict()))
                # Pr1 = _
                if convertion_dict[str(stmt.lhs)]['from'] == '_':
                    return f"{lhs} = {apply(to,rhs)}"
                else:
                    # now we can also have it for free to the other share type
                    other = convertion_dict[str(stmt.lhs)]['from']
                    new_key = f"{render_var(stmt.lhs,dict())}_{other}"
                    modify_stmt_details_dict(stmt_details_dict,render_var(stmt.lhs,dict()),other,new_key)
                    # keep both Pr1 Pr
                    conv = f"{lhs} = {apply(to,rhs)}; {new_key}  = {apply(other,lhs)}"
                    return conv
            else:
                # find the explicit convertion
                basic_stmt = f"{lhs} = {rhs}"
                if convertion_dict[str(stmt.lhs)]['from'] == '_' and len(convertion_dict[str(stmt.lhs)]['to']) == 2 and len(convertion_dict[str(stmt.lhs)]["convertion_tuple"]) == 0:
                    if isinstance(stmt.rhs,DropDim):
                        basic_stmt_A = replace_variables_in_protocol(stmt_details_dict,basic_stmt,'A')
                        basic_stmt_B = replace_variables_in_protocol(stmt_details_dict,basic_stmt,'B')
                        key = render_var(stmt.lhs,dict())
                        modify_stmt_details_dict(stmt_details_dict,key,'A',key)
                        modify_stmt_details_dict(stmt_details_dict,key,'B',f"{key}_B")
                        basic_stmt_B = basic_stmt_B.replace(key,f"{key}_B")
                        return f"{basic_stmt_A};{basic_stmt_B}"
                      
                key = render_var(stmt.lhs,dict())
                ordering = convertion_dict[str(stmt.lhs)]['convertion_tuple'][0]
                modify_stmt_details_dict(stmt_details_dict,key,ordering[0], key)
                new_key = f"{key}_{ordering[1]}"
                
                # initialize the new variable
                if 'declaration' in stmt_details_dict[key]:
                    # this means that we are processing a vector
                    # for dimsizes to exist it shall be an array stmt.lhs
                    if isinstance(stmt.lhs,Var):
                        raise Exception('No Var can have declaration statement , unless is a vector')
                    current_declaration = stmt_details_dict[key]['declaration'].replace(key,new_key)
                    convertion = basic_stmt +"\n" + current_declaration + "\n"
                    convertion += convert_vector(key,new_key,apply(ordering[1],f'{key}[_random_iter]',True))
                else:
                    # no vector just Var
                    convertion = basic_stmt + "\n"
                    convertion += f"{new_key} = {apply(ordering[1],f'{key}',True)}"

                # store the variable to the stmt details dict to use it when using protocol 2 for the lhs (1 -> 2)
                modify_stmt_details_dict(stmt_details_dict,key,ordering[1], new_key)
                return convertion
                
    elif isinstance(stmt, For):
        counter = render_var(stmt.counter, dict())
        bound_low = render_atom(stmt.bound_low, False, dict())
        bound_high = render_atom(stmt.bound_high, False, dict())
        body = indent(render_mixed_statements(stmt.body, stmt,convertion_dict,stmt_details_dict), "    ")
        exit_phi = render_loop_exit_phi(stmt)
        return (
            f"for {counter} in range({bound_low}, {bound_high}):\n"
            + f"{body}\n"
            + "# Loop exit ϕ values\n"
            + exit_phi
        )
    elif isinstance(stmt, Return):
        value = render_var(stmt.value, dict())
        return f"return {value}"
    else:
        assert_never(stmt)


def render_mixed_statements(stmts: list[Statement], containing_loop: Optional[For],convertion_dict,stmt_details_dict) -> str:
    result_stmts = []
    for stmt in stmts:
        mixed_stmt = render_mixed_statement(stmt, containing_loop,convertion_dict,stmt_details_dict)
        if hasattr(stmt,'lhs') and str(stmt.lhs) in convertion_dict:
            pass
        result_stmts.append(mixed_stmt)
    return "\n".join(result_stmts)


def render_statements(stmts: list[Statement], containing_loop: Optional[For]) -> str:
    return "\n".join(render_statement(stmt, containing_loop) for stmt in stmts)

#TODO: Check. Cludgy fix for SPDZ vectorized MUX (in binary)
def render_iterative_mux(lhs: VectorizedAccess, rhs: Mux):
    assert isinstance(rhs,Mux), f"Expected Mux rhs, found {type(rhs)}"
    lhs = normalize_vectorized_access(lhs)
    dest_array = render_var(lhs.array, dict())
    shape = render_array_shape(lhs.dim_sizes)
    indices = render_vec_indices(lhs, dict())
    # TODO: We need an assertions to make sure Vectorized accesses use same dimenstions and indices
    if isinstance(rhs.condition,VectorizedAccess):
       cond = render_var(normalize_vectorized_access(rhs.condition).array, dict())
    else:
       cond = render_assign_rhs(rhs.condition, dict())
    if isinstance(rhs.true_value,VectorizedAccess):   
       true_value = render_var(normalize_vectorized_access(rhs.true_value).array, dict())
    else: # rendering a constant or a variable
       true_value = render_assign_rhs(rhs.true_value, dict())
    if isinstance(rhs.false_value,VectorizedAccess):   
       false_value = render_var(normalize_vectorized_access(rhs.false_value).array, dict())
    else:
       false_value = render_assign_rhs(rhs.false_value, dict())
    return f"_v.iterative_mux({dest_array},{cond},{true_value},{false_value},{shape},{indices})"

def render_shared_array_decl(
    var: Var, datatype: Optional[DataType], dim_sizes: list[LoopBound]
) -> str:
    var_rendered = render_var(var, dict())
    size_rendered = " * ".join(
        [render_atom(dim_size, False, dict()) for dim_size in dim_sizes]
    )

    return f"{var_rendered} = [None] * ({size_rendered})"


def render_shared_array_decls(type_env: TypeEnv) -> str:
    return "\n".join(
        [
            render_shared_array_decl(var, var_type.datatype, var_type.dim_sizes)
            for var, var_type in sorted(type_env.items(), key=lambda x: str(x[0]))
            if var_type.dim_sizes is not None and var_type.dim_sizes != []
        ]
    )


def render_mixed_function(func: Function, type_env: TypeEnv, ran_vectorization: bool,mixed_config) -> str:
    
    # clear the list that holds declarations inside for loops
    global_declarations.clear()
    # will store all the stmt convertions
    convertion_dict = {}
    # will keep track of all the variables and the correspoding protocols ( A or B) that they are available
    stmt_details_dict = {}
    
    # identify the convertions in the mixed config file and store them in dict
    for i in range(len(mixed_config.assignments)) :
        convertion_dict[str(mixed_config.assignments[i][0].lhs)] = {
            "from":mixed_config.assignments[i][1],
            "to":mixed_config.assignments[i][2],
            "convertion_tuple":mixed_config.assignments[i][-1]
        }
    
    # identify all the vectorized versions
    for var, var_type in sorted(type_env.items(), key=lambda x: str(x[0])):
        if var_type.dim_sizes is not None and var_type.dim_sizes != []:
            stmt_details_dict[render_var(var,dict())] = {
                    "declaration":render_shared_array_decl(var, var_type.datatype, var_type.dim_sizes),
                    "A":None,
                    "B":None,
        }
    
    # initialize the convertions that will be made available in both protocols
    # example convertion tuple (B-> A) means that the result will be available directly on B
    # and then a convertion will be applied and stored on A
    for co in convertion_dict:
        key = str(co).replace("!", "_").split("{")[0]
        convertion_tuple = convertion_dict[co]['convertion_tuple']
        if len(convertion_tuple) > 0:
            key_from = key
            key_to = f"{key}_{convertion_tuple[0][1]}"
            modify_stmt_details_dict(stmt_details_dict,key,convertion_tuple[0][1], key_to)
            modify_stmt_details_dict(stmt_details_dict,key,convertion_tuple[0][0], key_from)
    
    # handle plaintext from mixed config
    plaintext_dict = mixed_config.plaintexts
    plaintext_convertions = ""

    func_args = {}
    for _random_iter in range(len(func.parameters)):
        func_args[render_var(func.parameters[_random_iter].var,dict())] = str(func.parameters[_random_iter])

    performed_plaintext_convertion = False

    input_convertions = ""
    # Handle multiple inputs in the protocol. In inputs we assume that if they are in {'A','B'} they have allready been passed as 'A'
    for inp in mixed_config.inputs:
        if len(mixed_config.inputs[inp]) == 2:
            small_key = render_var(inp,dict())
            new_key = f"{small_key}_B"
            stmt_details_dict[small_key] = {
                        "declaration":None,
                        "A":small_key,
                        "B":None,
            }
            
            input_convertions += f"{new_key} = [ siv32(elem) for elem in {small_key}] if isinstance({small_key}, list) else siv32({small_key})\n    "
            modify_stmt_details_dict(stmt_details_dict,small_key,'B' , new_key)
  
    # handle variables that are passed as plaintext inside the programme and the mixer requests them to have a protocol assigned
    for plain in plaintext_dict:
        small_key = render_var(plain,dict())
        new_key_plaintext = None
        
        if len(list(plaintext_dict[plain])) == 1 and list(plaintext_dict[plain])[0] == 'B':
            
            # simple types means simple convertion based on type
            if "list" not in func_args[small_key]:
                plaintext_convertions += f"{small_key}_B = sb32({small_key})\n"
                new_key_plaintext = f"{small_key}_B"
                stmt_details_dict[small_key] = {
                    "A":small_key,
                    "B":new_key_plaintext,
                }
                performed_plaintext_convertion = True
            else:
                # know we need to convert it as a list (iterate through the elements)
                # no vectorized convetion exists
                plaintext_convertions += f"{'' if performed_plaintext_convertion == False else '    '}"
                plaintext_convertions += convert_vector(small_key,small_key,f"sb32({small_key}[_random_iter])","     ")
                
                stmt_details_dict[small_key] = {
                    "A":None,
                    "B":small_key,
                }

                performed_plaintext_convertion = True
                
            plaintext_convertions +="\n"
        elif len(list(plaintext_dict[plain])) == 1 and list(plaintext_dict[plain])[0] == 'A':
            stmt_details_dict[small_key] = {
                    "A":small_key,
                    "B":None,
            }
            
    params = ", ".join(render_var(param.var, dict()) for param in func.parameters)
    shared_array_decls = indent(render_shared_array_decls(type_env), "    ")
    func_body = indent(render_mixed_statements(func.body, None,convertion_dict,stmt_details_dict), "    ")
    
    # We have validated that no cost is increased by this
    mix_activation = "program.options.binary = 32\n"
    # retrieve the programm flags for X or Y from mixer
    if 'Y' in mixed_config.flags:
        mix_activation += 'program.use_edabit(True)\n'
    if 'X' in mixed_config.flags:
        mix_activation += 'program.use_dabit = True\n'

    global_declarations_str = "\n    ".join(global_declarations)
    return (
        f"{mix_activation}"
        f"def {func.name}({params}):\n"
        + "    # Convertion functions\n"
        + "    siv32 = sbitintvec.get_type(32)\n"
        + "    sb32 = sbits.get_type(32)\n"
        + f"    {plaintext_convertions}\n"
        + f"    {input_convertions}\n"
        + "    # Shared array declarations\n"
        + f"{shared_array_decls}\n"
        + "    # Shared array convertion declarations\n"
        + f"    {global_declarations_str}\n"
        + "    # Function body\n"
        + f"{func_body}"
    )

def render_function(func: Function, type_env: TypeEnv, ran_vectorization: bool) -> str:
    params = ", ".join(render_var(param.var, dict()) for param in func.parameters)
    shared_array_decls = indent(render_shared_array_decls(type_env), "    ")
    func_body = indent(render_statements(func.body, None), "    ")
    return (
        f"def {func.name}({params}):\n"
        + "    # Shared array declarations\n"
        + f"{shared_array_decls}\n"
        + "    # Function body\n"
        + f"{func_body}"
    )


def render_load_args(func: Function,mixing: bool = False,mixed_config:OrderedConfig = OrderedConfig(Config())) -> str:
    ret = []
    program_args_index = 1
    for arg in func.parameters:
        var = render_var(arg.var, dict())
        party = arg.party_idx or 0
        dims = arg.var_type.dims
        actual_type = 'sint'
        if mixing:
            for mixed_input in mixed_config.inputs:
                if render_var(mixed_input,dict()) == var:
                    ty = list(mixed_config.inputs[mixed_input])
                    # if it is in multiple protocols pass it in A and convert inside the function
                    if len(ty) !=1:
                        protocol = 'A'
                    else:
                        protocol = ty[0]
                    if protocol == 'B':
                        actual_type = 'sb32'
        if dims == 0:
            if arg.var_type.is_plaintext():
                ret.append(f"{var} = int(program.args[{program_args_index}])")
                #program_args_index += 1
            else:
                ret.append(f"{var} = {actual_type}()")
                ret.append(f"{var}.input_from({party})")
            program_args_index += 1
        else:
            assert dims == 1
            if arg.var_type.is_plaintext():
                ret.append(f"{var} = int(program.args[{program_args_index}])")
            else:
                ret.append(f"{var} = {actual_type}.Array(int(program.args[{program_args_index}]))")
                ret.append(f"{var}.input_from({party})")
            program_args_index += 1
    return "\n".join(ret)


def render_default_arg(arg: Parameter,mixing: bool = False,mixed_config:OrderedConfig = OrderedConfig(Config())) -> str:
    var = render_var(arg.var, dict())
    actual_type = 'sint'
    protocol = 'A'
    if mixing:
        for mixed_input in mixed_config.inputs:
            if render_var(mixed_input,dict()) == var:
                ty = list(mixed_config.inputs[mixed_input])
                # if more than one protocol , consider it in A and then convert inside the programme
                if len(ty) !=1:
                    protocol = 'A'
                else:
                    protocol = ty[0]
                if protocol == 'B':
                    actual_type = 'sb32'
                    break
    dims = arg.var_type.dims
    value = arg.default_values[0]
    if dims == 0:
        if arg.var_type.is_plaintext():
            return f"{var} = {value}"
        else:
            return f"{var} = {actual_type}({value})"
    else:
        assert dims == 1
        input_vec = f"{var} = {value}\n"
        lift_oper =  f"{var} = _v.lift(lambda indices: {var}[indices[0]], [len({var})])\n"
        if protocol == 'B':
            input_vec += f"for _random_iter in range(0,len({var})):\n"
            input_vec += f"     {var}[_random_iter] = sb32({var}[_random_iter])\n"
        input_vec += lift_oper
        return input_vec


def render_default_args(func: Function,mixing: bool = False,mixed_config:OrderedConfig = OrderedConfig(Config())) -> str:
    return "\n".join(render_default_arg(arg,mixing,mixed_config) for arg in func.parameters)


def render_set_args(func: Function,mixing: bool = False,mixed_config:OrderedConfig = OrderedConfig(Config())) -> str:

    has_defaults = all(len(arg.default_values) >= 1 for arg in func.parameters)
    
    if has_defaults:
        return "\n".join(
            [
                "try:",
                "    # Load input arguments",
                f"{'' if mixing == False else '    siv32 = sbitint.get_type(32);sb32 = sbits.get_type(32)'}",
                indent(render_load_args(func,mixing,mixed_config), "    "),
                "except:",
                "    # Use default arguments",
                f"{'' if mixing == False else '    siv32 = sbitint.get_type(32);sb32 = sbits.get_type(32)'}",
                indent(render_default_args(func,mixing,mixed_config), "    "),
            ]
        )
    else:
        return render_load_args(func)


def render_args(func: Function) -> str:
    return ", ".join(render_var(arg.var, dict()) for arg in func.parameters)


def render_application(
    func: Function, type_env: TypeEnv, params: dict[str, Any], ran_vectorization: bool,mixing=False,mixed_config:OrderedConfig = OrderedConfig(Config())
) -> None:

    if mixing == True:
        func_rendered = render_mixed_function(func, type_env, ran_vectorization,mixed_config)
    else:
        func_rendered = render_function(func, type_env, ran_vectorization)
    set_args = render_set_args(func,mixing,mixed_config)
    args = render_args(func)
    app_rendered = (
        "from vectorization_library import VectorizationLibrary\n"
        + "_v = VectorizationLibrary(globals())\n"
        + "#from Compiler.util import OR\n"
        + "# The reason we comment this out is that OR uses as implementation a + b - a.bit_and(b) which doesnt allow parrallel binary computation on sbitvec([sbit])\n"
        + "def OR(a,b):\n    or_value  = ((a.bit_not()).bit_and(b.bit_not())).bit_not()\n    if type(or_value) == sint:\n        or_value = sintbit(or_value)\n    return or_value"
        + "\n"
        + "\n"
        + f"{func_rendered}\n"
        + "\n"
        + "\n"
        + "# Set arguments\n"
        + f"{set_args}\n"
        + "\n"
        + f"_v.mpc_print_result({func.name}({args}))"
    )
    with open(params["out_dir"], "w") as file:
        file.write(app_rendered + "\n")
