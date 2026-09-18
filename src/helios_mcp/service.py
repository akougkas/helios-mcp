"""HeliosService: the one engine API behind the MCP server and the CLI.

Every public method validates the persona name before touching disk, returns
plain JSON-ready dicts, and re-renders ``rendered/<persona>.md`` whenever the
persona's resolved profile may have changed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TypedDict

from .atomic_ops import atomic_write_text, git_commit
from .bootstrap import BootstrapManager
from .drift import DEFAULT_CONFIG, DriftAssessment, DriftConfig
from .estimator import Evidence
from .negotiation import Evaluation, Negotiator, describe
from .renderer import BehavioralRenderer
from .security import SecurityError, persona_path, validate_persona_name
from .store import ObservationStore, TurnObservation

logger = logging.getLogger(__name__)

DEFAULT_PERSONA_FILE = "default_persona"
FALLBACK_PERSONA = "default"


class DimensionReport(TypedDict):
    divergence: float
    credibility: float
    tier: str | None
    evidence: float
    dominant_declared: str
    dominant_observed: str
    declared: dict[str, float]
    posterior_mean: dict[str, float]


class DriftReport(TypedDict):
    persona: str
    turns: int
    negotiation_recommended: bool
    proposal_id: str | None
    proposal_tier: str | None
    summary: str
    per_dimension: dict[str, str]
    endorsed: dict[str, DimensionReport]
    fingerprint: dict[str, DimensionReport]
    auto_accepted: list[str]
    cooling_down: list[str]


class ObserveReport(TypedDict):
    persona: str
    observations_added: int
    turns: int
    negotiation_recommended: bool
    proposal_id: str | None
    proposal_tier: str | None
    auto_accepted: list[str]


class DecisionReport(TypedDict):
    persona: str
    proposal_id: str
    status: str
    dimensions: list[str]
    commit: str | None
    reason: str | None


def _dimension_reports(assessment: DriftAssessment) -> dict[str, DimensionReport]:
    out: dict[str, DimensionReport] = {}
    for dim, r in assessment.dimensions.items():
        out[dim] = {
            "divergence": round(r.divergence, 5),
            "credibility": round(r.credibility, 3),
            "tier": r.tier,
            "evidence": round(r.evidence, 2),
            "dominant_declared": max(r.declared, key=r.declared.__getitem__),
            "dominant_observed": max(r.posterior_mean,
                                     key=r.posterior_mean.__getitem__),
            "declared": {s: round(p, 4) for s, p in r.declared.items()},
            "posterior_mean": {s: round(p, 4) for s, p in r.posterior_mean.items()},
        }
    return out


def _ingest_module() -> Any:
    """The observe pipeline's ingest module, or None before it is installed."""
    try:
        from . import ingest  # type: ignore[attr-defined, unused-ignore]
    except ImportError:
        return None
    return ingest


class HeliosService:
    def __init__(self, helios_dir: Path, config: DriftConfig = DEFAULT_CONFIG,
                 bootstrap: bool = True) -> None:
        self.helios_dir = helios_dir
        self.config = config
        self.negotiator = Negotiator(helios_dir, config)
        self.ledger = ObservationStore(helios_dir)
        if bootstrap:
            manager = BootstrapManager(helios_dir)
            if manager.is_first_install():
                manager.bootstrap_installation()
                for persona in self.list_personas():
                    self.render(persona)

    # -- personas ------------------------------------------------------

    def persona(self, name: str | None) -> str:
        """Validate ``name``, or fall back to the configured default persona."""
        if name:
            return validate_persona_name(name)
        path = self.helios_dir / DEFAULT_PERSONA_FILE
        try:
            stored = path.read_text(encoding="utf-8").strip()
        except OSError:
            return FALLBACK_PERSONA
        try:
            return validate_persona_name(stored)
        except SecurityError:
            logger.warning("ignoring invalid default persona in %s", path)
            return FALLBACK_PERSONA

    def set_default_persona(self, name: str) -> str:
        persona = validate_persona_name(name)
        atomic_write_text(self.helios_dir / DEFAULT_PERSONA_FILE, persona + "\n")
        return persona

    def list_personas(self) -> list[str]:
        personas_dir = self.helios_dir / "personas"
        return sorted(
            p.stem for p in personas_dir.glob("*.yaml")
            if not p.stem.endswith("_user")
        )

    def context(self, name: str | None, model: str | None = None) -> dict[str, Any]:
        persona = self.persona(name)
        profile = self.negotiator.hierarchy.resolve(persona)
        evidence = self.negotiator.evidence(persona)
        return {
            "persona": persona,
            "behavioral_context": self.render_text(persona, model, evidence),
            "observation_count": evidence.turns,
            "specialization_level": profile.specialization_level,
        }

    def render_text(self, name: str | None, model: str | None = None,
                    evidence: Evidence | None = None) -> str:
        """The context text, with counter-tendency blocks for ``model`` or,
        when it is unknown, for the most observed models."""
        persona = self.persona(name)
        profile = self.negotiator.hierarchy.resolve(persona)
        fingerprints = [(m, a) for m, _, a in
                        self.negotiator.model_fingerprints(persona, evidence)]
        return BehavioralRenderer().render(profile, persona, fingerprints, model)

    def render(self, name: str | None, evidence: Evidence | None = None) -> Path:
        """Write ``rendered/<persona>.md`` for the SessionStart hook.

        The hook does not know which model the session will run, so the file
        carries the blocks for the most observed models.
        """
        persona = self.persona(name)
        path = persona_path(self.helios_dir / "rendered", persona, ".md")
        atomic_write_text(path, self.render_text(persona, evidence=evidence) + "\n")
        return path

    # -- observation ---------------------------------------------------

    def record(self, observations: list[TurnObservation],
               name: str | None) -> ObserveReport:
        persona = self.persona(name)
        strays = {o.persona for o in observations} - {persona}
        if strays:
            raise ValueError(f"observations for other personas: {sorted(strays)}")
        added = self.ledger.append(observations)
        return self._observe_report(persona, added, self._evaluate(persona))

    def observe_messages(self, name: str | None, messages: list[dict[str, Any]],
                         session_id: str | None = None) -> ObserveReport:
        persona = self.persona(name)
        ingest = _ingest_module()
        if ingest is None:
            raise RuntimeError("the ingest pipeline (helios_mcp.ingest) is missing")
        observations = ingest.observations_from_messages(
            persona=persona, messages=messages, session_id=session_id)
        return self.record(list(observations), persona)

    def ingest(self, name: str | None, transcript: Path, session_id: str,
               final: bool = False) -> ObserveReport:
        persona = self.persona(name)
        ingest = _ingest_module()
        if ingest is None:
            raise RuntimeError("the ingest pipeline (helios_mcp.ingest) is missing")
        added = int(ingest.ingest_session(
            self.helios_dir, persona, transcript, session_id, final=final))
        return self._observe_report(persona, added, self._evaluate(persona))

    # -- drift and negotiation -----------------------------------------

    def drift_report(self, name: str | None) -> DriftReport:
        """Current endorsed drift, fingerprint diagnostics and the pending proposal.

        Does not auto-accept, so reading a report never changes the profile.
        """
        persona = self.persona(name)
        evaluation = self.negotiator.evaluate(persona, auto_accept=False)
        summary, per_dim = describe(evaluation)
        return {
            "persona": persona,
            "turns": evaluation.evidence.turns,
            "negotiation_recommended": evaluation.proposal is not None,
            "proposal_id": evaluation.proposal.id if evaluation.proposal else None,
            "proposal_tier": (evaluation.proposal.tier if evaluation.proposal
                              else None),
            "summary": summary,
            "per_dimension": per_dim,
            "endorsed": _dimension_reports(evaluation.endorsed),
            "fingerprint": _dimension_reports(evaluation.fingerprint),
            "auto_accepted": evaluation.auto_accepted,
            "cooling_down": evaluation.cooling_down,
        }

    def accept(self, name: str | None, proposal_id: str,
               dimensions: list[str] | None = None) -> DecisionReport:
        persona = self.persona(name)
        decision = self.negotiator.accept(persona, proposal_id, dimensions)
        self.render(persona)
        return self._decision_report(persona, decision.proposal, decision.commit)

    def reject(self, name: str | None, proposal_id: str, reason: str = "",
               dimensions: list[str] | None = None) -> DecisionReport:
        persona = self.persona(name)
        decision = self.negotiator.reject(persona, proposal_id, reason, dimensions)
        return self._decision_report(persona, decision.proposal, decision.commit)

    # -- import and export ---------------------------------------------

    def import_profile(self, source: Path, name: str | None = None,
                       fmt: str = "auto") -> dict[str, Any]:
        from .importer import import_from_markdown

        if name:
            validate_persona_name(name)
        profile = import_from_markdown(source, format=fmt,
                                       helios_dir=self.helios_dir)
        persona = validate_persona_name(name or profile.agent_id)
        profile.agent_id = persona
        out = persona_path(self.helios_dir / "personas", persona, ".yaml")
        profile.save(out)
        commit = git_commit(self.helios_dir, [out],
                            f"{persona}: imported from {source.name}")
        self.render(persona)
        return {
            "persona": persona,
            "source": str(source),
            "saved_to": str(out),
            "commit": commit,
            "distributions": {
                dim: {"dominant": d.most_likely(),
                      "entropy": round(d.normalized_entropy(), 3)}
                for dim, d in profile.distributions.items()
            },
        }

    def export_profile(self, name: str | None, fmt: str = "yaml",
                       dimensions: list[str] | None = None) -> dict[str, Any]:
        from .exporter import export_dimensions, export_soulspec

        persona = self.persona(name)
        profile = self.negotiator.hierarchy.resolve(persona)
        if fmt == "soulspec":
            return {"persona": persona, "format": fmt,
                    "content": export_soulspec(profile)}
        if fmt not in ("yaml", "json"):
            raise ValueError(f"unknown export format {fmt!r}")
        exported = export_dimensions(profile, dimensions)
        return {"persona": persona, "format": fmt,
                "agent_id": exported["agent_id"], "level": exported["level"],
                "dimensions": exported["dimensions"]}

    # ------------------------------------------------------------------

    def _evaluate(self, persona: str) -> Evaluation:
        evaluation = self.negotiator.evaluate(persona)
        # New turns move the per-model fingerprints even when the profile holds.
        self.render(persona, evaluation.evidence)
        return evaluation

    @staticmethod
    def _observe_report(persona: str, added: int,
                        evaluation: Evaluation) -> ObserveReport:
        return {
            "persona": persona,
            "observations_added": added,
            "turns": evaluation.evidence.turns,
            "negotiation_recommended": evaluation.proposal is not None,
            "proposal_id": evaluation.proposal.id if evaluation.proposal else None,
            "proposal_tier": (evaluation.proposal.tier if evaluation.proposal
                              else None),
            "auto_accepted": evaluation.auto_accepted,
        }

    @staticmethod
    def _decision_report(persona: str, proposal: Any,
                         commit: str | None) -> DecisionReport:
        return {
            "persona": persona,
            "proposal_id": proposal.id,
            "status": proposal.status,
            "dimensions": list(proposal.decided_dimensions),
            "commit": commit,
            "reason": proposal.reason,
        }
