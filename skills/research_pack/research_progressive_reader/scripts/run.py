from __future__ import annotations

import math
import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[2]
SHARED = PACK_ROOT / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from research_utils import (  # noqa: E402
    collect_paper_files,
    create_artifact_dir,
    emit_result,
    extract_document_text,
    markdown_table,
    parse_query_and_focus,
    parse_requested_paths,
    progressive_reading_plan,
    rank_files,
    resolve_paper_root,
    skill_scan_limit,
    skill_top_k,
    to_pretty_path,
    write_json,
    write_markdown,
)


def estimate_tokens(text: str) -> int:
    return max(1, int(math.ceil(len(text.split()) * 1.2)))


def main() -> None:
    from research_utils import load_payload

    payload = load_payload()
    task_context = str(payload.get("task_context", ""))
    memory_context = [str(v) for v in payload.get("memory_context", [])]

    query, _ = parse_query_and_focus(task_context)
    requested = parse_requested_paths(task_context)

    paper_root = resolve_paper_root(task_context)
    files = collect_paper_files(paper_root, limit=skill_scan_limit(12000))
    file_map = {str(Path(item["path"]).resolve()): item for item in files}
    rel_map = {item["rel_path"]: item for item in files}

    selected: list[dict] = []
    for path_text in requested:
        p = Path(path_text).expanduser()
        key = str(p.resolve()) if p.exists() else ""
        if key in file_map:
            selected.append(file_map[key])
            continue
        if path_text in rel_map:
            selected.append(rel_map[path_text])

    if not selected:
        ranked = rank_files(files=files, query=query, memory_context=memory_context, top_k=skill_top_k(10))
        selected = ranked[:6]

    plans = []
    for item in selected:
        text = extract_document_text(Path(str(item["path"])))
        plan = progressive_reading_plan(item, text)

        stage_tokens = {
            "figures_and_captions": 120,
            "abstract": estimate_tokens(plan.get("abstract_preview", "")),
            "conclusion": estimate_tokens(plan.get("conclusion_preview", "")),
            "introduction": estimate_tokens(plan.get("introduction_preview", "")),
            "methods_context": 260,
        }
        stage_gate = {
            "after_abstract": "if relevance < 0.5, stop and switch paper",
            "after_conclusion": "if no claim overlap with query, skip methods",
            "after_introduction": "continue methods only when mechanism/evidence is required",
        }

        plan["token_budget_estimate"] = stage_tokens
        plan["progressive_gate"] = stage_gate
        plans.append(plan)

    artifact_dir = create_artifact_dir("research_progressive_reader", query)
    json_name = "progressive_reader_plan.json"
    md_name = "progressive_reader_plan.md"

    payload_json = {
        "query": query,
        "paper_root": to_pretty_path(paper_root),
        "selected_count": len(selected),
        "plans": plans,
        "strategy": {
            "order": ["figures", "abstract", "conclusion", "introduction", "methods"],
            "goal": "maximize evidence yield per token",
        },
    }

    rows = []
    for idx, plan in enumerate(plans, start=1):
        token_sum = sum(int(v) for v in plan.get("token_budget_estimate", {}).values())
        rows.append([
            str(idx),
            str(plan.get("paper", "")),
            str(token_sum),
            str(plan.get("abstract_preview", "")[:140]).replace("\n", " "),
        ])

    table = markdown_table(["#", "Paper", "Estimated Tokens", "Abstract Preview"], rows)
    md = "\n".join(
        [
            "# Progressive Literature Reading Plan",
            "",
            f"- Query: {query}",
            f"- Paper Root: {to_pretty_path(paper_root)}",
            "- Reading Order: figures -> abstract -> conclusion -> introduction -> methods",
            "",
            "## Paper Queue",
            table,
            "",
            "## Progressive Gate Rules",
            "1. After abstract: stop early if relevance is low.",
            "2. After conclusion: skip methods when no claim overlap.",
            "3. Read methods only when hypothesis testing or reproducibility requires it.",
        ]
    )

    write_json(artifact_dir / json_name, payload_json)
    write_markdown(artifact_dir / md_name, md)

    summary = (
        f"Progressive reading plan created for {len(plans)} paper(s). "
        "This plan is optimized for token-efficient evidence extraction."
    )
    print(emit_result(summary=summary, artifact_dir=artifact_dir, json_file=json_name, md_file=md_name))


if __name__ == "__main__":
    main()
