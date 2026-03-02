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
    write_json,
    write_markdown,
)


def _list_related_images(root: Path, focus_terms: list[str], limit: int = 40) -> list[str]:
    image_suffix = {".png", ".jpg", ".jpeg", ".svg", ".tif", ".tiff", ".webp"}
    candidates: list[tuple[int, str]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in image_suffix:
            continue
        text = str(path).lower()
        score = 0
        for term in focus_terms:
            if term in text:
                score += 1
        if score > 0:
            candidates.append((score, str(path)))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in candidates[:limit]]


def main() -> None:
    from research_utils import load_payload

    payload = load_payload()
    task_context = str(payload.get("task_context", ""))
    memory_context = [str(v) for v in payload.get("memory_context", [])]

    query, focus_terms = parse_query_and_focus(task_context)
    paper_root = resolve_paper_root(task_context)
    files = collect_paper_files(paper_root, limit=skill_scan_limit(12000))
    ranked = rank_files(files=files, query=query, memory_context=memory_context, top_k=skill_top_k(14))

    evidence_rows = []
    snippet_bank: list[str] = []
    for idx, row in enumerate(ranked[:10], start=1):
        path = Path(str(row["path"]))
        text = extract_document_text(path)
        sections = split_sections(text)

        abstract = clip(sections.get("abstract", ""), 260)
        conclusion = clip(sections.get("conclusion", ""), 260)
        introduction = clip(sections.get("introduction", ""), 220)

        snippet_bank.extend([abstract, conclusion, introduction])

        evidence_rows.append(
            {
                "id": f"E{idx:02d}",
                "paper": row["rel_path"],
                "score": row["score"],
                "folder": row["folder"],
                "abstract": abstract,
                "conclusion": conclusion,
                "introduction": introduction,
                "trace": {
                    "source_file": row["rel_path"],
                    "extraction_method": "local_preview_parser",
                },
            }
        )

    key_terms = top_terms(snippet_bank + [query] + memory_context, limit=16)
    images = _list_related_images(paper_root, focus_terms=focus_terms + key_terms, limit=30)

    artifact_dir = create_artifact_dir("research_evidence_structurer", query)
    main_json = "evidence_bundle.json"
    main_md = "evidence_bundle.md"

    research_map = {
        "query": query,
        "paper_root": to_pretty_path(paper_root),
        "evidence_count": len(evidence_rows),
        "source_files": [row["paper"] for row in evidence_rows],
        "key_terms": key_terms,
        "artifacts": {
            "evidence_bundle_json": str(artifact_dir / main_json),
            "evidence_bundle_md": str(artifact_dir / main_md),
            "machine_readable_table": str(artifact_dir / "evidence_table.json"),
            "user_readable_table": str(artifact_dir / "evidence_table.md"),
            "image_inventory": str(artifact_dir / "image_inventory.json"),
        },
        "traceability": {
            "all_evidence_rows_have_source": all(bool(row.get("paper")) for row in evidence_rows),
            "lineage": "query -> retrieval -> section extraction -> evidence table",
        },
    }

    table_rows = []
    for row in evidence_rows:
        table_rows.append(
            [
                row["id"],
                row["paper"],
                f"{row['score']:.2f}",
                row["folder"],
                row["abstract"],
                row["conclusion"],
            ]
        )

    table_md = markdown_table(
        headers=["ID", "Paper", "Score", "Folder", "Abstract", "Conclusion"],
        rows=table_rows,
    )

    user_doc = "\n".join(
        [
            "# Research Evidence Bundle",
            "",
            f"- Query: {query}",
            f"- Paper Root: {to_pretty_path(paper_root)}",
            f"- Evidence Entries: {len(evidence_rows)}",
            "",
            "## Evidence Table",
            table_md,
            "",
            "## Key Terms",
            ", ".join(key_terms),
            "",
            "## Image Inventory (Related Assets)",
            "\n".join([f"- {item}" for item in images[:20]]) if images else "- (none matched by current focus terms)",
            "",
            "## Traceability Notes",
            "1. Every row keeps source file path.",
            "2. JSON outputs are machine-readable for follow-up skills.",
            "3. Markdown outputs are user-verifiable for manual audit.",
        ]
    )

    write_json(artifact_dir / main_json, {"research_map": research_map, "evidence_rows": evidence_rows})
    write_markdown(artifact_dir / main_md, user_doc)
    write_json(artifact_dir / "evidence_table.json", {"rows": evidence_rows})
    write_markdown(artifact_dir / "evidence_table.md", table_md)
    write_json(artifact_dir / "image_inventory.json", {"images": images, "count": len(images)})
    write_json(artifact_dir / "overall_research_system.json", research_map)

    summary = (
        f"Evidence structuring completed with {len(evidence_rows)} entries and {len(images)} related images. "
        "Generated both machine-readable and user-auditable artifacts."
    )
    print(emit_result(summary=summary, artifact_dir=artifact_dir, json_file=main_json, md_file=main_md))


if __name__ == "__main__":
    main()
