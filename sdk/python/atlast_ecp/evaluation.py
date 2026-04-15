"""
ATLAST ECP — Evaluation Framework

Quality metrics beyond Trust Score:
- task_adherence: did the agent follow instructions?
- frustration_detection: user repeating/escalating?
- response_quality: meaningful vs empty/generic?

All rule-based pattern matching. No LLM-as-judge.
These are SEPARATE scores — they do NOT modify Trust Score.
"""

import json
import re
from typing import Optional


# ── Frustration Patterns ──
FRUSTRATION_PATTERNS = [
    r"i already told you",
    r"i said",
    r"again[!\.]",
    r"this is wrong",
    r"that'?s not what i",
    r"you'?re not listening",
    r"please just",
    r"why can'?t you",
    r"stop doing",
    r"i don'?t want",
    r"not what i asked",
    r"try again",
    r"wrong answer",
    r"you keep",
    r"for the .* time",
]

FRUSTRATION_RE = [re.compile(p, re.IGNORECASE) for p in FRUSTRATION_PATTERNS]


def evaluate_records(records: list, threads: Optional[list] = None) -> dict:
    """Evaluate records on multiple quality dimensions.

    Returns: {
        task_adherence: {score, details},
        frustration: {score, details},
        response_quality: {score, details},
        overall: float (0-100),
    }
    """
    if not records:
        return {"task_adherence": {"score": 100}, "frustration": {"score": 0},
                "response_quality": {"score": 100}, "overall": 100}

    total = len(records)

    # ── Task Adherence ──
    # Proxy: records with errors or empty outputs = failed tasks
    error_count = sum(1 for r in records if r.get("error"))
    empty_count = sum(1 for r in records
                      if not (r.get("output_preview") or "").strip()
                      and not (r.get("flags") or "").count("has_tool_calls"))
    adherence_failures = error_count + empty_count
    adherence_score = max(0, 100 - (adherence_failures / total * 100)) if total else 100

    # ── Frustration Detection ──
    # Scan input_preview for frustration language
    frustration_count = 0
    frustration_examples = []
    for r in records:
        inp = r.get("input_preview", "") or ""
        for pat in FRUSTRATION_RE:
            if pat.search(inp):
                frustration_count += 1
                if len(frustration_examples) < 3:
                    frustration_examples.append(inp[:80])
                break

    # Also detect repetition: same input appearing > 2 times
    inputs = [r.get("input_preview", "")[:50] for r in records if r.get("input_preview")]
    from collections import Counter
    input_counts = Counter(inputs)
    repeated = sum(1 for _, c in input_counts.items() if c > 2)

    frustration_score = min(100, (frustration_count + repeated * 2) / max(total, 1) * 100)

    # ── Response Quality ──
    # Check for generic/low-quality responses
    generic_patterns = [
        r"^i'?m sorry",
        r"^as an ai",
        r"^i cannot",
        r"^i don'?t have access",
        r"^unfortunately",
    ]
    generic_re = [re.compile(p, re.IGNORECASE) for p in generic_patterns]

    generic_count = 0
    short_count = 0
    for r in records:
        out = (r.get("output_preview") or "").strip()
        if not out:
            continue
        # Check for generic responses
        for pat in generic_re:
            if pat.search(out):
                generic_count += 1
                break
        # Check for very short responses (< 20 chars)
        if 0 < len(out) < 20:
            short_count += 1

    quality_issues = generic_count + short_count
    non_empty = sum(1 for r in records if (r.get("output_preview") or "").strip())
    quality_score = max(0, 100 - (quality_issues / max(non_empty, 1) * 100))

    # ── Overall ──
    # Weighted average: adherence 50%, frustration inverted 25%, quality 25%
    overall = (adherence_score * 0.5 +
               max(0, 100 - frustration_score) * 0.25 +
               quality_score * 0.25)

    return {
        "task_adherence": {
            "score": round(adherence_score, 1),
            "errors": error_count,
            "empty_outputs": empty_count,
            "total": total,
        },
        "frustration": {
            "score": round(frustration_score, 1),
            "frustration_count": frustration_count,
            "repeated_inputs": repeated,
            "examples": frustration_examples,
        },
        "response_quality": {
            "score": round(quality_score, 1),
            "generic_responses": generic_count,
            "short_responses": short_count,
        },
        "overall": round(overall, 1),
        "record_count": total,
    }
