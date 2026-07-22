"""
Golden Thread Service - MT's most unique feature.

Traces the complete causal chain from origin to present state in a human-readable narrative.
Uses GraphEngine (in-memory iGraph) instead of Postgres round-trips.
Same public API as before -- drop-in replacement.
"""

import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

from memory_thread.services.graph_engine import graph_engine
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
        pass

    def trace(self, entity_id: uuid.UUID, namespace: str = None) -> GoldenThreadResult:
        log.info(f"Tracing golden thread for entity: {entity_id}")
        entity_node = str(entity_id)

        raw_events = self._collect_entity_events(entity_node)
        ancestors = self._collect_ancestor_events(raw_events)
        all_events = self._merge_and_sort(raw_events, ancestors)

        trace = self._build_trace(entity_node, all_events)
        is_consistent, inconsistencies, replayed = (
            trace["is_consistent"],
            trace["inconsistencies"],
            trace.get("final_state", {}),
        )

        thread_events = self._build_thread_events(all_events)
        related_paths = self._find_related_paths(entity_node)

        entity_content = replayed.get("current_value", {}).get("content", "")
        current_truth = replayed.get("truth_vector", {})

        result = GoldenThreadResult(
            entity_id=str(entity_id),
            entity_content=entity_content,
            traced_at=datetime.utcnow().isoformat(),
            events=thread_events,
            current_state=replayed,
            current_truth=current_truth,
            is_consistent=is_consistent,
            inconsistencies=inconsistencies,
            related_paths=related_paths,
            narrative="",
        )

        result.narrative = self._generate_narrative(result)
        return result

    def trace_belief(self, belief_id: str) -> GoldenThreadResult:
        try:
            eid = uuid.UUID(belief_id)
        except ValueError:
            eid = uuid.uuid4()
        return self.trace(eid)

    def trace_topic(
        self,
        topic: str,
        max_entities: int = 10,
        max_events: int = 500,
    ) -> Dict:
        """
        Trace the evolution of a topic across all related entities.
        Resolves topic to entity nodes via graph search, then merges
        each entity's golden thread chronologically.

        Returns a dict with merged events, entity count, and narrative.
        """
        # Search for matching event vertices (only events have content attribute)
        event_matches = graph_engine.search_nodes(topic, attr="content")
        # Resolve to entity vertices by following modifies edges from event -> entity
        entity_nodes = set()
        for ename in event_matches:
            try:
                vidx = graph_engine.graph.vs.find(name=ename).index
            except (ValueError, KeyError):
                continue
            for e in graph_engine.graph.es:
                eattrs = e.attributes()
                if eattrs.get("type") == "modifies" and e.source == vidx:
                    entity_nodes.add(graph_engine.graph.vs[e.target]["name"])
            if len(entity_nodes) >= max_entities:
                break

        # Also search by name attribute for direct entity name matches
        name_matches = graph_engine.search_nodes(topic, attr="name")
        entity_nodes.update(name_matches)
        all_nodes = list(entity_nodes)[:max_entities]

        if not all_nodes:
            return {
                "topic": topic,
                "entity_count": 0,
                "event_count": 0,
                "events": [],
                "truncated": False,
                "narrative": f"No entities found for topic '{topic}'.",
            }

        all_events = []
        seen_event_names: set = set()

        for node_name in all_nodes:
            raw = self._collect_entity_events(node_name)
            ancestors = self._collect_ancestor_events(raw)
            merged = self._merge_and_sort(raw, ancestors)
            for evt in merged:
                ename = evt.get("_name", "")
                if ename not in seen_event_names:
                    seen_event_names.add(ename)
                    all_events.append(evt)

        all_events.sort(key=lambda x: x.get("timestamp", ""))
        truncated = len(all_events) > max_events
        if truncated:
            all_events = all_events[-max_events:]

        thread_events = self._build_thread_events(all_events)

        lines = [f"Topic Evolution: {topic}", "━" * 40, ""]
        for event in thread_events[-20:]:
            ts = event.timestamp[:19] if event.timestamp else "Unknown"
            lines.append(f"[{ts}] {event.event_type} by {event.actor}")
            content = event.delta.get("content", "")[:80]
            if content:
                lines.append(f'  "{content}"')
            lines.append("")
        lines.append("━" * 40)
        lines.append(f"{len(all_nodes)} entities \u00b7 {len(all_events)} events")

        return {
            "topic": topic,
            "entity_count": len(all_nodes),
            "event_count": len(all_events),
            "events": thread_events,
            "truncated": truncated,
            "narrative": "\n".join(lines),
        }

    # ── Graph Collection (replaces ReplayService + AncestryCache) ──────

    def _collect_entity_events(self, entity_node: str) -> List[Dict]:
        """All events that modified this entity, from the in-memory graph."""
        if not graph_engine._vertex_exists(entity_node):
            return []
        try:
            vidx = graph_engine.graph.vs.find(name=entity_node).index
        except (ValueError, KeyError):
            return []

        events = []
        for e in graph_engine.graph.es:
            eattrs = e.attributes()
            if eattrs.get("type") == "modifies" and e.target == vidx:
                event_node = graph_engine.graph.vs[e.source]
                events.append(self._vertex_to_event(event_node, eattrs))
        events.sort(key=lambda x: x.get("timestamp", ""))
        return events

    def _collect_ancestor_events(self, known_events: List[Dict]) -> List[Dict]:
        """All ancestor events reachable via causal edges, deduplicated."""
        ancestor_names = set()
        queue = [e["_name"] for e in known_events if "_name" in e]
        visited = set(queue)

        while queue:
            current = queue.pop(0)
            try:
                cidx = graph_engine.graph.vs.find(name=current).index
            except (ValueError, KeyError):
                continue
            for e in graph_engine.graph.es:
                eattrs = e.attributes()
                if eattrs.get("type") == "causes" and e.target == cidx:
                    src_name = graph_engine.graph.vs[e.source]["name"]
                    if src_name not in visited:
                        visited.add(src_name)
                        queue.append(src_name)
                        ancestor_names.add(src_name)

        result = []
        for name in ancestor_names:
            try:
                v = graph_engine.graph.vs.find(name=name)
                result.append(self._vertex_to_event(v))
            except (ValueError, KeyError):
                continue
        return result

    def _merge_and_sort(self, entity_events: List[Dict], ancestors: List[Dict]) -> List[Dict]:
        seen = set()
        merged = []
        for e in ancestors + entity_events:
            n = e.get("_name", "")
            if n not in seen:
                seen.add(n)
                merged.append(e)
        merged.sort(key=lambda x: x.get("timestamp") or "")
        return merged

    def _vertex_to_event(self, v, edge_attrs: Optional[Dict] = None) -> Dict:
        vattrs = v.attributes()
        import json

        delta_str = vattrs.get("delta_json", "{}")
        delta = {}
        if delta_str and delta_str != "{}":
            try:
                delta = json.loads(delta_str) if isinstance(delta_str, str) else dict(delta_str)
            except (json.JSONDecodeError, TypeError):
                delta = {"content": vattrs.get("content", "")}
        else:
            delta = {"content": vattrs.get("content", "")}
        return {
            "_name": v["name"],
            "event_id": v["name"],
            "timestamp": vattrs.get("timestamp") or "",
            "actor": vattrs.get("actor", "UNKNOWN"),
            "action": vattrs.get("action", "UNKNOWN"),
            "object_id": vattrs.get("object_id", ""),
            "delta": delta,
            "truth_vector": {
                "confidence": vattrs.get("truth_confidence") or 0.5,
                "authority": vattrs.get("truth_authority") or 0.5,
                "freshness": vattrs.get("truth_freshness") or 1.0,
                "corroboration": 0.0,
            },
            "antecedents": [],
            "edge_action": edge_attrs.get("action") if edge_attrs else None,
        }

    def _build_trace(self, entity_node: str, events: List[Dict]) -> Dict:
        """Replay events in order and detect real inconsistencies (not normal updates)."""
        inconsistencies = []
        final_state = {}

        for evt in events:
            delta = evt.get("delta", {})
            if delta.get("contradiction_detected") or delta.get("has_contradiction"):
                inconsistencies.append(delta.get("conflicting_content", "Contradiction detected"))
            if delta.get("resolved") or delta.get("conflict_resolved"):
                if inconsistencies:
                    inconsistencies.pop()
            final_state = {
                "current_value": {"content": evt.get("delta", {}).get("content", "")},
                "truth_vector": evt.get(
                    "truth_vector", {"confidence": 0.5, "authority": 0.5, "freshness": 1.0}
                ),
            }

        return {
            "events": events,
            "final_state": final_state,
            "is_consistent": len(inconsistencies) == 0,
            "inconsistencies": inconsistencies,
        }

        return {
            "events": events,
            "final_state": final_state,
            "is_consistent": len(inconsistencies) == 0,
            "inconsistencies": inconsistencies,
        }

    # ── Thread Event Building (UNCHANGED from original) ───────────────

    def _build_thread_events(self, events_data: List[Dict]) -> List[ThreadEvent]:
        thread_events = []
        for i, evt in enumerate(events_data):
            prev_state = events_data[i - 1].get("truth_vector") if i > 0 else None
            current_state = evt.get("truth_vector", {})
            event_type = self._classify_event_type(evt, prev_state, current_state)
            delta = evt.get("delta", {})
            related_entities = []
            if "antecedents" in evt:
                related_entities = [str(a) for a in evt.get("antecedents", [])]
            if "object_id" in evt:
                related_entities.append(str(evt.get("object_id")))
            description = self._build_event_description(evt, delta, event_type)
            thread_events.append(
                ThreadEvent(
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
            )
        return thread_events

    def _classify_event_type(self, event: Dict, prev_state: Optional[Dict], new_state: Dict) -> str:
        if not prev_state:
            return "CREATED"
        delta = event.get("delta", {})
        if delta.get("contradiction_detected") or delta.get("has_contradiction"):
            return "CONTRADICTED"
        if delta.get("resolved") or delta.get("conflict_resolved"):
            return "RESOLVED"
        if prev_state and new_state:
            old_f = prev_state.get("freshness") or 1.0
            new_f = new_state.get("freshness") or 1.0
            if old_f - new_f > 0.3:
                return "DECAYED"
        action = event.get("action", "")
        if action in ("UPDATE", "ADD"):
            return "UPDATED"
        if action == "OBSERVE":
            return "VERIFIED"
        return "UPDATED"

    def _build_event_description(self, event: Dict, delta: Dict, event_type: str) -> str:
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

    def _find_related_paths(self, entity_node: str) -> List[Dict]:
        paths = []
        try:
            neighbors = graph_engine.get_neighbors(
                entity_node, direction="both", edge_types=["relates"]
            )
            for n in neighbors[:10]:
                paths.append(
                    {
                        "source": entity_node,
                        "target": n.get("id", ""),
                        "relation": n.get("relation_type", "UNKNOWN"),
                        "confidence": n.get("confidence", 0.0),
                    }
                )
        except Exception as e:
            log.debug(f"Could not find related paths: {e}")
        return paths

    # ── Narrative Generation (UNCHANGED from original) ────────────────

    def _generate_narrative(self, result: GoldenThreadResult) -> str:
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
                content = (event.delta.get("content") or "")[:100]
                lines.append(f'  "{content}"')
            elif event.event_type == "CONTRADICTED":
                conflicting = event.delta.get("conflicting_content", "")
                if conflicting:
                    lines.append(f'  Conflicting: "{conflicting[:80]}"')
                if event.truth_before and event.truth_after:
                    before = event.truth_before.get("confidence", 0)
                    after = event.truth_after.get("confidence", 0)
                    lines.append(f"  Trust dropped: {before:.2f} -> {after:.2f}")
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
                    before = event.truth_before.get("freshness") or 0
                    after = event.truth_after.get("freshness") or 0
                    lines.append(f"  Freshness: {before:.2f} -> {after:.2f}")

            if event.truth_after:
                conf = event.truth_after.get("confidence", 0)
                auth = event.truth_after.get("authority", 0)
                fresh = event.truth_after.get("freshness") or 0
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
                path_strs.append(f"{result.entity_id[:8]} -> {rel} -> {target}")
            lines.append(f"Related:       {', '.join(path_strs)}")

        return "\n".join(lines)

    def render_rich(self, result: GoldenThreadResult) -> str:
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
                    lines.append(f"  Trust dropped: {before:.2f} -> {after:.2f}")
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
                    before = event.truth_before.get("freshness") or 0
                    after = event.truth_after.get("freshness") or 0
                    lines.append(f"  Freshness: {before:.2f} -> [yellow]{after:.2f}[/yellow]")
            elif event.event_type == "VERIFIED":
                lines.append("  [green]Verified through replay[/green]")

            if event.truth_after:
                conf = event.truth_after.get("confidence", 0)
                auth = event.truth_after.get("authority", 0)
                fresh = event.truth_after.get("freshness") or 0
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
                path_strs.append(f"{result.entity_id[:8]} -> {rel} -> {target}")
            lines.append(f"[bold]Related:[/bold]       {', '.join(path_strs)}")

        return "\n".join(lines)

    def _get_sequence_emoji(self, sequence: int) -> str:
        if sequence <= 10:
            nums = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]
            return nums[sequence - 1]
        return f"#{sequence}"

    @staticmethod
    def _calculate_truth_score(truth: Dict) -> float:
        if not truth:
            return 0.0
        confidence = truth.get("confidence", 0.5)
        authority = truth.get("authority", 0.5)
        freshness = truth.get("freshness", 0.5)
        return (confidence * 0.4) + (authority * 0.35) + (freshness * 0.25)

    def _get_event_color(self, event_type: str) -> str:
        return {
            "CREATED": "green",
            "CONTRADICTED": "red",
            "DECAYED": "yellow",
            "UPDATED": "blue",
            "VERIFIED": "green",
            "RESOLVED": "cyan",
        }.get(event_type, "white")

    def _get_trust_color(self, score: float) -> str:
        if score > 0.7:
            return "green"
        if score > 0.4:
            return "yellow"
        return "red"


golden_thread_service = GoldenThreadService()
