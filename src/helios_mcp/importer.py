"""Profile import engine for Helios v2.

Parses existing personality files (CLAUDE.md, soul.md, agents.md, etc.)
into Helios BehavioralProfile objects with probability distributions.

Two-stage pipeline:
1. Parse markdown into structured text blocks (personality-relevant sections)
2. Map text blocks to probability distributions via keyword heuristics

Format detection supports: CLAUDE.md, soul.md, agents.md, gemini.md,
and generic markdown personality files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .distribution import BehavioralDistribution
from .profile import BehavioralProfile
from .taxonomy import BEHAVIORAL_TAXONOMY, list_dimensions, list_states


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

@dataclass
class ImportSource:
    """Parsed import source with detected format and extracted text blocks."""

    path: Path
    format: str  # "claude" | "soul" | "agents" | "gemini" | "generic"
    text_blocks: list[str] = field(default_factory=list)
    raw_content: str = ""


def detect_format(content: str, filename: str = "") -> str:
    """Detect the personality file format from content and filename.

    Args:
        content: File content to analyze.
        filename: Original filename for hint-based detection.

    Returns:
        Format string: "claude", "soul", "agents", "gemini", or "generic".
    """
    lower_name = filename.lower()
    lower_content = content.lower()

    # Filename-based detection
    if "claude" in lower_name:
        return "claude"
    if "soul" in lower_name:
        return "soul"
    if "agents" in lower_name:
        return "agents"
    if "gemini" in lower_name:
        return "gemini"

    # Content-based detection
    if "claude code" in lower_content or "claude.md" in lower_content:
        return "claude"
    if "soulspec" in lower_content or "soul:" in lower_content:
        return "soul"
    if "agent_id" in lower_content or "behavioral_distributions" in lower_content:
        return "agents"
    if "gemini" in lower_content:
        return "gemini"

    return "generic"


# ---------------------------------------------------------------------------
# Markdown parsing
# ---------------------------------------------------------------------------

# Section headers that contain personality-relevant content
_PERSONALITY_HEADERS = re.compile(
    r"(?i)(tone|style|personality|behavior|communication|voice|"
    r"preferences|instructions|rules|constraints|identity|"
    r"approach|principles|mindset|role|character|persona)",
)


def extract_text_blocks(content: str, format: str) -> list[str]:
    """Extract personality-relevant text blocks from a markdown file.

    Splits the markdown by headers and returns sections whose headers
    match personality-related keywords.

    Args:
        content: Raw markdown content.
        format: Detected format (affects parsing strategy).

    Returns:
        List of text blocks containing personality-relevant content.
    """
    if not content.strip():
        return []

    # Split into sections by markdown headers
    sections = _split_by_headers(content)

    # Filter to personality-relevant sections
    blocks: list[str] = []
    for header, body in sections:
        if not body.strip():
            continue

        # For CLAUDE.md, nearly everything is personality-relevant
        if format == "claude":
            blocks.append(body.strip())
            continue

        # For soul.md, everything under SoulSpec structure is relevant
        if format == "soul":
            blocks.append(body.strip())
            continue

        # For other formats, filter by personality-relevant headers
        if header and _PERSONALITY_HEADERS.search(header):
            blocks.append(body.strip())
        elif not header and len(sections) <= 3:
            # Short documents without clear headers: include everything
            blocks.append(body.strip())

    # If no personality sections found, fall back to full content
    if not blocks:
        blocks = [content.strip()]

    return blocks


def _split_by_headers(content: str) -> list[tuple[str, str]]:
    """Split markdown content into (header, body) tuples.

    Returns a list of (header_text, body_text) pairs.
    The first entry may have an empty header if content starts without one.
    """
    header_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    sections: list[tuple[str, str]] = []

    matches = list(header_pattern.finditer(content))
    if not matches:
        return [("", content)]

    # Content before first header
    if matches[0].start() > 0:
        pre = content[:matches[0].start()]
        if pre.strip():
            sections.append(("", pre))

    for i, m in enumerate(matches):
        header = m.group(2)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[start:end]
        sections.append((header, body))

    return sections


# ---------------------------------------------------------------------------
# Keyword-based distribution mapping
# ---------------------------------------------------------------------------

# Keyword → (dimension, state, weight) mappings
# These are the deterministic heuristic fallback for when LLM projection
# is unavailable. Quality is intentionally lower than LLM-assisted projection.

_KEYWORD_MAP: dict[str, list[tuple[str, str, float]]] = {
    # epistemic_style keywords
    "direct": [("epistemic_style", "confident", 2.0)],
    "confident": [("epistemic_style", "confident", 2.0)],
    "assertive": [("epistemic_style", "confident", 1.5)],
    "decisive": [("epistemic_style", "confident", 1.5)],
    "opinionated": [("epistemic_style", "confident", 1.5)],
    "hedge": [("epistemic_style", "hedging", 2.0)],
    "careful": [("epistemic_style", "hedging", 1.0), ("risk_caution", "checks_before_acting", 1.5)],
    "uncertain": [("epistemic_style", "hedging", 1.5)],
    "honest": [("epistemic_style", "admits_ignorance", 1.5)],
    "transparent": [("epistemic_style", "admits_ignorance", 1.0)],
    "curious": [("epistemic_style", "speculating", 1.5)],
    "exploratory": [("epistemic_style", "speculating", 1.5)],
    "creative": [("epistemic_style", "speculating", 1.0)],

    # interaction_agency keywords
    "ask first": [("interaction_agency", "asks_first", 2.0)],
    "clarify": [("interaction_agency", "asks_first", 1.5)],
    "question": [("interaction_agency", "asks_first", 1.0)],
    "autonomous": [("interaction_agency", "assumes_and_acts", 2.0)],
    "proactive": [("interaction_agency", "assumes_and_acts", 1.5)],
    "execute": [("interaction_agency", "assumes_and_acts", 1.0)],
    "options": [("interaction_agency", "offers_options", 2.0)],
    "alternatives": [("interaction_agency", "offers_options", 1.5)],
    "suggest": [("interaction_agency", "offers_options", 1.0)],
    "independent": [("interaction_agency", "decides_unilaterally", 1.5)],
    "defer": [("interaction_agency", "defers_to_user", 2.0)],
    "user control": [("interaction_agency", "defers_to_user", 1.5)],

    # communication_register keywords
    "concise": [("communication_register", "terse", 2.0)],
    "terse": [("communication_register", "terse", 2.5)],
    "brief": [("communication_register", "terse", 2.0)],
    "minimal": [("communication_register", "terse", 1.5)],
    "short": [("communication_register", "terse", 1.5)],
    "balanced": [("communication_register", "moderate", 1.5)],
    "moderate": [("communication_register", "moderate", 1.5)],
    "thorough": [("communication_register", "thorough", 2.0)],
    "comprehensive": [("communication_register", "thorough", 2.0)],
    "detailed": [("communication_register", "thorough", 1.5)],
    "verbose": [("communication_register", "thorough", 1.5)],
    "technical": [("communication_register", "technical_dense", 2.0)],
    "jargon": [("communication_register", "technical_dense", 1.5)],
    "expert": [("communication_register", "technical_dense", 1.0)],
    "plain": [("communication_register", "plain_accessible", 2.0)],
    "simple": [("communication_register", "plain_accessible", 1.5)],
    "accessible": [("communication_register", "plain_accessible", 1.5)],

    # risk_caution keywords
    "fast": [("risk_caution", "acts_immediately", 1.5)],
    "act immediately": [("risk_caution", "acts_immediately", 2.0)],
    "quick": [("risk_caution", "acts_immediately", 1.0)],
    "verify": [("risk_caution", "checks_before_acting", 2.0)],
    "check": [("risk_caution", "checks_before_acting", 1.5)],
    "confirm": [("risk_caution", "checks_before_acting", 1.5)],
    "test": [("risk_caution", "checks_before_acting", 1.0)],
    "warn": [("risk_caution", "warns_frequently", 2.0)],
    "caution": [("risk_caution", "warns_frequently", 1.5)],
    "risk": [("risk_caution", "warns_frequently", 1.0)],
    "safe": [("risk_caution", "warns_frequently", 1.0)],
    "refuse": [("risk_caution", "refuses_ambiguity", 2.0)],
    "ambiguity": [("risk_caution", "refuses_ambiguity", 1.5)],
    "strict": [("risk_caution", "refuses_ambiguity", 1.0)],
}


def keyword_project(text_blocks: list[str]) -> dict[str, BehavioralDistribution]:
    """Map text blocks to behavioral distributions via keyword matching.

    Scans all text blocks for keywords and accumulates weighted
    contributions to each behavioral state. The result is normalized
    into proper probability distributions.

    This is the deterministic fallback when LLM-assisted projection
    is unavailable.

    Args:
        text_blocks: List of personality-relevant text extracted from markdown.

    Returns:
        Dict mapping dimension name to BehavioralDistribution.
    """
    # Accumulate weights per dimension per state
    weights: dict[str, dict[str, float]] = {}
    for dim in list_dimensions():
        weights[dim] = {s: 0.1 for s in list_states(dim)}  # uniform prior

    full_text = " ".join(text_blocks).lower()

    for keyword, contributions in _KEYWORD_MAP.items():
        if keyword in full_text:
            for dim, state, weight in contributions:
                weights[dim][state] = weights[dim].get(state, 0.0) + weight

    # Normalize to distributions
    dists: dict[str, BehavioralDistribution] = {}
    for dim in list_dimensions():
        total = sum(weights[dim].values())
        if total > 0:
            normalized = {s: v / total for s, v in weights[dim].items()}
        else:
            n = len(weights[dim])
            normalized = {s: 1.0 / n for s in weights[dim]}
        dists[dim] = BehavioralDistribution(dim, normalized)

    return dists


# ---------------------------------------------------------------------------
# Main import function
# ---------------------------------------------------------------------------

def import_from_markdown(
    path: Path,
    format: str = "auto",
) -> BehavioralProfile:
    """Import a personality file into a Helios BehavioralProfile.

    Two-stage pipeline:
    1. Parse the file, detect format, extract personality-relevant blocks
    2. Project text blocks to probability distributions via keyword heuristics

    Args:
        path: Path to the markdown/personality file.
        format: File format. "auto" for auto-detection.
            Valid values: "auto", "claude", "soul", "agents", "gemini", "generic".

    Returns:
        A BehavioralProfile with projected distributions.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the file is empty or format is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"Import source not found: {path}")

    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"Import source is empty: {path}")

    # Stage 1: parse
    if format == "auto":
        format = detect_format(content, path.name)

    valid_formats = ("claude", "soul", "agents", "gemini", "generic")
    if format not in valid_formats:
        raise ValueError(f"Unknown format: {format!r}. Valid: {valid_formats}")

    text_blocks = extract_text_blocks(content, format)

    # Stage 2: project to distributions
    distributions = keyword_project(text_blocks)

    # Build profile
    persona_name = path.stem.lower().replace(" ", "_")
    profile = BehavioralProfile(
        agent_id=persona_name,
        level="user",
        distributions=distributions,
        parent_id="base",
        specialization_level=3,
        base_importance=0.7,
        description=f"Imported from {path.name}",
    )

    return profile


def import_from_text(
    text: str,
    name: str = "imported",
    format: str = "auto",
) -> BehavioralProfile:
    """Import from raw text content (no file required).

    Useful for MCP tool calls where the content is provided directly.

    Args:
        text: Raw markdown/personality text.
        name: Name for the resulting profile.
        format: File format hint.

    Returns:
        A BehavioralProfile with projected distributions.
    """
    if not text.strip():
        raise ValueError("Import text is empty")

    if format == "auto":
        format = detect_format(text)

    text_blocks = extract_text_blocks(text, format)
    distributions = keyword_project(text_blocks)

    return BehavioralProfile(
        agent_id=name,
        level="user",
        distributions=distributions,
        parent_id="base",
        specialization_level=3,
        base_importance=0.7,
        description=f"Imported from text ({format} format)",
    )
