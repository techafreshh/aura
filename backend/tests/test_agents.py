import pytest
from pydantic_ai.models.test import TestModel
from models.schemas import EvaluationResult, FinalReport, SectionGrade

# Import the agents
from agent.evaluator import evaluator_agent
from agent.reporter import reporter_agent

@pytest.mark.asyncio
async def test_evaluator_agent():
    # Use TestModel for deterministic testing without API calls
    test_model = TestModel(custom_output_args={
        "score": "Good",
        "feedback": "Solid answer with good examples.",
        "suggested_follow_up": "Can you elaborate on the testing strategy?"
    })
    
    # Run the agent with the TestModel
    with evaluator_agent.override(model=test_model):
        result = await evaluator_agent.run("Test prompt")
        
    assert isinstance(result.output, EvaluationResult)
    assert result.output.score == "Good"
    assert result.output.feedback == "Solid answer with good examples."
    assert result.output.suggested_follow_up == "Can you elaborate on the testing strategy?"

@pytest.mark.asyncio
async def test_reporter_agent():
    # Use TestModel for deterministic testing without API calls
    test_model = TestModel(custom_output_args={
        "candidate_name": "Jane Doe",
        "overall_score": 85,
        "section_grades": [
            SectionGrade(section_name="Technical", score=9, comments="Excellent coding skills.")
        ],
        "strengths": ["Python", "System Design"],
        "weaknesses": ["Frontend"],
        "recommendation": "Strong Hire",
        "summary": "Jane is a great fit for the backend role."
    })
    
    # Run the agent with the TestModel
    with reporter_agent.override(model=test_model):
        result = await reporter_agent.run("Test transcript")
        
    assert isinstance(result.output, FinalReport)
    assert result.output.candidate_name == "Jane Doe"
    assert result.output.overall_score == 85
    assert len(result.output.section_grades) == 1
    assert result.output.recommendation == "Strong Hire"
