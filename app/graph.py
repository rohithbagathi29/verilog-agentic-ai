from langgraph.graph import StateGraph, START, END

from app.core.state import VerilogAgentState

from app.agents.production_agents import (
    requirement_understanding_agent_v2,
    hardware_specification_agent,
    rtl_generation_agent,
    rtl_validation_agent,
    testbench_generation_agent,
    complete_testbench_validation_agent,
    simulation_agent,
    debug_analysis_agent,
    rtl_repair_agent,
    production_testbench_repair_agent,
    repaired_rtl_validation_node,
    repaired_testbench_validation_node,
    final_report_agent,
)

from app.agents.routers import (
    clarification_router,
    simulation_result_router_v2,
    bounded_debug_router,
    repaired_rtl_validation_router,
)


def build_production_graph():
    """
    Build the production V7 Verilog Agentic AI graph.

    The graph implements:
        requirements
        -> specification
        -> RTL generation
        -> RTL validation
        -> testbench generation
        -> testbench validation
        -> simulation
        -> debugging
        -> bounded RTL/TB repair
        -> revalidation
        -> final report
    """

    builder = StateGraph(VerilogAgentState)

    # -----------------------------------------------------
    # Production nodes
    # -----------------------------------------------------

    builder.add_node(
        "requirement_understanding",
        requirement_understanding_agent_v2,
    )

    builder.add_node(
        "hardware_specification",
        hardware_specification_agent,
    )

    builder.add_node(
        "rtl_generation",
        rtl_generation_agent,
    )

    builder.add_node(
        "rtl_validation",
        rtl_validation_agent,
    )

    builder.add_node(
        "testbench_generation",
        testbench_generation_agent,
    )

    builder.add_node(
        "testbench_validation",
        complete_testbench_validation_agent,
    )

    builder.add_node(
        "simulation",
        simulation_agent,
    )

    builder.add_node(
        "debug_analysis",
        debug_analysis_agent,
    )

    builder.add_node(
        "rtl_repair",
        rtl_repair_agent,
    )

    builder.add_node(
        "testbench_repair",
        production_testbench_repair_agent,
    )

    builder.add_node(
        "rtl_revalidation",
        repaired_rtl_validation_node,
    )

    builder.add_node(
        "testbench_revalidation",
        repaired_testbench_validation_node,
    )

    builder.add_node(
        "final_report",
        final_report_agent,
    )

    # -----------------------------------------------------
    # Initial flow
    # -----------------------------------------------------

    builder.add_edge(
        START,
        "requirement_understanding",
    )

    builder.add_conditional_edges(
        "requirement_understanding",
        clarification_router,
        {
            "clarification_required": END,
            "continue": "hardware_specification",
        },
    )

    builder.add_edge(
        "hardware_specification",
        "rtl_generation",
    )

    builder.add_edge(
        "rtl_generation",
        "rtl_validation",
    )

    # -----------------------------------------------------
    # RTL validation
    # -----------------------------------------------------

    builder.add_conditional_edges(
        "rtl_validation",
        lambda state: (
            "valid"
            if state.get("rtl_validation", {}).get("status") == "PASS"
            else "invalid"
        ),
        {
            "valid": "testbench_generation",
            "invalid": "final_report",
        },
    )

    # -----------------------------------------------------
    # Testbench generation / validation
    # -----------------------------------------------------

    builder.add_edge(
        "testbench_generation",
        "testbench_validation",
    )

    builder.add_conditional_edges(
        "testbench_validation",
        lambda state: (
            "valid"
            if state.get("testbench_validation", {}).get("status") == "PASS"
            else "invalid"
        ),
        {
            "valid": "simulation",
            "invalid": "testbench_repair",
        },
    )

    # -----------------------------------------------------
    # Simulation
    # -----------------------------------------------------

    builder.add_conditional_edges(
        "simulation",
        simulation_result_router_v2,
        {
            "pass": "final_report",
            "fail": "debug_analysis",
        },
    )

    # -----------------------------------------------------
    # Debugging / bounded repair
    # -----------------------------------------------------

    builder.add_conditional_edges(
        "debug_analysis",
        bounded_debug_router,
        {
            "rtl_repair": "rtl_repair",
            "testbench_repair": "testbench_repair",
            "max_attempts": "final_report",
        },
    )

    # -----------------------------------------------------
    # RTL repair path
    # -----------------------------------------------------

    builder.add_edge(
        "rtl_repair",
        "rtl_revalidation",
    )

    builder.add_conditional_edges(
        "rtl_revalidation",
        repaired_rtl_validation_router,
        {
            "simulation": "simulation",
            "repair": "rtl_repair",
        },
    )

    # -----------------------------------------------------
    # Testbench repair path
    # -----------------------------------------------------

    builder.add_edge(
        "testbench_repair",
        "testbench_revalidation",
    )

    builder.add_conditional_edges(
        "testbench_revalidation",
        lambda state: (
            "valid"
            if state.get("testbench_validation", {}).get("status") == "PASS"
            else "repair"
        ),
        {
            "valid": "simulation",
            "repair": "testbench_repair",
        },
    )

    # -----------------------------------------------------
    # Final report
    # -----------------------------------------------------

    builder.add_edge(
        "final_report",
        END,
    )

    return builder


builder_v7 = build_production_graph()

verilog_agentic_graph_v7 = builder_v7.compile()

production_graph_v7 = verilog_agentic_graph_v7
