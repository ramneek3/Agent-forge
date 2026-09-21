"""Input and output guardrails."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GuardrailResult:
    passed: bool
    name: str
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(your\s+)?(system|previous)\s+(prompt|instructions)",
    r"you\s+are\s+now\s+(dan|jailbroken|unrestricted)",
    r"reveal\s+(your\s+)?system\s+prompt",
    r"<\s*/?\s*system\s*>",
]

UNSAFE_OUTPUT_PATTERNS = [
    r"\bhow to (make|build|assemble) (a )?bomb\b",
    r"\bcredit card number\b.*\d{4}[-\s]?\d{4}",
]


class GuardrailService:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.max_prompt_length = int(self.config.get("max_prompt_length", 16_000))
        self.blocked_patterns = list(self.config.get("blocked_patterns", []))
        self.require_grounding = bool(self.config.get("require_grounding", False))

    def check_input(self, text: str) -> list[GuardrailResult]:
        results: list[GuardrailResult] = []

        # Length
        if len(text) > self.max_prompt_length:
            results.append(
                GuardrailResult(
                    False,
                    "prompt_length",
                    f"Prompt exceeds max length ({self.max_prompt_length})",
                    {"length": len(text)},
                )
            )
        else:
            results.append(
                GuardrailResult(True, "prompt_length", "OK", {"length": len(text)})
            )

        # Injection
        lowered = text.lower()
        hit = None
        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, lowered, re.I):
                hit = pattern
                break
        if hit:
            results.append(
                GuardrailResult(
                    False,
                    "prompt_injection",
                    "Potential prompt injection detected",
                    {"pattern": hit},
                )
            )
        else:
            results.append(GuardrailResult(True, "prompt_injection", "OK"))

        # Blocked patterns
        blocked_hit = None
        for pattern in self.blocked_patterns:
            if re.search(pattern, text, re.I):
                blocked_hit = pattern
                break
        if blocked_hit:
            results.append(
                GuardrailResult(
                    False,
                    "blocked_pattern",
                    "Blocked pattern matched",
                    {"pattern": blocked_hit},
                )
            )
        else:
            results.append(GuardrailResult(True, "blocked_pattern", "OK"))

        return results

    def check_output(
        self,
        text: str,
        *,
        used_rag: bool = False,
        citations: list[Any] | None = None,
    ) -> list[GuardrailResult]:
        results: list[GuardrailResult] = []

        if not text or not text.strip():
            results.append(
                GuardrailResult(False, "empty_response", "Model returned empty response")
            )
        else:
            results.append(GuardrailResult(True, "empty_response", "OK"))

        unsafe_hit = None
        for pattern in UNSAFE_OUTPUT_PATTERNS:
            if re.search(pattern, text, re.I):
                unsafe_hit = pattern
                break
        if unsafe_hit:
            results.append(
                GuardrailResult(
                    False,
                    "unsafe_output",
                    "Potential unsafe output detected",
                    {"pattern": unsafe_hit},
                )
            )
        else:
            results.append(GuardrailResult(True, "unsafe_output", "OK"))

        if used_rag and self.require_grounding:
            has_cite = bool(citations) or bool(
                re.search(r"\[citation:|according to|based on (the )?(document|context|source)", text, re.I)
            )
            if not has_cite:
                results.append(
                    GuardrailResult(
                        False,
                        "grounding",
                        "RAG used but response lacks grounding/citations",
                    )
                )
            else:
                results.append(GuardrailResult(True, "grounding", "OK"))
        elif used_rag:
            results.append(
                GuardrailResult(
                    True,
                    "grounding",
                    "Grounding check soft-pass",
                    {"citations": len(citations or [])},
                )
            )

        return results

    def assert_all_passed(self, results: list[GuardrailResult]) -> None:
        from app.core.exceptions import GuardrailError

        failures = [r for r in results if not r.passed]
        if failures:
            f = failures[0]
            raise GuardrailError(f.message, guardrail=f.name)
