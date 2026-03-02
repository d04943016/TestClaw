# MyOpenClaw 案例模板手冊（5 種情境）

版本：`0.1.x`

本文件提供「可以直接複製再改」的模板，讓你基於 MyOpenClaw 快速建立特定功能的 agent 系統。

## 1. 使用方式

建議每次套用模板都照這個順序：
1. 建立對應 `skills/<name>/SKILL.md`
2. 把案例中的 `eval cases` 加到 `src/myopenclaw/evals/cases.yaml`
3. 調整 `src/myopenclaw/config.py` memory 參數
4. 跑 `python -m myopenclaw eval run`
5. 跑 `python -m myopenclaw chat --session <name>` 做情境驗收

## 2. 模板案例 1：知識庫問答 Agent

### A. 功能目標
- 對知識庫問答，並提供來源線索與不確定性說明。

### B. Skill 組合模板
- `skills/retrieve_knowledge/SKILL.md`
- `skills/answer_with_citation/SKILL.md`

### C. SKILL.md 模板：`retrieve_knowledge`

```md
---
name: retrieve_knowledge
version: 0.1.0
description: Retrieve relevant knowledge snippets for user question.
inputs:
  - user_question
  - memory_context
outputs:
  - evidence_snippets
constraints:
  - Prefer high-relevance snippets.
  - Keep citation handles.
---
# Retrieve Knowledge

## Intent
Find the most relevant background context and preserve source handles.

## Instructions
1. Identify core query intent.
2. Select high relevance snippets from context.
3. Return concise evidence list.

## Output Format
- query intent
- evidence snippets
- source handles
```

### D. SKILL.md 模板：`answer_with_citation`

```md
---
name: answer_with_citation
version: 0.1.0
description: Answer user question with evidence and confidence.
inputs:
  - user_question
  - evidence_snippets
outputs:
  - answer
constraints:
  - Be explicit about unknowns.
  - Include evidence section.
---
# Answer With Citation

## Intent
Answer with grounded evidence and clear uncertainty handling.

## Instructions
1. Provide direct answer.
2. Include evidence and rationale.
3. If not enough evidence, state unknown clearly.

## Output Format
- answer
- evidence
- confidence
- unknowns
```

### E. Eval Case 模板

```json
{
  "id": "kbqa-grounding-1",
  "skill": "answer_with_citation",
  "task": "Answer an internal policy question and cite evidence.",
  "expected_keywords": ["answer", "evidence", "confidence", "unknown"]
}
```

### F. Memory 初始設定
- `short_term_window = 40`
- `chunk_target_tokens = 700`
- `rollup_batch_size = 8`

### G. 驗證步驟
1. `python -m myopenclaw skills show answer_with_citation`
2. `python -m myopenclaw eval run`
3. `python -m myopenclaw chat --session kbqa-demo`

## 3. 模板案例 2：程式碼審查 Agent

### A. 功能目標
- 對程式碼變更做風險導向審查與修正建議。

### B. Skill 組合模板
- `skills/analyze_diff/SKILL.md`
- `skills/review_report/SKILL.md`

### C. SKILL.md 模板：`analyze_diff`

```md
---
name: analyze_diff
version: 0.1.0
description: Analyze code diff and identify risk patterns.
inputs:
  - diff_text
  - historical_context
outputs:
  - risk_findings
constraints:
  - Highlight behavior changes.
  - Include edge cases.
---
# Analyze Diff

## Intent
Understand what changed and where hidden regressions may appear.

## Instructions
1. Parse changed files and logic branches.
2. Identify risk hotspots.
3. Prioritize by severity.

## Output Format
- changed areas
- risk hotspots
- severity rationale
```

### D. SKILL.md 模板：`review_report`

```md
---
name: review_report
version: 0.1.0
description: Produce actionable review findings.
inputs:
  - risk_findings
outputs:
  - findings_report
constraints:
  - Keep findings actionable.
  - Include fix suggestion.
---
# Review Report

## Intent
Transform analysis into developer-friendly findings.

## Instructions
1. Report the issue and impact.
2. Add concrete fix direction.
3. Keep concise and testable.

## Output Format
- severity
- file
- line
- issue
- fix suggestion
```

### E. Eval Case 模板

```json
{
  "id": "review-regression-1",
  "skill": "review_report",
  "task": "Review a patch and identify potential regression risks.",
  "expected_keywords": ["severity", "file", "line", "issue", "fix"]
}
```

### F. Memory 初始設定
- `short_term_window = 20`
- `chunk_target_tokens = 1200`
- `rollup_batch_size = 10`

### G. 驗證步驟
1. `python -m myopenclaw skills show review_report`
2. `python -m myopenclaw eval run`
3. 對同一段 diff 連跑 5 輪，確認輸出穩定

## 4. 模板案例 3：客服工單分流 Agent

### A. 功能目標
- 自動分類、分級並判斷是否升級人工處理。

### B. Skill 組合模板
- `skills/classify_ticket/SKILL.md`
- `skills/draft_reply/SKILL.md`
- `skills/escalation_policy/SKILL.md`

### C. SKILL.md 模板：`classify_ticket`

```md
---
name: classify_ticket
version: 0.1.0
description: Classify ticket category and urgency.
inputs:
  - ticket_text
  - customer_history
outputs:
  - classification
constraints:
  - Keep category and priority explicit.
---
# Classify Ticket

## Intent
Assign priority/category for SLA handling.

## Instructions
1. Detect issue type.
2. Estimate urgency and impact.
3. Return structured classification.

## Output Format
- priority
- category
- sla target
```

### D. SKILL.md 模板：`escalation_policy`

```md
---
name: escalation_policy
version: 0.1.0
description: Decide whether ticket should escalate.
inputs:
  - classification
  - draft_reply
outputs:
  - escalation_decision
constraints:
  - Explain escalation reason.
---
# Escalation Policy

## Intent
Apply escalation policy for high-risk customer tickets.

## Instructions
1. Check risk signals.
2. Decide escalate true/false.
3. Explain the reason.

## Output Format
- escalate
- reason
- next owner
```

### E. Eval Case 模板

```json
{
  "id": "support-escalation-1",
  "skill": "escalation_policy",
  "task": "Customer reports payment failures and possible data inconsistency.",
  "expected_keywords": ["escalate", "reason", "priority", "sla"]
}
```

### F. Memory 初始設定
- `short_term_window = 50`
- `chunk_target_tokens = 900`
- `rollup_batch_size = 8`

### G. 驗證步驟
1. 建立 3 種風險等級票單（低/中/高）
2. 跑 `python -m myopenclaw eval run`
3. 確認高風險案例一定有 `escalate: true`

## 5. 模板案例 4：研究整合 Agent

### A. 功能目標
- 整合多來源材料，輸出可決策的綜合簡報。

### B. Skill 組合模板
- `skills/extract_claims/SKILL.md`
- `skills/compare_evidence/SKILL.md`
- `skills/write_brief/SKILL.md`

### C. SKILL.md 模板：`extract_claims`

```md
---
name: extract_claims
version: 0.1.0
description: Extract core claims and assumptions from sources.
inputs:
  - source_docs
outputs:
  - claims
constraints:
  - Distinguish fact vs assumption.
---
# Extract Claims

## Intent
Extract clear claims to support later comparison.

## Instructions
1. Identify key claims.
2. Mark assumptions.
3. Preserve source traceability.

## Output Format
- claims
- assumptions
- source map
```

### D. SKILL.md 模板：`write_brief`

```md
---
name: write_brief
version: 0.1.0
description: Produce executive brief with recommendations.
inputs:
  - compared_evidence
outputs:
  - brief
constraints:
  - Include supporting and opposing evidence.
---
# Write Brief

## Intent
Generate decision-oriented brief for stakeholders.

## Instructions
1. Summarize thesis.
2. Include supporting/opposing evidence.
3. Provide recommendation with assumptions.

## Output Format
- thesis
- supporting evidence
- opposing evidence
- assumptions
- recommendation
```

### E. Eval Case 模板

```json
{
  "id": "research-conflict-1",
  "skill": "write_brief",
  "task": "Synthesize conflicting studies and provide recommendation.",
  "expected_keywords": ["thesis", "supporting", "opposing", "assumptions", "recommendation"]
}
```

### F. Memory 初始設定
- `short_term_window = 25`
- `chunk_target_tokens = 800`
- `embedding_dim = 512`

### G. 驗證步驟
1. 使用互相矛盾資料做測試
2. 跑 `python -m myopenclaw eval run`
3. 檢查輸出是否同時保留支持與反證

## 6. 模板案例 5：個人執行力教練 Agent

### A. 功能目標
- 建立週計畫、每日聚焦與週期復盤。

### B. Skill 組合模板
- `skills/weekly_plan/SKILL.md`
- `skills/daily_focus/SKILL.md`
- `skills/retro_coach/SKILL.md`

### C. SKILL.md 模板：`weekly_plan`

```md
---
name: weekly_plan
version: 0.1.0
description: Build weekly plan with measurable outcomes.
inputs:
  - goals
  - constraints
outputs:
  - weekly_plan
constraints:
  - Include measurable outcomes.
---
# Weekly Plan

## Intent
Turn goals into realistic weekly plan.

## Instructions
1. Select top priorities.
2. Define measurable outcomes.
3. Add risk mitigation.

## Output Format
- priorities
- measurable outcomes
- blockers
- next actions
```

### D. SKILL.md 模板：`retro_coach`

```md
---
name: retro_coach
version: 0.1.0
description: Guide retrospective and next-cycle improvement.
inputs:
  - week_results
outputs:
  - retro_summary
constraints:
  - Keep improvement actionable.
---
# Retro Coach

## Intent
Analyze what worked and what should change next cycle.

## Instructions
1. Evaluate completed commitments.
2. Identify blockers.
3. Propose next-cycle actions.

## Output Format
- wins
- misses
- blockers
- next actions
```

### E. Eval Case 模板

```json
{
  "id": "coach-retro-1",
  "skill": "retro_coach",
  "task": "Review weekly execution and produce next-week improvements.",
  "expected_keywords": ["priorities", "blockers", "next actions", "measurement"]
}
```

### F. Memory 初始設定
- `short_term_window = 60`
- `chunk_target_tokens = 600`
- `rollup_batch_size = 6`

### G. 驗證步驟
1. 連續 2 週輸入 daily records
2. 跑 `python -m myopenclaw eval run`
3. 檢查輸出是否能追蹤承諾完成率

## 7. 通用實作檢查清單

每個新系統至少檢查以下 10 項：
1. `skills list` 可看到新 skill
2. `skills show <name>` metadata 正確
3. 輸出格式有固定章節
4. `eval run` 不退化
5. `evolve run --skill <name>` gate 行為符合預期
6. 無越界寫檔（僅 `skills/`）
7. `short_term_window` 與 token budget 相容
8. 壓縮後能召回關鍵決策
9. 高風險案例有明確處理策略
10. 回滾快照可追溯

## 8. 建議搭配閱讀

1. `docs/USER_MANUAL_zh-TW.md`
2. `docs/AGENTIC_SYSTEM_DESIGN_GUIDE_zh-TW.md`

