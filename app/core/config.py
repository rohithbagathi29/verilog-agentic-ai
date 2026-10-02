import os


MODEL_NAME = os.getenv(
    "VERILOG_AGENT_MODEL",
    "gemini-3.1-flash-lite-preview"
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


MAX_RTL_REPAIR_ATTEMPTS = int(
    os.getenv("MAX_RTL_REPAIR_ATTEMPTS", "3")
)

MAX_TESTBENCH_REPAIR_ATTEMPTS = int(
    os.getenv("MAX_TESTBENCH_REPAIR_ATTEMPTS", "3")
)


def validate_configuration():
    """
    Validate required runtime configuration.

    The API key is intentionally read from the environment
    and is never stored in source code.
    """

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not configured."
        )

    return True
