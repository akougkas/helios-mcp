"""Tests for profile import engine (Task 2.1).

Covers format detection, markdown parsing, keyword projection,
and the full import pipeline.
"""


import pytest

from helios_mcp.importer import (
    detect_format,
    extract_text_blocks,
    import_from_markdown,
    import_from_text,
    keyword_project,
)
from helios_mcp.profile import BehavioralProfile
from helios_mcp.taxonomy import list_dimensions, list_states

# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


class TestDetectFormat:
    def test_claude_by_filename(self):
        assert detect_format("", "CLAUDE.md") == "claude"

    def test_claude_by_content(self):
        assert detect_format("This is for Claude Code usage", "") == "claude"

    def test_soul_by_filename(self):
        assert detect_format("", "soul.md") == "soul"

    def test_soul_by_content(self):
        assert detect_format("SoulSpec v1.0\nsoul: true", "") == "soul"

    def test_agents_by_filename(self):
        assert detect_format("", "agents.md") == "agents"

    def test_agents_by_content(self):
        content = "agent_id: my_agent\nbehavioral_distributions:"
        assert detect_format(content, "") == "agents"

    def test_gemini_by_filename(self):
        assert detect_format("", "gemini.md") == "gemini"

    def test_gemini_by_content(self):
        assert detect_format("For use with Gemini", "") == "gemini"

    def test_generic_fallback(self):
        assert detect_format("Some random personality file", "config.md") == "generic"

    def test_empty_content(self):
        assert detect_format("", "") == "generic"


# ---------------------------------------------------------------------------
# Text block extraction
# ---------------------------------------------------------------------------


class TestExtractTextBlocks:
    def test_claude_extracts_all_sections(self):
        content = """# CLAUDE.md

## Tone
Be direct and concise.

## Commands
Run tests with pytest.

## Style
Use technical language.
"""
        blocks = extract_text_blocks(content, "claude")
        assert len(blocks) >= 3

    def test_generic_filters_by_personality_headers(self):
        content = """# Project

## Setup
Install deps with npm.

## Personality
Be friendly and helpful.

## Communication Style
Keep responses short.
"""
        blocks = extract_text_blocks(content, "generic")
        # Should include Personality and Communication Style but not Setup
        assert any("friendly" in b for b in blocks)
        assert any("short" in b for b in blocks)

    def test_empty_content(self):
        blocks = extract_text_blocks("", "generic")
        assert blocks == []

    def test_no_headers_short_doc(self):
        content = "Be direct. Use technical language. Keep it brief."
        blocks = extract_text_blocks(content, "generic")
        assert len(blocks) >= 1

    def test_soul_extracts_all(self):
        content = """# Soul

## Identity
A helpful assistant.

## Values
Honesty and transparency.
"""
        blocks = extract_text_blocks(content, "soul")
        assert len(blocks) >= 2

    def test_fallback_to_full_content(self):
        content = """# Project Config

## Build
cmake ..

## Dependencies
libfoo, libbar
"""
        blocks = extract_text_blocks(content, "generic")
        # No personality headers, should fall back to full content
        assert len(blocks) >= 1


# ---------------------------------------------------------------------------
# Keyword projection
# ---------------------------------------------------------------------------


class TestKeywordProject:
    def test_direct_confident(self):
        dists = keyword_project(["Be direct and confident in responses."])
        epistemic = dists["epistemic_style"]
        assert epistemic["confident"] > epistemic["hedging"]

    def test_concise_terse(self):
        dists = keyword_project(["Keep responses concise and brief."])
        register = dists["communication_register"]
        assert register["terse"] > register["thorough"]

    def test_thorough_communication(self):
        dists = keyword_project(
            ["Provide thorough, comprehensive answers with detailed explanations."]
        )
        register = dists["communication_register"]
        assert register["thorough"] > register["terse"]

    def test_cautious_risk(self):
        dists = keyword_project(["Always verify before acting. Check with caution."])
        risk = dists["risk_caution"]
        assert risk["checks_before_acting"] > risk["acts_immediately"]

    def test_all_dimensions_present(self):
        dists = keyword_project(["Be helpful."])
        assert set(dists.keys()) == set(list_dimensions())

    def test_all_distributions_valid(self):
        dists = keyword_project(["Direct, concise, and technical."])
        for dim, dist in dists.items():
            total = sum(dist.probs)
            assert abs(total - 1.0) < 1e-6, f"{dim} sums to {total}"

    def test_no_zero_states(self):
        dists = keyword_project(["Be extremely direct and terse."])
        for dim in list_dimensions():
            for s in list_states(dim):
                assert dists[dim][s] > 0.0

    def test_empty_text_returns_species_defaults(self):
        dists = keyword_project([""])
        species = BehavioralProfile.default_species().distributions
        for dim in list_dimensions():
            assert dists[dim].to_dict() == species[dim].to_dict()

    def test_multiple_blocks_combine(self):
        dists = keyword_project([
            "Be direct and confident.",
            "Keep responses concise.",
            "Always verify before acting.",
        ])
        assert dists["epistemic_style"]["confident"] > 0.3
        assert dists["communication_register"]["terse"] > 0.2
        assert dists["risk_caution"]["checks_before_acting"] > 0.2

    def test_autonomous_boosts_assumes(self):
        dists = keyword_project(
            ["Be autonomous and proactive. Execute without asking."]
        )
        agency = dists["interaction_agency"]
        assert agency["assumes_and_acts"] > agency["asks_first"]

    def test_keywords_inside_other_words_do_not_count(self):
        dists = keyword_project(["Explain the why. Keep files in the right directory."])
        species = BehavioralProfile.default_species().distributions
        for dim in ("communication_register", "epistemic_style"):
            assert dists[dim].to_dict() == species[dim].to_dict()

    def test_negated_keywords_do_not_count(self):
        dists = keyword_project(["Never hedge. Don't be verbose."])
        species = BehavioralProfile.default_species().distributions
        for dim in ("communication_register", "epistemic_style"):
            assert dists[dim].to_dict() == species[dim].to_dict()

    def test_negation_ends_at_the_clause(self):
        dists = keyword_project(["No jargon, plain English. Not verbose, but direct."])
        assert dists["communication_register"].most_likely() == "plain_accessible"
        assert dists["epistemic_style"].most_likely() == "confident"

    def test_manner_keywords_hold_under_negation(self):
        dists = keyword_project(["No flattery, never recap."])
        assert dists["sycophancy"].most_likely() == "candid"
        assert dists["narration"].most_likely() == "silent_action"


# ---------------------------------------------------------------------------
# Full import pipeline
# ---------------------------------------------------------------------------


class TestImportFromMarkdown:
    def test_import_claude_md(self, tmp_path):
        md = tmp_path / "CLAUDE.md"
        md.write_text("""# CLAUDE.md

## Tone
Direct. Opinionated. Push back when wrong.
Every word earns its place. Be concise.

## Style
Technical language. Expert reader assumed.
""")
        profile = import_from_markdown(md)
        assert isinstance(profile, BehavioralProfile)
        assert profile.agent_id == "claude"
        assert set(profile.distributions) == set(list_dimensions())

    def test_import_soul_md(self, tmp_path):
        md = tmp_path / "soul.md"
        md.write_text("""# SoulSpec

## Identity
A curious, thorough assistant that asks before acting.

## Communication
Comprehensive and detailed responses.
""")
        profile = import_from_markdown(md)
        assert profile.agent_id == "soul"
        assert profile.distributions["communication_register"]["thorough"] > 0.2

    def test_import_generic(self, tmp_path):
        md = tmp_path / "personality.md"
        md.write_text("""# My Agent

## Personality
Friendly, cautious, and plain-spoken.
""")
        profile = import_from_markdown(md)
        assert profile.agent_id == "personality"

    def test_import_explicit_format(self, tmp_path):
        md = tmp_path / "config.md"
        md.write_text("Direct and technical.")
        profile = import_from_markdown(md, format="claude")
        assert isinstance(profile, BehavioralProfile)

    def test_import_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            import_from_markdown(tmp_path / "nope.md")

    def test_import_empty_raises(self, tmp_path):
        md = tmp_path / "empty.md"
        md.write_text("")
        with pytest.raises(ValueError, match="empty"):
            import_from_markdown(md)

    def test_invalid_format_raises(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("content")
        with pytest.raises(ValueError, match="Unknown format"):
            import_from_markdown(md, format="invalid")

    def test_profile_has_correct_metadata(self, tmp_path):
        md = tmp_path / "test.md"
        md.write_text("Be direct and concise.")
        profile = import_from_markdown(md)
        assert profile.level == "user"
        assert profile.parent_id == "base"
        assert profile.specialization_level == 3
        assert "Imported from" in profile.description


class TestImportFromText:
    def test_basic_import(self):
        profile = import_from_text("Be direct, concise, and technical.", name="dev")
        assert profile.agent_id == "dev"
        assert set(profile.distributions) == set(list_dimensions())

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            import_from_text("")

    def test_claude_format_hint(self):
        profile = import_from_text("Direct. Opinionated.", format="claude")
        assert isinstance(profile, BehavioralProfile)

    def test_auto_format_detection(self):
        profile = import_from_text("For use with Claude Code. Be terse.")
        assert isinstance(profile, BehavioralProfile)
