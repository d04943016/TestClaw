# Survey 研究智能體 README（Research Pack）

本文件是給「做文獻 survey / related work」的實務用說明，基於本專案既有 `LLM + memory + skills` 架構。

## 1. 適用範圍

適合任務：
1. 快速掃描大量 paper（先召回、再分層精讀）
2. 產生可追溯的 evidence table（可給人審核）
3. 彙整研究缺口、提出可驗證假說與後續 study design

## 2. 核心技能組合（建議順序）

1. `research_deep_research_orchestrator`：端到端總控，一次先出全局盤點  
2. `research_rag`：語意 + 關鍵字混合召回  
3. `research_graphrag`：看社群與關聯邊，補齊跨主題連結  
4. `research_progressive_reader`：先圖表/摘要/結論，控制 token 成本  
5. `research_evidence_structurer`：輸出 JSON + Markdown 可追溯證據包  
6. `research_gap_finder`：找 coverage 不足點  
7. `research_hypothesis_generator`：證據足夠時才提假說  
8. `research_study_designer`：把假說落地成可執行驗證設計

## 3. 快速啟用

1. 在 `.env` 放 LLM 與 embedding key（分離）  
2. 設定 profile（建議）：

```dotenv
MYOPENCLAW_PROFILE=profiles/paper_deep_research.env
```

3. 啟動互動：

```bash
PYTHONPATH=src python -m myopenclaw chat --session survey
```

## 4. API Key 分離（重點）

主智能體 memory retrieval：
1. `AGENT_EMBEDDING_API_KEY`
2. `AGENT_EMBEDDING_MODEL`
3. `AGENT_EMBEDDING_BASE_URL`

research skills retrieval：
1. `SKILL_EMBEDDING_API_KEY`
2. `SKILL_EMBEDDING_MODEL`
3. `SKILL_EMBEDDING_BASE_URL`

對話 LLM：
1. `OPENAI_API_KEY`
2. `ANTHROPIC_API_KEY`
3. `GEMINI_API_KEY`

## 5. 推薦 Prompt 模板（Survey）

### 5.1 一次總覽

```text
請使用 research_deep_research_orchestrator。
主題：<你的研究主題>
focus: <關鍵詞1>, <關鍵詞2>, <關鍵詞3>
請輸出可追溯 evidence 與研究缺口。
```

### 5.2 先召回再精讀

```text
請使用 research_rag。
主題：<你的主題>
focus: baseline, sota, benchmark, ablation
```

```text
請使用 research_progressive_reader。
請對剛剛 top papers 做 token-efficient 閱讀計畫。
```

### 5.3 產出 Survey 主體素材

```text
請使用 research_evidence_structurer。
把目前證據整理成可直接寫 Related Work 的結構化輸出。
```

## 6. 產物位置與用途

每次技能執行會在以下位置產生可審核輸出：

`.agent_state/research_outputs/<skill>/<timestamp_slug>/`

常見檔案：
1. `*.json`：系統可讀（可供後續技能串接）
2. `*.md`：人類可讀（可人工審核與整理進稿件）
3. `overall_research_system.json`：流程追蹤

## 7. 調參建議（Survey 預設）

先使用 `profiles/paper_deep_research.env`，再依任務調整：
1. `SKILL_RETRIEVAL_TOP_K`：主題很廣時可提高
2. `SKILL_FILE_SCAN_LIMIT`：資料量很大時提高掃描上限
3. `SKILL_MEMORY_SEMANTIC_WEIGHT`：語意檢索比重
4. `AGENT_MEMORY_TOP_K`：聊天時帶入的長期記憶片段數

## 8. 實務規則（Design Rules）

1. 先廣召回，再分層精讀，不要一開始就全篇精讀。  
2. 任何結論都要可追溯到 source path。  
3. 假說必須可否證，不要只做敘述性總結。  
4. 每輪輸出都保持 JSON + Markdown 雙格式。  
5. 若 evidence 不足，優先補召回，不要硬下結論。  
