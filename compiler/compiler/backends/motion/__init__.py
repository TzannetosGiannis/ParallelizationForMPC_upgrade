import dataclasses as dt
import io
from jinja2 import Environment, FileSystemLoader  # type: ignore
import os
import shutil
from textwrap import indent
from typing import Any, Union
import re

from ...ast_shared import VectorizedAccess

from ...util import assert_never
from ...loop_linear_code import Function, Statement, Phi, Assign, For, Return
from ...type_analysis import TypeEnv, VarVisibility, Constant, DataType
from ... import tac_cfg, ast_shared
from ...protocol_mixing import OrderedConfig,Config

from .low_level_rendering import (
    RenderContext,
    render_datatype,
    render_expr,
    render_param,
    render_stmt,
    render_mixed_stmt,
    render_type,
)

# supported protocols
VALID_PROTOCOLS = ["ArithmeticGmw","BooleanGmw", "Bmr"]

# protocol representations in native motion
PROTOCOL_CONVERTIONS = {
    "A":'encrypto::motion::MpcProtocol::kArithmeticGmw',
    "B":'encrypto::motion::MpcProtocol::kBooleanGmw',
    "Y":'encrypto::motion::MpcProtocol::kBmr'
}


def _render_prototype(func: Function, type_env: TypeEnv) -> str:
    assert isinstance(func.body[-1], Return)
    return_value = func.body[-1].value
    if isinstance(return_value, VectorizedAccess):
        return_value = return_value.array

    return_type = render_type(type_env[return_value], plaintext=False)
    return (
        f"template <encrypto::motion::MpcProtocol Protocol>\n"
        f"{return_type} {func.name}(\n"
        + indent("encrypto::motion::PartyPointer &party,\n", "    ")
        + indent(
            ",\n".join(render_param(param, type_env) for param in func.parameters),
            "    ",
        )
        + "\n)"
    )


def _render_call(func: Function, type_env: TypeEnv) -> str:
    return (
        f"{func.name}({', '.join(str(param.var.name) for param in func.parameters)});"
    )


def _collect_constants(stmts: list[Statement]) -> list[Constant]:
    def expr_constants(
        expr: Union[
            tac_cfg.AssignRHS,
            tac_cfg.SubscriptIndex,
            tac_cfg.LiftExpr,
            tac_cfg.DropDim,
            VectorizedAccess,
        ]
    ) -> list[Constant]:
        if isinstance(expr, Constant):
            return [expr]
        elif isinstance(expr, (tac_cfg.Var, tac_cfg.Subscript)):
            return []
        elif isinstance(expr, (tac_cfg.BinOp, ast_shared.SubscriptIndexBinOp)):
            return [*expr_constants(expr.left), *expr_constants(expr.right)]
        elif isinstance(expr, (tac_cfg.UnaryOp, ast_shared.SubscriptIndexUnaryOp)):
            return expr_constants(expr.operand)
        elif isinstance(expr, tac_cfg.List):
            return [const for val in expr.items for const in expr_constants(val)]
        elif isinstance(expr, tac_cfg.Tuple):
            # TODO: Figure out the best way to handle constants here
            return [const for val in expr.items for const in expr_constants(val)]
        elif isinstance(expr, tac_cfg.Mux):
            return [
                val
                for val in (expr.true_value, expr.false_value)
                if isinstance(val, Constant)
            ]
        elif isinstance(expr, tac_cfg.Update):
            return [*expr_constants(expr.index), *expr_constants(expr.value)]
        elif isinstance(expr, tac_cfg.LiftExpr):
            return [
                const
                for _, dim_bound in expr.dims
                for const in expr_constants(dim_bound)
            ] + expr_constants(expr.expr)
        elif isinstance(expr, tac_cfg.DropDim):
            return [
                const for dim_bound in expr.dims for const in expr_constants(dim_bound)
            ]
        elif isinstance(expr, VectorizedAccess):
            return [const for size in expr.dim_sizes for const in expr_constants(size)]
        elif isinstance(expr, tac_cfg.VectorizedUpdate):
            return [
                const for size in expr.dim_sizes for const in expr_constants(size)
            ] + [const for const in expr_constants(expr.value)]
        else:
            assert_never(expr)

    def stmt_constants(stmt: Statement) -> list[Constant]:
        if isinstance(stmt, For):
            return _collect_constants(stmt.body)
        elif isinstance(stmt, Assign):
            return expr_constants(stmt.rhs)
        elif isinstance(stmt, Phi):
            return [const for rhs in stmt.rhs_vars() for const in expr_constants(rhs)]
        elif isinstance(stmt, Return):
            return expr_constants(stmt.value)
        else:
            assert_never(stmt)

    return [const for stmt in stmts for const in stmt_constants(stmt)]



def render_mixed_function(func: Function, type_env: TypeEnv, ran_vectorization: bool, mixed_config: OrderedConfig) -> str:
    
    render_ctx = RenderContext(type_env)
    convertion_dict = {}
    stmt_details_dict = {}
    
    
    for i in range(len(mixed_config.assignments)) :
        convertion_dict[str(mixed_config.assignments[i][0].lhs)] = {
            "from":mixed_config.assignments[i][1],
            "to":mixed_config.assignments[i][2],
            "convertion_tuple":mixed_config.assignments[i][-1]
        }

    
    func_header = f"{_render_prototype(func, type_env)} {{"
    
    # remove template line 
    func_header = "\n".join(func_header.split("\n")[1:])

    
    # Initialize an empty string to store the shared variable declarations
    var_definitions = "// Shared variable declarations\n"

    # Iterate over sorted type environment items
    for var, var_type in sorted(type_env.items(), key=lambda x: str(x[0])):
        # Check if the variable is not a shared parameter
        if not any(param.var == var and param.var_type.is_shared() for param in func.parameters):
            
            # Render the type of the variable for shared context (plaintext=False)
            rendered_var_type = render_type(var_type, plaintext=False)
            
            # Render the expression for the variable
            rendered_expr = render_expr(var, dt.replace(render_ctx, plaintext=False))
                
            # Initialize a string for the variable declaration
            var_declaration = rendered_var_type + " " + rendered_expr
            
            # If the variable has dimension sizes, render them and append to the declaration
            if var_type.dim_sizes:
                dims = "((" + ") * (".join(
                    # Allocate an extra slot per dimension for vectorized arrays
                    render_expr(bound, dt.replace(render_ctx, plaintext=True))
                    for bound in var_type.dim_sizes
                ) + "))"
                var_declaration += dims
            
            # Append a semicolon to complete the declaration
            var_declaration += ";"
            
            # Add the variable declaration to the shared variable definitions
            var_definitions += var_declaration + "\n"
            stmt_details_dict[rendered_expr] = {
                "declaration":var_declaration,
                "A":None,
                "B":None,
                "Y":None,
            }
            

    # phi nodes will create problems so  we will iterate here to fill stmt_details_dict
    # the problem is that if access variables that are not registered yet

    for key in convertion_dict:
        convertion_tuple = convertion_dict[key]['convertion_tuple']
        if len(convertion_tuple) > 0:
            small_key = key.split("{")[0].replace("!","_")
            stmt_details_dict[small_key][convertion_tuple[0][0]] = small_key
            stmt_details_dict[small_key][convertion_tuple[0][1]] = f"{small_key}_{convertion_tuple[0][1]}"

    plaintext_var_definitions = (
        "// Plaintext variable declarations\n"
        + "\n".join(
            render_type(var_type, plaintext=True)
            + " "
            + render_expr(var, dt.replace(render_ctx, plaintext=True))
            # Initialize vectorized arrays with a size
            + (
                "(("
                + ") * (".join(
                    render_expr(bound, dt.replace(render_ctx, plaintext=True)) + " + 1"
                    for bound in var_type.dim_sizes
                )
                + "))"
                if var_type.dim_sizes
                else ""
            )
            + ";"
            for var, var_type in sorted(type_env.items(), key=lambda x: str(x[0]))
            if var_type.is_plaintext()
            if not any(
                param.var == var and param.var_type.is_plaintext()
                for param in func.parameters
            )
        )
        + "\n"
    )

 
    plaintext_constants = set(_collect_constants(func.body))

    constant_initialization = "// Constant initializations\n"
    
    for i, const in enumerate(sorted(plaintext_constants, key=lambda c: str(c.value))):
        
        render_key = render_expr(const, render_ctx)
        # Convert keys of mixed_config.constants to str if they are int
        string_constants_keys = {str(k): v for k, v in mixed_config.constants.items()}

        # constants in motion need to be in specific protocol
        if str(const.value) in string_constants_keys:
            for elem in string_constants_keys[str(const.value)]:
                retrieved_protocol = PROTOCOL_CONVERTIONS[elem]
                const_declaration = f"{render_datatype(const.datatype, plaintext=False)} {render_key} = party->In<Protocol>({render_expr(const, dt.replace(render_ctx, as_motion_input=True))}, 0);\n"
                
                # first time we see this variable
                if render_key not in stmt_details_dict:
                    stmt_details_dict[render_key] = {
                        "declaration":var_declaration,
                        "A":None,
                        "B":None,
                        "Y":None,
                    }
                    stmt_details_dict[render_key][elem] = render_key
                else:
                    new_render_key = render_key+f"_{elem}"
                    stmt_details_dict[render_key][elem] = new_render_key
                    const_declaration = const_declaration.replace(render_key,new_render_key)
                
                constant_initialization += const_declaration.replace('Protocol',retrieved_protocol)

    plaintext_param_assignments = "// Plaintext parameter assignments\n"

    plaintext_dict = {}
    plaintext_replace_dict = {}

    # plaintext need to be in specific protocol
    for var_key in mixed_config.plaintexts:  # Get keys only
        key_str = str(var_key)  # Convert Var to string
        plaintext_dict[key_str.replace("!", "_")] = mixed_config.plaintexts[var_key]


    # handle the input variables , for now allow one protocol only
    # [TODO] revisit inputs of {"var": {A,B}} 
    func_header_declrations = [elem.replace(",","").lstrip() for elem in func_header.split("\n")][2:]
    parameter_input_convertions_initialization = "// Input Protocol Convertions\n"
    for var_key in mixed_config.inputs:  
        key = str(var_key)  # Ensure key is a string
        value = mixed_config.inputs[var_key]
        dict_key = str(key).replace("!","_")
        if len(value) > 1:
            if dict_key not in plaintext_dict:
                plaintext_dict[dict_key] = list(value)
                stmt_details_dict[dict_key] = {
                    "declaration":next((x for x in func_header_declrations if x.endswith(dict_key)), "None"),
                    "A":None,
                    "B":None,
                    "Y":None,
                }
                l = sorted(list(value))
                for i in range(len(l)):
                    if i ==0:
                        stmt_details_dict[dict_key][l[i]] = dict_key
                    else:
                        stmt_details_dict[dict_key][l[i]] = f"{dict_key}_{l[i]}"
                        if  "vector" in str(stmt_details_dict[dict_key]['declaration']):
                            convertion = str(stmt_details_dict[dict_key]['declaration']).replace(dict_key, f"{dict_key}_{l[i]}") + f"({dict_key}.size());\n"
                            convertion += f"vectorized_assign({dict_key}_{l[i]}, {{{dict_key}.size()}}, {{true}}, {{}}, (vectorized_access({dict_key}, {{{dict_key}.size()}}, {{true}}, {{}}).Get().Convert<{PROTOCOL_CONVERTIONS[l[i]]}>()));\n"
                            parameter_input_convertions_initialization += convertion
                        else:
                            raise NotImplementedError("Only vectors are supported as multiple protocols input")
        else:
            if dict_key not in plaintext_dict:
                plaintext_dict[dict_key] = list(value)
                stmt_details_dict[dict_key] = {
                    "declaration":next((x for x in func_header_declrations if x.endswith(dict_key)), None),
                            "A":None,
                            "B":None,
                            "Y":None,
                }
                stmt_details_dict[dict_key][plaintext_dict[dict_key][0]] = dict_key

        
    # handle parameters both as scalar and vectors with respect to protocol assignment
    for i, param in enumerate(sorted(func.parameters, key=str)):
        
        if param.var_type.is_plaintext() and render_expr(param.var, dt.replace(render_ctx, plaintext=False)) in plaintext_dict:
            dict_key = render_expr(param.var, dt.replace(render_ctx, plaintext=False))
            retrieved_protocol_list = plaintext_dict[dict_key]
    
            if param.var_type.dims == 0:
                assigment_declaration = (
                        f"input_variable_1 = party->In<Protocol>("
                        f"encrypto::motion::ToInput(input_value_1), 0);\n"
                )
                assignment = ""
                for pr in retrieved_protocol_list:
                    if stmt_details_dict[dict_key]['A'] == None and stmt_details_dict[dict_key]['B'] == None and stmt_details_dict[dict_key]['Y'] == None:
                        assignment += (assigment_declaration 
                                        .replace("input_variable_1",render_expr(param.var, render_ctx))
                                        .replace("input_value_1",render_expr(param.var, dt.replace(render_ctx, plaintext=True)))
                                        .replace("Protocol",PROTOCOL_CONVERTIONS[pr])
                        )
                        stmt_details_dict[dict_key][pr] = dict_key
                    else:
                        new_key = f"{dict_key}_{pr}"
                        plaintext_replace_dict[f"MPC_PLAINTEXT_{new_key}"] = f"MPC_PLAINTEXT_{dict_key}"
                        initialization = (assigment_declaration
                                        .replace("input_variable_1",new_key)
                                        .replace("input_value_1",render_expr(param.var, dt.replace(render_ctx, plaintext=True)))
                                        .replace("Protocol",PROTOCOL_CONVERTIONS[pr])
                        )
                        assigment_declaration = str(stmt_details_dict[dict_key]["declaration"]).replace(dict_key,new_key)
                        assignment += (
                            f"{assigment_declaration}\n"
                            f"{initialization}"
                        )
                        stmt_details_dict[dict_key][pr] = new_key

            else:
                retrieved_protocol = PROTOCOL_CONVERTIONS[retrieved_protocol_list[0]]
                assignment = (
                    f"{render_expr(param.var, render_ctx)}.clear();\n"
                    f"std::transform("
                    f"{render_expr(param.var, dt.replace(render_ctx, plaintext=True))}.begin(), "
                    f"{render_expr(param.var, dt.replace(render_ctx, plaintext=True))}.end(), "
                    f"std::back_inserter({render_expr(param.var, render_ctx)}), "
                    f"[&](const auto &val) {{ return party->In<{retrieved_protocol}>("
                    f"encrypto::motion::ToInput(val), 0); }});\n"
                )
            
            plaintext_param_assignments += assignment

    func_body = "// Function body\n"
    for i, stmt in enumerate(func.body):
        if not isinstance(stmt, Phi):
            rendered_stmt = render_mixed_stmt(stmt, type_env,render_ctx, ran_vectorization,convertion_dict,stmt_details_dict)
            func_body += rendered_stmt + "\n"
            
    cpp_script = (
        func_header
        + "\n"
        + indent(var_definitions, "    ")
        + "\n"
        + indent(plaintext_var_definitions, "    ")
        + "\n"
        + indent(constant_initialization, "    ")
        + "\n"
        + indent(parameter_input_convertions_initialization, "    ")
        + "\n"
        + indent(plaintext_param_assignments, "    ")
        + "\n"
        + indent(func_body, "    ")
        + "\n}"
    )

    # Define the pattern and the replacement
    pattern = r"party->In<encrypto::motion::MpcProtocol::kArithmeticGmw>\(encrypto::motion::ToInput\((.*?)\), (.*?)\)\)"
    replacement = r"party->In<encrypto::motion::MpcProtocol::kArithmeticGmw>(\1, \2))"

    # Replace using re.sub
    # Apply iterative replacement until no changes occur
    while True:
        new_script = re.sub(pattern, replacement, cpp_script, flags=re.DOTALL)
        if new_script == cpp_script:
            break  # Stop when no further replacements are made
        cpp_script = new_script  # Update the string for the next iteration
     
    return cpp_script
    

def render_function(func: Function, type_env: TypeEnv, ran_vectorization: bool) -> str:
    render_ctx = RenderContext(type_env)

    func_header = f"{_render_prototype(func, type_env)} {{"

    var_definitions = (
        "// Shared variable declarations\n"
        + "\n".join(
            render_type(var_type, plaintext=False)
            + " "
            + render_expr(var, dt.replace(render_ctx, plaintext=False))
            # Initialize vectorized arrays with a size
            + (
                "(("
                + ") * (".join(
                    # Vectorized arrays are often assigned to via phi nodes, which means that
                    # they end up getting an extra final value per dimension.  We account for
                    # this by allocating an extra slot per dimension here and working around
                    # that dimension inside the C++ helper functions
                    render_expr(bound, dt.replace(render_ctx, plaintext=True))
                    for bound in var_type.dim_sizes
                )
                + "))"
                if var_type.dim_sizes
                else ""
            )
            + ";"
            for var, var_type in sorted(type_env.items(), key=lambda x: str(x[0]))
            if not any(
                param.var == var and param.var_type.is_shared()
                for param in func.parameters
            )
        )
        + "\n"
    )

    plaintext_var_definitions = (
        "// Plaintext variable declarations\n"
        + "\n".join(
            render_type(var_type, plaintext=True)
            + " "
            + render_expr(var, dt.replace(render_ctx, plaintext=True))
            # Initialize vectorized arrays with a size
            + (
                "(("
                + ") * (".join(
                    render_expr(bound, dt.replace(render_ctx, plaintext=True)) + " + 1"
                    for bound in var_type.dim_sizes
                )
                + "))"
                if var_type.dim_sizes
                else ""
            )
            + ";"
            for var, var_type in sorted(type_env.items(), key=lambda x: str(x[0]))
            if var_type.is_plaintext()
            if not any(
                param.var == var and param.var_type.is_plaintext()
                for param in func.parameters
            )
        )
        + "\n"
    )
    
    plaintext_constants = set(_collect_constants(func.body))
    constant_initialization = (
        "// Constant initializations\n"
        + "\n".join(
            f"{render_datatype(const.datatype, plaintext=False)} {render_expr(const, render_ctx)} = "
            + f"party->In<Protocol>({render_expr(const, dt.replace(render_ctx, as_motion_input=True))}, 0);"
            for const in sorted(plaintext_constants, key=lambda c: str(c.value))
        )
        + "\n"
    )

    plaintext_param_assignments = (
        "// Plaintext parameter assignments\n"
        + "\n".join(
            # Initialize the shared version
            (
                render_expr(param.var, render_ctx)
                + " = party->In<Protocol>(encrypto::motion::ToInput("
                + render_expr(param.var, dt.replace(render_ctx, plaintext=True))
                + "), 0);"
            )
            if param.var_type.dims == 0
            else (
                f"{render_expr(param.var, render_ctx)}.clear();\n"
                + "std::transform("
                + render_expr(param.var, dt.replace(render_ctx, plaintext=True))
                + ".begin(), "
                + render_expr(param.var, dt.replace(render_ctx, plaintext=True))
                + ".end(), "
                + f"std::back_inserter({render_expr(param.var, render_ctx)}), "
                + "[&](const auto &val) { return party->In<Protocol>(encrypto::motion::ToInput(val), 0); });"
            )
            for param in sorted(func.parameters, key=str)
            if param.var_type.is_plaintext()
        )
        + "\n"
    )

    func_body = (
        "// Function body\n"
        + "\n".join(
            render_stmt(stmt, type_env, ran_vectorization)
            for stmt in func.body
            if not isinstance(stmt, Phi)
        )
        + "\n"
    )

    return (
        func_header
        + "\n"
        + indent(var_definitions, "    ")
        + "\n"
        + indent(plaintext_var_definitions, "    ")
        + "\n"
        + indent(constant_initialization, "    ")
        + "\n"
        + indent(plaintext_param_assignments, "    ")
        + "\n"
        + indent(func_body, "    ")
        + "\n}"
    )


def render_application(
    func: Function, type_env: TypeEnv, params: dict[str, Any], ran_vectorization: bool,mixing=False,mixed_config:OrderedConfig = OrderedConfig(Config())
) -> None:

    
    template_dir = os.path.abspath(os.path.dirname(__file__))
    project_root = os.path.abspath(os.path.join(template_dir, "..", "..", "..", ".."))

    template_loader = FileSystemLoader(os.path.abspath(os.path.dirname(__file__)))
    template_env = Environment(loader=template_loader)

    main_template = template_env.get_template("main.cpp.jinja")
    header_template = template_env.get_template("header.h.jinja")
    cpp_template = template_env.get_template("circuit_gen.cpp.jinja")
    cmakelists_template = template_env.get_template("CMakeLists.txt.jinja")

    assert isinstance(func.body[-1], Return)
    return_type = type_env[func.body[-1].value]


    rendered_main = main_template.render(
        header_fname=f"{func.name}.h",
        params=[
            {
                "name": param.var.name,
                "cpp_type": render_type(
                    param.var_type, plaintext=type_env[param.var].is_plaintext()
                ),
                "plaintext_cpp_type": render_type(param.var_type, plaintext=True),
                "is_shared": param.var_type.visibility == VarVisibility.SHARED,
                "dims": param.var_type.dims,
                "party_idx": param.party_idx,
                "default_value": param.default_values[0]
                if len(param.default_values) > 0
                else None,
            }
            for param in func.parameters
        ],
        protocol=f"encrypto::motion::MpcProtocol::k{params['protocol']}" if "protocol" in params else "",
        num_returns=type_env[func.body[-1].value].dims,
        outputs=[render_type(return_type, plaintext=True)]
        if return_type.datatype != DataType.TUPLE
        else [render_type(t, plaintext=True) for t in return_type.tuple_types],
        function_name=func.name,
    )

    rendered_context = None
    if mixing:
        rendered_context = render_mixed_function(func,type_env,ran_vectorization,mixed_config)
    else:
        rendered_context = render_function(func, type_env, ran_vectorization)


    rendered_header = header_template.render(
        circuit_generator=rendered_context
    )

    rendered_cmakelists = cmakelists_template.render(
        app_name=func.name,
        motion_dir=os.path.join(project_root, "backend_submodules", "MOTION"),
        cpp_files=["main.cpp", "collect_stats.cpp"],
    )

    output_dir = os.path.abspath(params["out_dir"])
    
    os.makedirs(output_dir, exist_ok=params["overwrite"])
    
    
    if mixing:
        # Regex to match the full string and replace
        rendered_main = re.sub(rf"auto output = {func.name}<>", f"auto output = {func.name}", rendered_main)

    for key,value in mixed_config.inputs.items():
        pattern = rf"({key.name}.*?party->In<)(>.*$)"  # Capturing groups to modify content inside <>
        match = re.search(pattern, rendered_main, re.MULTILINE)
        if match:
            rendered_main = re.sub(pattern, rf"\1{PROTOCOL_CONVERTIONS[value[0]]}\2", rendered_main, flags=re.MULTILINE)
        else:
            print("No match found",pattern)
            # raise NotImplementedError("This part should not be explored, dark times require dark measures")

    # Define the pattern and the replacement
    pattern = r"party->In<encrypto::motion::MpcProtocol::kArithmeticGmw>\(encrypto::motion::ToInput\((.*?)\), (.*?)\)\)"
    replacement = r"party->In<encrypto::motion::MpcProtocol::kArithmeticGmw>(\1, \2))"

     # Replace using re.sub
    # Apply iterative replacement until no changes occur
    while True:
        new_script = re.sub(pattern, replacement, rendered_main, flags=re.DOTALL)
        if new_script == rendered_main:
            break  # Stop when no further replacements are made
        rendered_main = new_script  # Update the string for the next iteration
   
    with open(os.path.join(output_dir, "main.cpp"), "w") as main_file:
        main_file.write(rendered_main)
    
    with open(os.path.join(output_dir, f"{func.name}.h"), "w") as header_file:
        header_file.write(rendered_header)

    with open(os.path.join(output_dir, "CMakeLists.txt"), "w") as cmakelists_file:
        cmakelists_file.write(rendered_cmakelists)

    shutil.copyfile(
        os.path.join(template_dir, "collect_stats.h"),
        os.path.join(output_dir, "collect_stats.h"),
    )
    shutil.copyfile(
        os.path.join(template_dir, "collect_stats.cpp"),
        os.path.join(output_dir, "collect_stats.cpp"),
    )
    
