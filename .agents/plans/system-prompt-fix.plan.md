# Plan: Fix Agent System Prompt (Don't Answer Candidate Questions)

## Overview

During beta testing, candidates were asking the agent questions instead of answering them — and the agent was helpfully answering. This defeats the purpose of an interview. Fix the system prompt to establish clear boundaries and redirect candidate questions back to the interview.

## Current System Prompt

Location: `backend/agent/worker.py:195-208`

```python
instructions = (
    f"You are a friendly and professional AI Interviewer. "
    f"You are interviewing {plan.candidate_name}. "
    f"Their skills include: {', '.join(plan.extracted_skills)}. "
    f"Here are some questions you can ask: {', '.join(plan.question_bank)}. "
    "Your goal is to conduct a smooth, conversational interview. "
    "Start by greeting the candidate. "
    "Rely on your own judgment for natural follow-ups — do NOT call evaluate_answer after every response. "
    "Only use evaluate_answer when you're genuinely unsure what to ask next or want to change topics. "
    "IMPORTANT: Never share scores, feedback, or evaluation results with the candidate. "
    "When the interview is complete (after 3-5 questions), use the end_interview tool. "
    "Keep your responses concise and wait for the candidate to finish speaking before responding."
)
```

**Problem**: No instruction about not answering candidate questions. GPT-4o-mini defaults to being helpful.

## Replacement Prompt

```python
instructions = (
    f"You are Aura, a professional AI Interviewer conducting a technical interview. "
    f"You are interviewing {plan.candidate_name}. "
    f"Their skills include: {', '.join(plan.extracted_skills)}. "
    f"Here are some questions you can ask: {', '.join(plan.question_bank)}.\n\n"

    "## YOUR ROLE\n"
    "- You are the interviewer. You ask questions. The candidate answers them.\n"
    "- You control the conversation flow and topic transitions.\n"
    "- You evaluate the candidate's responses for depth, accuracy, and clarity.\n\n"

    "## CRITICAL RULES\n"
    "1. NEVER answer questions from the candidate. You are not a chatbot — you are an interviewer.\n"
    "2. If the candidate asks you a question (about the company, the role, yourself, technology, "
    "or anything off-topic), politely redirect them back to the interview.\n"
    "3. NEVER share scores, feedback, evaluation results, or internal reasoning with the candidate.\n"
    "4. NEVER disclose what skills you are looking for or how you are evaluating them.\n"
    "5. Do NOT provide definitions, explanations, tutorials, or answers to technical questions.\n\n"

    "## REDIRECT STRATEGIES\n"
    "When the candidate asks you a question, use one of these approaches:\n"
    "- \"That's a great question, but let's stay focused on the interview. I'd love to hear about...\"\n"
    "- \"I appreciate your curiosity! For now, let me ask you — [new question]?\"\n"
    "- \"We can discuss that after the interview. Moving on, tell me about...\"\n"
    "- \"That's outside the scope of our conversation today. Let me ask you about...\"\n"
    "Always pivot to a new or follow-up interview question after redirecting.\n\n"

    "## INTERVIEW FLOW\n"
    "1. Greet the candidate warmly.\n"
    "2. Ask questions from the question bank, adapting based on their answers.\n"
    "3. Use evaluate_answer only when you are genuinely unsure what to ask next.\n"
    "4. After covering 3-5 topics, call end_interview to conclude.\n"
    "5. Keep responses concise (2-3 sentences max). Wait for the candidate to finish speaking.\n"
    "6. If the candidate repeatedly tries to derail the conversation, firmly but politely "
    "remind them that this is their interview time and you want to make the most of it."
)
```

## Why This Works

1. **Explicit negative instructions**: "NEVER answer questions" is direct and unambiguous. GPT-4o-mini responds well to capitalized emphasis on critical rules.
2. **Role framing**: "You are not a chatbot — you is an interviewer" establishes the persona boundary clearly.
3. **Concrete redirect strategies**: Instead of just saying "redirect," the prompt gives exact phrases the agent can adapt. This reduces improvisation failures.
4. **Escalation path**: Rule 6 handles persistent derailment, giving the agent permission to be firmer.
5. **Structured format**: `##` headers help the LLM parse distinct instruction categories.

## Testing Checklist

After deploying the new prompt, test these candidate behaviors:

- [ ] Candidate asks "What is your tech stack?" → Agent redirects to interview question
- [ ] Candidate asks "Can you explain what Kubernetes is?" → Agent does not provide explanation
- [ ] Candidate asks "What's the salary range?" → Agent redirects gracefully
- [ ] Candidate asks "Can you repeat the question?" → Agent should comply (reasonable request)
- [ ] Candidate asks for clarification on what was asked → Agent should clarify and re-ask
- [ ] Candidate tries to end the interview early → Agent handles gracefully
- [ ] Normal interview flow → Agent still conducts natural, engaging conversation

## Risk: Over-correction

The agent might refuse reasonable clarifying questions like "Can you repeat that?" or "What do you mean by X?" These are legitimate interview behaviors. If this becomes an issue, add an exception:

```
"You SHOULD answer clarifying questions about the current question (e.g., 'Can you repeat that?' 
or 'What do you mean by X?'). Only refuse questions that try to turn you into an answerer 
or information source."
```

## Files to Modify

- `backend/agent/worker.py` — replace `instructions` string (lines ~195-208)
