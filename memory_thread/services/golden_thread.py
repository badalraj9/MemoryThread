"""
Golden Thread Service - MT's most unique feature.

Traces the complete causal chain from origin to present state in a human-readable narrative.
Orchestrates replay_service.py, ancestry_cache.py, and reasoning/query_engine.py together.
"""

import uuid
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

from memory_thread.services.replay_service import ReplayService
from memory_thread.services.ancestry_cache import AncestryCache
from memory_thread.services.reasoning.query_engine import QueryEngine
from memory_thread.db.postgres_client import PostgresClient
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class ThreadEvent:
    sequence: int
    timestamp: str
    event_type: str
    actor: str
    description: str
    truth_before: Optional[Dict]
    truth_after: Dict
    delta: Dict
    related_entities: List[str] = field(default_factory=list)


@dataclass
class GoldenThreadResult:
    entity_id: str
    entity_content: str
    traced_at: str
    events: List[ThreadEvent]
    current_state: Dict
    current_truth: Dict
    is_consistent: bool
    inconsistencies: List[str]
    related_paths: List[Dict]
    narrative: str


class GoldenThreadService:
    def __init__(self):
        self.replay = ReplayService()
        self.ancestry = AncestryCache()
        self.query = QueryEngine()
        self.pg = PostgresClient()

    def trace(self, entity_id: uuid.UUID, namespace: str = None) -> GoldenThreadResult:
        """
        Trace the complete causal chain for an entity.

        Step by step:
        1. Call ancestry.rebuild_cache(entity_id) to ensure cache is current
        2. Call replay.capture_trace(entity_id) to get full event history
        3. Call replay.replay_trace(trace) to verify consistency
        4. Call _build_thread_events(trace) to convert raw events to ThreadEvents
        5. Call _find_related_paths(entity_id) to get relationship context
        6. Call _generate_narrative(result) to build human-readable story
        7. Return complete GoldenThreadResult
        """
        log.info(f"Tracing golden thread for entity: {entity_id}")

        self.ancestry.rebuild_cache(entity_id)

        trace = self.replay.capture_trace(entity_id)

        is_consistent, inconsistencies, replayed_state = self.replay.replay_trace(trace)

        thread_events = self._build_thread_events(trace)

        related_paths = self._find_related_paths(entity_id)

        entity_content = trace.get("final_state", {}).get("current_value", {}).get("content", "")
        current_truth = trace.get("final_state", {}).get("truth_vector", {})

        result = GoldenThreadResult(
            entity_id=str(entity_id),
            entity_content=entity_content,
            traced_at=datetime.utcnow().isoformat(),
            events=thread_events,
            current_state=trace.get("final_state", {}),
            current_truth=current_truth,
            is_consistent=is_consistent,
            inconsistencies=inconsistencies,
            related_paths=related_paths,
            narrative="",
        )

        result.narrative = self._generate_narrative(result)

        return result

    def trace_belief(self, belief_id: str) -> GoldenThreadResult:
        """Trace a belief's golden thread."""
        try:
            entity_id = uuid.UUID(belief_id)
        except ValueError:
            entity_id = uuid.uuid4()

        return self.trace(entity_id)

    def _build_thread_events(self, trace: Dict) -> List[ThreadEvent]:
        """Convert raw events to ThreadEvents with event type classification."""
        events_data = trace.get("events", [])
        thread_events = []

        for i, evt in enumerate(events_data):
            prev_state = None
            if i > 0:
                prev_evt = events_data[i - 1]
                prev_state = prev_evt.get("truth_vector", {})

            current_state = evt.get("truth_vector", {})

            event_type = self._classify_event_type(evt, prev_state, current_state)

            delta = evt.get("delta", {})

            related_entities = []
            if "antecedents" in evt:
                related_entities = [str(a) for a in evt.get("antecedents", [])]
            if "object_id" in evt:
                related_entities.append(str(evt.get("object_id")))

            description = self._build_event_description(evt, delta, event_type)

            thread_event = ThreadEvent(
                sequence=i + 1,
                timestamp=evt.get("timestamp", ""),
                event_type=event_type,
                actor=evt.get("actor", "UNKNOWN"),
                description=description,
                truth_before=prev_state,
                truth_after=current_state,
                delta=delta,
                related_entities=related_entities,
            )
            thread_events.append(thread_event)

        return thread_events

    def _classify_event_type(self, event: Dict, prev_state: Optional[Dict], new_state: Dict) -> str:
        """
        Classify the event type based on state changes:
        - First event ever → CREATED
        - Delta has contradiction flag or content changed significantly → CONTRADICTED
        - Truth vector freshness dropped significantly (>0.3) → DECAYED
        - Conflict was resolved → RESOLVED
        - Content/value updated → UPDATED
        - State verified by replay → VERIFIED
        """
        if not prev_state:
            return "CREATED"

        delta = event.get("delta", {})

        if delta.get("contradiction_detected") or delta.get("has_contradiction"):
            return "CONTRADICTED"

        if delta.get("resolved") or delta.get("conflict_resolved"):
            return "RESOLVED"

        if prev_state and new_state:
            old_freshness = prev_state.get("freshness", 1.0)
            new_freshness = new_state.get("freshness", 1.0)
            if old_freshness - new_freshness > 0.3:
                return "DECAYED"

        action = event.get("action", "")
        if action in ["UPDATE", "ADD"]:
            return "UPDATED"

        if action == "OBSERVE":
            return "VERIFIED"

        return "UPDATED"

    def _build_event_description(self, event: Dict, delta: Dict, event_type: str) -> str:
        """Build a human-readable description for the event."""
        content = delta.get("content", "")

        if event_type == "CREATED":
            return f'Created memory: "{content[:100]}"' if content else "Created new entity"

        if event_type == "CONTRADICTED":
            conflicting = delta.get("conflicting_content", "")
            return (
                f'Content contradicted: "{conflicting[:80]}"'
                if conflicting
                else "State contradiction detected"
            )

        if event_type == "DECAYED":
            return "Memory freshness decayed over time"

        if event_type == "RESOLVED":
            return "Conflict resolved"

        if event_type == "UPDATED":
            changes = []
            for key, value in delta.items():
                if key != "content" and not key.startswith("_"):
                    changes.append(f"{key}={value}")
            if changes:
                return f"Changed: {', '.join(changes[:3])}"
            return f'Updated content: "{content[:80]}"' if content else "Updated"

        if event_type == "VERIFIED":
            return "State verified through replay"

        return f"Event: {event.get('action', 'UNKNOWN')}"

    def _find_related_paths(self, entity_id: uuid.UUID) -> List[Dict]:
        """Find how this entity connects to others."""
        paths = []

        try:
            from memory_thread.services.graph_service import GraphService

            graph = GraphService()

            relations = graph.get_relations(entity_id, direction="both")

            for rel in relations[:10]:
                paths.append(
                    {
                        "source": str(entity_id),
                        "target": str(rel.get("target_entity_id", "")),
                        "relation": rel.get("relation_type", "UNKNOWN"),
                        "confidence": rel.get("confidence", 0.0),
                    }
                )
        except Exception as e:
            log.debug(f"Could not find related paths: {e}")

        return paths

    def _generate_narrative(self, result: GoldenThreadResult) -> str:
        """Generate human-readable narrative in the specified format."""
        lines = []

        entity_truncated = result.entity_content[:60] if result.entity_content else "Unknown"
        lines.append(f"Golden Thread: {entity_truncated}")
        lines.append("━" * 40)
        lines.append("")

        for event in result.events:
            seq_emoji = self._get_sequence_emoji(event.sequence)
            ts = event.timestamp[:19] if event.timestamp else "Unknown"

            lines.append(f"{seq_emoji} {ts}  {event.event_type} by {event.actor}")

            if event.event_type == "CREATED":
                content = event.delta.get("content", "")[:100]
                lines.append(f'  "{content}"')
            elif event.event_type == "CONTRADICTED":
                conflicting = event.delta.get("conflicting_content", "")
                if conflicting:
                    lines.append(f'  Conflicting: "{conflicting[:80]}"')
                if event.truth_before and event.truth_after:
                    before = event.truth_before.get("confidence", 0)
                    after = event.truth_after.get("confidence", 0)
                    lines.append(f"  Trust dropped: {before:.2f} → {after:.2f}")
            elif event.event_type == "UPDATED":
                if event.delta:
                    changes = []
                    for k, v in event.delta.items():
                        if k != "content":
                            changes.append(f"{k}={str(v)[:30]}")
                    if changes:
                        lines.append(f"  Changed: {', '.join(changes)}")
            elif event.event_type == "DECAYED":
                if event.truth_before and event.truth_after:
                    before = event.truth_before.get("freshness", 0)
                    after = event.truth_after.get("freshness", 0)
                    lines.append(f"  Freshness: {before:.2f} → {after:.2f}")

            if event.truth_after:
                conf = event.truth_after.get("confidence", 0)
                auth = event.truth_after.get("authority", 0)
                fresh = event.truth_after.get("freshness", 0)
                lines.append(
                    f"  Truth: confidence={conf:.2f}, authority={auth:.2f}, freshness={fresh:.2f}"
                )

            lines.append("")

        lines.append("━" * 40)
        lines.append("")

        current_truncated = result.entity_content[:50] if result.entity_content else "Unknown"
        truth_score = self._calculate_truth_score(result.current_truth)
        lines.append(f'Current State: "{current_truncated}" [trust: {truth_score:.0%}]')

        if result.is_consistent:
            lines.append("Consistency:   ✓ Verified")
        else:
            reasons = "; ".join(result.inconsistencies[:2])
            lines.append(f"Consistency:   ✗ Inconsistent: {reasons}")

        if result.related_paths:
            paths_sample = result.related_paths[:3]
            path_strs = []
            for p in paths_sample:
                target = p.get("target", "")[:8]
                rel = p.get("relation", "UNKNOWN")
                path_strs.append(f"{result.entity_id[:8]} → {rel} → {target}")
            lines.append(f"Related:       {', '.join(path_strs)}")

        return "\n".join(lines)

    def _get_sequence_emoji(self, sequence: int) -> str:
        """Get sequence indicator (①, ②, ③, etc.)"""
        if sequence <= 10:
            nums = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]
            return nums[sequence - 1]
        return f"#{sequence}"

    def _calculate_truth_score(self, truth: Dict) -> float:
        """Calculate overall truth score from truth vector."""
        if not truth:
            return 0.0
        confidence = truth.get("confidence", 0.5)
        authority = truth.get("authority", 0.5)
        freshness = truth.get("freshness", 0.5)
        return (confidence * 0.4) + (authority * 0.35) + (freshness * 0.25)

    def render_rich(self, result: GoldenThreadResult) -> str:
        """Render golden thread with rich markup."""
        lines = []

        entity_truncated = result.entity_content[:60] if result.entity_content else "Unknown"
        lines.append(f"[bold cyan]Golden Thread:[/bold cyan] {entity_truncated}")
        lines.append("[dim]" + "━" * 40 + "[/dim]")
        lines.append("")

        for event in result.events:
            seq = f"[cyan]{self._get_sequence_emoji(event.sequence)}[/cyan]"
            ts = event.timestamp[:19] if event.timestamp else "Unknown"

            event_color = self._get_event_color(event.event_type)

            lines.append(
                f"{seq} [dim]{ts}[/dim]  [{event_color}]{event.event_type}[/{event_color}] by [yellow]{event.actor}[/yellow]"
            )

            if event.event_type == "CREATED":
                content = event.delta.get("content", "")[:100]
                lines.append(f'  [green]"{content}"[/green]')
            elif event.event_type == "CONTRADICTED":
                conflicting = event.delta.get("conflicting_content", "")
                if conflicting:
                    lines.append(f'  [red]Conflicting: "{conflicting[:80]}"[/red]')
                if event.truth_before and event.truth_after:
                    before = event.truth_before.get("confidence", 0)
                    after = event.truth_after.get("confidence", 0)
                    lines.append(f"  Trust dropped: {before:.2f} → {after:.2f}")
            elif event.event_type == "UPDATED":
                if event.delta:
                    changes = []
                    for k, v in event.delta.items():
                        if k != "content":
                            changes.append(f"{k}={str(v)[:30]}")
                    if changes:
                        lines.append(f"  Changed: {', '.join(changes)}")
            elif event.event_type == "DECAYED":
                if event.truth_before and event.truth_after:
                    before = event.truth_before.get("freshness", 0)
                    after = event.truth_after.get("freshness", 0)
                    lines.append(f"  Freshness: {before:.2f} → [yellow]{after:.2f}[/yellow]")
            elif event.event_type == "VERIFIED":
                lines.append("  [green]Verified through replay[/green]")

            if event.truth_after:
                conf = event.truth_after.get("confidence", 0)
                auth = event.truth_after.get("authority", 0)
                fresh = event.truth_after.get("freshness", 0)
                lines.append(
                    f"  Truth: confidence={conf:.2f}, authority={auth:.2f}, freshness={fresh:.2f}"
                )

            lines.append("")

        lines.append("[dim]" + "━" * 40 + "[/dim]")
        lines.append("")

        current_truncated = result.entity_content[:50] if result.entity_content else "Unknown"
        truth_score = self._calculate_truth_score(result.current_truth)
        trust_color = self._get_trust_color(truth_score)

        lines.append(
            f'[bold]Current State:[/bold] "{current_truncated}" [trust: [{trust_color}]{truth_score:.0%}[/{trust_color}]]'
        )

        if result.is_consistent:
            lines.append("[green]Consistency:   ✓ Verified[/green]")
        else:
            reasons = "; ".join(result.inconsistencies[:2])
            lines.append(f"[red]Consistency:   ✗ Inconsistent: {reasons}[/red]")

        if result.related_paths:
            paths_sample = result.related_paths[:3]
            path_strs = []
            for p in paths_sample:
                target = p.get("target", "")[:8]
                rel = p.get("relation", "UNKNOWN")
                path_strs.append(f"{result.entity_id[:8]} → {rel} → {target}")
            lines.append(f"[bold]Related:[/bold]       {', '.join(path_strs)}")

        return "\n".join(lines)

    def _get_event_color(self, event_type: str) -> str:
        """Get color for event type."""
        colors = {
            "CREATED": "green",
            "CONTRADICTED": "red",
            "DECAYED": "yellow",
            "UPDATED": "blue",
            "VERIFIED": "green",
            "RESOLVED": "cyan",
        }
        return colors.get(event_type, "white")

    def _get_trust_color(self, score: float) -> str:
        """Get color for trust score."""
        if score > 0.7:
            return "green"
        elif score > 0.4:
            return "yellow"
        return "red"


golden_thread_service = GoldenThreadService()
