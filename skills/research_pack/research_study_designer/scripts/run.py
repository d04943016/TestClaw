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


def _build_study_design(query: str, terms: list[str]) -> list[dict]:
    if len(terms) < 4:
        terms = terms + ["baseline", "treatment", "performance", "stability"]

    variables = list(itertools.islice(itertools.combinations(terms[:8], 2), 4))
    designs = []
    for idx, (factor, metric) in enumerate(variables, start=1):
        designs.append(
            {
                "id": f"D{idx:02d}",
                "objective": f"Quantify effect of {factor} on {metric} for query scope '{query[:80]}'.",
                "independent_variable": factor,
                "dependent_metric": metric,
                "control_group": "current_baseline_setup",
                "treatment_group": f"targeted_{factor}_intervention",
                "evaluation_protocol": [
                    "pre-register assumptions",
                    "run repeated measurements",
                    "compare control vs treatment",
                    "report effect size and uncertainty",
                ],
                "success_criterion": f"statistically meaningful shift in {metric} with practical relevance.",
                "failure_criterion": "no significant effect or unstable result across repeats.",
            }
        )
    return designs


def main() -> None:
    from research_utils import load_payload

    payload = load_payload()
    task_context = str(payload.get("task_context", ""))
    memory_context = [str(v) for v in payload.get("memory_context", [])]

    query, _ = parse_query_and_focus(task_context)
    paper_root = resolve_paper_root(task_context)

    snippets: list[str] = []

    for path_text in find_existing_artifacts(memory_context):
        path = Path(path_text)
        if path.name.endswith("hypotheses.json"):
            payload_json = load_json_if_exists(path)
            if payload_json:
                for hyp in payload_json.get("hypotheses", []):
                    if isinstance(hyp, dict):
                        snippets.append(str(hyp.get("hypothesis", "")))
                        snippets.append(str(hyp.get("falsifiable_prediction", "")))

    if len(snippets) < 4:
        files = collect_paper_files(paper_root, limit=skill_scan_limit(12000))
        ranked = rank_files(files=files, query=query, memory_context=memory_context, top_k=skill_top_k(8))
        for row in ranked:
            text = extract_document_text(Path(str(row["path"])))
            sections = split_sections(text)
            snippets.append(sections.get("abstract", ""))
            snippets.append(sections.get("conclusion", ""))

    terms = top_terms(snippets + [query], limit=16)
    designs = _build_study_design(query=query, terms=terms)

    artifact_dir = create_artifact_dir("research_study_designer", query)
    json_name = "study_designs.json"
    md_name = "study_designs.md"

    payload_json = {
        "query": query,
        "paper_root": to_pretty_path(paper_root),
        "terms": terms,
        "designs": designs,
        "methodology_guardrails": {
            "reproducibility": "document assumptions and measurement protocol",
            "bias_control": "include contradictory evidence and negative controls",
            "decision_rule": "accept hypothesis only if success criterion is met",
        },
    }

    rows = []
    for item in designs:
        rows.append(
            [
                item["id"],
                clip(item["objective"], 120),
                item["independent_variable"],
                item["dependent_metric"],
                clip(item["success_criterion"], 100),
            ]
        )

    table = markdown_table(["ID", "Objective", "Variable", "Metric", "Success"], rows)
    md = "\n".join(
        [
            "# Study Design Blueprint",
            "",
            f"- Query: {query}",
            f"- Paper Root: {to_pretty_path(paper_root)}",
            "",
            "## Candidate Designs",
            table,
            "",
            "## Execution Checklist",
            "1. Confirm control/treatment comparability.",
            "2. Predefine acceptance/rejection criteria.",
            "3. Log raw observations for reproducibility.",
            "4. Re-run with perturbation for robustness.",
        ]
    )

    write_json(artifact_dir / json_name, payload_json)
    write_markdown(artifact_dir / md_name, md)

    summary = f"Study design generation completed with {len(designs)} candidate design(s)."
    print(emit_result(summary=summary, artifact_dir=artifact_dir, json_file=json_name, md_file=md_name))


if __name__ == "__main__":
    main()
