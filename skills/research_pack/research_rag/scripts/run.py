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
    parse_query_and_focus,
    rank_files,
    resolve_paper_root,
    skill_scan_limit,
    skill_top_k,
    split_sections,
    to_pretty_path,
    write_json,
    write_markdown,
)


def main() -> None:
    from research_utils import load_payload, markdown_table

    payload = load_payload()
    task_context = str(payload.get("task_context", ""))
    memory_context = [str(v) for v in payload.get("memory_context", [])]

    query, _ = parse_query_and_focus(task_context)
    paper_root = resolve_paper_root(task_context)
    files = collect_paper_files(paper_root, limit=skill_scan_limit(12000))
    ranked = rank_files(files=files, query=query, memory_context=memory_context, top_k=skill_top_k(30))

    top_candidates = []
    for row in ranked[:10]:
        path = Path(str(row["path"]))
        text = extract_document_text(path)
        sections = split_sections(text)
        top_candidates.append(
            {
                "rel_path": row["rel_path"],
                "score": row["score"],
                "folder": row["folder"],
                "size_mb": row["size_mb"],
                "abstract_preview": clip(sections.get("abstract", ""), 280),
                "conclusion_preview": clip(sections.get("conclusion", ""), 280),
            }
        )

    artifact_dir = create_artifact_dir("research_rag", query)
    json_name = "rag_retrieval.json"
    md_name = "rag_retrieval.md"

    payload_json = {
        "query": query,
        "paper_root": to_pretty_path(paper_root),
        "total_files_scanned": len(files),
        "top_candidates": top_candidates,
        "notes": [
            "Ranking is hybrid semantic + keyword with metadata/content preview.",
            "For deeper retrieval quality, pair this with research_graphrag and research_progressive_reader.",
        ],
    }

    rows = []
    for idx, item in enumerate(top_candidates, start=1):
        rows.append(
            [
                str(idx),
                item["rel_path"],
                f"{item['score']:.2f}",
                item["folder"],
                item["abstract_preview"],
            ]
        )

    table = markdown_table(
        headers=["#", "Paper", "Score", "Folder", "Abstract Preview"],
        rows=rows,
    )

    md = "\n".join(
        [
            f"# RAG Retrieval Result",
            f"",
            f"- Query: {query}",
            f"- Paper Root: {to_pretty_path(paper_root)}",
            f"- Files Scanned: {len(files)}",
            f"",
            "## Top Candidates",
            table,
            "",
            "## Next Recommended Skill",
            "1. `research_progressive_reader` for staged reading plan.",
            "2. `research_evidence_structurer` for traceable evidence artifacts.",
        ]
    )

    write_json(artifact_dir / json_name, payload_json)
    write_markdown(artifact_dir / md_name, md)

    summary = (
        f"RAG retrieval completed for query: {query}\n"
        f"Scanned {len(files)} files under {to_pretty_path(paper_root)}.\n"
        f"Top hit: {top_candidates[0]['rel_path'] if top_candidates else 'N/A'}"
    )
    print(emit_result(summary=summary, artifact_dir=artifact_dir, json_file=json_name, md_file=md_name))


if __name__ == "__main__":
    main()
