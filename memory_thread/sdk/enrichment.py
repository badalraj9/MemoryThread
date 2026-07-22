"""EnrichmentPipeline — async entity extraction and relation inference."""

import uuid
import queue
import threading
import logging
from typing import List, Dict, Optional

from memory_thread.models.events import Event, EntityState, TruthVector, ActorEnum, ActionEnum
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


class EnrichmentPipeline:
    """Background enrichment worker pool for entity/relation extraction."""

    def __init__(self, namespace: str, memories: dict, persistence):
        self.namespace = namespace
        self._memories = memories
        self._persistence = persistence
        self._queue: "queue.Queue[Optional[Dict]]" = queue.Queue()
        self._workers: List[threading.Thread] = []

    def start(self):
        self._workers = [
            threading.Thread(
                target=self._worker_loop,
                name=f"mt-enrichment-{self.namespace}-{i}",
                daemon=True,
            )
            for i in range(2)
        ]
        for w in self._workers:
            w.start()

    def schedule(self, source, content, entity_id, event_id, memory_type, state):
        if source == "user":
            self._queue.put(
                {
                    "kind": "entity_extraction",
                    "content": content,
                    "entity_id": entity_id,
                    "event_id": event_id,
                }
            )

    def shutdown(self):
        self._queue.join()
        for _ in self._workers:
            self._queue.put(None)
        for w in self._workers:
            w.join(timeout=1.0)

    def drain(self):
        self._queue.join()

    # ── Worker loop ────────────────────────────────────────────────────

    def _worker_loop(self):
        while True:
            task = self._queue.get()
            if task is None:
                self._queue.task_done()
                break
            try:
                if task["kind"] == "entity_extraction":
                    self._run_extraction(
                        content=task["content"],
                        entity_id=task["entity_id"],
                        event_id=task["event_id"],
                    )
            finally:
                self._queue.task_done()

    def _run_extraction(self, content, entity_id, event_id):
        from memory_thread.services.graph_engine import graph_engine

        try:
            extracted_entities = self._extract_entities(content)
            extracted_relations = self._infer_user_relations(content, extracted_entities)

            def get_context(text, entity_value, window_chars=50):
                pos = text.lower().find(entity_value.lower())
                if pos == -1:
                    return ""
                start = max(0, pos - window_chars)
                end = min(len(text), pos + len(entity_value) + window_chars)
                return text[start:end].strip()

            for ent in extracted_entities:
                ent_type = ent.get("entity", "UNKNOWN")
                ent_value = ent.get("value", "")
                if ent_value and ent_type in ["PERSON", "ORG", "GPE", "PRODUCT"]:
                    context_window = get_context(content, ent_value)
                    ent_id = uuid.uuid4()
                    tv = TruthVector(
                        confidence=ent.get("confidence", 0.9),
                        authority=0.9,
                        freshness=1.0,
                        corroboration=0,
                    )
                    ent_event = Event(
                        id=uuid.uuid4(),
                        namespace=self.namespace,
                        actor=ActorEnum.SYSTEM,
                        action=ActionEnum.OBSERVE,
                        object_id=ent_id,
                        delta={
                            "content": ent_value,
                            "context": context_window,
                            "type": "entity",
                            "entity_type": ent_type,
                            "source_memory_id": str(entity_id),
                        },
                        antecedents=[entity_id],
                        truth_vector=tv,
                    )
                    ent_state = EntityState(
                        entity_id=ent_id,
                        namespace=self.namespace,
                        current_value={
                            "content": ent_value,
                            "context": context_window,
                            "type": "entity",
                            "entity_type": ent_type,
                            "source_memory_id": str(entity_id),
                        },
                        truth_vector=tv,
                        version=0,
                        last_event_id=ent_event.id,
                    )
                    self._memories[ent_id] = ent_state
                    self._persistence.save(ent_id, ent_value, "entity", ent_state, ent_event)
                    graph_engine.apply_event(ent_event)

            for rel in extracted_relations:
                rel_id = uuid.uuid4()
                tv = TruthVector(
                    confidence=rel.get("confidence", 0.9),
                    authority=0.9,
                    freshness=1.0,
                    corroboration=0,
                )
                rel_event = Event(
                    id=uuid.uuid4(),
                    namespace=self.namespace,
                    actor=ActorEnum.SYSTEM,
                    action=ActionEnum.OBSERVE,
                    object_id=rel_id,
                    delta={
                        "content": f"USER {rel['type']} {rel['target']}",
                        "type": "relation",
                        "relation_type": rel["type"],
                        "target": rel["target"],
                        "target_type": rel["target_type"],
                        "source_memory_id": str(entity_id),
                    },
                    antecedents=[entity_id],
                    truth_vector=tv,
                )
                rel_state = EntityState(
                    entity_id=rel_id,
                    namespace=self.namespace,
                    current_value={
                        "content": f"USER {rel['type']} {rel['target']}",
                        "type": "relation",
                        "relation_type": rel["type"],
                        "target": rel["target"],
                        "target_type": rel["target_type"],
                        "source_memory_id": str(entity_id),
                    },
                    truth_vector=tv,
                    version=0,
                    last_event_id=rel_event.id,
                )
                self._memories[rel_id] = rel_state
                self._persistence.save(
                    rel_id,
                    rel_state.current_value.get("content", ""),
                    "relation",
                    rel_state,
                    rel_event,
                )
                graph_engine.apply_event(rel_event)

            if extracted_entities or extracted_relations:
                log.info(
                    "Extracted %d entities, %d relations",
                    len(extracted_entities),
                    len(extracted_relations),
                )
        except Exception as e:
            log.debug("Entity extraction skipped: %s", e)

    # ── NLP utilities ──────────────────────────────────────────────────

    def _extract_entities(self, text: str) -> List[Dict]:
        try:
            from memory_thread.services.hybrid_ner_service import extract_entities

            return extract_entities(text)
        except ImportError:
            log.warning("hybrid_ner_service not available, skipping entity extraction")
            return []
        except Exception as e:
            log.warning(f"Entity extraction failed: {e}")
            return []

    def _infer_user_relations(self, text: str, entities: List[Dict]) -> List[Dict]:
        relations = []
        text_lower = text.lower()

        if any(p in text_lower for p in ["my name is", "i am ", "i'm ", "call me "]):
            for ent in entities:
                if ent.get("entity") == "PERSON":
                    relations.append(
                        {
                            "type": "HAS_NAME",
                            "target": ent["value"],
                            "target_type": "PERSON",
                            "confidence": 0.95,
                        }
                    )

        if any(
            p in text_lower for p in ["work at", "work for", "working at", "employed at", "job at"]
        ):
            for ent in entities:
                if ent.get("entity") in ["ORG", "ORGANIZATION"]:
                    relations.append(
                        {
                            "type": "WORKS_AT",
                            "target": ent["value"],
                            "target_type": "ORG",
                            "confidence": 0.9,
                        }
                    )

        if any(p in text_lower for p in ["live in", "from ", "based in", "located in"]):
            for ent in entities:
                if ent.get("entity") in ["GPE", "LOC", "LOCATION"]:
                    relations.append(
                        {
                            "type": "LOCATED_IN",
                            "target": ent["value"],
                            "target_type": "LOCATION",
                            "confidence": 0.85,
                        }
                    )

        if any(p in text_lower for p in ["i like", "i prefer", "i love", "i enjoy"]):
            for keyword in ["like", "prefer", "love", "enjoy"]:
                if keyword in text_lower:
                    idx = text_lower.find(keyword)
                    preference = text[idx + len(keyword) :].strip()
                    if preference and len(preference) < 50:
                        relations.append(
                            {
                                "type": "PREFERS",
                                "target": preference.rstrip(".!"),
                                "target_type": "PREFERENCE",
                                "confidence": 0.9,
                            }
                        )
                    break

        return relations
