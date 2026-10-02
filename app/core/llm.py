from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import (
    GEMINI_API_KEY,
    MODEL_NAME,
)


def get_llm():
    """
    Create the LLM client used by the Verilog agent system.

    The API key is obtained from the environment through
    the configuration layer.
    """

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not configured."
        )

    return ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=GEMINI_API_KEY,
        temperature=0,
    )


llm = get_llm()
