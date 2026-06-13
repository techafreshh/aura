from dataclasses import dataclass, field
from models.schemas import InterviewPlan


@dataclass
class InterviewContext:
    plan: InterviewPlan
    current_phase: str = "Intro"
    transcript: list = field(default_factory=list)
    start_time: float = 0.0
    report_generated: bool = False
    wrap_up_triggered: bool = False
