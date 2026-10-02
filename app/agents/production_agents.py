import re
import tempfile
from pathlib import Path

from app.core.state import (
    VerilogAgentState,
    HardwareSpecification,
)

from app.core.llm import llm

from app.utils.helpers import validate_testbench_interface
from app.utils.helpers import validate_testbench_safety
from app.utils.helpers import (
    append_history,
    compile_and_simulate,
    extract_json,
    extract_verilog,
    generate_final_report,
)

def requirement_understanding_agent_v2(
    state: VerilogAgentState
):
    user_request = state["user_request"]

    prompt = f"""
You are an expert digital hardware requirements analyst.

Your job is to understand a user's hardware request written
in ordinary natural language and determine whether enough
information is available to generate correct synthesizable RTL.

USER REQUEST:
{user_request}

Return ONLY valid JSON using exactly this structure:

{{
  "hardware_type": "string",
  "understanding": "clear description of what the user wants",
  "clarification_required": false,
  "clarification_questions": [],
  "inferred_requirements": [
    "requirement 1",
    "requirement 2"
  ]
}}

============================================================
CLARIFICATION POLICY
============================================================

Set clarification_required to TRUE when an essential
hardware behavior is missing and different reasonable
interpretations would produce different RTL.

For example, for a counter, clarification may be required
when the user has not specified essential information such as:

- counter width or range
- count direction, when it is not clear
- reset behavior, when a reset is expected but unspecified
- enable behavior, when the request implies conditional counting

Do NOT ask unnecessary questions about:

- implementation style
- simulator
- FPGA/ASIC technology
- timing constraints
- physical/electrical characteristics
- coding style
- other details that are not necessary to determine the
  requested logical behavior

============================================================
IMPORTANT
============================================================

Do NOT assume an unspecified requirement if multiple
reasonable hardware implementations are possible.

However, do NOT ask for information that can be safely
inferred from the request.

Examples:

Example 1:
"I want a 2-to-1 multiplexer. When sel is 0 select a,
when sel is 1 select b."

Result:
clarification_required = false

Example 2:
"I want a D flip-flop that captures d on the rising edge
of clk."

Result:
clarification_required = false

Example 3:
"I want a digital counter."

Result:
clarification_required = true

Possible clarification questions:
- "What counter width or counting range do you want?"
- "Should it count upward, downward, or both?"

Example 4:
"I want a 4-bit up counter with active-high synchronous
reset."

Result:
clarification_required = false

The goal is to avoid both:
1. unnecessary clarification questions
2. guessing essential hardware behavior

Return ONLY valid JSON.
"""

    response = llm.invoke(prompt)

    understanding = extract_json(
        response.content
    )

    history = append_history(
        state,
        {
            "agent":
                "requirement_understanding_agent_v2",
            "status":
                "completed"
        }
    )

    return {
        "hardware_understanding":
            understanding,

        "clarification_required":
            understanding.get(
                "clarification_required",
                False
            ),

        "clarification_questions":
            understanding.get(
                "clarification_questions",
                []
            ),

        "history":
            history
    }


def hardware_specification_agent(state: VerilogAgentState):

    understanding = state["hardware_understanding"]

    # If clarification is required, stop here.
    if state.get("clarification_required", False):

        history = append_history(
            state,
            {
                "agent": "hardware_specification_agent",
                "status": "waiting_for_clarification"
            }
        )

        return {
            "history": history
        }

    prompt = f"""
You are an expert digital hardware specification engineer.

Convert the following understood hardware requirement into
a precise structured specification for RTL generation.

UNDERSTANDING:
{understanding}

Return ONLY valid JSON using exactly this structure:

{{
  "module_name": "string",
  "description": "string",
  "ports": [
    {{
      "name": "string",
      "direction": "input or output",
      "width": 1
    }}
  ],
  "clock": "string or null",
  "reset": "string or null",
  "reset_polarity": "active-high, active-low, or null",
  "reset_type": "synchronous, asynchronous, or null",
  "requirements": [
    "precise requirement 1",
    "precise requirement 2"
  ]
}}

Rules:

1. Use only supported information.
2. Do not invent unnecessary ports.
3. Preserve user-specified port names.
4. Choose simple conventional names when names are absent.
5. Use width 1 if width is unspecified.
6. Identify clock only when required.
7. Identify reset only when required.
8. Identify reset polarity only when specified or clearly implied.
9. Identify reset type only when specified or clearly implied.
10. Describe precise hardware behavior.
11. The specification must be sufficient for RTL generation.
12. Return JSON only.
"""

    response = llm.invoke(prompt)

    structured_data = extract_json(response.content)

    hardware_spec = HardwareSpecification.model_validate(
        structured_data
    )

    history = append_history(
        state,
        {
            "agent": "hardware_specification_agent",
            "status": "completed"
        }
    )

    return {
        "hardware_spec": hardware_spec.model_dump(),
        "history": history
    }


def rtl_generation_agent(state: VerilogAgentState):
    """
    Generate synthesizable IEEE Verilog-2001 RTL
    from the structured hardware specification.
    """

    hardware_spec = state["hardware_spec"]

    prompt = f"""
You are an expert RTL design engineer.

Generate synthesizable IEEE Verilog-2001 RTL
from the following hardware specification.

HARDWARE SPECIFICATION:
{hardware_spec}

IMPORTANT RULES:

1. Implement exactly the specified functionality.

2. Preserve the module name exactly.

3. Preserve every port name exactly.

4. Preserve every port direction exactly.

5. Preserve every port width exactly.

6. Do not add unnecessary ports.

7. Do not remove required ports.

8. Use synthesizable Verilog-2001.

9. Use combinational logic for combinational requirements.

10. Use sequential logic with always @(posedge clock)
    when clocked behavior is required.

11. Implement reset behavior exactly when specified.

12. Do not generate a testbench.

13. Do not include explanations.

14. Return ONLY the Verilog RTL code.

The output must contain a complete module beginning
with 'module' and ending with 'endmodule'.
"""

    response = llm.invoke(prompt)

    rtl_code = extract_verilog(response.content)

    return {
        "rtl_code": rtl_code,
        "history": [
            {
                "agent": "rtl_generation_agent",
                "status": "completed"
            }
        ]
    }


def rtl_validation_agent(state: VerilogAgentState):

    rtl_code = state["rtl_code"]
    hardware_spec = state["hardware_spec"]

    errors = []

    # -----------------------------------------------------
    # Check module declaration
    # -----------------------------------------------------

    module_match = re.search(
        r"\bmodule\s+([A-Za-z_][A-Za-z0-9_]*)",
        rtl_code
    )

    if not module_match:
        errors.append(
            "Module declaration not found."
        )
    else:
        actual_module = module_match.group(1)
        expected_module = hardware_spec["module_name"]

        if actual_module != expected_module:
            errors.append(
                f"Expected module '{expected_module}' "
                f"but found '{actual_module}'."
            )

    # -----------------------------------------------------
    # Check endmodule
    # -----------------------------------------------------

    if "endmodule" not in rtl_code:
        errors.append(
            "endmodule not found."
        )

    # -----------------------------------------------------
    # Check every required port
    # -----------------------------------------------------

    for port in hardware_spec["ports"]:

        port_name = port["name"]
        direction = port["direction"]
        width = port.get("width", 1)

        # Check port name
        if not re.search(
            rf"\b{re.escape(port_name)}\b",
            rtl_code
        ):
            errors.append(
                f"Required port '{port_name}' not found."
            )
            continue

        # Check direction
        direction_pattern = (
            rf"\b{direction}\b"
            rf"(?:\s+wire|\s+reg)?"
            rf"(?:\s*\[[^\]]+\])?"
            rf"\s+{re.escape(port_name)}\b"
        )

        if not re.search(
            direction_pattern,
            rtl_code
        ):
            errors.append(
                f"Port '{port_name}' may not have "
                f"the correct direction."
            )

        # Check width
        if width > 1:

            expected_range = (
                f"[{width - 1}:0]"
            )

            if expected_range not in rtl_code:
                errors.append(
                    f"Port '{port_name}' does not appear "
                    f"to have width {width}."
                )

    # -----------------------------------------------------
    # Check module count
    # -----------------------------------------------------

    module_count = len(
        re.findall(
            r"\bmodule\s+",
            rtl_code
        )
    )

    if module_count != 1:
        errors.append(
            f"Expected exactly one module, "
            f"found {module_count}."
        )

    # -----------------------------------------------------
    # Final validation result
    # -----------------------------------------------------

    validation = {
        "status": "PASS" if len(errors) == 0 else "FAIL",
        "valid": len(errors) == 0,
        "errors": errors
    }

    history = append_history(
        state,
        {
            "agent": "rtl_validation_agent",
            "status": (
                "passed"
                if validation["status"] == "PASS"
                else "failed"
            )
        }
    )

    return {
        "rtl_validation": validation,
        "history": history
    }


def testbench_generation_agent(state: VerilogAgentState):
    """
    Generate a self-checking Verilog testbench from
    the hardware specification.
    """

    hardware_spec = state["hardware_spec"]
    rtl_code = state["rtl_code"]

    prompt = f"""
You are an expert digital verification engineer.

Generate a self-checking IEEE Verilog-2001 testbench
for the RTL design described below.

HARDWARE SPECIFICATION:
{hardware_spec}

RTL CODE:
{rtl_code}

IMPORTANT RULES:

1. The testbench must verify the FUNCTIONAL REQUIREMENTS
   from the hardware specification.

2. The testbench must instantiate the DUT using the exact
   module name from the specification.

3. Use the exact port names from the specification.

4. Do not modify the DUT.

5. Do not generate or modify RTL.

6. The testbench must be self-checking.

7. The testbench must print:

   VERIFICATION_PASS

   when all required tests pass.

8. The testbench must print:

   VERIFICATION_FAIL

   if any required test fails.

9. Include meaningful test cases covering the specified
   functional behavior.

10. For combinational circuits, test all meaningful input
    combinations whenever practical.

11. For sequential circuits, include appropriate clock
    generation and reset testing when required.

12. Do NOT use loops whose control variable can overflow
    and cause an infinite loop.

13. If a loop is used, make sure its termination condition
    is guaranteed.

14. The simulation must terminate using $finish.

15. Do not wait indefinitely for an event.

16. Do not depend on undocumented simulator behavior.

17. Do not use SystemVerilog-only features.

18. Use IEEE Verilog-2001 syntax compatible with Icarus Verilog.

19. Return ONLY the complete testbench code.

20. Do not include markdown code fences.

The testbench must independently verify the intended
behavior rather than simply checking that the RTL compiles.
"""

    response = llm.invoke(prompt)

    testbench_code = extract_verilog(response.content)

    return {
        "testbench_code": testbench_code,
        "history": [
            {
                "agent": "testbench_generation_agent",
                "status": "completed"
            }
        ]
    }


def complete_testbench_validation_agent(state: VerilogAgentState):
    """
    Validate both the testbench interface and its simulation safety.
    """

    testbench_code = state["testbench_code"]
    hardware_spec = state["hardware_spec"]

    # Interface validation
    interface_result = validate_testbench_interface(
        testbench_code,
        hardware_spec
    )

    # Safety validation
    safety_result = validate_testbench_safety(
        testbench_code
    )

    errors = []

    errors.extend(
        interface_result.get("errors", [])
    )

    errors.extend(
        safety_result.get("errors", [])
    )

    validation = {
        "status": "PASS" if len(errors) == 0 else "FAIL",
        "valid": len(errors) == 0,
        "errors": errors,
        "interface_valid": interface_result["valid"],
        "safety_valid": safety_result["valid"]
    }

    return {
        "testbench_validation": validation,
        "history": [{
            "agent": "complete_testbench_validation_agent",
            "status": "passed" if validation["valid"] else "failed"
        }]
    }


def simulation_agent(state: VerilogAgentState):
    """
    Save the generated RTL and testbench, then compile
    and simulate them using Icarus Verilog.
    """

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as temp_dir:

        workspace = Path(temp_dir)

        design_file = workspace / "design.v"
        testbench_file = workspace / "testbench.v"

        # Save RTL
        design_file.write_text(
            state["rtl_code"],
            encoding="utf-8"
        )

        # Save testbench
        testbench_file.write_text(
            state["testbench_code"],
            encoding="utf-8"
        )

        # Compile and simulate
        simulation_result = compile_and_simulate(
            workspace=workspace,
            design_file=design_file,
            testbench_file=testbench_file
        )

    return {
        "compile_result": {
            "compile_return_code": simulation_result[
                "compile_return_code"
            ],
            "compile_stdout": simulation_result[
                "compile_stdout"
            ],
            "compile_stderr": simulation_result[
                "compile_stderr"
            ]
        },
        "simulation_result": {
            "simulation_return_code": simulation_result[
                "simulation_return_code"
            ],
            "simulation_stdout": simulation_result[
                "simulation_stdout"
            ],
            "simulation_stderr": simulation_result[
                "simulation_stderr"
            ]
        },
        "verification_status": simulation_result["status"],
        "history": [
            {
                "agent": "simulation_agent",
                "status": simulation_result["status"]
            }
        ]
    }


def debug_analysis_agent(state: VerilogAgentState):
    """
    Analyze compilation/simulation failures and produce
    a structured debugging explanation for the repair agent.
    """

    user_request = state.get("user_request", "")
    hardware_spec = state.get("hardware_spec", {})
    rtl_code = state.get("rtl_code", "")
    testbench_code = state.get("testbench_code", "")

    compile_result = state.get("compile_result", {})
    simulation_result = state.get("simulation_result", {})

    compile_stdout = compile_result.get(
        "compile_stdout",
        ""
    )

    compile_stderr = compile_result.get(
        "compile_stderr",
        ""
    )

    simulation_stdout = simulation_result.get(
        "simulation_stdout",
        ""
    )

    simulation_stderr = simulation_result.get(
        "simulation_stderr",
        ""
    )

    verification_status = state.get(
        "verification_status",
        ""
    )

    prompt = f"""
You are an expert digital hardware debugging engineer.

Analyze the failed RTL verification attempt.

USER REQUEST:
{user_request}

HARDWARE SPECIFICATION:
{hardware_spec}

VERIFICATION STATUS:
{verification_status}

RTL CODE:
{rtl_code}

TESTBENCH CODE:
{testbench_code}

COMPILER STDOUT:
{compile_stdout}

COMPILER STDERR:
{compile_stderr}

SIMULATION STDOUT:
{simulation_stdout}

SIMULATION STDERR:
{simulation_stderr}

Your job is to identify the likely cause of the failure.

IMPORTANT RULES:

1. Focus on the RTL implementation.

2. Do NOT modify the testbench.

3. Treat the hardware specification as the intended
   functional behavior.

4. Distinguish between:
   - syntax/compile errors
   - incorrect RTL functionality
   - port/interface mismatch
   - timing/sequential logic problems
   - other implementation problems

5. If the testbench itself appears problematic, explicitly
   identify that rather than changing the RTL blindly.

6. Do not invent errors that are not supported by the
   available evidence.

7. Provide actionable information that a repair agent
   can use.

Return ONLY valid JSON using this structure:

{{
  "failure_category": "string",
  "root_cause": "string",
  "evidence": [
    "evidence 1",
    "evidence 2"
  ],
  "repair_guidance": [
    "specific repair instruction 1",
    "specific repair instruction 2"
  ],
  "testbench_change_required": false
}}
"""

    response = llm.invoke(prompt)

    analysis = extract_json(response.content)

    return {
        "analysis": analysis,
        "history": [
            {
                "agent": "debug_analysis_agent",
                "status": "completed"
            }
        ]
    }


def rtl_repair_agent(state: VerilogAgentState):
    """
    Repair RTL based on verification/debugging evidence.

    The testbench is strictly read-only.
    """

    hardware_spec = state["hardware_spec"]
    rtl_code = state["rtl_code"]
    testbench_code = state["testbench_code"]
    analysis = state.get("analysis", {})

    current_attempts = state.get(
        "repair_attempts",
        0
    )

    prompt = f"""
You are an expert RTL repair engineer.

A generated Verilog design failed verification.

Your task is to repair ONLY the RTL implementation.

HARDWARE SPECIFICATION:
{hardware_spec}

CURRENT RTL:
{rtl_code}

TESTBENCH:
{testbench_code}

DEBUG ANALYSIS:
{analysis}

CURRENT REPAIR ATTEMPT:
{current_attempts + 1}

STRICT RULES:

1. Modify ONLY the RTL.

2. NEVER modify the testbench.

3. NEVER weaken, remove, bypass, or change testbench
   checks to make the design pass.

4. Preserve the exact module name.

5. Preserve every required port name.

6. Preserve every required port direction.

7. Preserve every required port width.

8. Implement the hardware specification exactly.

9. Use synthesizable IEEE Verilog-2001.

10. Do not add unnecessary ports.

11. Do not add simulation-only behavior.

12. Do not use delays such as #10 in the RTL.

13. Do not hard-code outputs merely to satisfy the
    current test vectors.

14. Fix the underlying implementation problem.

15. Return ONLY the complete corrected Verilog RTL.

The result must contain exactly the repaired RTL module.
"""

    response = llm.invoke(prompt)

    repaired_rtl = extract_verilog(
        response.content
    )

    return {
        "rtl_code": repaired_rtl,
        "repair_attempts": current_attempts + 1,
        "history": [
            {
                "agent": "rtl_repair_agent",
                "status": "completed",
                "attempt": current_attempts + 1
            }
        ]
    }


def production_testbench_repair_agent(state: VerilogAgentState):
    """
    Production testbench repair agent.

    Uses the validated V2 repair logic.
    """

    return testbench_repair_agent_v2(state)


def repaired_rtl_validation_node(state: VerilogAgentState):

    result = rtl_validation_agent(state)

    return {
        "rtl_validation": result["rtl_validation"],
        "history": result["history"]
    }


def repaired_testbench_validation_node(state: VerilogAgentState):

    result = complete_testbench_validation_agent(state)

    history = append_history(
        state,
        result["history"]
    )

    return {
        "testbench_validation": result["testbench_validation"],
        "history": history
    }


def final_report_agent(state: VerilogAgentState):
    """
    Generates the final structured verification report
    after the autonomous verification workflow completes.
    """

    report = generate_final_report(state)

    history = append_history(
        state,
        {
            "agent": "final_report_agent",
            "status": "completed"
        }
    )

    return {
        "final_report": report,
        "history": history
    }


def testbench_repair_agent_v2(
    state: VerilogAgentState
):
    hardware_spec = state["hardware_spec"]
    rtl_code = state["rtl_code"]
    testbench_code = state["testbench_code"]
    validation = state.get(
        "testbench_validation",
        {}
    )
    analysis = state.get(
        "analysis",
        {}
    )

    current_attempts = state.get(
        "testbench_repair_attempts",
        0
    )

    prompt = f"""
You are an expert digital verification engineer
specialized in synchronous RTL verification.

A generated Verilog testbench failed functional
simulation.

Your task is to repair ONLY the testbench.

============================================================
HARDWARE SPECIFICATION
============================================================

{hardware_spec}

============================================================
RTL DESIGN
============================================================

{rtl_code}

============================================================
CURRENT TESTBENCH
============================================================

{testbench_code}

============================================================
TESTBENCH VALIDATION
============================================================

{validation}

============================================================
DEBUG ANALYSIS
============================================================

{analysis}

============================================================
CURRENT REPAIR ATTEMPT
============================================================

{current_attempts + 1}

============================================================
CRITICAL TIMING ANALYSIS REQUIREMENT
============================================================

Before generating the repaired testbench, mentally
simulate the DUT cycle by cycle.

For every synchronous output:

1. Identify the clock edge that updates the DUT.
2. Determine the DUT output value immediately after
   that clock edge.
3. Determine when the testbench samples the output.
4. Determine what the expected value must be at that
   exact sampling point.
5. Ensure the expected-value model advances in the same
   sequence as the DUT.

For example, if the RTL contains:

    always @(posedge clk)
        count <= count + 1'b1;

and the testbench does:

    @(posedge clk);
    #1;
    if (count !== expected_count)

then the DUT has ALREADY performed the increment before
the comparison.

Therefore expected_count must represent the NEW DUT state,
not the state before the clock edge.

============================================================
SYNCHRONOUS RESET ANALYSIS
============================================================

For synchronous reset:

    always @(posedge clk) begin
        if (reset)
            q <= 0;
        else
            q <= next_value;
    end

reset only takes effect at the active clock edge.

The testbench must therefore:

1. Assert reset.
2. Provide the appropriate active clock edge.
3. Verify the reset state.
4. Deassert reset.
5. Predict the state produced by the NEXT active edge.
6. Compare against that predicted state.

Do NOT compare a pre-edge expected value with a
post-edge DUT value.

============================================================
EXPECTED-VALUE MODEL
============================================================

When testing sequential logic, construct the expected
value according to the SAME state transition performed
by the DUT.

For a counter:

    expected_next = expected_current + 1

must occur conceptually BEFORE comparing the DUT output
after the active clock edge.

The exact implementation is up to you, but the comparison
must represent the DUT's post-edge state.

============================================================
STRICT RULES
============================================================

1. Modify ONLY the testbench.
2. NEVER modify the RTL.
3. NEVER weaken verification checks.
4. NEVER remove verification checks.
5. NEVER bypass verification checks.
6. Preserve the exact DUT module name.
7. Preserve all DUT port names.
8. Verify every functional requirement.
9. The testbench must be self-checking.
10. Print VERIFICATION_PASS when all tests pass.
11. Print VERIFICATION_FAIL when any test fails.
12. Every loop must terminate.
13. Loop variables must have sufficient width.
14. Avoid infinite loops.
15. Do not use unbounded forever loops for test execution.
16. Include $finish.
17. Do not use indefinite waits.
18. Use IEEE Verilog-2001 syntax.
19. Make the testbench compatible with Icarus Verilog.
20. Do not modify the DUT.
21. Do not hard-code outputs for specific test vectors.
22. Verify actual hardware behavior.
23. Preserve meaningful functional coverage.
24. Do not simply remove failing tests.
25. Do not merely shift the comparison by one cycle
    without updating the expected-value model.
26. Return ONLY Verilog code.
27. Do not use markdown code fences.

============================================================
FINAL SELF-CHECK BEFORE RETURNING
============================================================

Before returning the testbench, verify mentally:

- Does reset get sampled on the correct clock edge?
- After reset is released, what is the DUT output
  immediately after the first active edge?
- Does expected_count represent that same value?
- Does the expected model wrap at the correct value?
- Is every comparison aligned with the corresponding
  DUT state?
- Does the testbench terminate?
- Does VERIFICATION_PASS occur only when all checks pass?

Return ONLY the repaired Verilog testbench.
"""

    response = llm.invoke(prompt)

    repaired_testbench = extract_verilog(
        response.content
    )

    new_attempt = current_attempts + 1

    history = append_history(
        state,
        {
            "agent":
                "testbench_repair_agent_v2",
            "status":
                "completed",
            "attempt":
                new_attempt
        }
    )

    return {
        "testbench_code":
            repaired_testbench,

        "testbench_repair_attempts":
            new_attempt,

        "history":
            history
    }
