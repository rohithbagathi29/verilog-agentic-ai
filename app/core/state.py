from typing import TypedDict, Dict, Any, List, Optional
from pydantic import BaseModel, Field


class PortDefinition(BaseModel):
    name: str
    direction: str
    width: int = 1


class HardwareSpecification(BaseModel):
    module_name: str
    description: str
    ports: List[PortDefinition]
    clock: Optional[str] = None
    reset: Optional[str] = None
    reset_polarity: Optional[str] = None
    reset_type: Optional[str] = None
    requirements: List[str] = Field(default_factory=list)


class VerilogAgentState(TypedDict, total=False):
    user_request: str
    hardware_understanding: Dict[str, Any]
    clarification_required: bool
    clarification_questions: List[str]
    hardware_spec: Dict[str, Any]
    rtl_code: str
    rtl_validation: Dict[str, Any]
    testbench_code: str
    testbench_validation: Dict[str, Any]
    compile_result: Dict[str, Any]
    simulation_result: Dict[str, Any]
    verification_status: str
    analysis: Dict[str, Any]
    repair_attempts: int
    testbench_repair_attempts: int
    history: List[Dict[str, Any]]
    final_report: Dict[str, Any]
