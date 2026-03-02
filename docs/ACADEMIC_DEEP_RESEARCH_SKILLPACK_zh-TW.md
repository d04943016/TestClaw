# Academic Deep Research 功能設計與使用指南

版本：`0.1.x`

本文件說明如何以 skills + system prompt 建立一套類似 deep research 的學術研究流程，並補充目前版本新增的 hybrid retrieval/profile 能力。

## 1. 這次方案是否修改 `src`？

分成兩層：
1. deep-research skillpack 本身：可不修改 `src`。
2. 目前專案版本：已加入 `src` 的 memory hybrid retrieval 與 profile 參數載入，讓主智能體 memory search 與 skill retrieval 都可用 semantic+keyword 策略。

技能層新增內容：
1. 研究專屬技能包
2. 研究專屬 system prompt（寫在各技能 `SKILL.md`）
3. 研究流程文件

## 2. 專屬技能路徑（範例）

### 2.1 專屬路徑

- 技能包主路徑：`skills/research_pack/`
- 可被現行系統載入的入口：`skills/` 下同名 symlink

原因：現行 `SkillRegistry` 掃描 `skills/*/SKILL.md`（一層），
因此採「專屬路徑 + 頂層 symlink」設計，兼顧隔離與相容。

### 2.2 技能清單

1. `research_deep_research_orchestrator`
2. `research_rag`
3. `research_graphrag`
4. `research_progressive_reader`
5. `research_evidence_structurer`
6. `research_hypothesis_generator`
7. `research_gap_finder`
8. `research_study_designer`

## 3. 對照你提出的 skill spec

### (1) RAG / GraphRAG

1. `research_rag`
- 針對本地文獻庫做檔案層級檢索與排序

2. `research_graphrag`
- 建立 folder/community 與文件關聯邊，提供關聯式檢索視角

### (2) 有效率讀文獻、漸進式披露

`research_progressive_reader` 固定流程：
1. Figure/caption
2. Abstract
3. Conclusion
4. Introduction
5. Methods（僅必要時）

並提供 early-stop gate，降低 token 消耗。

### (3) 建立表格/圖片/重點與可追溯文件

`research_evidence_structurer` 輸出：
1. `evidence_table.json`（系統可讀）
2. `evidence_table.md`（使用者可讀）
3. `image_inventory.json`
4. `overall_research_system.json`（整體研究流程追溯）

### (4) 適當時機提出假說

`research_hypothesis_generator` 內建規則：
1. 證據不足（例如來源過少）時，不給高信心假說
2. 證據足夠才輸出「可否證」假說 + 最小測試設計

### (5) 其他研究相關 skill

1. `research_gap_finder`：找出文獻缺口與盲區
2. `research_study_designer`：把問題/假說轉成可重現研究設計
3. `research_deep_research_orchestrator`：端到端整合流程

### (6) 智能體是否可「自行建構」以上 skills？

結論：
1. `可部分自我改善`
- 現有 evolver 可針對既有 skill 做內容改寫與升版（受 gate 控制）

2. `不可完整自動新建技能包`
- 目前框架沒有「自動新建 skill 資料夾 + 註冊 + 驗證」全自動流程
- 因此本次已直接建立完整技能包（你可直接用）

## 4. 如何 prompting 讓系統進入 deep research 模式

由於 planner 目前是關鍵詞/skill 名稱匹配，建議在使用者訊息中明確點名 skill 名稱。

### 4.1 一次跑端到端

範例 prompt：

```text
請使用 research_deep_research_orchestrator。
研究問題：有機發光材料中，哪些機制最影響效率 roll-off？
focus: OLED, efficiency roll-off, triplet, exciton
```

### 4.2 分階段執行

1. 檢索：
```text
請使用 research_rag。
研究問題：metasurface OLED display pixel density optimization
```

2. 關聯圖：
```text
請使用 research_graphrag。
研究問題：inverse design for photonic OLED structures
```

3. 省 token 閱讀計畫：
```text
請使用 research_progressive_reader。
研究問題：polarized OLED emission mechanisms
```

4. 證據整理：
```text
請使用 research_evidence_structurer。
研究問題：整理上述檢索到的關鍵論文證據
```

5. 產生假說：
```text
請使用 research_hypothesis_generator。
研究問題：在以上證據下，提出可驗證假說
```

6. 缺口分析：
```text
請使用 research_gap_finder。
研究問題：目前文獻還缺什麼關鍵證據？
```

7. 研究設計：
```text
請使用 research_study_designer。
研究問題：如何驗證假說 H1/H2？
```

## 5. 執行與資料路徑

### 5.1 文獻庫路徑

預設使用：
- `/Users/weikai/Library/CloudStorage/Dropbox/paper`

可覆蓋：
```bash
export PAPER_ROOT=/path/to/another/paper_root
```

若你要快速套用 `/Users/weikai/Library/CloudStorage/Dropbox/paper` 的預設研究參數，可在 `.env` 加入：
```dotenv
MYOPENCLAW_PROFILE=profiles/paper_deep_research.env
```
此 profile 會套用 memory 壓縮、agent memory 檢索、research skill 檢索的建議值（不含任何 secret key）。

### 5.2 Embedding API Key 分離策略（重要）

本次已將 embedding key 分成兩套，避免和主聊天模型 key 混用：

1. 主智能體 memory hybrid search（`src`）
- `AGENT_EMBEDDING_API_KEY`
- `AGENT_EMBEDDING_MODEL`
- `AGENT_EMBEDDING_BASE_URL`
- `AGENT_MEMORY_SEMANTIC_WEIGHT`

2. 研究 skillpack hybrid retrieval（`skills/research_pack`）
- `SKILL_EMBEDDING_API_KEY`
- `SKILL_EMBEDDING_MODEL`
- `SKILL_EMBEDDING_BASE_URL`
- `SKILL_MEMORY_SEMANTIC_WEIGHT`

3. 聊天/推理模型 key（LLM completion）仍維持：
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

這代表你可以分開控管權限、配額與成本。

### 5.2.1 Best Default Research Profile（paper 路徑）

`profiles/paper_deep_research.env` 已提供一組可直接用的建議值，包含：
1. 主智能體 memory：
- `AGENT_MEMORY_SEMANTIC_WEIGHT=0.75`
- `AGENT_MEMORY_TOP_K=8`
- `MEMORY_SHORT_TERM_WINDOW=36`
- `MEMORY_CHUNK_TARGET_TOKENS=900`

2. 研究 skillpack：
- `SKILL_MEMORY_SEMANTIC_WEIGHT=0.78`
- `SKILL_FILE_SCAN_LIMIT=24000`
- `SKILL_RETRIEVAL_TOP_K=36`
- `SKILL_PRESELECT_MULTIPLIER=10`

3. 使用方式：
1. `.env` 放 API keys（`OPENAI_API_KEY` / `AGENT_EMBEDDING_API_KEY` / `SKILL_EMBEDDING_API_KEY`）
2. `.env` 加上 `MYOPENCLAW_PROFILE=profiles/paper_deep_research.env`
3. 重新執行 `python -m myopenclaw chat`

### 5.3 產出路徑

所有技能產物輸出於：
- `.agent_state/research_outputs/<skill>/<timestamp_slug>/`

每次至少包含：
1. JSON（機器可讀）
2. Markdown（人類可審核）

## 6. 與使用者協作的建議 workflow

1. 先用 `research_deep_research_orchestrator` 打第一版全局地圖
2. 針對重點主題跑 `research_rag` / `research_graphrag`
3. 用 `research_progressive_reader` 降低閱讀 token 消耗
4. 用 `research_evidence_structurer` 形成可追溯證據包
5. 再用 `research_hypothesis_generator` / `research_study_designer` 進入研究設計

## 7. 品質與風險提示

1. 目前 RAG/GraphRAG 是本地腳本層級（非向量 DB + 知識圖引擎完整版）
2. PDF 內容萃取依環境工具（`pdftotext`/`mdls`）可用性而異
3. 假說輸出有「證據充足檢查」，避免過度推論
4. 真正定稿前，建議人工檢視 evidence markdown 與 source path

## 8. 你可以怎麼擴充（不改 `src`）

1. 在 `skills/research_pack/<skill>/SKILL.md` 強化 system prompt
2. 在 `skills/research_pack/<skill>/scripts/run.py` 擴充處理邏輯
3. 新增同路徑 skill，並在 `skills/` 建立 symlink 入口
4. 用 `python -m myopenclaw evolve run --skill <skill_name>` 嘗試自我改善既有 skill

---

相關檔案：
1. `skills/research_pack/README.md`
2. `docs/AGENTIC_SYSTEM_DESIGN_GUIDE_zh-TW.md`
3. `docs/CASE_TEMPLATES_zh-TW.md`
