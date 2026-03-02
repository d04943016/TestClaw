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
    progressive_reading_plan,
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


def _build_hypotheses(query: str, terms: list[str], sources: list[str]) -> list[dict]:
    hypotheses = []
    if len(terms) < 4:
        return hypotheses
    for idx in range(min(3, len(terms) - 1)):
        a = terms[idx]
        b = terms[idx + 1]
        hypotheses.append(
            {
                "id": f"H{idx+1:02d}",
                "hypothesis": f"Optimizing {a} is likely to shift {b}-related outcomes for '{query[:100]}'.",
                "prediction": f"Controlled intervention on {a} should measurably alter {b} metrics.",
                "evidence_sources": sources[:5],
                "test_hint": f"Run ablation around {a} and monitor {b} changes.",
            }
        )
    return hypotheses


def main() -> None:
    from research_utils import load_payload

    payload = load_payload()
    task_context = str(payload.get("task_context", ""))
    memory_context = [str(v) for v in payload.get("memory_context", [])]

    query, _ = parse_query_and_focus(task_context)
    paper_root = resolve_paper_root(task_context)

    files = collect_paper_files(paper_root, limit=skill_scan_limit(15000))
    ranked = rank_files(files=files, query=query, memory_context=memory_context, top_k=skill_top_k(24))

    progressive_plans = []
    evidence_rows = []
    snippets: list[str] = []
    source_refs: list[str] = []

    for row in ranked[:8]:
        path = Path(str(row["path"]))
        text = extract_document_text(path)
        sections = split_sections(text)

        progressive_plans.append(progressive_reading_plan(row, text))
        source_refs.append(str(row["rel_path"]))

        abstract = clip(sections.get("abstract", ""), 240)
        conclusion = clip(sections.get("conclusion", ""), 240)
        snippets.extend([abstract, conclusion])

        evidence_rows.append(
            {
                "paper": row["rel_path"],
                "score": row["score"],
                "folder": row["folder"],
                "abstract": abstract,
                "conclusion": conclusion,
                "trace": {"source_file": row["rel_path"]},
            }
        )

    terms = top_terms(snippets + [query] + memory_context, limit=14)
    hypotheses = _build_hypotheses(query=query, terms=terms, sources=source_refs)

    # Gap detection based on uncovered query terms.
    query_terms = set(top_terms([query], limit=12))
    observed_terms = set(top_terms(snippets, limit=30))
    undercovered_terms = sorted([term for term in query_terms if term not in observed_terms])

    artifact_dir = create_artifact_dir("research_deep_research_orchestrator", query)
    json_name = "deep_research_report.json"
    md_name = "deep_research_report.md"

    report_json = {
        "query": query,
        "paper_root": to_pretty_path(paper_root),
        "retrieval": {
            "files_scanned": len(files),
            "top_candidates": ranked,
        },
        "progressive_reading_plan": progressive_plans,
        "evidence_rows": evidence_rows,
        "key_terms": terms,
        "hypotheses": hypotheses,
        "gaps": undercovered_terms,
        "research_system_map": {
            "stage_1_retrieval": str(artifact_dir / "deep_research_report.json"),
            "stage_2_progressive_reading": "embedded in progressive_reading_plan",
            "stage_3_evidence_structuring": "embedded in evidence_rows",
            "stage_4_hypothesis": "embedded in hypotheses",
            "stage_5_gap_analysis": "embedded in gaps",
        },
    }

    rows = []
    for idx, item in enumerate(evidence_rows, start=1):
        rows.append(
            [
                str(idx),
                item["paper"],
                f"{item['score']:.2f}",
                item["folder"],
                item["abstract"],
            ]
        )
    evidence_table = markdown_table(["#", "Paper", "Score", "Folder", "Abstract"], rows)

    hypothesis_lines = []
    for hyp in hypotheses:
        hypothesis_lines.append(f"- {hyp['id']}: {hyp['hypothesis']}")
        hypothesis_lines.append(f"  - Prediction: {hyp['prediction']}")
        hypothesis_lines.append(f"  - Test Hint: {hyp['test_hint']}")

    if not hypothesis_lines:
        hypothesis_lines.append("- Evidence not sufficient for confident hypothesis proposal yet.")

    gap_lines = [f"- {g}" for g in undercovered_terms] if undercovered_terms else ["- No major uncovered query terms detected in current top set."]

    md = "\n".join(
        [
            "# Deep Research Report",
            "",
            f"- Query: {query}",
            f"- Paper Root: {to_pretty_path(paper_root)}",
            f"- Files Scanned: {len(files)}",
            "",
            "## Retrieval + Evidence",
            evidence_table,
            "",
            "## Progressive Reading Strategy",
            "1. Figures/Captions -> 2. Abstract -> 3. Conclusion -> 4. Introduction -> 5. Methods on demand",
            "",
            "## Hypotheses",
            *hypothesis_lines,
            "",
            "## Research Gaps",
            *gap_lines,
            "",
            "## Recommended Follow-up Skills",
            "1. `research_graphrag` for relationship-centric retrieval.",
            "2. `research_evidence_structurer` for auditable output bundles.",
            "3. `research_study_designer` for experiment plans.",
        ]
    )

    write_json(artifact_dir / json_name, report_json)
    write_markdown(artifact_dir / md_name, md)
    write_json(artifact_dir / "research_system_map.json", report_json["research_system_map"])

    summary = (
        f"Deep research orchestration completed. Candidates: {len(ranked)}; "
        f"hypotheses: {len(hypotheses)}; gaps: {len(undercovered_terms)}."
    )
    print(emit_result(summary=summary, artifact_dir=artifact_dir, json_file=json_name, md_file=md_name))


if __name__ == "__main__":
    main()
