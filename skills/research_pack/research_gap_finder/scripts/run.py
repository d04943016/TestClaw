from __future__ import annotations

import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[2]
SHARED = PACK_ROOT / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from research_utils import (  # noqa: E402
    clip,
    collect_paper_files,
    create_artifact_dir,
    emit_result,
    extract_document_text,
    markdown_table,
    parse_query_and_focus,
    rank_files,
    resolve_paper_root,
    skill_scan_limit,
    skill_top_k,
    split_sections,
    to_pretty_path,
    top_terms,
    tokenize,
    write_json,
    write_markdown,
)


def main() -> None:
    from research_utils import load_payload

    payload = load_payload()
    task_context = str(payload.get("task_context", ""))
    memory_context = [str(v) for v in payload.get("memory_context", [])]

    query, focus_terms = parse_query_and_focus(task_context)
    paper_root = resolve_paper_root(task_context)
    files = collect_paper_files(paper_root, limit=skill_scan_limit(12000))
    ranked = rank_files(files=files, query=query, memory_context=memory_context, top_k=skill_top_k(20))

    snippets: list[str] = []
    folder_hits: dict[str, int] = {}
    for row in ranked:
        folder = str(row.get("folder", "_root"))
        folder_hits[folder] = folder_hits.get(folder, 0) + 1
        text = extract_document_text(Path(str(row["path"])))
        sections = split_sections(text)
        snippets.append(sections.get("abstract", ""))
        snippets.append(sections.get("conclusion", ""))

    observed_terms = set(top_terms(snippets, limit=40))
    requested_terms = set(tokenize(query) + focus_terms)

    undercovered_terms = sorted([term for term in requested_terms if term not in observed_terms])

    dominant_folders = sorted(folder_hits.items(), key=lambda x: x[1], reverse=True)
    weak_folders = dominant_folders[-3:] if len(dominant_folders) >= 3 else dominant_folders

    gaps = []
    for idx, term in enumerate(undercovered_terms[:6], start=1):
        gaps.append(
            {
                "id": f"G{idx:02d}",
                "gap": f"Insufficient explicit coverage on term '{term}' in top retrieved literature.",
                "evidence": "Query term is rarely represented in retrieved abstract/conclusion snippets.",
                "priority": "high" if idx <= 3 else "medium",
                "next_action": f"Run targeted retrieval for '{term}' using research_rag with focused query.",
            }
        )

    for folder, count in weak_folders[:3]:
        gaps.append(
            {
                "id": f"GF-{folder}",
                "gap": f"Potentially underexplored folder/domain '{folder}'.",
                "evidence": f"Only {count} retrieved paper(s) from this folder in top set.",
                "priority": "medium",
                "next_action": f"Manually inspect {folder} folder and add representative papers to reading queue.",
            }
        )

    artifact_dir = create_artifact_dir("research_gap_finder", query)
    json_name = "research_gaps.json"
    md_name = "research_gaps.md"

    payload_json = {
        "query": query,
        "paper_root": to_pretty_path(paper_root),
        "observed_terms": sorted(observed_terms),
        "requested_terms": sorted(requested_terms),
        "undercovered_terms": undercovered_terms,
        "dominant_folders": dominant_folders,
        "gaps": gaps,
    }

    rows = []
    for gap in gaps:
        rows.append([gap["id"], clip(gap["gap"], 120), gap["priority"], clip(gap["next_action"], 140)])
    table = markdown_table(["ID", "Gap", "Priority", "Next Action"], rows)

    md = "\n".join(
        [
            "# Literature Gap Finder Result",
            "",
            f"- Query: {query}",
            f"- Paper Root: {to_pretty_path(paper_root)}",
            f"- Retrieved Candidate Count: {len(ranked)}",
            "",
            "## Gap Table",
            table,
            "",
            "## Interpretation",
            "1. High-priority gaps indicate direct mismatch between query intent and current evidence.",
            "2. Folder-level gaps indicate collection imbalance and potential blind spots.",
            "3. Resolve top gaps before finalizing hypothesis claims.",
        ]
    )

    write_json(artifact_dir / json_name, payload_json)
    write_markdown(artifact_dir / md_name, md)

    summary = (
        f"Gap analysis completed with {len(gaps)} identified gap(s). "
        f"Undercovered terms: {', '.join(undercovered_terms[:6]) if undercovered_terms else 'none'}"
    )
    print(emit_result(summary=summary, artifact_dir=artifact_dir, json_file=json_name, md_file=md_name))


if __name__ == "__main__":
    main()
