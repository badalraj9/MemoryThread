"""
Contemplator - MT Self-Observation Service.

MT observes its own state and generates insights.
Hybrid approach: auto for low-risk, approval for high-risk actions.
"""

import json
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

CONTEMPLATION_INTERVAL_HOURS = 24


class Contemplator:
    """
    MT's self-reflection engine.

    Observes:
    - Memory health (truth distribution)
    - Conflict patterns
    - Access anomalies
    - Decay status
    - Consolidation opportunities

    Actions:
    - Auto: Low-risk observations, reports
    - Approval: Consolidation, pruning recommendations
    """

    def __init__(self, auto_start: bool = True, namespace: Optional[str] = None):
        self._pg = None
        self._insights_log = []
        self._timer = None
        self.namespace = namespace
        self._load_insights_from_db()

        if auto_start:
            self._schedule_next_reflection()

    @property
    def pg(self):
        if not self._pg:
            try:
                from memory_thread.db.postgres_client import PostgresClient

                self._pg = PostgresClient()
            except Exception as e:
                log.warning(f"Failed to connect to Postgres: {e}")
        return self._pg

    def _load_insights_from_db(self):
        """Load last N reflections from DB into _insights_log."""
        try:
            if not self.pg:
                return

            with self.pg.get_cursor() as cur:
                cur.execute("""
                    SELECT timestamp, reflection_json
                    FROM insights_log
                    ORDER BY timestamp DESC
                    LIMIT 100
                """)
                rows = cur.fetchall()

                for row in reversed(rows):
                    self._insights_log.append(json.loads(row[1]))

                log.info(f"Loaded {len(rows)} insights from DB")
        except Exception as e:
            log.debug(f"Could not load insights from DB: {e}")

    def _persist_insight(self, reflection: Dict[str, Any]):
        """Persist a single reflection to DB."""
        try:
            if not self.pg:
                return

            with self.pg.get_cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS insights_log (
                        id SERIAL PRIMARY KEY,
                        timestamp TIMESTAMP NOT NULL,
                        reflection_json JSONB NOT NULL
                    )
                """)

                cur.execute(
                    """
                    INSERT INTO insights_log (timestamp, reflection_json)
                    VALUES (%s, %s)
                """,
                    (reflection["timestamp"], json.dumps(reflection)),
                )

        except Exception as e:
            log.warning(f"Failed to persist insight: {e}")

    def _schedule_next_reflection(self):
        """Schedule the next daily reflection."""

        def run_reflection():
            try:
                self.daily_reflection()
            finally:
                self._schedule_next_reflection()

        self._timer = threading.Timer(CONTEMPLATION_INTERVAL_HOURS * 3600, run_reflection)
        self._timer.daemon = True
        self._timer.start()
        log.info(f"Scheduled next reflection in {CONTEMPLATION_INTERVAL_HOURS} hours")

    def daily_reflection(self) -> Dict[str, Any]:
        """
        Run daily reflection - generate comprehensive insights.

        Returns:
            {
                timestamp,
                memory_health,
                conflict_report,
                access_anomalies,
                decay_recommendations,
                consolidation_candidates,
                actions_taken (auto),
                actions_pending (need approval)
            }
        """
        timestamp = datetime.utcnow().isoformat()

        reflection = {
            "timestamp": timestamp,
            "memory_health": self.assess_memory_health(),
            "conflict_report": self.summarize_conflicts(),
            "access_anomalies": self.detect_access_anomalies(),
            "decay_recommendations": self.identify_stale_domains(),
            "consolidation_candidates": self.find_consolidation_candidates(),
            "actions_taken": [],
            "actions_pending": [],
        }

        if reflection["memory_health"]["avg_truth_score"] < 0.3:
            reflection["actions_taken"].append(
                {
                    "action": "alert",
                    "reason": "Low average truth score detected",
                    "severity": "warning",
                }
            )

        if reflection["consolidation_candidates"]["count"] > 10:
            reflection["actions_pending"].append(
                {
                    "action": "consolidate",
                    "count": reflection["consolidation_candidates"]["count"],
                    "description": "Consolidate similar memories to reduce redundancy",
                }
            )

        self._insights_log.append(reflection)
        self._persist_insight(reflection)

        log.info(
            f"Daily reflection complete: {len(reflection['actions_taken'])} auto actions, {len(reflection['actions_pending'])} pending"
        )

        return reflection

    def assess_memory_health(self) -> Dict[str, Any]:
        """Analyze truth score distribution across memories using proper scoring formula."""
        try:
            from memory_thread.services.tms_service import TruthVectorService

            if not self.pg:
                return self._mock_memory_health()

            with self.pg.get_cursor() as cur:
                if self.namespace:
                    cur.execute(
                        """
                        SELECT 
                            entity_id,
                            truth_vector
                        FROM entity_state
                        WHERE namespace = %s
                    """,
                        (self.namespace,),
                    )
                else:
                    cur.execute("""
                        SELECT 
                            entity_id,
                            truth_vector
                        FROM entity_state
                    """)
                rows = cur.fetchall()

                if not rows:
                    return self._mock_memory_health()

                total_scores = []
                total_confidence = 0
                total_authority = 0
                total_freshness = 0

                for row in rows:
                    tv_data = row[1]
                    if isinstance(tv_data, str):
                        tv_data = json.loads(tv_data)

                    from memory_thread.models.events import TruthVector

                    tv = TruthVector(**tv_data)

                    score = TruthVectorService.calculate_score(tv)
                    total_scores.append(score)
                    total_confidence += tv.confidence
                    total_authority += tv.authority
                    total_freshness += tv.freshness

                count = len(rows)
                avg_confidence = total_confidence / count if count > 0 else 0
                avg_authority = total_authority / count if count > 0 else 0
                avg_freshness = total_freshness / count if count > 0 else 0
                avg_truth_score = sum(total_scores) / count if count > 0 else 0

                return {
                    "total_memories": count,
                    "avg_confidence": round(avg_confidence, 3),
                    "avg_authority": round(avg_authority, 3),
                    "avg_freshness": round(avg_freshness, 3),
                    "avg_truth_score": round(avg_truth_score, 3),
                    "status": "healthy" if avg_confidence > 0.5 else "degraded",
                }
        except Exception as e:
            log.warning(f"Memory health check failed: {e}")

        return self._mock_memory_health()

    def _mock_memory_health(self) -> Dict[str, Any]:
        return {
            "total_memories": 0,
            "avg_confidence": 0.8,
            "avg_authority": 0.7,
            "avg_freshness": 0.6,
            "avg_truth_score": 0.7,
            "status": "unknown (no db)",
        }

    def summarize_conflicts(self) -> Dict[str, Any]:
        """Get summary of active conflicts across agent universes by querying DB."""
        try:
            if not self.pg:
                return {"active_conflicts": 0, "note": "No DB connection"}

            with self.pg.get_cursor() as cur:
                if self.namespace:
                    cur.execute(
                        """
                        SELECT id, object_id, delta, truth_vector, actor
                        FROM events
                        WHERE namespace = %s AND action = 'UPDATE'
                        ORDER BY timestamp DESC
                        LIMIT 1000
                    """,
                        (self.namespace,),
                    )
                else:
                    cur.execute("""
                        SELECT id, object_id, delta, truth_vector, actor
                        FROM events
                        WHERE action = 'UPDATE'
                        ORDER BY timestamp DESC
                        LIMIT 1000
                    """)
                events = cur.fetchall()

                beliefs_by_fact = defaultdict(list)
                for event in events:
                    event_id, object_id, delta, truth_vector, actor = event
                    if isinstance(delta, str):
                        delta = json.loads(delta)
                    if isinstance(truth_vector, str):
                        truth_vector = json.loads(truth_vector)

                    for key in delta.keys():
                        beliefs_by_fact[key].append(
                            {
                                "event_id": str(event_id),
                                "entity_id": str(object_id),
                                "value": delta.get(key),
                                "confidence": truth_vector.get("confidence", 0.5)
                                if truth_vector
                                else 0.5,
                                "authority": truth_vector.get("authority", 0.5)
                                if truth_vector
                                else 0.5,
                                "actor": actor,
                            }
                        )

                conflicts = []
                for fact, beliefs in beliefs_by_fact.items():
                    if len(beliefs) < 2:
                        continue

                    values = set(str(b["value"]) for b in beliefs)
                    if len(values) > 1:
                        conflicts.append(
                            {"fact": fact, "beliefs": beliefs[:5], "type": "value_mismatch"}
                        )

                return {
                    "active_conflicts": len(conflicts),
                    "conflicts": conflicts[:10],
                    "by_severity": {
                        "high": len([c for c in conflicts if len(c["beliefs"]) > 3]),
                        "medium": 0,
                        "low": len(conflicts),
                    },
                    "oldest_unresolved": None,
                    "recommendation": "No conflicts detected"
                    if not conflicts
                    else "Review conflicts",
                }
        except Exception as e:
            log.warning(f"Conflict summary failed: {e}")
            return {"active_conflicts": 0, "error": str(e)}

    def detect_access_anomalies(self) -> Dict[str, Any]:
        """Detect unusual access patterns."""
        try:
            if not self.pg:
                return {"anomalies": [], "note": "No DB connection"}

            with self.pg.get_cursor() as cur:
                cur.execute("""
                    SELECT user_id, COUNT(*) as access_count
                    FROM audit_log
                    WHERE timestamp > NOW() - INTERVAL '24 hours'
                    GROUP BY user_id
                    HAVING COUNT(*) > 100
                """)
                high_freq = cur.fetchall()

                anomalies = []
                for row in high_freq:
                    anomalies.append(
                        {
                            "type": "high_frequency_access",
                            "user_id": row[0],
                            "count": row[1],
                            "severity": "medium",
                        }
                    )

                return {"anomalies": anomalies, "checked_at": datetime.utcnow().isoformat()}
        except Exception as e:
            log.debug(f"Access anomaly check skipped: {e}")
            return {"anomalies": [], "note": "Check skipped"}

    def identify_stale_domains(self) -> Dict[str, Any]:
        """Find domains with high staleness (low freshness)."""
        try:
            if not self.pg:
                return {"stale_domains": [], "recommendation": None}

            with self.pg.get_cursor() as cur:
                if self.namespace:
                    cur.execute(
                        """
                        SELECT namespace, AVG((truth_vector->>'freshness')::float) as avg_freshness
                        FROM entity_state
                        WHERE namespace = %s
                        GROUP BY namespace
                        HAVING AVG((truth_vector->>'freshness')::float) < 0.3
                        ORDER BY avg_freshness ASC
                        LIMIT 5
                    """,
                        (self.namespace,),
                    )
                else:
                    cur.execute("""
                        SELECT namespace, AVG((truth_vector->>'freshness')::float) as avg_freshness
                        FROM entity_state
                        GROUP BY namespace
                        HAVING AVG((truth_vector->>'freshness')::float) < 0.3
                        ORDER BY avg_freshness ASC
                        LIMIT 5
                    """)
                stale = cur.fetchall()

                domains = [
                    {"namespace": row[0], "avg_freshness": round(row[1], 3)} for row in stale
                ]

                return {
                    "stale_domains": domains,
                    "recommendation": f"Consider refreshing {len(domains)} stale domains"
                    if domains
                    else None,
                }
        except Exception as e:
            log.debug(f"Stale domain check skipped: {e}")
            return {"stale_domains": [], "recommendation": None}

    def find_consolidation_candidates(self) -> Dict[str, Any]:
        """Find memories that could be consolidated using AssimilatorService."""
        try:
            from memory_thread.services.assimilator import AssimilatorService

            if not self.pg:
                return {"count": 0, "potential_savings": "0%", "recommendation": "No DB connection"}

            assimilator = AssimilatorService()

            patterns = assimilator.detect_patterns()

            count = len(patterns.get("clusters", [])) if patterns else 0
            potential_savings = f"{count * 5}%" if count > 0 else "0%"

            return {
                "count": count,
                "potential_savings": potential_savings,
                "patterns": patterns,
                "recommendation": f"Consider consolidating {count} clusters"
                if count > 0
                else "No consolidation needed",
            }
        except Exception as e:
            log.debug(f"Consolidation check skipped: {e}")
            return {"count": 0, "error": str(e)}

    def generate_insight_summary(self) -> str:
        """Generate natural language summary of latest reflection."""
        if not self._insights_log:
            return "No reflections yet. Run daily_reflection() first."

        latest = self._insights_log[-1]

        lines = [
            f"MT Reflection Summary ({latest['timestamp'][:10]})",
            "=" * 40,
            f"Memory Health: {latest['memory_health']['status']}",
            f"  - {latest['memory_health']['total_memories']} memories",
            f"  - Avg truth score: {latest['memory_health']['avg_truth_score']:.0%}",
            f"Conflicts: {latest['conflict_report']['active_conflicts']} active",
            f"Stale Domains: {len(latest['decay_recommendations']['stale_domains'])}",
            f"Consolidation: {latest['consolidation_candidates']['count']} candidates",
            "",
            f"Auto Actions: {len(latest['actions_taken'])}",
            f"Pending Approval: {len(latest['actions_pending'])}",
        ]

        return "\n".join(lines)

    def get_insights_history(self, limit: int = 10) -> List[Dict]:
        """Get recent insight history."""
        return self._insights_log[-limit:]


contemplator = Contemplator()
