import subprocess
from pathlib import Path
import json
import re
from app.core.state import VerilogAgentState

def append_history(state, new_entry):
    """
    Append a new agent execution record to the existing history.
    """

    history = list(state.get("history", []))

    if isinstance(new_entry, list):
        history.extend(new_entry)
    else:
        history.append(new_entry)

    return history


def compile_and_simulate(
    workspace,
    design_file,
    testbench_file,
    timeout=20
):
    """
    Compile the RTL and testbench using Icarus Verilog,
    then run the simulation using VVP.

    Returns all important evidence.
    """

    workspace = Path(workspace)
    design_file = Path(design_file)
    testbench_file = Path(testbench_file)

    simulation_file = workspace / "simulation.vvp"

    # STEP 1: COMPILE
    compile_command = [
        "iverilog",
        "-g2005",
        "-Wall",
        "-o",
        str(simulation_file),
        str(design_file),
        str(testbench_file)
    ]

    try:
        compile_result = subprocess.run(
            compile_command,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout
        )

    except subprocess.TimeoutExpired:
        return {
            "status": "COMPILE_TIMEOUT",
            "compile_return_code": -1,
            "compile_stdout": "",
            "compile_stderr": "Compilation timed out.",
            "simulation_return_code": None,
            "simulation_stdout": "",
            "simulation_stderr": ""
        }

    compile_stdout = compile_result.stdout
    compile_stderr = compile_result.stderr

    if compile_result.returncode != 0:
        return {
            "status": "COMPILE_ERROR",
            "compile_return_code": compile_result.returncode,
            "compile_stdout": compile_stdout,
            "compile_stderr": compile_stderr,
            "simulation_return_code": None,
            "simulation_stdout": "",
            "simulation_stderr": ""
        }

    # STEP 2: SIMULATION
    try:
        simulation_result = subprocess.run(
            ["vvp", str(simulation_file)],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=timeout
        )

    except subprocess.TimeoutExpired:
        return {
            "status": "SIMULATION_TIMEOUT",
            "compile_return_code": compile_result.returncode,
            "compile_stdout": compile_stdout,
            "compile_stderr": compile_stderr,
            "simulation_return_code": -1,
            "simulation_stdout": "",
            "simulation_stderr": "Simulation timed out."
        }

    simulation_stdout = simulation_result.stdout
    simulation_stderr = simulation_result.stderr

    simulation_output = (
        simulation_stdout +
        simulation_stderr
    )

    # STEP 3: DETERMINE STATUS
    if "VERIFICATION_PASS" in simulation_output:
        status = "VERIFICATION_PASS"

    elif (
        "VERIFICATION_FAIL" in simulation_output
        or "TEST_FAIL" in simulation_output
    ):
        status = "VERIFICATION_FAIL"

    else:
        status = "VERIFICATION_INCONCLUSIVE"

    return {
        "status": status,
        "compile_return_code": compile_result.returncode,
        "compile_stdout": compile_stdout,
        "compile_stderr": compile_stderr,
        "simulation_return_code": simulation_result.returncode,
        "simulation_stdout": simulation_stdout,
        "simulation_stderr": simulation_stderr
    }


def extract_json(text):
    """
    Extract JSON from an AI response.
    """

    if isinstance(text, list):

        combined = ""

        for item in text:

            if isinstance(item, dict):
                if item.get("type") == "text":
                    combined += item.get("text", "")

            elif isinstance(item, str):
                combined += item

        text = combined

    text = str(text).strip()

    # Remove Markdown JSON fences if present
    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    return json.loads(text.strip())


def extract_verilog(response_content):
    """
    Extracts Verilog code from different AI response formats.
    """

    # Case 1: response is a list containing dictionaries
    if isinstance(response_content, list):

        extracted_text = ""

        for item in response_content:

            if isinstance(item, dict):

                if item.get("type") == "text":
                    extracted_text += item.get("text", "")

            elif isinstance(item, str):
                extracted_text += item

        response_content = extracted_text

    # Case 2: response is not a normal string
    elif not isinstance(response_content, str):

        response_content = str(response_content)

    code = response_content.strip()

    # Remove Markdown code fences
    code = re.sub(
        r"^```(?:verilog|v|hdl)?\s*",
        "",
        code,
        flags=re.IGNORECASE
    )

    code = re.sub(
        r"\s*```$",
        "",
        code
    )

    # Basic HDL validation
    if "module" not in code:
        raise ValueError("No Verilog module found.")

    if "endmodule" not in code:
        raise ValueError("endmodule is missing.")

    return code.strip()


def generate_final_report(state: VerilogAgentState):

    verification_status = state.get(
        "verification_status",
        "UNKNOWN"
    )

    rtl_validation = state.get(
        "rtl_validation"
    )

    testbench_validation = state.get(
        "testbench_validation"
    )

    compile_result = state.get(
        "compile_result"
    )

    simulation_result = state.get(
        "simulation_result"
    )

    history = state.get(
        "history",
        []
    )

    # RTL validation status
    if rtl_validation is None:
        rtl_status = "NOT_RUN"
        rtl_errors = []

    elif rtl_validation.get("valid", False):
        rtl_status = "PASS"
        rtl_errors = []

    else:
        rtl_status = "FAIL"
        rtl_errors = rtl_validation.get(
            "errors",
            []
        )

    # Testbench validation status
    if testbench_validation is None:
        testbench_status = "NOT_RUN"
        testbench_errors = []

    elif testbench_validation.get("valid", False):
        testbench_status = "PASS"
        testbench_errors = []

    else:
        testbench_status = "FAIL"
        testbench_errors = testbench_validation.get(
            "errors",
            []
        )

    # Compilation status
    if compile_result is None:
        compilation_status = "NOT_RUN"
        compile_return_code = None

    elif compile_result.get(
        "compile_return_code"
    ) == 0:

        compilation_status = "PASS"
        compile_return_code = 0

    else:

        compilation_status = "FAIL"
        compile_return_code = compile_result.get(
            "compile_return_code"
        )

    # Simulation status
    if simulation_result is None:

        simulation_status = "NOT_RUN"
        simulation_return_code = None

    elif verification_status == "VERIFICATION_PASS":

        simulation_status = "PASS"
        simulation_return_code = simulation_result.get(
            "simulation_return_code"
        )

    else:

        simulation_status = "FAIL"
        simulation_return_code = simulation_result.get(
            "simulation_return_code"
        )

    # Overall result
    if verification_status == "VERIFICATION_PASS":

        final_result = (
            "The generated RTL passed "
            "automated verification."
        )

    elif verification_status == "VERIFICATION_FAIL":

        final_result = (
            "The generated RTL failed "
            "automated verification."
        )

    elif verification_status == "UNKNOWN":

        final_result = (
            "Verification was not completed."
        )

    else:

        final_result = (
            f"Verification ended with status: "
            f"{verification_status}"
        )

    # Final report
    report = {

        "verification_status":
            verification_status,

        "rtl_repair_attempts":
            state.get(
                "repair_attempts",
                0
            ),

        "testbench_repair_attempts":
            state.get(
                "testbench_repair_attempts",
                0
            ),

        "rtl_validation": {
            "status": rtl_status,
            "errors": rtl_errors
        },

        "testbench_validation": {
            "status": testbench_status,
            "errors": testbench_errors
        },

        "compilation": {
            "status": compilation_status,
            "return_code": compile_return_code
        },

        "simulation": {
            "status": simulation_status,
            "return_code": simulation_return_code
        },

        "execution_history":
            history,

        "final_result":
            final_result
    }

    return report

def validate_testbench_interface(testbench_code, hardware_spec):
    errors = []

    if not re.search(r"\bmodule\s+\w+", testbench_code):
        errors.append("Testbench module declaration not found.")

    if "endmodule" not in testbench_code:
        errors.append("endmodule not found.")

    dut_name = hardware_spec["module_name"]

    if not re.search(
        rf"\b{re.escape(dut_name)}\b",
        testbench_code
    ):
        errors.append(
            f"DUT module '{dut_name}' is not referenced in the testbench."
        )

    for port in hardware_spec["ports"]:
        port_name = port["name"]

        if not re.search(
            rf"\b{re.escape(port_name)}\b",
            testbench_code
        ):
            errors.append(
                f"Port '{port_name}' is not referenced in the testbench."
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }

def validate_testbench_safety(testbench_code):
    errors = []

    # Require a terminating simulation statement.
    if "$finish" not in testbench_code and "$stop" not in testbench_code:
        errors.append(
            "Testbench does not contain $finish or $stop."
        )

    # Detect potentially unbounded forever loops.
    if re.search(
        r"\bforever\s+begin\b",
        testbench_code,
        re.IGNORECASE
    ):
        errors.append(
            "Unbounded forever loop detected."
        )

    # Detect bounded loops whose loop variable can wrap
    # before reaching the requested limit.
    loop_pattern = re.compile(
        r"for\s*\(\s*reg\s*\[\s*(\d+)\s*:\s*0\s*\]\s*"
        r"(\w+)\s*=\s*0\s*;\s*\2\s*<\s*(\d+)",
        re.IGNORECASE
    )

    for match in loop_pattern.finditer(testbench_code):
        width = int(match.group(1)) + 1
        limit = int(match.group(3))
        max_value = (2 ** width) - 1

        if limit > max_value:
            errors.append(
                f"Loop variable '{match.group(2)}' with width "
                f"{width} bits cannot safely reach loop limit {limit}."
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }

