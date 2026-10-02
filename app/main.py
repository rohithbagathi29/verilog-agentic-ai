from app.graph import production_graph_v7


def run_verilog_agent(user_request: str):
    if not user_request or not user_request.strip():
        raise ValueError("user_request cannot be empty.")

    result = production_graph_v7.invoke({
        "user_request": user_request
    })

    return result
