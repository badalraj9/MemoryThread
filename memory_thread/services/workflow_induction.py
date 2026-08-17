"""
Workflow Induction — Procedural memory (AWM-style).

Extracts reusable workflows from successful agent action trajectories
in the event graph. Stores them as Workflow nodes in the graph so
agents can reuse learned procedures instead of rediscovering them.

Inspired by AWM (Agent Workflow Memory) — extracts common subroutines
from past action sequences and stores them as reusable patterns.
"""

import uuid
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

from memory_thread.config.settings import settings
from memory_thread.services.graph_engine import graph_engine
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class Workflow:
    workflow_id: str
    title: str
    description: str
    steps: List[Dict]
    success_count: int
    avg_duration_seconds: float
    created_from: str


class WorkflowInduction:
    """
    Mines the event graph for reusable procedural patterns.

    Usage:
        inducer = WorkflowInduction()
        inducer.extract_from_thread(thread_id)
        workflow = inducer.match_workflow("deploy to production")
    """

    def extract_from_thread(self, thread_id: str) -> Optional[Workflow]:
        """Extract a workflow from a thread's event sequence."""
        from memory_thread.services.thread_service import thread_service

        result = thread_service.get_thread(thread_id)
        if not result or len(result.events) < settings.WORKFLOW_MIN_EVENTS:
            return None

        actions = self._deduce_steps(result.events)
        if len(actions) < 2:
            return None

        title = self._infer_title(result.thread.title, actions)
        wf = self._store_workflow(thread_id, title, actions)
        log.info(
            "Extracted workflow '%s' from thread %s (%d steps)", title, thread_id[:8], len(actions)
        )
        return wf

    def _deduce_steps(self, events: List[Dict]) -> List[str]:
        """Extract action descriptions from events, deduplicating consecutive repeats."""
        steps = []
        last = ""
        for evt in events:
            content = (evt.get("content") or evt.get("delta", {}).get("content") or "").strip()
            if content and content != last:
                steps.append(content[:120])
                last = content

        # Summarize very long sequences
        if len(steps) > 10:
            # Heuristic: take first 3, last 2, and a summary of the middle
            steps = steps[:3] + [f"... ({len(steps) - 5} intermediate steps)"] + steps[-2:]

        return steps

    def _infer_title(self, thread_title: str, actions: List[str]) -> str:
        """Use thread title if available, otherwise infer from first action."""
        if thread_title and thread_title != "Untitled":
            return thread_title
        if actions:
            first = actions[0][:60]
            return f"Workflow: {first}"
        return "Untitled Workflow"

    def _store_workflow(self, thread_id: str, title: str, steps: List[str]) -> Workflow:
        """Store workflow as nodes + edges in the graph."""
        wf_id = str(uuid.uuid4())

        # Fix #1: use _ensure_node so the vertex is registered in _vertex_names
        graph_engine._ensure_node(
            wf_id,
            type="workflow",
            title=title,
            description=f"Extracted from {thread_id[:8]}",
            created_from=thread_id,
            success_count=1,
            avg_duration=0.0,
            created_at=datetime.utcnow().isoformat(),
        )

        for i, step_desc in enumerate(steps):
            step_id = str(uuid.uuid4())
            # Fix #1: use _ensure_node so the vertex is registered in _vertex_names
            graph_engine._ensure_node(
                step_id,
                type="step",
                description=step_desc,
                order=i,
            )
            graph_engine.graph.add_edge(
                wf_id,
                step_id,
                type="has_step",
                order=i,
            )

        return Workflow(
            workflow_id=wf_id,
            title=title,
            description=f"Extracted from {thread_id[:8]}",
            steps=[{"order": i, "description": s} for i, s in enumerate(steps)],
            success_count=1,
            avg_duration_seconds=0.0,
            created_from=thread_id,
        )

    def match_workflow(self, query: str, top_k: int = None) -> List[Workflow]:
        """Find workflows matching a query by title or step content."""
        top_k = top_k or settings.WORKFLOW_TOP_K
        results = []

        for v in graph_engine.graph.vs:
            vattrs = v.attributes()
            if vattrs.get("type") != "workflow":
                continue

            title = str(vattrs.get("title", ""))
            wf_id = v["name"]

            if query.lower() in title.lower():
                wf = self._load_workflow(wf_id, vattrs)
                if wf:
                    results.append(wf)
                continue

            # Check step descriptions
            try:
                vidx = graph_engine.graph.vs.find(name=wf_id).index
            except (ValueError, KeyError):
                continue

            for e in graph_engine.graph.es:
                eattrs = e.attributes()
                if eattrs.get("type") == "has_step" and e.source == vidx:
                    step_v = graph_engine.graph.vs[e.target]
                    step_desc = str(step_v.attributes().get("description", ""))
                    if query.lower() in step_desc.lower():
                        wf = self._load_workflow(wf_id, vattrs)
                        if wf and not any(r.workflow_id == wf_id for r in results):
                            results.append(wf)
                        break

        results.sort(key=lambda x: -x.success_count)
        return results[:top_k]

    def _load_workflow(self, wf_id: str, vattrs: Dict) -> Optional[Workflow]:
        """Load a workflow from the graph, including its steps."""
        steps = []
        try:
            vidx = graph_engine.graph.vs.find(name=wf_id).index
            for e in graph_engine.graph.es:
                eattrs = e.attributes()
                if eattrs.get("type") == "has_step" and e.source == vidx:
                    step_v = graph_engine.graph.vs[e.target]
                    sv = step_v.attributes()
                    steps.append(
                        {
                            "order": sv.get("order", 0),
                            "description": sv.get("description", ""),
                        }
                    )
            steps.sort(key=lambda x: x["order"])
        except (ValueError, KeyError):
            pass

        return Workflow(
            workflow_id=wf_id,
            title=vattrs.get("title", ""),
            description=vattrs.get("description", ""),
            steps=steps,
            success_count=vattrs.get("success_count", 1),
            avg_duration_seconds=vattrs.get("avg_duration", 0.0),
            created_from=vattrs.get("created_from", ""),
        )

    def record_success(self, workflow_id: str):
        """Increment success counter when workflow is reused successfully."""
        try:
            v = graph_engine.graph.vs.find(name=workflow_id)
            v["success_count"] = v.attributes().get("success_count", 0) + 1
        except (ValueError, KeyError):
            pass

    def list_workflows(self) -> List[Workflow]:
        """List all workflows sorted by success count."""
        wfs = []
        for v in graph_engine.graph.vs:
            vattrs = v.attributes()
            if vattrs.get("type") == "workflow":
                wf = self._load_workflow(v["name"], vattrs)
                if wf:
                    wfs.append(wf)
        wfs.sort(key=lambda x: -x.success_count)
        return wfs


workflow_induction = WorkflowInduction()
