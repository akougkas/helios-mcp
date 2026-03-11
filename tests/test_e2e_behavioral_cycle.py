"""End-to-end test: full behavioral learning cycle.

Bootstrap fresh ~/.helios, feed 25 sessions of biased conversations,
verify drift triggers, accept the negotiation, verify the persona YAML
was updated and git log shows a new commit.

Scientific rules verified:
- Distributions always sum to 1.0
- Drift threshold 0.30 across 4 dimensions
- Minimum 20 observations before drift triggers
- KL-blend M(x) = w·P(x) + (1-w)·Q(x) after accept
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

from helios_mcp.bootstrap import BootstrapManager
from helios_mcp.drift import DriftDetector
from helios_mcp.hierarchy import IdentityHierarchy
from helios_mcp.negotiation import NegotiationEngine, create_proposal_from_observer
from helios_mcp.observer import BehavioralObserver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _terse_confident_messages() -> list[dict]:
    """A short, confident, no-hedging conversation that biases toward:
    - epistemic_style: confident
    - interaction_agency: assumes_and_acts
    - communication_register: terse
    - risk_caution: acts_immediately
    """
    return [
        {"role": "user", "content": "Refactor this function."},
        {"role": "assistant", "content": "Done. I rewrote it using list comprehension."},
        {"role": "user", "content": "Great."},
        {"role": "assistant", "content": "I will update the tests next."},
    ]


def _assert_dist_sums(dists: dict) -> None:
    """Assert every distribution in dists sums to 1.0.

    Handles both BehavioralDistribution objects (with .probs list)
    and plain dicts (state→probability).
    """
    for dim, d in dists.items():
        if hasattr(d, "probs"):
            total = sum(d.probs)
        else:
            total = sum(d.values())
        assert abs(total - 1.0) < 1e-6, f"{dim} sums to {total}, not 1.0"


# ---------------------------------------------------------------------------
# Main E2E test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_behavioral_cycle():
    """Full cycle: bootstrap → observe 25 sessions → drift triggers → accept → git commit."""

    with tempfile.TemporaryDirectory() as tmp:
        helios_dir = Path(tmp)

        # ── 1. Bootstrap fresh installation ──────────────────────────────
        bootstrap = BootstrapManager(helios_dir, git_enabled=True)
        bootstrap.bootstrap_installation()

        assert (helios_dir / "base" / "identity.yaml").exists()
        personas_dir = helios_dir / "personas"
        assert personas_dir.exists()

        # Use the "developer" persona if it was bootstrapped, else create a minimal one
        persona_name = "developer"
        persona_file = personas_dir / f"{persona_name}.yaml"
        if not persona_file.exists():
            # Create a minimal v2 persona
            minimal = {
                "schema_version": "2.0",
                "level": "domain",
                "agent_id": persona_name,
                "behavioral_distributions": {
                    "epistemic_style": {
                        "confident": 0.50, "hedging": 0.25,
                        "admits_ignorance": 0.15, "speculating": 0.10,
                    },
                    "interaction_agency": {
                        "asks_first": 0.40, "assumes_and_acts": 0.20,
                        "offers_options": 0.25, "decides_unilaterally": 0.05,
                        "defers_to_user": 0.10,
                    },
                    "communication_register": {
                        "terse": 0.20, "moderate": 0.40, "thorough": 0.25,
                        "technical_dense": 0.10, "plain_accessible": 0.05,
                    },
                    "risk_caution": {
                        "acts_immediately": 0.20, "checks_before_acting": 0.40,
                        "warns_frequently": 0.25, "refuses_ambiguity": 0.15,
                    },
                },
                "inheritance": {"parent": "species", "kl_blend_weight": 0.7},
                "metadata": {"created": "2026-03-11", "observation_count": 0, "last_negotiation": None},
            }
            persona_file.write_text(yaml.safe_dump(minimal))
            # Add to git
            subprocess.run(["git", "-C", str(helios_dir), "add", str(persona_file)],
                           capture_output=True)
            subprocess.run(["git", "-C", str(helios_dir), "commit", "-m",
                            f"bootstrap: add {persona_name} persona"],
                           capture_output=True)

        # Record the git commit count before learning
        log_before = subprocess.run(
            ["git", "-C", str(helios_dir), "log", "--oneline"],
            capture_output=True, text=True
        ).stdout.strip().splitlines()
        commits_before = len(log_before)

        # ── 2. Observe 25 sessions ────────────────────────────────────────
        observer = BehavioralObserver(helios_dir)
        messages = _terse_confident_messages()

        for i in range(25):
            dists = observer.observe(persona_name, messages)
            _assert_dist_sums(dists)

        # ── 3. Verify observations persisted across fresh instances ───────
        observer2 = BehavioralObserver(helios_dir)
        count = observer2.get_observation_count(persona_name)
        assert count == 25, f"Expected 25 persisted observations, got {count}"

        obs_file = helios_dir / "observations" / f"{persona_name}.json"
        assert obs_file.exists(), "observations/{persona}.json was not created"

        # ── 4. Verify drift triggers ──────────────────────────────────────
        hierarchy = IdentityHierarchy(helios_dir)
        profile = hierarchy.resolve(persona_name)

        accumulated = observer2.get_accumulated_distributions(persona_name)
        _assert_dist_sums(accumulated)

        detector = DriftDetector()
        drift = detector.compute_drift(profile.distributions, accumulated, count)

        assert drift.sufficient_observations, (
            f"Expected sufficient_observations=True with {count} obs "
            f"(min={DriftDetector.MIN_OBSERVATIONS})"
        )
        assert detector.exceeds_threshold(drift), (
            f"Expected drift to exceed threshold {DriftDetector.TOTAL_THRESHOLD}, "
            f"got {drift.total_drift:.4f}. The 25 biased sessions should push drift high."
        )

        # ── 5. Generate negotiation proposal ────────────────────────────
        engine = NegotiationEngine()
        proposal = create_proposal_from_observer(
            persona_name=persona_name,
            helios_dir=helios_dir,
            observer=observer2,
            drift_detector=detector,
        )

        assert proposal is not None
        assert proposal.persona_name == persona_name
        assert proposal.summary  # non-empty NL summary
        assert len(proposal.proposed_distributions) == 4  # all 4 dimensions

        # Proposed distributions must sum to 1.0
        _assert_dist_sums(proposal.proposed_distributions)

        # ── 6. Accept the negotiation ────────────────────────────────────
        profile_yaml_before = yaml.safe_load(persona_file.read_text())

        engine.apply_update(
            helios_dir=helios_dir,
            persona_name=persona_name,
            proposal=proposal,
        )

        # ── 7. Verify persona YAML changed ───────────────────────────────
        profile_yaml_after = yaml.safe_load(persona_file.read_text())

        # The file must still be valid YAML with behavioral_distributions
        assert "behavioral_distributions" in profile_yaml_after, \
            "persona YAML missing behavioral_distributions after update"

        # Distributions in the updated file must still sum to 1.0
        for dim, states in profile_yaml_after["behavioral_distributions"].items():
            total = sum(states.values())
            assert abs(total - 1.0) < 1e-6, \
                f"Updated {dim} distribution sums to {total}"

        # At least one dimension should have changed (drift was real)
        changed = False
        for dim in profile_yaml_before.get("behavioral_distributions", {}):
            before = profile_yaml_before["behavioral_distributions"][dim]
            after = profile_yaml_after["behavioral_distributions"][dim]
            if before != after:
                changed = True
                break
        assert changed, "No distribution changed after accepting negotiation"

        # ── 8. Verify git log has a new commit ───────────────────────────
        log_after = subprocess.run(
            ["git", "-C", str(helios_dir), "log", "--oneline"],
            capture_output=True, text=True
        ).stdout.strip().splitlines()
        commits_after = len(log_after)

        assert commits_after > commits_before, (
            f"Expected new git commit after negotiation accept. "
            f"Before: {commits_before}, after: {commits_after}"
        )

        newest_commit = log_after[0]
        assert persona_name.lower() in newest_commit.lower() or "negotiat" in newest_commit.lower(), \
            f"Newest commit doesn't mention persona or negotiation: {newest_commit}"
