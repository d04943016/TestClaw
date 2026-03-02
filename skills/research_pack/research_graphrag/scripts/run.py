from __future__ import annotations

import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[2]
SHARED = PACK_ROOT / "_shared"
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from research_utils import (  # noqa: E402
    build_folder_graph,
    build_similarity_edges,
    collect_paper_files,
    create_artifact_dir,
    emit_result,
    markdown_table,
    parse_query_and_focus,
    rank_files,
    resolve_paper_root,
    skill_scan_limit,
    skill_top_k,
    to_pretty_path,
    write_json,
    write_markdown,
)


def main() -> None:
    from research_utils import load_payload

    payload = load_payload()
    task_context = str(payload.get("task_context", ""))
    memory_context = [str(v) for v in payload.get("memory_context", [])]

    query, _ = parse_query_and_focus(task_context)
    paper_root = resolve_paper_root(task_context)
    files = collect_paper_files(paper_root, limit=skill_scan_limit(15000))
    ranked = rank_files(files=files, query=query, memory_context=memory_context, top_k=skill_top_k(80))

    folder_graph = build_folder_graph(ranked)
    similarity_edges = build_similarity_edges(ranked, max_pairs=70)

    communities = []
    for node in folder_graph.get("nodes", [])[:12]:
        folder = str(node.get("id", "_root"))
        count = int(node.get("count", 0))
        members = [item["rel_path"] for item in ranked if item.get("folder") == folder][:6]
        communities.append({"folder": folder, "paper_count": count, "sample_members": members})

    artifact_dir = create_artifact_dir("research_graphrag", query)
    json_name = "graph_rag.json"
    md_name = "graph_rag.md"

    payload_json = {
        "query": query,
        "paper_root": to_pretty_path(paper_root),
        "scanned_files": len(files),
        "ranked_candidates": ranked,
        "folder_graph": folder_graph,
        "similarity_edges": similarity_edges,
        "communities": communities,
    }

    node_rows = [[c["folder"], str(c["paper_count"]), ", ".join(c["sample_members"][:3])] for c in communities]
    edge_rows = [
        [
            str(edge.get("left", "")),
            str(edge.get("right", "")),
            str(edge.get("score", "")),
            ", ".join(edge.get("overlap_terms", [])[:5]),
        ]
        for edge in similarity_edges[:20]
    ]

    node_table = markdown_table(["Community", "Count", "Examples"], node_rows)
    edge_table = markdown_table(["Paper A", "Paper B", "Similarity", "Overlap Terms"], edge_rows)

    md = "\n".join(
        [
            "# GraphRAG Retrieval Result",
            "",
            f"- Query: {query}",
            f"- Paper Root: {to_pretty_path(paper_root)}",
            f"- Files Scanned: {len(files)}",
            "",
            "## Folder Communities",
            node_table,
            "",
            "## Cross-Paper Similarity Edges",
            edge_table,
            "",
            "## Suggested Next Steps",
            "1. Read representative papers from top 2 communities first.",
            "2. Use `research_progressive_reader` for staged token-efficient reading.",
            "3. Use `research_gap_finder` to identify unresolved directions.",
        ]
    )

    write_json(artifact_dir / json_name, payload_json)
    write_markdown(artifact_dir / md_name, md)

    summary = (
        f"GraphRAG built {len(folder_graph.get('nodes', []))} folder communities and "
        f"{len(similarity_edges)} similarity edges for query: {query}."
    )
    print(emit_result(summary=summary, artifact_dir=artifact_dir, json_file=json_name, md_file=md_name))


if __name__ == "__main__":
    main()
