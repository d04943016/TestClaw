from __future__ import annotations

import itertools
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
    find_existing_artifacts,
    load_json_if_exists,
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


def _build_hypotheses(query: str, terms: list[str], sources: list[str]) -> list[dict]:
    hypotheses = []
    pair_iter = itertools.combinations(terms[:8], 2)
    for idx, (left, right) in enumerate(pair_iter, start=1):
        hypotheses.append(
            {
                "id": f"H{idx:02d}",
                "hypothesis": f"If {left} is optimized, then {right}-related performance should improve for tasks in scope '{query[:100]}'.",
                "rationale": f"Repeated term co-occurrence observed in retrieved evidence: {left}, {right}.",
                "falsifiable_prediction": f"Under controlled setting, changing {left} should produce measurable shift in {right} metric.",
                "minimal_test": {
                    "control": f"Baseline system without targeted {left} intervention",
                    "treatment": f"System with targeted {left} intervention",
                    "primary_metric": right,
                    "expected_direction": "increase_or_decrease_to_be_determined",
                },
                "evidence_sources": sources[:5],
                "risk": "Potential confounders and publication bias.",
            }
        )
        if len(hypotheses) >= 4:
            break
    return hypotheses


def main() -> None:
    from research_utils import load_payload

    payload = load_payload()
    task_context = str(payload.get("task_context", ""))
    memory_context = [str(v) for v in payload.get("memory_context", [])]

    query, _ = parse_query_and_focus(task_context)
    paper_root = resolve_paper_root(task_context)

    snippets: list[str] = []
    source_refs: list[str] = []

    # Prefer previously structured artifacts if present.
    artifact_paths = find_existing_artifacts(memory_context)
    for path_text in artifact_paths:
        path = Path(path_text)
        if path.suffix.lower() == ".json":
            payload_json = load_json_if_exists(path)
            if not payload_json:
                continue
            rows = payload_json.get("evidence_rows", []) if isinstance(payload_json, dict) else []
            if isinstance(rows, list):
                for row in rows[:12]:
                    if isinstance(row, dict):
                        snippets.append(str(row.get("abstract", "")))
                        snippets.append(str(row.get("conclusion", "")))
                        source = str(row.get("paper", ""))
                        if source:
                            source_refs.append(source)

    if len(snippets) < 6:
        files = collect_paper_files(paper_root, limit=skill_scan_limit(10000))
        ranked = rank_files(files=files, query=query, memory_context=memory_context, top_k=skill_top_k(10))
        for row in ranked[:8]:
            text = extract_document_text(Path(str(row["path"])))
            sections = split_sections(text)
            snippets.append(sections.get("abstract", ""))
            snippets.append(sections.get("conclusion", ""))
            source_refs.append(str(row["rel_path"]))

    terms = top_terms(snippets + [query], limit=14)

    sufficient_evidence = len(source_refs) >= 3 and len(terms) >= 4
    hypotheses = _build_hypotheses(query=query, terms=terms, sources=source_refs) if sufficient_evidence else []

    artifact_dir = create_artifact_dir("research_hypothesis_generator", query)
    json_name = "hypotheses.json"
    md_name = "hypotheses.md"

    if sufficient_evidence:
        decision_note = "Evidence appears sufficient for initial hypothesis proposal."
    else:
        decision_note = (
            "Evidence appears insufficient for reliable hypothesis proposal. "
            "Run research_evidence_structurer first or provide targeted paper paths."
        )

    payload_json = {
        "query": query,
        "paper_root": to_pretty_path(paper_root),
        "evidence_source_count": len(source_refs),
        "top_terms": terms,
        "sufficient_evidence": sufficient_evidence,
        "decision_note": decision_note,
        "hypotheses": hypotheses,
    }

    hypothesis_lines = []
    for hyp in hypotheses:
        hypothesis_lines.extend(
            [
                f"### {hyp['id']}",
                f"- Hypothesis: {hyp['hypothesis']}",
                f"- Rationale: {clip(hyp['rationale'], 260)}",
                f"- Prediction: {clip(hyp['falsifiable_prediction'], 260)}",
                f"- Minimal Test: control={hyp['minimal_test']['control']}; treatment={hyp['minimal_test']['treatment']}; metric={hyp['minimal_test']['primary_metric']}",
                f"- Risk: {hyp['risk']}",
                "",
            ]
        )

    if not hypothesis_lines:
        hypothesis_lines = ["- (No high-confidence hypotheses generated yet)"]

    md = "\n".join(
        [
            "# Hypothesis Proposal",
            "",
            f"- Query: {query}",
            f"- Decision: {decision_note}",
            f"- Evidence Sources: {len(source_refs)}",
            "",
            "## Candidate Hypotheses",
            *hypothesis_lines,
            "",
            "## Recommended Next Steps",
            "1. Validate each hypothesis with explicit control/treatment comparison.",
            "2. Add at least 2 contradictory papers to reduce confirmation bias.",
            "3. Use research_study_designer for experiment planning.",
        ]
    )

    write_json(artifact_dir / json_name, payload_json)
    write_markdown(artifact_dir / md_name, md)

    summary = (
        f"Hypothesis generation finished. Evidence sources: {len(source_refs)}; "
        f"hypotheses proposed: {len(hypotheses)}."
    )
    print(emit_result(summary=summary, artifact_dir=artifact_dir, json_file=json_name, md_file=md_name))


if __name__ == "__main__":
    main()
