from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.main import run_verilog_agent


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_FILE = PROJECT_ROOT / "frontend" / "index.html"


app = FastAPI(
    title="Verilog Agentic AI",
    description="AI-powered Verilog RTL generation and automated verification system.",
    version="1.0.0",
)


class GenerateRequest(BaseModel):
    user_request: str = Field(
        ...,
        min_length=1,
        description="Natural-language hardware requirement."
    )


class GenerateResponse(BaseModel):
    verification_status: str | None = None
    rtl_code: str | None = None
    testbench_code: str | None = None
    final_report: Dict[str, Any] = Field(default_factory=dict)


@app.get("/", include_in_schema=False)
def frontend():
    if not FRONTEND_FILE.exists():
        raise HTTPException(
            status_code=500,
            detail="Frontend index.html was not found."
        )

    return FileResponse(
        FRONTEND_FILE,
        media_type="text/html"
    )


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/generate", response_model=GenerateResponse)
def generate_verilog(request: GenerateRequest):
    try:
        result = run_verilog_agent(request.user_request)

        return GenerateResponse(
            verification_status=result.get("verification_status"),
            rtl_code=result.get("rtl_code"),
            testbench_code=result.get("testbench_code"),
            final_report=result.get("final_report", {})
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )
