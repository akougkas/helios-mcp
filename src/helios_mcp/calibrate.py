"""Corpus calibration for the observe pipeline, aggregates only.

Runs the heuristic classifier and endorsement judge over a directory of
Claude Code transcripts, optionally labels a sample of sessions with the
model, and reports label distributions, endorsement and correction rates, and
heuristic-versus-model agreement. The report holds numbers only; no transcript
text leaves this process.

    python -m helios_mcp.calibrate ~/.claude/projects --llm-sample 20
    python -m helios_mcp.calibrate ~/.claude/projects --label-into DIR

``--label-into`` writes a full-corpus observation ledger (heuristic and model
rows, persona ``corpus``) under DIR through the same ingest path SessionEnd
uses. Re-running it labels only turns that still lack a model row.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .classify import classify_turn
from .endorsement import judge_turn
from .ingest import ingest_session
from .llm import LLMClient, LLMTurnLabel, default_client, label_session
from .taxonomy import list_dimensions
from .transcript import AgentTurn, Session, parse_transcript

EXCLUDE_MARKERS = ("helios-lab", "helios-wt")
CORPUS_PERSONA = "corpus"


def iter_transcripts(root: Path) -> Iterator[Path]:
    """Main-session transcripts under ``root``, skipping subagents and lab runs."""
    for path in sorted(root.glob("*/*.jsonl")):
        if any(marker in str(path) for marker in EXCLUDE_MARKERS):
            continue
        yield path


def _js(p: dict[str, float], q: dict[str, float]) -> float:
    def kl(a: dict[str, float], m: dict[str, float]) -> float:
        return sum(v * math.log(v / m[k]) for k, v in a.items() if v > 0)

    m = {k: 0.5 * (p.get(k, 0.0) + q.get(k, 0.0)) for k in {*p, *q}}
    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def _argmax(d: dict[str, float]) -> str:
    return max(d, key=d.__getitem__)


def _quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    values = sorted(values)

    def pick(q: float) -> float:
        return values[min(int(q * len(values)), len(values) - 1)]

    return {
        "p10": round(pick(0.1), 4),
        "p50": round(pick(0.5), 4),
        "p90": round(pick(0.9), 4),
        "mean": round(statistics.fmean(values), 4),
    }


class HeuristicStats:
    def __init__(self) -> None:
        self.sessions = 0
        self.turns = 0
        self.turns_per_session: list[float] = []
        self.label_sum: dict[str, Counter[str]] = defaultdict(Counter)
        self.label_n: Counter[str] = Counter()
        self.argmax: dict[str, Counter[str]] = defaultdict(Counter)
        self.confidence: dict[str, list[float]] = defaultdict(list)
        self.peak: dict[str, list[float]] = defaultdict(list)
        self.endorsement_kind: Counter[str] = Counter()
        self.prompt_kind: Counter[str] = Counter()
        self.hints: Counter[str] = Counter()
        self.flags: Counter[str] = Counter()

    def add(self, session: Session) -> None:
        self.sessions += 1
        self.turns += len(session.turns)
        self.turns_per_session.append(float(len(session.turns)))
        for turn in session.turns:
            out = classify_turn(turn)
            for dim, label in out.labels.items():
                self.label_n[dim] += 1
                self.label_sum[dim].update(label)
                self.argmax[dim][_argmax(label)] += 1
                self.confidence[dim].append(out.confidence[dim])
                self.peak[dim].append(max(label.values()))
            verdict = judge_turn(turn)
            self.endorsement_kind[verdict.kind] += 1
            for dim, state in (verdict.correction_hint or {}).items():
                self.hints[f"{dim}.{state}"] += 1
            self.prompt_kind[turn.prompt.kind if turn.prompt else "none"] += 1
            self.flags["interrupted"] += turn.interrupted
            self.flags["denied"] += bool(turn.denials)
            self.flags["steered"] += bool(turn.steers)
            self.flags["ask_tool"] += any(
                c.name == "AskUserQuestion" for c in turn.tool_calls
            )

    def report(self) -> dict[str, Any]:
        dims: dict[str, Any] = {}
        for dim in list_dimensions():
            n = self.label_n[dim]
            if not n:
                continue
            dims[dim] = {
                "turns_labeled": n,
                "mean_label": {
                    s: round(v / n, 4) for s, v in self.label_sum[dim].items()
                },
                "argmax_share": {
                    s: round(c / n, 4) for s, c in self.argmax[dim].most_common()
                },
                "confidence": _quantiles(self.confidence[dim]),
                "peak_probability": _quantiles(self.peak[dim]),
            }
        human = sum(
            v for k, v in self.endorsement_kind.items() if k not in {"neutral", "none"}
        )
        return {
            "sessions": self.sessions,
            "turns": self.turns,
            "turns_per_session": _quantiles(self.turns_per_session),
            "dimensions": dims,
            "endorsement_kind": dict(self.endorsement_kind.most_common()),
            "correction_rate_of_human_followed": round(
                sum(
                    self.endorsement_kind[k]
                    for k in ("corrected", "interrupted", "denied")
                )
                / human,
                4,
            )
            if human
            else None,
            "correction_hints": dict(self.hints.most_common()),
            "turn_started_by": dict(self.prompt_kind.most_common()),
            "turn_flags": dict(self.flags),
        }


class AgreementStats:
    def __init__(self) -> None:
        self.sessions = 0
        self.turns = 0
        self.labeled = 0
        self.dims: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "both": 0,
                "argmax_agree": 0,
                "js": [],
                "llm_only": 0,
                "heuristic_only": 0,
                "llm_mean": Counter(),
            }
        )
        self.endorse = Counter[str]()
        self.hint = Counter[str]()
        self.llm_hints = Counter[str]()
        self.llm_endorse_kind = Counter[str]()

    def add(self, turns: list[AgentTurn], labels: dict[str, LLMTurnLabel]) -> None:
        self.sessions += 1
        self.turns += len(turns)
        for turn in turns:
            llm = labels.get(turn.turn_id)
            if llm is None:
                continue
            self.labeled += 1
            heur = classify_turn(turn)
            for dim in list_dimensions():
                h, m = heur.labels.get(dim), llm.labels.get(dim)
                stats = self.dims[dim]
                if m is not None:
                    stats["llm_mean"].update(m)
                if h is not None and m is not None:
                    stats["both"] += 1
                    stats["argmax_agree"] += _argmax(h) == _argmax(m)
                    stats["js"].append(_js(h, m))
                elif m is not None:
                    stats["llm_only"] += 1
                elif h is not None:
                    stats["heuristic_only"] += 1
            verdict = judge_turn(turn)
            hv, mv = verdict.value, llm.endorsement
            if mv is None:
                self.llm_endorse_kind["none"] += 1
            else:
                self.llm_endorse_kind[
                    "corrected" if mv < 0 else ("neutral" if mv == 0 else "positive")
                ] += 1
            if hv is not None and mv is not None:
                self.endorse["both"] += 1
                self.endorse["sign_agree"] += (hv < 0) == (mv < 0)
                self.endorse["heuristic_neg_llm_nonneg"] += hv < 0 <= mv
                self.endorse["llm_neg_heuristic_nonneg"] += mv < 0 <= hv
            hh, mh = verdict.correction_hint or {}, llm.correction_hint or {}
            for dim, state in mh.items():
                self.llm_hints[f"{dim}.{state}"] += 1
            if hh or mh:
                self.hint["either"] += 1
                self.hint["exact_match"] += hh == mh
                self.hint["heuristic_only"] += bool(hh) and not mh
                self.hint["llm_only"] += bool(mh) and not hh

    def report(self) -> dict[str, Any]:
        dims: dict[str, Any] = {}
        for dim, s in self.dims.items():
            total = sum(s["llm_mean"].values()) or 1.0
            dims[dim] = {
                "both_labeled": s["both"],
                "argmax_agreement": round(s["argmax_agree"] / s["both"], 4)
                if s["both"]
                else None,
                "js_divergence": _quantiles(s["js"]),
                "llm_only": s["llm_only"],
                "heuristic_only": s["heuristic_only"],
                "llm_mean_label": {
                    k: round(v / total, 4) for k, v in s["llm_mean"].items()
                },
            }
        return {
            "sessions": self.sessions,
            "turns": self.turns,
            "llm_labeled_turns": self.labeled,
            "dimensions": dims,
            "endorsement": dict(self.endorse),
            "llm_endorsement_kind": dict(self.llm_endorse_kind),
            "correction_hint": dict(self.hint),
            "llm_correction_hints": dict(self.llm_hints.most_common()),
        }


def heuristic_report(paths: Iterable[Path]) -> dict[str, Any]:
    stats = HeuristicStats()
    for path in paths:
        stats.add(parse_transcript(path))
    return stats.report()


def agreement_report(
    sessions: list[Session], client: LLMClient, workers: int = 4
) -> dict[str, Any]:
    stats = AgreementStats()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(lambda s: (s, label_session(s.turns, client)), sessions)
        for session, labels in results:
            stats.add(session.turns, labels)
    return stats.report()


def sample_sessions(
    paths: list[Path], n: int, seed: int, min_turns: int = 3, max_turns: int = 40
) -> list[Session]:
    """A seeded sample of sessions with at least one human prompt, truncated."""
    rng = random.Random(seed)
    order = paths[:]
    rng.shuffle(order)
    picked: list[Session] = []
    for path in order:
        if len(picked) >= n:
            break
        session = parse_transcript(path)
        human = [t for t in session.turns if t.prompt and t.prompt.kind == "prompt"]
        if len(session.turns) < min_turns or not human:
            continue
        session.turns = session.turns[:max_turns]
        picked.append(session)
    return picked


def label_corpus(
    paths: list[Path], helios_dir: Path, client: LLMClient, workers: int = 4
) -> dict[str, Any]:
    """Ingest every transcript with model labels into ``helios_dir``.

    Smallest transcripts go first so the ledger becomes useful early. Progress
    is written to ``status.json`` after every session; one failing session
    never stops the pass.
    """
    helios_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(paths, key=lambda p: p.stat().st_size)
    status: dict[str, Any] = {
        "persona": CORPUS_PERSONA,
        "ledger": str(helios_dir / "observations" / f"{CORPUS_PERSONA}.jsonl"),
        "sessions_total": len(ordered),
        "sessions_done": 0,
        "sessions_failed": 0,
        "rows_added": 0,
        "started": time.time(),
        "finished": None,
    }
    status_path = helios_dir / "status.json"

    def one(path: Path) -> int:
        return ingest_session(
            helios_dir, CORPUS_PERSONA, path, path.stem, final=True, client=client
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, p) for p in ordered]
        for future in futures:
            try:
                status["rows_added"] += future.result()
                status["sessions_done"] += 1
            except Exception:  # one bad transcript must not stop the pass
                status["sessions_failed"] += 1
            status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    status["finished"] = time.time()
    status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("--llm-sample", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--label-into", type=Path, default=None)
    args = parser.parse_args(argv)

    paths = list(iter_transcripts(args.root.expanduser()))
    if args.label_into is not None:
        client = default_client()
        if client is None:
            print(
                "model labeling is disabled or claude is not on PATH", file=sys.stderr
            )
            return 2
        status = label_corpus(paths, args.label_into, client, args.workers)
        json.dump(status, sys.stdout, indent=2)
        print()
        return 0
    report: dict[str, Any] = {"heuristic": heuristic_report(paths)}
    if args.llm_sample > 0:
        client = default_client()
        if client is None:
            print(
                "model labeling is disabled or claude is not on PATH", file=sys.stderr
            )
            return 2
        sessions = sample_sessions(paths, args.llm_sample, args.seed)
        report["agreement"] = agreement_report(sessions, client, args.workers)
    json.dump(report, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
