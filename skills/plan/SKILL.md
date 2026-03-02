---
name: plan
version: 0.1.0
description: Convert a goal into an executable implementation plan.
inputs:
  - objective
  - constraints
outputs:
  - execution_plan
constraints:
  - Stay within scope.
  - Call out assumptions.
  - Keep sequence actionable.
---
# Planning Skill

## Intent
Convert user goals and constraints into a practical task plan.

## Instructions
1. Clarify objective and boundaries.
2. Break work into ordered tasks.
3. Capture risks and required follow-ups.

## Output Format
- Goal
- Scope
- Steps
- Risks
