from app.core.state import VerilogAgentState

from app.core.config import (
    MAX_RTL_REPAIR_ATTEMPTS,
    MAX_TESTBENCH_REPAIR_ATTEMPTS,
)


def clarification_router(state: VerilogAgentState):
    """
    Decide whether the workflow should continue to
    hardware specification or stop for clarification.
    """

    if state.get("clarification_required", False):
        return "clarification_required"

    return "continue"


def simulation_result_router_v2(state: VerilogAgentState):
    """
    Route simulation results to the final report or
    debugging stage.
    """

    status = state.get(
        "verification_status",
        ""
    )

    if status == "VERIFICATION_PASS":
        return "pass"

    if status in [
        "VERIFICATION_FAIL",
        "COMPILE_ERROR",
        "COMPILE_TIMEOUT",
        "SIMULATION_TIMEOUT",
        "SIMULATION_ERROR",
        "VERIFICATION_INCONCLUSIVE",
    ]:
        return "fail"

    return "fail"


def bounded_debug_router(state: VerilogAgentState):
    """
    Decide whether a failed verification should go to
    RTL repair, testbench repair, or stop because the
    maximum repair attempts have been reached.
    """

    analysis = state.get(
        "analysis",
        {}
    )

    failure_category = analysis.get(
        "failure_category",
        ""
    ).lower()

    testbench_change_required = analysis.get(
        "testbench_change_required",
        False
    )

    rtl_attempts = state.get(
        "repair_attempts",
        0
    )

    testbench_attempts = state.get(
        "testbench_repair_attempts",
        0
    )

    if (
        testbench_change_required
        or "testbench" in failure_category
    ):

        if testbench_attempts >= MAX_TESTBENCH_REPAIR_ATTEMPTS:
            return "max_attempts"

        return "testbench_repair"

    if rtl_attempts >= MAX_RTL_REPAIR_ATTEMPTS:
        return "max_attempts"

    return "rtl_repair"


def repaired_rtl_validation_router(state: VerilogAgentState):
    """
    Decide what to do after an RTL repair is validated.
    """

    validation = state.get(
        "rtl_validation",
        {}
    )

    attempts = state.get(
        "repair_attempts",
        0
    )

    if validation.get("valid", False):
        return "simulation"

    if attempts >= MAX_RTL_REPAIR_ATTEMPTS:
        return "max_attempts"

    return "repair"
