# MyOpenClaw 使用說明手冊（MVP）

版本：`0.1.x`

本手冊是 README 的擴充版，目標是讓你可以從「可跑」走到「可維運、可擴充、可持續改善」。

若你要看完整的工程落地順序與風險控管，請搭配：
`docs/TECHNICAL_ROADMAP_zh-TW.md`

## 1. 專案目標與核心能力

MyOpenClaw 是一個純 Python 的本地 Agent MVP，核心能力如下：

1. `skills` 系統
- 採用 Claude-style 結構：`skills/<name>/SKILL.md`
- 支援技能自我演化與回滾

2. 可壓縮記憶系統（近似無限上下文）
- 短期保留原文
- 長期壓縮成 `L1/L2/L3` 摘要
- 檢索時混合近期上下文 + 向量召回 + 高層摘要

3. 多模型供應商支援
- `OpenAI / Anthropic / Gemini`
- 透過 `LiteLLM` 統一呼叫介面

4. 自主進化閘門
- 任務後觸發候選 skill 改寫
- 以評測結果決定是否採用
- 不通過則自動回滾

## 2. 目錄導覽

```text
myopenclaw/
  src/myopenclaw/
    cli.py
    config.py
    llm/router.py
    memory/
      manager.py
      compressor.py
      retriever.py
      store.py
    skills/
      registry.py
      executor.py
      evolver.py
      sandbox.py
    evals/
      harness.py
      scorer.py
      cases.yaml
    core/
      agent.py
      planner.py
      types.py
  skills/
    summarize/SKILL.md
    plan/SKILL.md
  data/
  docs/
    USER_MANUAL_zh-TW.md
  .env.example
  requirements.txt
  README.md
```

## 3. 安裝與啟動

### 3.1 環境需求

1. Python `3.11+`
2. 建議先建立虛擬環境

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### 3.2 API Keys（放在 `.env`）

複製範本：

```bash
cp .env.example .env
```

`.env` 內容至少要有一組 key：

```dotenv
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
# GOOGLE_API_KEY=  # Gemini 別名也可
```

可選：如果你要直接套用 `/Users/weikai/Library/CloudStorage/Dropbox/paper` 的研究最佳化參數，加入：

```dotenv
MYOPENCLAW_PROFILE=profiles/paper_deep_research.env
```

### 3.3 驗證 provider

```bash
python -m myopenclaw providers list
```

若回傳 `available_providers` 空陣列，代表 `.env` 或環境變數尚未提供有效 key。

## 4. CLI 使用指南

### 4.1 互動聊天

```bash
python -m myopenclaw chat --session demo
```

- 每輪會：
1. 寫入 user 訊息
2. 檢索記憶上下文
3. 選 skill 並執行
4. 寫入 assistant 訊息
5. 觸發 memory 壓縮
6. 記錄 task run
7. 嘗試 skill 演化

### 4.2 skills 查詢

```bash
python -m myopenclaw skills list
python -m myopenclaw skills show summarize
```

### 4.3 手動壓縮記憶

```bash
python -m myopenclaw memory compress --session demo
```

### 4.4 跑評測

```bash
python -m myopenclaw eval run
```

### 4.5 手動觸發技能演化

```bash
python -m myopenclaw evolve run --skill summarize
```

### 4.6 觀測最近任務 trace

```bash
python -m myopenclaw trace tail --session demo --limit 5
```

## 5. 新增 Skill（重點章節）

以下流程是最小可行且可被系統穩定讀取的做法。

### 5.1 新 skill 目錄結構

建立：

```text
skills/
  my_skill/
    SKILL.md
    scripts/
    references/
    assets/
```

`SKILL.md` 是必填，其餘目錄可選。

### 5.2 SKILL.md 必備格式

`SKILL.md` 建議模板：

```md
---
name: my_skill
version: 0.1.0
description: One-line skill description.
inputs:
  - objective
  - context
outputs:
  - result
constraints:
  - Stay factual.
  - Keep output actionable.
---
# My Skill

## Intent
Describe what this skill solves.

## Instructions
1. Step one.
2. Step two.

## Output Format
- Goal
- Steps
- Risks
- Output
```

前段 YAML metadata 建議至少填：
1. `name`
2. `version`
3. `description`
4. `inputs`
5. `outputs`
6. `constraints`

### 5.3 使用 script 當執行入口（可選）

如果你希望 skill 直接執行 Python script，可在 frontmatter 增加：

```yaml
entry_script: run.py
```

並放置 `skills/my_skill/scripts/run.py`。

腳本會收到 JSON stdin，包含：
1. `task_context`
2. `memory_context`
3. `skill`

腳本輸出可用 `stdout` 回傳結果。

### 5.4 驗證新 skill

1. 載入檢查

```bash
python -m myopenclaw skills list
python -m myopenclaw skills show my_skill
```

2. 行為檢查

```bash
python -m myopenclaw chat --session skill-dev
```

3. 回歸檢查

```bash
python -m myopenclaw eval run
```

### 5.5 讓演化系統更容易優化你的 skill

請在 skill body 明確要求輸出包含：
1. `goal`
2. `constraints`
3. `steps`
4. `risks`
5. `output`

原因：目前 scorer 對「結構化可執行輸出」有顯著加分，能提高演化成功率。

## 6. Memory 系統改善指南（重點章節）

本節分成「低風險調參」和「架構升級」兩層。

### 6.1 現行 memory 流程

1. 短期記憶
- 保存最近 `short_term_window` 則訊息原文

2. 壓縮
- 超出窗口的舊訊息切 chunk
- 每 chunk 生成 `L1` 摘要
- 每 10 個 `L1` 生成 1 個 `L2`
- 每 10 個 `L2` 生成 1 個 `L3`

3. 檢索拼接（依優先順序）
- recent raw messages
- vector top-k chunks
- 高層摘要（L3/L2）

### 6.2 低風險改善（先做）

主要在 `src/myopenclaw/config.py` 調整：

1. `short_term_window`
- 增加：近期細節更完整，token 成本較高
- 減少：壓縮更快觸發，可能喪失即時細節

2. `chunk_target_tokens`
- 小：摘要更細粒度，chunk 數量變多
- 大：摘要較粗，召回可能不夠精準

3. `rollup_batch_size`
- 小：更快形成 L2/L3
- 大：高層摘要較穩定但延遲更高

4. `embedding_dim`
- 增大可提升區分度，但運算與儲存上升

建議順序：
1. 先固定測試集
2. 單次只改一個參數
3. 以 `eval run` + 真實 chat 任務比較前後差異

### 6.3 中風險改善（推薦）

1. 改善 chunk 切分策略
- 目前偏 token 長度切分
- 可改成語義段落切分（例如按段落、標題、主題轉換點）

2. 改善摘要器 prompt
- 在 `memory/compressor.py` 增加固定輸出欄位：
  - facts
  - decisions
  - constraints
  - unresolved

3. 增加去重機制
- 召回階段可做語義去重，避免重複段落浪費 token

4. 檢索打分混合
- 將相似度分數與 recency 分數加權
- 使近期與高相關片段更平衡

### 6.4 高風險升級（需做遷移規劃）

1. Embedding 來源升級
- 從 hashing fallback 升級為真實 embedding API
- 需要處理 index 重建與向後相容

2. Memory schema 擴充
- 在 `compressed_chunks` 增加欄位（如 topic、importance、ttl）
- 需規劃 migration script

3. 多索引策略
- 依 session、topic 分 index
- 可降低大索引污染，提高召回精度

### 6.5 建議的 memory 改善流程（實務版）

1. 先定義場景與成功指標
- 例如「跨 50 輪對話仍保留核心決策」

2. 建立基線
- 固定測試題與期望輸出

3. 改一項
- 只改單一策略或參數

4. 回歸驗證
- 跑 `eval run` + 手動場景測試

5. 留下變更紀錄
- 紀錄 config、分數、優劣、回滾條件

## 7. 自主演化（Skill Evolution）運作細節

### 7.1 觸發時機

- 每次任務完成後，`post_task_evolve` 會被呼叫。

### 7.2 決策輸出格式

meta-agent 決策預期為 JSON：

```json
{
  "should_evolve": true,
  "target_skill": "summarize",
  "hypothesis": "improve constraints handling"
}
```

### 7.3 Gate 條件

候選 skill 必須同時滿足：
1. `avg_delta >= +0.15`
2. 不得出現 case delta `< -0.20`
3. safety checks 全通過

否則拒絕並回滾。

### 7.4 版本與快照

所有候選與報告會留在：

```text
.agent_state/skill_versions/<skill>/<snapshot_id>/
```

包含：
1. `original/`
2. `candidate/`
3. `patch.diff`
4. `eval_report.json`

## 8. 常見問題排查

### 8.1 `providers list` 是空的

1. 確認 `.env` 存在
2. 確認 key 名稱拼字正確
3. 重新開 shell 後再跑

### 8.2 `chat` 出現 offline fallback

代表目前 provider 呼叫不可用，常見原因：
1. 未安裝依賴（如 `litellm`）
2. 無法連外
3. API key 無效或配額限制

### 8.3 `evolve run` 一直不通過

1. 候選改寫幅度不足（avg_delta 不夠）
2. 某些 case 發生回歸
3. skill 文本缺少 scorer 需要的關鍵結構

建議先調整 skill 輸出格式，再跑評測。

## 9. 開發與測試建議流程

1. 開新 skill 或改 skill body
2. `skills list` / `skills show` 快速驗證
3. `chat` 做情境測試
4. `eval run` 檢查回歸
5. 必要時 `evolve run --skill <name>` 看 gate 行為

## 10. 建議後續路線圖

1. 引入真實 embedding provider 與 index migration
2. 讓 eval cases 分領域管理（general/coding/research）
3. 增加 memory 指標儀表（召回率、壓縮比、token 節省）
4. 將 skill 進化策略拆成可配置 policy

---

延伸閱讀：
- `docs/AGENTIC_SYSTEM_DESIGN_GUIDE_zh-TW.md`（核心概念、design rules、5 個場景設計案例）
- `docs/CASE_TEMPLATES_zh-TW.md`（5 個可直接複製的案例模板：skill/eval/memory/驗收）
- `docs/ACADEMIC_DEEP_RESEARCH_SKILLPACK_zh-TW.md`（學術 deep-research 專用技能包與 prompting）

如果你要，我可以下一步直接幫你再補一份：
`docs/SKILL_AUTHORING_GUIDE_zh-TW.md`（專門給 skill 撰寫者）和
`docs/MEMORY_TUNING_PLAYBOOK_zh-TW.md`（專門給記憶系統調參/升級）。
