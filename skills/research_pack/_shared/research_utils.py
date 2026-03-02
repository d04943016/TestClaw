from __future__ import annotations

import json
import hashlib
import math
import os
import re
import shlex
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import request

PAPER_ROOT_DEFAULT = Path("/Users/weikai/Library/CloudStorage/Dropbox/paper")
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".doc",
    ".docx",
    ".tex",
    ".ppt",
    ".pptx",
}
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "using",
    "use",
    "study",
    "paper",
    "papers",
    "about",
    "under",
    "over",
    "your",
    "their",
    "there",
    "where",
    "what",
    "when",
    "which",
    "have",
    "has",
    "had",
    "been",
    "were",
    "will",
    "would",
    "could",
    "should",
    "them",
    "than",
    "then",
    "also",
    "more",
    "most",
    "such",
    "need",
    "read",
    "reading",
    "research",
    "academic",
}


def load_payload() -> dict[str, Any]:
    raw = ""
    try:
        raw = os.read(0, 10_000_000).decode("utf-8", errors="ignore")
    except Exception:
        raw = ""

    if not raw.strip():
        return {"task_context": "", "memory_context": [], "skill": ""}

    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            payload.setdefault("task_context", "")
            payload.setdefault("memory_context", [])
            payload.setdefault("skill", "")
            return payload
    except Exception:
        pass

    return {"task_context": raw, "memory_context": [], "skill": ""}


def _env_int(name: str, default: int, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parsed = int(raw)
    except Exception:
        return default
    return max(min_value, min(max_value, parsed))


def _env_float(name: str, default: float, min_value: float, max_value: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        parsed = float(raw)
    except Exception:
        return default
    return max(min_value, min(max_value, parsed))


def skill_scan_limit(default: int) -> int:
    return _env_int("SKILL_FILE_SCAN_LIMIT", default, min_value=500, max_value=100_000)


def skill_top_k(default: int) -> int:
    return _env_int("SKILL_RETRIEVAL_TOP_K", default, min_value=3, max_value=200)


def _clean_token(token: str) -> str:
    return token.strip().strip(".,:;!?()[]{}\"'`").lower()


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in re.split(r"\s+", text):
        token = _clean_token(raw)
        if len(token) < 3:
            continue
        if token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _normalize_vector(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0:
        return vec
    return [v / norm for v in vec]


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _normalize_scores(scores: list[float]) -> list[float]:
    if not scores:
        return []
    max_score = max(scores)
    min_score = min(scores)
    if abs(max_score - min_score) < 1e-9:
        return [1.0 if max_score > 0 else 0.0 for _ in scores]
    return [(score - min_score) / (max_score - min_score) for score in scores]


class HashingEmbedder:
    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        terms = tokenize(text)
        for term in terms:
            digest = hashlib.sha256(term.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        return _normalize_vector(vec)


class OpenAICompatibleEmbedder:
    def __init__(self, api_key: str, model: str, base_url: str, timeout: int = 30) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _endpoint(self) -> str:
        if self.base_url.endswith("/embeddings"):
            return self.base_url
        return self.base_url + "/embeddings"

    def _request_batch(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": texts}
        req = request.Request(
            self._endpoint(),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as resp:
            decoded = json.loads(resp.read().decode("utf-8", errors="ignore"))

        data = decoded.get("data", []) if isinstance(decoded, dict) else []
        if not isinstance(data, list):
            raise RuntimeError(f"Invalid embedding response: {decoded}")
        ordered = sorted(
            [row for row in data if isinstance(row, dict)],
            key=lambda item: int(item.get("index", 0)),
        )
        vectors: list[list[float]] = []
        for row in ordered:
            emb = row.get("embedding", [])
            if not isinstance(emb, list):
                emb = []
            vectors.append(_normalize_vector([float(v) for v in emb]))
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Embedding batch mismatch: expected {len(texts)}, got {len(vectors)}"
            )
        return vectors

    def embed_batch(self, texts: list[str], batch_size: int = 24) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            out.extend(self._request_batch(texts[i : i + batch_size]))
        return out


def _skill_semantic_embedder() -> OpenAICompatibleEmbedder | None:
    api_key = os.getenv("SKILL_EMBEDDING_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("SKILL_EMBEDDING_MODEL", "text-embedding-3-small").strip() or "text-embedding-3-small"
    base_url = os.getenv("SKILL_EMBEDDING_BASE_URL", "https://api.openai.com/v1").strip() or "https://api.openai.com/v1"
    return OpenAICompatibleEmbedder(api_key=api_key, model=model, base_url=base_url)


def extract_possible_paths(text: str) -> list[str]:
    # Capture absolute and relative path-like tokens in prompts.
    pattern = r"(?:/Users/[^\s,;\)]+|\./[^\s,;\)]+|[A-Za-z0-9_\-./]+\.(?:pdf|txt|md|docx|doc|tex|pptx|ppt))"
    return re.findall(pattern, text)


def resolve_paper_root(task_context: str = "") -> Path:
    env_root = os.getenv("PAPER_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser()
        if candidate.exists() and candidate.is_dir():
            return candidate

    for token in extract_possible_paths(task_context):
        candidate = Path(token).expanduser()
        if candidate.exists() and candidate.is_dir():
            return candidate

    return PAPER_ROOT_DEFAULT


def run_cmd(args: list[str], timeout: int = 15) -> str:
    try:
        proc = subprocess.run(
            args,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout
        return proc.stdout + "\n" + proc.stderr
    except Exception:
        return ""


def command_exists(name: str) -> bool:
    probe = run_cmd(["/usr/bin/env", "which", name], timeout=5).strip()
    return bool(probe)


def collect_paper_files(root: Path, limit: int = 5000) -> list[dict[str, Any]]:
    if not root.exists():
        return []

    rows: list[dict[str, Any]] = []
    count = 0
    for path in root.rglob("*"):
        if count >= limit:
            break
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue

        try:
            stat = path.stat()
        except Exception:
            continue

        rel = str(path.relative_to(root))
        folder = rel.split("/")[0] if "/" in rel else "_root"
        rows.append(
            {
                "path": str(path),
                "rel_path": rel,
                "name": path.name,
                "stem": path.stem,
                "suffix": path.suffix.lower(),
                "folder": folder,
                "size_mb": round(stat.st_size / (1024 * 1024), 3),
                "mtime": int(stat.st_mtime),
            }
        )
        count += 1

    return rows


def _metadata_text(file_row: dict[str, Any]) -> str:
    return " ".join(
        [
            str(file_row.get("rel_path", "")),
            str(file_row.get("stem", "")),
            str(file_row.get("folder", "")),
            str(file_row.get("suffix", "")),
        ]
    )


def _keyword_scores(file_rows: list[dict[str, Any]], query_terms: list[str]) -> list[float]:
    if not file_rows or not query_terms:
        return [0.0 for _ in file_rows]

    tokenized = [tokenize(_metadata_text(row)) for row in file_rows]
    doc_freq: Counter[str] = Counter()
    doc_lengths = [len(tokens) for tokens in tokenized]
    avg_doc_len = (sum(doc_lengths) / len(doc_lengths)) if doc_lengths else 1.0
    total_docs = len(tokenized)

    for tokens in tokenized:
        for token in set(tokens):
            doc_freq[token] += 1

    k1 = 1.5
    b = 0.75
    scores: list[float] = []
    for tokens in tokenized:
        tf = Counter(tokens)
        doc_len = max(1, len(tokens))
        score = 0.0
        for term in query_terms:
            freq = tf.get(term, 0)
            if freq <= 0:
                continue
            df = max(1, doc_freq.get(term, 1))
            idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
            denom = freq + k1 * (1 - b + b * doc_len / max(1.0, avg_doc_len))
            score += idf * ((freq * (k1 + 1)) / max(1e-9, denom))

        scores.append(score)
    return scores


def _build_semantic_text(file_row: dict[str, Any], include_preview: bool) -> str:
    base = (
        f"path: {file_row.get('rel_path', '')}\n"
        f"folder: {file_row.get('folder', '')}\n"
        f"title: {file_row.get('stem', '')}\n"
    )
    if not include_preview:
        return base[:3000]

    path = Path(str(file_row.get("path", "")))
    preview = extract_document_text(path, max_chars=1800) if path.exists() else ""
    if preview:
        base += f"content_preview:\n{preview}\n"
    return base[:7000]


def _semantic_scores_for_candidates(
    candidates: list[dict[str, Any]],
    query_text: str,
    preview_count: int = 24,
) -> tuple[list[float], str]:
    if not candidates:
        return [], "none"

    semantic_texts = []
    for idx, row in enumerate(candidates):
        semantic_texts.append(_build_semantic_text(row, include_preview=idx < preview_count))

    embedder = _skill_semantic_embedder()
    if embedder:
        try:
            query_vec = embedder.embed_batch([query_text])[0]
            doc_vecs = embedder.embed_batch(semantic_texts)
            scores = [_dot(vec, query_vec) for vec in doc_vecs]
            return scores, "skill_embedding_api"
        except Exception:
            pass

    fallback = HashingEmbedder(dim=256)
    q_vec = fallback.embed(query_text)
    doc_vecs = [fallback.embed(text) for text in semantic_texts]
    scores = [_dot(vec, q_vec) for vec in doc_vecs]
    return scores, "hashing_fallback"


def rank_files(
    files: list[dict[str, Any]],
    query: str,
    memory_context: list[str] | None = None,
    top_k: int = 20,
) -> list[dict[str, Any]]:
    if not files:
        return []

    memory_blob = "\n".join(memory_context or [])
    terms = tokenize(query + "\n" + memory_blob)
    if not terms:
        terms = ["research", "paper"]

    semantic_weight = _env_float("SKILL_MEMORY_SEMANTIC_WEIGHT", 0.72, min_value=0.0, max_value=1.0)
    keyword_weight = 1.0 - semantic_weight if terms else 0.0
    if not terms:
        semantic_weight = 1.0

    keyword_raw_all = _keyword_scores(files, terms)
    keyword_norm_all = _normalize_scores(keyword_raw_all)

    scored_all = []
    for row, score in zip(files, keyword_raw_all):
        candidate = dict(row)
        candidate["_keyword_raw"] = float(score)
        scored_all.append(candidate)

    # Keyword pre-filter before semantic pass.
    preselect_multiplier = _env_int("SKILL_PRESELECT_MULTIPLIER", 8, min_value=2, max_value=20)
    preselect_min = _env_int("SKILL_PRESELECT_MIN", 80, min_value=20, max_value=500)
    preselect_max = _env_int("SKILL_PRESELECT_MAX", 240, min_value=50, max_value=1200)
    preselect_size = max(preselect_min, min(preselect_max, top_k * preselect_multiplier))
    pre_candidates = sorted(scored_all, key=lambda x: float(x["_keyword_raw"]), reverse=True)[:preselect_size]

    if not pre_candidates:
        pre_candidates = sorted(files, key=lambda x: -int(x.get("mtime", 0)))[:preselect_size]
        pre_candidates = [dict(row) for row in pre_candidates]
        for row in pre_candidates:
            row["_keyword_raw"] = 0.0

    semantic_preview_count = _env_int("SKILL_SEMANTIC_PREVIEW_COUNT", 24, min_value=4, max_value=120)
    semantic_raw, backend = _semantic_scores_for_candidates(
        candidates=pre_candidates,
        query_text=query + "\n" + memory_blob,
        preview_count=semantic_preview_count,
    )
    semantic_norm = [min(1.0, max(0.0, (value + 1.0) / 2.0)) for value in semantic_raw]

    # Build keyword normalization map for all rows by absolute path.
    keyword_map: dict[str, float] = {}
    for row, score in zip(files, keyword_norm_all):
        keyword_map[str(row.get("path", ""))] = float(score)

    merged: list[dict[str, Any]] = []
    for idx, row in enumerate(pre_candidates):
        semantic_score = semantic_norm[idx] if idx < len(semantic_norm) else 0.0
        keyword_score = keyword_map.get(str(row.get("path", "")), 0.0)
        final_score = semantic_weight * semantic_score + keyword_weight * keyword_score
        candidate = dict(row)
        candidate["score"] = float(final_score)
        candidate["semantic_score"] = float(semantic_score)
        candidate["keyword_score"] = float(keyword_score)
        candidate["retrieval_backend"] = backend
        merged.append(candidate)

    merged.sort(key=lambda x: (float(x.get("score", 0.0)), -int(x.get("mtime", 0))), reverse=True)

    # If everything is flat, fallback to recency selection.
    if merged and max(float(row.get("score", 0.0)) for row in merged) <= 0:
        merged = sorted(merged, key=lambda x: -int(x.get("mtime", 0)))
        for row in merged:
            row["score"] = 0.1

    return merged[:top_k]


def extract_ascii_strings(binary_blob: bytes, min_len: int = 5) -> str:
    text = binary_blob.decode("latin1", errors="ignore")
    parts = re.findall(rf"[A-Za-z0-9,.;:()\-\[\]/ ]{{{min_len},}}", text)
    return "\n".join(parts[:300])


def extract_document_text(path: Path, max_chars: int = 7000) -> str:
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md", ".tex"}:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
        except Exception:
            return ""

    if suffix == ".pdf":
        if command_exists("pdftotext"):
            out = run_cmd(["pdftotext", "-f", "1", "-l", "2", str(path), "-"])
            if out.strip() and "%PDF" not in out[:50]:
                return out[:max_chars]

        # macOS Spotlight text extraction fallback
        if command_exists("mdls"):
            out = run_cmd(["mdls", "-raw", "-name", "kMDItemTextContent", str(path)])
            if out.strip() and out.strip() != "(null)":
                return out[:max_chars]

        try:
            blob = path.read_bytes()[:2_000_000]
            return extract_ascii_strings(blob)[:max_chars]
        except Exception:
            return ""

    try:
        blob = path.read_bytes()[:2_000_000]
        return extract_ascii_strings(blob)[:max_chars]
    except Exception:
        return ""


def split_sections(text: str) -> dict[str, str]:
    lowered = text.lower()
    section_heads = [
        "abstract",
        "introduction",
        "background",
        "method",
        "methods",
        "result",
        "results",
        "discussion",
        "conclusion",
        "conclusions",
    ]

    positions: list[tuple[int, str]] = []
    for head in section_heads:
        idx = lowered.find("\n" + head)
        if idx == -1:
            idx = lowered.find(head + "\n")
        if idx != -1:
            positions.append((idx, head))

    positions.sort(key=lambda x: x[0])
    if not positions:
        return {
            "abstract": text[:1200].strip(),
            "introduction": text[:1200].strip(),
            "conclusion": text[-1200:].strip() if text else "",
        }

    sections: dict[str, str] = {}
    for i, (start, head) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        sections[head] = text[start:end].strip()[:2200]

    abstract = sections.get("abstract", text[:1200])
    intro = sections.get("introduction", sections.get("background", text[:1200]))
    conclusion = sections.get("conclusion", sections.get("conclusions", text[-1200:]))

    return {
        "abstract": abstract.strip(),
        "introduction": intro.strip(),
        "conclusion": conclusion.strip(),
    }


def progressive_reading_plan(file_row: dict[str, Any], text: str) -> dict[str, Any]:
    sections = split_sections(text)
    return {
        "paper": file_row.get("rel_path", file_row.get("name", "")),
        "order": [
            "figures_and_captions",
            "abstract",
            "conclusion",
            "introduction",
            "methods_context",
        ],
        "abstract_preview": sections.get("abstract", "")[:500],
        "conclusion_preview": sections.get("conclusion", "")[:500],
        "introduction_preview": sections.get("introduction", "")[:500],
    }


def top_terms(texts: list[str], limit: int = 12) -> list[str]:
    counter: Counter[str] = Counter()
    for text in texts:
        counter.update(tokenize(text))
    return [term for term, _ in counter.most_common(limit)]


def build_folder_graph(files: list[dict[str, Any]]) -> dict[str, Any]:
    folder_counts: Counter[str] = Counter()
    for item in files:
        folder_counts[str(item.get("folder", "_root"))] += 1

    nodes = [{"id": folder, "count": count} for folder, count in folder_counts.items()]

    edges: list[dict[str, Any]] = []
    folders = sorted(folder_counts.keys())
    for i, left in enumerate(folders):
        for right in folders[i + 1 :]:
            left_tokens = set(tokenize(left.replace("_", " ")))
            right_tokens = set(tokenize(right.replace("_", " ")))
            overlap = left_tokens.intersection(right_tokens)
            if overlap:
                edges.append(
                    {
                        "source": left,
                        "target": right,
                        "weight": len(overlap),
                        "shared_terms": sorted(overlap),
                    }
                )

    return {
        "nodes": sorted(nodes, key=lambda x: x["count"], reverse=True),
        "edges": sorted(edges, key=lambda x: x["weight"], reverse=True),
    }


def build_similarity_edges(files: list[dict[str, Any]], max_pairs: int = 50) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    capped = files[:40]
    for i, left in enumerate(capped):
        left_tokens = set(tokenize(str(left.get("rel_path", ""))))
        if not left_tokens:
            continue
        for right in capped[i + 1 :]:
            right_tokens = set(tokenize(str(right.get("rel_path", ""))))
            if not right_tokens:
                continue
            overlap = left_tokens.intersection(right_tokens)
            union = left_tokens.union(right_tokens)
            if not union:
                continue
            jaccard = len(overlap) / len(union)
            if jaccard >= 0.18:
                pairs.append(
                    {
                        "left": left.get("rel_path", ""),
                        "right": right.get("rel_path", ""),
                        "score": round(jaccard, 3),
                        "overlap_terms": sorted(overlap)[:8],
                    }
                )

    pairs.sort(key=lambda x: x["score"], reverse=True)
    return pairs[:max_pairs]


def slugify(text: str, max_len: int = 36) -> str:
    parts = tokenize(text)
    if not parts:
        return "research"
    slug = "-".join(parts[:6])
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("-")
    return slug or "research"


def create_artifact_dir(skill_name: str, query: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = slugify(query)
    root = Path(".agent_state") / "research_outputs" / skill_name / f"{stamp}_{slug}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers:
        return ""
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        safe = [str(col).replace("\n", " ").strip() for col in row]
        out.append("| " + " | ".join(safe) + " |")
    return "\n".join(out)


def emit_result(summary: str, artifact_dir: Path, json_file: str, md_file: str) -> str:
    return (
        summary
        + "\n\n"
        + f"Artifacts:\n- JSON: {artifact_dir / json_file}\n- Markdown: {artifact_dir / md_file}\n"
    )


def clip(text: str, max_chars: int = 500) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def parse_query_and_focus(task_context: str) -> tuple[str, list[str]]:
    query = task_context.strip()
    focus = tokenize(query)

    # Optional inline syntax: focus: term1, term2
    match = re.search(r"focus\s*:\s*(.+)$", task_context, re.IGNORECASE | re.MULTILINE)
    if match:
        hint = match.group(1)
        focus.extend(tokenize(hint))

    dedup: list[str] = []
    for token in focus:
        if token not in dedup:
            dedup.append(token)
    return query, dedup


def parse_requested_paths(task_context: str) -> list[str]:
    paths: list[str] = []
    for token in extract_possible_paths(task_context):
        lowered = token.lower()
        if lowered.endswith((".pdf", ".txt", ".md", ".doc", ".docx", ".tex", ".ppt", ".pptx")):
            paths.append(token)
    dedup: list[str] = []
    for item in paths:
        if item not in dedup:
            dedup.append(item)
    return dedup


def safe_load_text_file(path: Path, max_chars: int = 8000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def find_existing_artifacts(memory_context: list[str]) -> list[str]:
    blob = "\n".join(memory_context)
    paths = re.findall(r"\.agent_state/research_outputs/[^\s\n]+", blob)
    dedup: list[str] = []
    for item in paths:
        if item not in dedup:
            dedup.append(item)
    return dedup


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        return None
    return None


def to_pretty_path(path: Path) -> str:
    try:
        return str(path.resolve())
    except Exception:
        return str(path)


def shell_quote(value: str) -> str:
    return shlex.quote(value)
