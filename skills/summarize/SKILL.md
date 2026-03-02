---
name: summarize
version: 0.1.0
description: Summarize long context into actionable concise output.
inputs:
  - raw_text
  - context
outputs:
  - concise_summary
constraints:
  - Keep factual accuracy.
  - Preserve explicit decisions.
  - Highlight open issues.
---
# Summarize Skill

## Intent
You transform long conversations or documents into concise summaries for fast decision making.

## Instructions
1. Extract core facts and decisions.
2. Keep output concise and directly useful.
3. Include the most important open problems.

## Output Format
- Summary
- Key decisions
- Open questions
