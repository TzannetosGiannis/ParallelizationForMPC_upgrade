# [TODO] identify what will happen if the mixer requires a variable in multiple protocols , example if we had a convertion tuple (A-->B,A-->Y)

from copy import copy
import dataclasses as dc
from textwrap import indent
from typing import Optional, Union, Dict, Any

from ...ast_shared import (
    BinOpKind,
    Constant,
    DataType,
    Parameter,
    Subscript,
    SubscriptIndex,
    SubscriptIndexBinOp,
    SubscriptIndexUnaryOp,
    TypeEnv,
    UnaryOpKind,
    Var,
    VarType,
    VarVisibility,
    VectorizedAccess,
)
from ...tac_cfg import (
    Assign,
    AssignRHS,
    BinOp,
    List,
    Mux,
    Tuple,
    UnaryOp,
    Update,
    VectorizedUpdate,
    LiftExpr,
    DropDim,
)
from ...util import assert_never
from ...loop_linear_code import For, Phi, Return
from ...type_analysis import type_assign_expr, PLAINTEXT_INT


@dc.dataclass(frozen=True)
class RenderContext:
    type_env: TypeEnv
    plaintext: bool = False
    as_motion_input: bool = False
    int_type: str = "std::uint32_t"
    var_mappings: dict[Var, str] = dc.field(default_factory=dict)
    enclosing_loops: list[For] = dc.field(default_factory=list)


# safe modify dictionary that keeps variables and allocated protocol
def modify_stmt_details_dict(stmt_details_dict,key,field,value):
    if stmt_details_dict[key][field] is None:
        stmt_details_dict[key][field] = value

    assert value.startswith(key)

def render_type(var_type: VarType, plaintext: Optional[bool] = None) -> str:
    assert var_type.visibility is not None
    assert var_type.datatype is not None
    assert var_type.unvectorized_dims is not None

    if var_type.datatype == DataType.TUPLE:
        return (
            "std::tuple<"
            + ", ".join(render_type(t, plaintext) for t in var_type.tuple_types)
            + ">"
        )

    str_rep = ""
    if var_type.unvectorized_dims > 0:
        str_rep += "std::vector<"

    str_rep += render_datatype(
        var_type.datatype,
        plaintext=plaintext
        if plaintext is not None
        else var_type.visibility == VarVisibility.PLAINTEXT,
    )

    if var_type.unvectorized_dims > 0:
        str_rep += ">"

    return str_rep


def render_datatype(datatype: DataType, plaintext: bool) -> str:
    if datatype == DataType.INT:
        if plaintext:
            return "std::uint32_t"
        else:
            return "encrypto::motion::SecureUnsignedInteger"

    elif datatype == DataType.BOOL:
        if plaintext:
            return "bool"
        else:
            return "encrypto::motion::ShareWrapper"

    raise NotImplementedError(f"Unsupported datatype: {datatype}")


def render_param(param: Parameter, type_env: TypeEnv) -> str:
    plaintext = param.var_type.is_plaintext()

    return (
        render_type(param.var_type, plaintext)
        + " "
        + render_expr(param.var, RenderContext(type_env, plaintext=plaintext))
    )


# Collect counter uses for conversion to shared variables
def collect_counter_uses(expr: AssignRHS, enclosing_loops: list[For]) -> list[Var]:
    if isinstance(expr, Var):
        if any(loop.counter == expr for loop in enclosing_loops):
            return [expr]
        else:
            return []
    elif isinstance(expr, UnaryOp):
        return collect_counter_uses(expr.operand, enclosing_loops)
    elif isinstance(expr, BinOp):
        return collect_counter_uses(expr.left, enclosing_loops) + collect_counter_uses(
            expr.right, enclosing_loops
        )
    elif isinstance(expr, (List, Tuple)):
        return [
            var
            for elem in expr.items
            for var in collect_counter_uses(elem, enclosing_loops)
        ]
    elif isinstance(expr, (Update, VectorizedUpdate)):
        return collect_counter_uses(expr.value, enclosing_loops)
    elif isinstance(expr, Mux):
        return (
            collect_counter_uses(expr.condition, enclosing_loops)
            + collect_counter_uses(expr.true_value, enclosing_loops)
            + collect_counter_uses(expr.false_value, enclosing_loops)
        )
    elif isinstance(expr, LiftExpr):
        return collect_counter_uses(expr.expr, enclosing_loops)
    # The below expressions never require conversion to plaintext
    elif isinstance(expr, (Constant, Subscript, VectorizedAccess, DropDim)):
        return []
    else:
        assert_never(expr)


def render_stmt(
    stmt: Union[Assign, For, Return],
    type_env: TypeEnv,
    ran_vectorization: bool,
    enclosing_loops=[],
) -> str:
    if isinstance(stmt, Assign):
        # Convert any plaintext assignments
        vars_needing_conversions = collect_counter_uses(stmt.rhs, enclosing_loops)
        plaintext_conversions = "\n".join(
            render_expr(
                var,
                RenderContext(
                    type_env, plaintext=False, enclosing_loops=enclosing_loops
                ),
            )
            + " = party->In<Protocol>("
            + render_expr(
                var,
                RenderContext(
                    type_env,
                    as_motion_input=True,
                    enclosing_loops=enclosing_loops,
                ),
            )
            + ", 0);"
            for var in vars_needing_conversions
        )

        if plaintext_conversions:
            plaintext_conversions += "\n"

        # If we're assigning to a vectorized value, use a specialized function for this.
        if isinstance(stmt.lhs, VectorizedAccess):
            ctx = RenderContext(
                type_env, plaintext=False, enclosing_loops=enclosing_loops
            )
            val_expr = render_expr(stmt.rhs, ctx)

            # If this isn't a true vectorized access, just subscript normally
            if all(not vectorized for vectorized in stmt.lhs.vectorized_dims):
                lhs = render_expr(stmt.lhs, ctx)
                return plaintext_conversions + f"{lhs} = {val_expr};"

            dim_sizes = (
                "{"
                + ", ".join(
                    render_expr(loop_bound, dc.replace(ctx, plaintext=True))
                    for loop_bound in stmt.lhs.dim_sizes
                )
                + "}"
            )
            vectorized_dims = (
                "{"
                + ", ".join(
                    str(vectorized).lower() for vectorized in stmt.lhs.vectorized_dims
                )
                + "}"
            )
            idxs = (
                "{"
                + ", ".join(
                    render_expr(var, dc.replace(ctx, plaintext=True))
                    for var, vectorized in zip(
                        stmt.lhs.idx_vars, stmt.lhs.vectorized_dims
                    )
                    if not vectorized
                )
                + "}"
            )

            return (
                plaintext_conversions
                + f"vectorized_assign({render_expr(stmt.lhs.array, ctx)}, {dim_sizes}, {vectorized_dims}, {idxs}, {val_expr});"
            )

        if isinstance(stmt.rhs, Update):
            shared_assignment = (
                (
                    render_expr(
                        stmt.rhs,
                        RenderContext(
                            type_env, plaintext=False, enclosing_loops=enclosing_loops
                        ),
                    )
                    + ";\n"
                )
                + render_expr(
                    stmt.lhs,
                    RenderContext(
                        type_env, plaintext=False, enclosing_loops=enclosing_loops
                    ),
                )
                + " = "
                + render_expr(
                    stmt.rhs.array,
                    RenderContext(
                        type_env, plaintext=False, enclosing_loops=enclosing_loops
                    ),
                )
                + ";"
            )
            plaintext_assignment = (
                (
                    render_expr(
                        stmt.rhs,
                        RenderContext(
                            type_env, plaintext=True, enclosing_loops=enclosing_loops
                        ),
                    )
                    + ";\n"
                )
                + render_expr(
                    stmt.lhs,
                    RenderContext(
                        type_env, plaintext=True, enclosing_loops=enclosing_loops
                    ),
                )
                + " = "
                + render_expr(
                    stmt.rhs.array,
                    RenderContext(
                        type_env, plaintext=True, enclosing_loops=enclosing_loops
                    ),
                )
                + ";"
            )

        else:
            shared_assignment = (
                render_expr(
                    stmt.lhs,
                    RenderContext(
                        type_env, plaintext=False, enclosing_loops=enclosing_loops
                    ),
                )
                + " = "
                + render_expr(
                    stmt.rhs,
                    RenderContext(
                        type_env, plaintext=False, enclosing_loops=enclosing_loops
                    ),
                )
                + ";"
            )
            plaintext_assignment = (
                render_expr(
                    stmt.lhs,
                    RenderContext(
                        type_env, plaintext=True, enclosing_loops=enclosing_loops
                    ),
                )
                + " = "
                + render_expr(
                    stmt.rhs,
                    RenderContext(
                        type_env, plaintext=True, enclosing_loops=enclosing_loops
                    ),
                )
                + ";"
            )

        if (
            type_env[stmt.lhs].is_shared()
            or type_env[stmt.lhs].datatype == DataType.TUPLE
        ):
            return plaintext_conversions + shared_assignment
        else:
            return (
                plaintext_conversions + shared_assignment + "\n" + plaintext_assignment
            )

    elif isinstance(stmt, For):
        ctr_initializer = (
            "// Initialize loop counter\n"
            + render_expr(
                stmt.counter,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + " = "
            + render_expr(
                stmt.bound_low,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + ";"
        )

        phi_initializations = "// Initialize phi values\n" + "\n".join(
            render_stmt(Assign(phi.lhs, phi.rhs_false), type_env, ran_vectorization)
            for phi in stmt.body
            if isinstance(phi, Phi)
        )

        header = (
            "for (; "
            + render_expr(
                stmt.counter,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + " < "
            + render_expr(
                stmt.bound_high,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + "; "
            + render_expr(
                stmt.counter,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + "++) {"
        )

        phi_assignments = "\n".join(
            render_stmt(Assign(phi.lhs, phi.rhs_true), type_env, ran_vectorization)
            for phi in stmt.body
            if isinstance(phi, Phi)
        )

        phi_updates = (
            "// Update phi values\n"
            + "if ("
            + render_expr(
                stmt.counter,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + " != "
            + render_expr(
                stmt.bound_low,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + ") {\n"
            + indent(
                phi_assignments,
                "    ",
            )
            + "\n}\n"
        )

        body = (
            "\n".join(
                render_stmt(
                    substmt, type_env, ran_vectorization, enclosing_loops + [stmt]
                )
                for substmt in stmt.body
                if not isinstance(substmt, Phi)
            )
            + "\n"
        )

        if not ran_vectorization:
            phi_finalizations = "// Assign final phi values\n" + phi_assignments + "\n"
        else:
            phi_finalizations = ""

        return (
            "\n"
            + ctr_initializer
            + "\n"
            + phi_initializations
            + "\n"
            + header
            + "\n"
            + indent(phi_updates, "    ")
            + "\n"
            + indent(body, "    ")
            + "\n}\n"
            + phi_finalizations
        )

    elif isinstance(stmt, Return):
        return (
            "return "
            + render_expr(
                stmt.value,
                RenderContext(
                    type_env, plaintext=False, enclosing_loops=enclosing_loops
                ),
            )
            + ";"
        )

    return assert_never(stmt)


def identify_protocols(
    convertions_dict: Dict[str, Any]
) -> list[str]:
    
    convertions_set = convertions_dict['to']
    if (len(convertions_set)) == 0:
        convertions_set = set()
        convertions_set.add(convertions_dict['from'])
    result = []
    if 'A' in convertions_set:
        result.append('encrypto::motion::MpcProtocol::kArithmeticGmw')
    if 'B' in convertions_set:
        result.append('encrypto::motion::MpcProtocol::kBooleanGmw')
    if 'Y' in convertions_set:
        result.append('encrypto::motion::MpcProtocol::kBmr')
    
    return result
    

def retrieve_ABY_tag(
     Mpc_protocol   
) -> str:
    
    if Mpc_protocol == 'encrypto::motion::MpcProtocol::kArithmeticGmw':
        return 'A'
    if Mpc_protocol == 'encrypto::motion::MpcProtocol::kBooleanGmw':
        return 'B'
    if Mpc_protocol == 'encrypto::motion::MpcProtocol::kBmr':
        return 'Y'

    print('PANIC [UNSOPPORTED CONVETION]')
    print(Mpc_protocol)
    exit()
    
# for easier handling  
def extract_convertion_dict(convertion_dict,key):
    return (
        convertion_dict[key]['convertion_tuple'],
        convertion_dict[key]['from'],
       convertion_dict[key]['to']
    )
    
# iterate throught the strings associated with the current code line and replace with the correct protocol
# if we have a line in B and the rendered is in A we can find it here and replace it with the B 
def replace_variables_in_protocol(stmt_details_dict,assigned_value,protocol_to_be_replaced,avoid_key=None):
    for k in stmt_details_dict:
        # check that the key is not part of an other key and that the protocol given is not _ in case of searching for input protocol (FROM)
        if k in assigned_value and f"_{k}" not in assigned_value and protocol_to_be_replaced !='_':
            # if the key exists and is not part of other key
            # replace with the representation of the correct protocol_to_be_replaced
            if stmt_details_dict[k][protocol_to_be_replaced] is not None and k!=avoid_key:
                assigned_value = assigned_value.replace(k,stmt_details_dict[k][protocol_to_be_replaced])
    return assigned_value
                    
def render_mixed_stmt(
    stmt: Union[Assign, For, Return],
    type_env: TypeEnv,
    render_ctx,
    ran_vectorization: bool,
    convertions_dict = {},
    stmt_details_dict = {},
    enclosing_loops=[],
) -> str:
    if isinstance(stmt, Assign):
        # Convert any plaintext assignments
        
        # If we're assigning to a vectorized value, use a specialized function for this.
        if isinstance(stmt.lhs, VectorizedAccess):
            to_be_converted = identify_protocols(convertions_dict[str(stmt.lhs)])
            convertion_tuple, _ , _ = extract_convertion_dict(convertions_dict,str(stmt.lhs))
            
            ctx = RenderContext(
                type_env, plaintext=False, enclosing_loops=enclosing_loops
            )
            val_expr = render_expr(stmt.rhs, ctx)

            # If this isn't a true vectorized access, just subscript normally
            if all(not vectorized for vectorized in stmt.lhs.vectorized_dims):
                lhs = render_expr(stmt.lhs, ctx)
                # if we subscript nornally we still need to check for convertions
                convertion = ""
                convertion_tuple,convertion_from,convertion_to = extract_convertion_dict(convertions_dict,str(stmt.lhs))
                if len(convertion_tuple) > 0:
                    convertion_tuple = convertion_tuple[0]
                    stmt_key = render_expr(stmt.lhs.array, dc.replace(render_ctx, plaintext=False))
                    new_key = stmt_key+f"_{convertion_tuple[1]}"
                    modify_stmt_details_dict(stmt_details_dict,stmt_key,convertion_tuple[0],stmt_key)
                    modify_stmt_details_dict(stmt_details_dict,stmt_key,convertion_tuple[1],new_key)
                    identified_pr = identify_protocols({"to": set(convertion_tuple[1])})[0]
                    extraction = '.Get()' if not "encrypto::motion::ShareWrapper" in stmt_details_dict[stmt_key]['declaration'] else ""
                    convertion = f"{lhs.replace(stmt_key,new_key)} = {lhs}{extraction}.Convert<{identified_pr}>();"
                    current_stmt = f"{lhs} = {val_expr}"     
                    current_stmt = replace_variables_in_protocol(stmt_details_dict,current_stmt,convertion_tuple[0],avoid_key=lhs)
                    return  f"{current_stmt}; {convertion}"
                elif convertion_from != '_' and len(convertion_to) == 0:
                    current_stmt = f"{lhs} = {val_expr}"
                    current_stmt = replace_variables_in_protocol(stmt_details_dict,current_stmt,convertion_from)
                    return  f"{current_stmt};"
                           
                return  f"{lhs} = {val_expr}; {convertion}"

            dim_sizes = (
                "{"
                + ", ".join(
                    render_expr(loop_bound, dc.replace(ctx, plaintext=True))
                    for loop_bound in stmt.lhs.dim_sizes
                )
                + "}"
            )
            vectorized_dims = (
                "{"
                + ", ".join(
                    str(vectorized).lower() for vectorized in stmt.lhs.vectorized_dims
                )
                + "}"
            )
            idxs = (
                "{"
                + ", ".join(
                    render_expr(var, dc.replace(ctx, plaintext=True))
                    for var, vectorized in zip(
                        stmt.lhs.idx_vars, stmt.lhs.vectorized_dims
                    )
                    if not vectorized
                )
                + "}"
            )

            mixed_convertion = f"vectorized_assign({render_expr(stmt.lhs.array, ctx)}, {dim_sizes}, {vectorized_dims}, {idxs}, {val_expr});"
            # assign the protocol based on the convertion dict
            if "party->In<Protocol>" in mixed_convertion:
                mixed_convertion =  mixed_convertion.replace("party->In<Protocol>",f"party->In<{to_be_converted[0]}>")

            stmt_key = render_expr(stmt.lhs.array, dc.replace(render_ctx, plaintext=False))
            if len(convertion_tuple) == 0:
                # still we have to make sure that every variable is in the correct protocol
                if isinstance(stmt.rhs,LiftExpr):
                    initial_convertion = ""
                    current_key = str(stmt.lhs).split("{")[0].replace("!","_")
                    raise_key = str(stmt.rhs.expr).split("{")[0].replace("!","_").split("[")[0]
                    first_time = True
                    new_declaration = ""
                    for prot in list(convertions_dict[str(stmt.lhs)]['to']):
                        if first_time == True:
                            modify_stmt_details_dict(stmt_details_dict,current_key,prot,current_key)
                            first_time = False
                            new_declaration = ""
                        else:

                            modify_stmt_details_dict(stmt_details_dict,current_key,prot,f"{current_key}_{prot}")
                            new_declaration = stmt_details_dict[current_key]["declaration"].replace(current_key,f"{current_key}_{prot}") + "\n"
                        temp_convertion = mixed_convertion
                        if raise_key in temp_convertion and not f"{raise_key}_" in temp_convertion:
                            temp_convertion = replace_variables_in_protocol(stmt_details_dict,temp_convertion,prot)
                        else:
                            temp_convertion = mixed_convertion
                        initial_convertion += (new_declaration + temp_convertion)
                        
                        
                    mixed_convertion = initial_convertion
                else:
                    mixed_convertion = replace_variables_in_protocol(stmt_details_dict,mixed_convertion,convertions_dict[str(stmt.lhs)]['from'],render_expr(stmt.lhs.array, dc.replace(render_ctx, plaintext=False)))
                modify_stmt_details_dict(stmt_details_dict,stmt_key,retrieve_ABY_tag(to_be_converted[0]),stmt_key)
                return mixed_convertion
            else:
                    
                mixed_convertion = replace_variables_in_protocol(stmt_details_dict,mixed_convertion,convertion_tuple[0][0],render_expr(stmt.lhs.array, dc.replace(render_ctx, plaintext=False)))
                for i in range( len(convertion_tuple) ):
                    # the from should be writen in the dictionary and shall remain
                    stmt_key = render_expr(stmt.lhs.array, dc.replace(render_ctx, plaintext=False))
                    modify_stmt_details_dict(stmt_details_dict,stmt_key,convertion_tuple[i][0], stmt_key)
                    new_key = stmt_key + f"_{convertion_tuple[i][1]}"
                    
                    #  declare the new share variable
                    new_declaration = "\n" + stmt_details_dict[stmt_key]['declaration'].replace(stmt_key,new_key)
                    mixed_convertion += new_declaration
                    identified_pr = identify_protocols(
                            {
                                "to": set(convertion_tuple[i][1])
                            }
                    )[0]
                    
                    extraction = '.Get()' if not "encrypto::motion::ShareWrapper" in stmt_details_dict[stmt_key]['declaration'] else ""
                    convertion_vectorized_access = f"(vectorized_access({stmt_key}, {dim_sizes}, {vectorized_dims}, {idxs}){extraction}.Convert<{identified_pr}>()))"
                    convertion_stmt = f"vectorized_assign({new_key}, {dim_sizes}, {vectorized_dims}, {idxs}, {convertion_vectorized_access};\n"            
                    mixed_convertion = mixed_convertion + "\n"
                    mixed_convertion += convertion_stmt
                
                    # store for future reference
                    modify_stmt_details_dict(stmt_details_dict,stmt_key,convertion_tuple[i][1], new_key)
                    return mixed_convertion

            # validate that the used variables are correspoding to the mixed ones
            # example that the mixed has generated also _8_0_Y while a statement that uses _8_0
            # expectes this to be the Y version and thus needs to be replaced

            _, convertion_from, convertion_to = extract_convertion_dict(convertions_dict,str(stmt.lhs))          
            for key in stmt_details_dict.keys():
                if key in mixed_convertion:
                    # if you havent identified it yet it is already declared on the default protocol
                    if convertion_from == '_' and stmt_details_dict[key][list(convertion_to)[0]] == None:
                        modify_stmt_details_dict(stmt_details_dict,key,list(convertion_to)[0], key)
                    if convertion_from == '_' and stmt_details_dict[key][list(convertion_to)[0]] != None:
                        pass
                    else:
                        # if it is default it will stay the same
                        # if it was registered by creating the new variable , this will be used 
                        if not stmt_details_dict[key][convertion_from] is None:
                            mixed_convertion = mixed_convertion.replace(key,stmt_details_dict[key][convertion_from])
                  
            return mixed_convertion

        if isinstance(stmt.rhs, Update):
            
            shared_assignment = (
                (
                    render_expr(
                        stmt.rhs,
                        RenderContext(
                            type_env, plaintext=False, enclosing_loops=enclosing_loops
                        ),
                    )
                    + ";\n"
                )
                + render_expr(
                    stmt.lhs,
                    RenderContext(
                        type_env, plaintext=False, enclosing_loops=enclosing_loops
                    ),
                )
                + " = "
                + render_expr(
                    stmt.rhs.array,
                    RenderContext(
                        type_env, plaintext=False, enclosing_loops=enclosing_loops
                    ),
                )
                + ";"
            )
            plaintext_assignment = (
                (
                    render_expr(
                        stmt.rhs,
                        RenderContext(
                            type_env, plaintext=True, enclosing_loops=enclosing_loops
                        ),
                    )
                    + ";\n"
                )
                + render_expr(
                    stmt.lhs,
                    RenderContext(
                        type_env, plaintext=True, enclosing_loops=enclosing_loops
                    ),
                )
                + " = "
                + render_expr(
                    stmt.rhs.array,
                    RenderContext(
                        type_env, plaintext=True, enclosing_loops=enclosing_loops
                    ),
                )
                + ";"
            )

        else:
            if  not (type_env[stmt.lhs].is_shared() or type_env[stmt.lhs].datatype == DataType.TUPLE):
                to_be_converted = identify_protocols(convertions_dict[str(stmt.lhs)])
                rendered_expr = render_expr(
                        stmt.rhs,
                        RenderContext(
                            type_env, plaintext=False, enclosing_loops=enclosing_loops
                        ),
                )

                shared_assignment = (
                    render_expr(
                        stmt.lhs,
                        RenderContext(
                            type_env, plaintext=False, enclosing_loops=enclosing_loops
                        ),
                    )
                    + " = "
                    + f"{stmt_details_dict[rendered_expr][retrieve_ABY_tag(to_be_converted[0])]}"
                    + ";"
                )    
            else:
                shared_assignment = (
                render_expr(
                    stmt.lhs,
                    RenderContext(
                        type_env, plaintext=False, enclosing_loops=enclosing_loops
                    ),
                )
                + " = "
                + render_expr(
                    stmt.rhs,
                    RenderContext(
                        type_env, plaintext=False, enclosing_loops=enclosing_loops
                    ),
                )
                + ";"
            )
            
            plaintext_assignment = (
                render_expr(
                    stmt.lhs,
                    RenderContext(
                        type_env, plaintext=True, enclosing_loops=enclosing_loops
                    ),
                )
                + " = "
                + render_expr(
                    stmt.rhs,
                    RenderContext(
                        type_env, plaintext=True, enclosing_loops=enclosing_loops
                    ),
                )
                + ";"
            )

        lhs_key = render_expr(
                                stmt.lhs,
                                RenderContext(
                                    type_env, plaintext=False, enclosing_loops=enclosing_loops
                                ),
                            )

        rhs_key = render_expr(
                                stmt.rhs,
                                RenderContext(
                                    type_env, plaintext=False, enclosing_loops=enclosing_loops
                                ),
                            )

        if (
            type_env[stmt.lhs].is_shared()
            or type_env[stmt.lhs].datatype == DataType.TUPLE
        ):
            mixed_convertion = shared_assignment

            if type_env[stmt.lhs].datatype != DataType.TUPLE:
                convertion_tuple,convertion_from,convertion_to = extract_convertion_dict(convertions_dict,str(stmt.lhs))
                initial_convertion = mixed_convertion
                for key in stmt_details_dict.keys():
                    if key in mixed_convertion and key != lhs_key:
                        if len(convertion_to) > 0 and stmt_details_dict[key][list(convertion_to)[0]]:
                            mixed_convertion = mixed_convertion.replace(key,stmt_details_dict[key][list(convertion_to)[0]])
                    
                # find out if it is only an explicit convertion
                if convertion_from != '_' and len(convertion_to) == 1:
                        
                    for key in stmt_details_dict.keys():
                        if key in initial_convertion:
                            initial_convertion = initial_convertion.replace(key,stmt_details_dict[key][convertion_from])
                    
                    # find if you have the stmt keys in the input protocol
                    initial_convertion = initial_convertion + "\n" + stmt_details_dict[lhs_key]['declaration'].replace(lhs_key,f"{lhs_key}_{list(convertion_to)[0]}") +  "\n"
            
                    identified_pr = identify_protocols(
                            {
                                "to": convertion_to
                            }
                    )[0]
            
                    extraction = '.Get()' if not "encrypto::motion::ShareWrapper" in stmt_details_dict[lhs_key]['declaration'] else ""
                    mixed_convertion = initial_convertion + f"{lhs_key}_{list(convertion_to)[0]} = {lhs_key}{extraction}.Convert<{identified_pr}>();" 
                    modify_stmt_details_dict(stmt_details_dict,lhs_key,convertion_from,lhs_key)

                elif convertion_from == '_' and len(convertion_to) > 1:
                    
                    # the first is in the protocol as declared and then we follow
                    # the convertions based on the hint by mixer 
                    current_key = render_expr(stmt.lhs, dc.replace(render_ctx, plaintext=False))
                    if len(convertion_tuple) > 0:
                        modify_stmt_details_dict(stmt_details_dict,current_key,convertion_tuple[0][0], current_key)
                        mixed_convertion += "\n"
                        
                        for explicit_convertion in convertion_tuple:
                            explicit_from = explicit_convertion[0]
                            explicit_to = explicit_convertion[1]
                          
                            identified_pr = identify_protocols(
                                {
                                    "to": set([explicit_to])
                                }
                            )[0]
                            new_key = f"{current_key}_{explicit_to}"
                            mixed_convertion += f"{stmt_details_dict[current_key]['declaration'].replace(current_key,new_key)}\n"
                            extraction = '.Get()' if not "encrypto::motion::ShareWrapper" in stmt_details_dict[current_key]['declaration'] else ""
                            mixed_convertion += f"{new_key} = {stmt_details_dict[current_key][explicit_from]}{extraction}.Convert<{identified_pr}>();\n"
                            modify_stmt_details_dict(stmt_details_dict,current_key,explicit_to, new_key)
                    
                    else:
                        # _ {Y,B} _ 
                        # example drop in both protocols
                        if isinstance(stmt.rhs,DropDim):
                            # we can drop in B and create variable in B
                            # then do the same for Y
                            dims = [render_expr(dim, dc.replace(render_ctx, plaintext=False)) for dim in stmt.rhs.dims]
                            chosen_prot = ""
                            chosen_key = ""
                            for key in stmt_details_dict:   
                                if key in mixed_convertion and key not in dims:
                                    chosen_key = key
                            if f"{chosen_key}_B" in mixed_convertion:
                                chosen_prot = 'B'
                            elif f"{chosen_key}_Y" in mixed_convertion:
                                chosen_prot = 'Y'
                            else:
                                # here we should find the key that matches
                                chosen_prot = next((prot for prot in ['A', 'B', 'Y'] if stmt_details_dict[chosen_key][prot] == chosen_key), "None")
                            
                        modify_stmt_details_dict(stmt_details_dict,current_key,chosen_prot, current_key)
                        convertion = ""
                        for prot in convertion_to:
                            if prot == chosen_prot:
                                continue
                            new_key = f"{current_key}_{prot}"
                            convertion += "\n" + ( stmt_details_dict[current_key]["declaration"].replace(current_key,new_key) + " "  + mixed_convertion.replace(current_key,new_key).replace(stmt_details_dict[chosen_key][chosen_prot],stmt_details_dict[chosen_key][prot]))
                            modify_stmt_details_dict(stmt_details_dict,current_key,prot, new_key)
                        mixed_convertion+=f" {convertion}"

                elif len(convertion_to) == 0:
                    # find if you have the stmt keys in the input protocol
                    for key in stmt_details_dict:
                       if key in rhs_key:
                            mixed_convertion = mixed_convertion.replace(key,stmt_details_dict[key][convertion_from])
                    modify_stmt_details_dict(stmt_details_dict,lhs_key,convertion_from, lhs_key)

                elif convertion_from == '_' and len(convertion_to) == 1:  
                    modify_stmt_details_dict(stmt_details_dict,lhs_key,list(convertion_to)[0], lhs_key)
                else:
                    raise NotImplementedError("Not implemented convertion")
        
            return mixed_convertion
        else:    
            convertion_assignment = ""
            initial_assignment = shared_assignment
            for prot in convertions_dict[str(stmt.lhs)]['to']:
                if stmt_details_dict[lhs_key]['A'] == None and stmt_details_dict[lhs_key]['B'] == None and stmt_details_dict[lhs_key]['Y'] == None:
                    modify_stmt_details_dict(stmt_details_dict,lhs_key,prot,lhs_key)
                    convertion_assignment += initial_assignment + "\n"
                elif stmt_details_dict[lhs_key][prot] != None:
                    convertion_assignment += initial_assignment + "\n"
                else:
                    new_key = f"{lhs_key}_{prot}"
                    modify_stmt_details_dict(stmt_details_dict,lhs_key,prot,new_key)
                    convertion_assignment += stmt_details_dict[lhs_key]["declaration"].replace(lhs_key,new_key) + "\n" + initial_assignment.replace(lhs_key,new_key).replace(rhs_key,stmt_details_dict[rhs_key][prot]) + "\n"
            return (
                convertion_assignment + plaintext_assignment
            )

    elif isinstance(stmt, For):
        ctr_initializer = (
            "// Initialize loop counter\n"
            + render_expr(
                stmt.counter,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + " = "
            + render_expr(
                stmt.bound_low,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + ";"
        )

        phi_initializations = "// Initialize phi values\n" + "\n".join(
            render_mixed_stmt(
                stmt=Assign(phi.lhs, phi.rhs_false), 
                type_env=type_env, 
                render_ctx=render_ctx,
                ran_vectorization=ran_vectorization,
                stmt_details_dict=stmt_details_dict,
                convertions_dict=convertions_dict)
            for phi in stmt.body
            if isinstance(phi, Phi)
        )

        header = (
            "for (; "
            + render_expr(
                stmt.counter,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + " < "
            + render_expr(
                stmt.bound_high,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + "; "
            + render_expr(
                stmt.counter,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + "++) {"
        )

        phi_assignments = "\n".join(
            render_mixed_stmt(
                stmt=Assign(phi.lhs, phi.rhs_true), 
                type_env=type_env, 
                render_ctx=render_ctx,
                ran_vectorization=ran_vectorization,
                stmt_details_dict=stmt_details_dict,
                convertions_dict=convertions_dict
            )
            for phi in stmt.body
            if isinstance(phi, Phi)
        )

        phi_updates = (
            "// Update phi values\n"
            + "if ("
            + render_expr(
                stmt.counter,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + " != "
            + render_expr(
                stmt.bound_low,
                RenderContext(
                    type_env, plaintext=True, enclosing_loops=enclosing_loops
                ),
            )
            + ") {\n"
            + indent(
                phi_assignments,
                "    ",
            )
            + "\n}\n"
        )
        body_list = []
        for substmt in stmt.body:
            if not isinstance(substmt, Phi):
                body_list.append(render_mixed_stmt(
                    stmt=substmt, 
                    type_env=type_env, 
                    ran_vectorization=ran_vectorization, 
                    enclosing_loops=enclosing_loops + [stmt],
                    stmt_details_dict=stmt_details_dict,
                    convertions_dict=convertions_dict,
                    render_ctx=render_ctx
                    )
                )

        body = "\n".join(body_list) + "\n"

        if not ran_vectorization:
            phi_finalizations = "// Assign final phi values\n" + phi_assignments + "\n"
        else:
            phi_finalizations = ""

        result_stmt =  (
            "\n"
            + ctr_initializer
            + "\n"
            + phi_initializations
            + "\n"
            + header
            + "\n"
            + indent(phi_updates, "    ")
            + "\n"
            + indent(body, "    ")
            + "\n}\n"
            + phi_finalizations
        )

        identified_in_loop = {}
        for body_stmt in stmt.body:
            if not hasattr(body_stmt,"lhs"):
                continue
            _, convertion_from, convertion_to = extract_convertion_dict(convertions_dict,str(body_stmt.lhs))
            for key in stmt_details_dict.keys():
                if key in result_stmt:
                    # if you havent identified it yet it is already declared on the default protocol
                    if convertion_from == '_' and stmt_details_dict[key][list(convertion_to)[0]] == None:
                        modify_stmt_details_dict(stmt_details_dict,key,list(convertion_to)[0], key)
                    if convertion_from == '_' and stmt_details_dict[key][list(convertion_to)[0]] != None:
                        pass
                    else:
                        # if it is default it will stay the same
                        # if it was registered by creating the new variable , this will be used 
                        if stmt_details_dict[key][convertion_from] is None:
                            modify_stmt_details_dict(stmt_details_dict,key,convertion_from, key)

                        # if we find something from explicit convertion we store it to initialize it later
                        if len(convertion_to) != 0 and hasattr(body_stmt.lhs,"array"):
                            identified_in_loop[body_stmt.lhs.array] = list(convertion_to)[0]

        global_declarations = ""
        for variable_in_loop in identified_in_loop:
            
            loop_key = render_expr(
                    variable_in_loop,
                    RenderContext(
                        type_env, plaintext=False
                    ),
            )
            new_key = f"{loop_key}_{identified_in_loop[variable_in_loop]}"
            identified_pr = identify_protocols(
                            {
                                "to": set(identified_in_loop[variable_in_loop])
                            }
            )[0]

            decl = stmt_details_dict[loop_key]['declaration'].replace(loop_key,new_key)
            # remove it from the loop
            if  decl in result_stmt:
                result_stmt = result_stmt.replace(f"{decl}\n","")
            # declare it on top
            global_declarations += (f"{stmt_details_dict[loop_key]['declaration'].replace(loop_key,new_key)}\n")
        return f"{global_declarations}{result_stmt}"

    elif isinstance(stmt, Return):
        return (
            "return "
            + render_expr(
                stmt.value,
                RenderContext(
                    type_env, plaintext=False, enclosing_loops=enclosing_loops
                ),
            )
            + ";"
        )

    return assert_never(stmt)



def _render_operator(op: Union[BinOpKind, UnaryOpKind]) -> str:
    if op == BinOpKind.AND:
        return "&"

    if op == BinOpKind.OR:
        return "|"

    if op == BinOpKind.DIV:
        return "/"

    if op == UnaryOpKind.NOT:
        return "~"

    return str(op)


def render_expr(expr: Union[AssignRHS, SubscriptIndex], ctx: RenderContext) -> str:
    if ctx.as_motion_input:
        cpp_var = render_expr(
            expr, dc.replace(ctx, plaintext=True, as_motion_input=False)
        )

        if type_assign_expr(expr, ctx.type_env, None, None).datatype == DataType.INT:
            return f"encrypto::motion::ToInput({cpp_var})"
        elif type_assign_expr(expr, ctx.type_env, None, None).datatype == DataType.BOOL:
            return f"encrypto::motion::BitVector(1, {cpp_var})"
        else:
            raise NotImplementedError(
                f"Unsupported datatype: {type_assign_expr(expr, ctx.type_env, None, None).datatype}"
            )

    if isinstance(expr, (BinOp, SubscriptIndexBinOp)):
        if expr.operator == BinOpKind.LT:
            return render_expr(
                dc.replace(
                    expr, left=expr.right, right=expr.left, operator=BinOpKind.GT  # type: ignore
                ),
                ctx,
            )
        elif expr.operator == BinOpKind.NOT_EQ:
            if isinstance(expr, BinOp):
                return render_expr(
                    UnaryOp(UnaryOpKind.NOT, dc.replace(expr, operator=BinOpKind.EQ)),
                    ctx,
                )
            else:
                return render_expr(
                    SubscriptIndexUnaryOp(
                        UnaryOpKind.NOT, dc.replace(expr, operator=BinOpKind.EQ)
                    ),
                    ctx,
                )
        elif expr.operator == BinOpKind.LT_E:
            return (
                "("
                + render_expr(dc.replace(expr, operator=BinOpKind.LT), ctx)
                + " | "
                + render_expr(dc.replace(expr, operator=BinOpKind.EQ), ctx)
                + ")"
            )
        elif expr.operator == BinOpKind.GT_E:
            return (
                "("
                + render_expr(dc.replace(expr, operator=BinOpKind.GT), ctx)
                + " | "
                + render_expr(dc.replace(expr, operator=BinOpKind.EQ), ctx)
                + ")"
            )

        operand_dims = None
        if isinstance(expr.left, VectorizedAccess):
            operand_dims = tuple(
                (idx_var, dim_size)
                for idx_var, dim_size, vectorized in zip(
                    expr.left.idx_vars,
                    expr.left.dim_sizes,
                    expr.left.vectorized_dims,
                )
                if vectorized
            )
        elif isinstance(expr.right, VectorizedAccess):
            operand_dims = tuple(
                (idx_var, dim_size)
                for idx_var, dim_size, vectorized in zip(
                    expr.right.idx_vars,
                    expr.right.dim_sizes,
                    expr.right.vectorized_dims,
                )
                if vectorized
            )

        if operand_dims and isinstance(expr.left, (Constant, Var)):
            lift_expr = LiftExpr(expr.left, operand_dims)
            left_expr = f"decltype({render_expr(expr.left, ctx)})::Simdify({render_expr(lift_expr, ctx)})"
        else:
            left_expr = render_expr(expr.left, ctx)

        if operand_dims and isinstance(expr.right, (Constant, Var)):
            lift_expr = LiftExpr(expr.right, operand_dims)
            right_expr = f"decltype({render_expr(expr.right, ctx)})::Simdify({render_expr(lift_expr, ctx)})"
        else:
            right_expr = render_expr(expr.right, ctx)

        # If we're using an arithmetic primitive operation or we're operating on plaintext values,
        # don't cast to a share wrapper
        if ctx.plaintext or expr.operator in (
            BinOpKind.ADD,
            BinOpKind.SUB,
            BinOpKind.MUL,
            BinOpKind.DIV,
            BinOpKind.GT,
        ):
            return f"({left_expr} {expr.operator.value} {right_expr})"

        # Otherwise, convert to a ShareWrapper since they have more operators defined
        # TODO: go through the operators for ShareWrapper and make sure they're all valid
        # for the default protocol
        else:
            return (
                "("
                + (
                    "to_share_wrapper("
                    + left_expr
                    + ")"
                    + " "
                    + _render_operator(expr.operator)
                    + " "
                    + "to_share_wrapper("
                    + right_expr
                    + ")"
                )
                + ")"
            )

    elif isinstance(expr, Constant):
        if ctx.plaintext:
            if expr.datatype == DataType.INT:
                return f"{ctx.int_type}({expr.value})"
            elif expr.datatype == DataType.BOOL:
                return str(expr).lower()
            else:
                raise NotImplementedError(f"Unsupported datatype: {expr.datatype}")

        else:
            return "_MPC_CONSTANT_" + str(expr).lower()

    elif isinstance(expr, DropDim):
        specialization = ""
        # Since we want to manipulate the array, we don't want the input to drop_dim()
        # to be vectorized
        if isinstance(expr.array, VectorizedAccess):
            array = render_expr(expr.array, ctx) + ".Unsimdify()"
            # TODO: move this operation into the vectorization phase
            # Essentially, we may have modified which dimensions are actually getting dropped
            # by lifting this statement out of a loop in phase 2 of vectorization.  The below
            # check makes sure that we're only considering the dimensions which are actually
            # vectorized.
            droppable_dims = tuple(
                dim_size
                for dim_size, vectorized in zip(expr.dims, expr.array.vectorized_dims)
                if vectorized
            )
        else:
            array = render_expr(expr.array, ctx)
            droppable_dims = expr.dims

        if len(droppable_dims) == 1:
            specialization = "_monoreturn"

        dims = (
            "{"
            + ", ".join(
                render_expr(dim_size, dc.replace(ctx, plaintext=True))
                for dim_size in droppable_dims
            )
            + "}"
        )

        return f"drop_dim{specialization}({array}, {dims})"

    elif isinstance(expr, List):
        items = ", ".join(render_expr(item, ctx) for item in expr.items)
        return "{" + items + "}"

    elif isinstance(expr, Mux):
        cpp_cond = render_expr(expr.condition, ctx)
        cond_dims = None
        if isinstance(expr.condition, VectorizedAccess):
            cond_dims = tuple(
                (idx_var, dim_size)
                for idx_var, dim_size, vectorized in zip(
                    expr.condition.idx_vars,
                    expr.condition.dim_sizes,
                    expr.condition.vectorized_dims,
                )
                if vectorized
            )

        if cond_dims and isinstance(expr.true_value, (Constant, Var)):
            lift_expr = LiftExpr(expr.true_value, cond_dims)
            cpp_true_val = f"decltype({render_expr(expr.true_value, ctx)})::Simdify({render_expr(lift_expr, ctx)})"
        else:
            cpp_true_val = render_expr(expr.true_value, ctx)

        if cond_dims and isinstance(expr.false_value, (Constant, Var)):
            lift_expr = LiftExpr(expr.false_value, cond_dims)
            cpp_false_val = f"decltype({render_expr(expr.false_value, ctx)})::Simdify({render_expr(lift_expr, ctx)})"
        else:
            cpp_false_val = render_expr(expr.false_value, ctx)

        return f"{cpp_cond}.Mux({cpp_true_val}.Get(), {cpp_false_val}.Get())"

    elif isinstance(expr, LiftExpr):
        raw_idx_map = lambda idx: f"indices[{idx}]"
        augmented_env = copy(ctx.type_env)
        for idx_var, _dim_size in expr.dims:
            augmented_env[idx_var] = PLAINTEXT_INT
        if (
            not ctx.plaintext
            and type_assign_expr(expr.expr, augmented_env, None, None).is_plaintext()
        ):
            to_shared = (
                lambda val: f"encrypto::motion::SecureUnsignedInteger(party->In<Protocol>(encrypto::motion::ToInput({val}), 0))"
            )

            idx_map = lambda idx: to_shared(raw_idx_map(idx))
        else:
            idx_map = raw_idx_map

        # If we're lifting a vectorized array, don't render a vectorized access or else the lifted array
        # will hold too many values
        expr_to_render = expr.expr
        if isinstance(expr_to_render, VectorizedAccess) and any(
            vectorized for vectorized in expr_to_render.vectorized_dims
        ):
            post_expr = ".Unsimdify()"
        else:
            post_expr = ""

        inner_ctx = dc.replace(
            ctx,
            int_type="std::uint32_t",
            var_mappings={
                var: idx_map(i)
                for i, (var, _) in enumerate(expr.dims)
                if not any(var == loop.counter for loop in ctx.enclosing_loops)
            },
        )
        inner_expr = f"std::function([&](const std::vector<std::uint32_t> &indices){{return {render_expr(expr_to_render, inner_ctx)}{post_expr};}})"

        dims = (
            "{"
            + ", ".join(
                render_expr(loop_bound, dc.replace(ctx, plaintext=True))
                for _, loop_bound in expr.dims
            )
            + "}"
        )

        return f"lift({inner_expr}, {dims})"

    elif isinstance(expr, Subscript):
        return f"{render_expr(expr.array, ctx)}[{render_expr(expr.index, dc.replace(ctx, plaintext=True))}]"

    elif isinstance(expr, Tuple):
        items = ", ".join(render_expr(item, ctx) for item in expr.items)
        return f"std::make_tuple({items})"

    elif isinstance(expr, (UnaryOp, SubscriptIndexUnaryOp)):
        return f"({_render_operator(expr.operator)}{render_expr(expr.operand, ctx)})"

    elif isinstance(expr, Update):
        cpp_arr_access = render_expr(Subscript(expr.array, expr.index), ctx)
        cpp_val = render_expr(expr.value, ctx)
        return f"{cpp_arr_access} = {cpp_val}"

    elif isinstance(expr, Var):
        if expr in ctx.var_mappings:
            return ctx.var_mappings[expr]

        cpp_str = str(expr).replace("!", "_")
        if ctx.plaintext:
            return f"_MPC_PLAINTEXT_{cpp_str}"
        else:
            return cpp_str

    elif isinstance(expr, VectorizedAccess):
        # If this isn't a true vectorized access, just subscript normally
        if all(not vectorized for vectorized in expr.vectorized_dims):
            subscript = " + ".join(
                f"({render_expr(idx, dc.replace(ctx, plaintext=True))} * "
                + "*".join(
                    render_expr(bound, dc.replace(ctx, plaintext=True))
                    for bound in expr.dim_sizes[dim + 1 :]
                )
                + ")"
                # Skip the last dimension for now since it doesn't get multiplied
                for dim, idx in enumerate(expr.idx_vars[:-1])
            )

            # Since the last dimension has no multiplicative factor, render it separately
            if subscript:
                subscript += " + "
            subscript += render_expr(expr.idx_vars[-1], dc.replace(ctx, plaintext=True))
            return f"{render_expr(expr.array, ctx)}[{subscript}]"

        dim_sizes = (
            "{"
            + ", ".join(
                render_expr(loop_bound, dc.replace(ctx, plaintext=True))
                for loop_bound in expr.dim_sizes
            )
            + "}"
        )
        vectorized_dims = (
            "{"
            + ", ".join(str(vectorized).lower() for vectorized in expr.vectorized_dims)
            + "}"
        )
        idxs = (
            "{"
            + ", ".join(
                render_expr(var, dc.replace(ctx, plaintext=True))
                for var, vectorized in zip(expr.idx_vars, expr.vectorized_dims)
                if not vectorized
            )
            + "}"
        )
        return f"vectorized_access({render_expr(expr.array, ctx)}, {dim_sizes}, {vectorized_dims}, {idxs})"

    elif isinstance(expr, VectorizedUpdate):
        dim_sizes = (
            "{"
            + ", ".join(
                render_expr(loop_bound, dc.replace(ctx, plaintext=True))
                for loop_bound, vectorized in zip(expr.dim_sizes, expr.vectorized_dims)
                if vectorized
            )
            + "}"
        )
        vectorized_dims = (
            "{"
            + ", ".join(
                str(vectorized).lower()
                for vectorized in expr.vectorized_dims
                if vectorized
            )
            + "}"
        )

        specialization = ""
        if all(not vectorized for vectorized in expr.vectorized_dims):
            specialization = "_monoreturn"

        idxs = "{}"
        update_array = expr.array
        if isinstance(update_array, VectorizedAccess) and all(
            vectorized for vectorized in update_array.vectorized_dims
        ):
            update_array = update_array.array
        return f"vectorized_update{specialization}({render_expr(update_array, ctx)}, {dim_sizes}, {vectorized_dims}, {idxs}, {render_expr(expr.value, ctx)})"

    return assert_never(expr)
