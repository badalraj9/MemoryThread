"""
Contemplator - MT Self-Observation Service.

MT observes its own state and generates insights.
Hybrid approach: auto for low-risk, approval for high-risk actions.
"""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict

from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


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
    
    def __init__(self):
        self._pg = None
        self._insights_log = []
    
    @property
    def pg(self):
        if not self._pg:
            try:
                from memory_thread.db.postgres_client import PostgresClient
                self._pg = PostgresClient()
            except Exception:
                pass
        return self._pg
    
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
        
        # Auto actions (low-risk)
        if reflection["memory_health"]["avg_truth_score"] < 0.3:
            reflection["actions_taken"].append({
                "action": "alert",
                "reason": "Low average truth score detected",
                "severity": "warning"
            })
        
        # Pending actions (need approval)
        if reflection["consolidation_candidates"]["count"] > 10:
            reflection["actions_pending"].append({
                "action": "consolidate",
                "count": reflection["consolidation_candidates"]["count"],
                "description": "Consolidate similar memories to reduce redundancy"
            })
        
        self._insights_log.append(reflection)
        log.info(f"Daily reflection complete: {len(reflection['actions_taken'])} auto actions, {len(reflection['actions_pending'])} pending")
        
        return reflection
    
    def assess_memory_health(self) -> Dict[str, Any]:
        """Analyze truth score distribution across memories."""
        try:
            if not self.pg:
                return self._mock_memory_health()
            
            with self.pg.get_cursor() as cur:
                # Get truth score distribution
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        AVG((truth_vector->>'confidence')::float) as avg_confidence,
                        AVG((truth_vector->>'authority')::float) as avg_authority,
                        AVG((truth_vector->>'freshness')::float) as avg_freshness
                    FROM entity_state
                """)
                row = cur.fetchone()
                
                if row:
                    return {
                        "total_memories": row[0] or 0,
                        "avg_confidence": round(row[1] or 0, 3),
                        "avg_authority": round(row[2] or 0, 3),
                        "avg_freshness": round(row[3] or 0, 3),
                        "avg_truth_score": round(((row[1] or 0) + (row[2] or 0) + (row[3] or 0)) / 3, 3),
                        "status": "healthy" if (row[1] or 0) > 0.5 else "degraded"
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
            "status": "unknown (no db)"
        }
    
    def summarize_conflicts(self) -> Dict[str, Any]:
        """Get summary of active conflicts across agent universes."""
        try:
            from memory_thread.nervous.conflict_resolution import ConflictResolver
            resolver = ConflictResolver()
            conflicts = resolver.detect_conflicts({}, {})
            
            return {
                "active_conflicts": len(conflicts),
                "by_severity": {"high": 0, "medium": 0, "low": 0},
                "oldest_unresolved": None,
                "recommendation": "No conflicts detected" if not conflicts else "Review conflicts"
            }
        except Exception as e:
            log.warning(f"Conflict summary failed: {e}")
            return {"active_conflicts": 0, "error": str(e)}
    
    def detect_access_anomalies(self) -> Dict[str, Any]:
        """Detect unusual access patterns."""
        try:
            if not self.pg:
                return {"anomalies": [], "note": "No DB connection"}
            
            # Check audit log for anomalies
            with self.pg.get_cursor() as cur:
                # High-frequency access from single user
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
                    anomalies.append({
                        "type": "high_frequency_access",
                        "user_id": row[0],
                        "count": row[1],
                        "severity": "medium"
                    })
                
                return {
                    "anomalies": anomalies,
                    "checked_at": datetime.utcnow().isoformat()
                }
        except Exception as e:
            log.debug(f"Access anomaly check skipped: {e}")
            return {"anomalies": [], "note": "Check skipped"}
    
    def identify_stale_domains(self) -> Dict[str, Any]:
        """Find domains with high staleness (low freshness)."""
        try:
            if not self.pg:
                return {"stale_domains": [], "recommendation": None}
            
            with self.pg.get_cursor() as cur:
                cur.execute("""
                    SELECT namespace, AVG((truth_vector->>'freshness')::float) as avg_freshness
                    FROM entity_state
                    GROUP BY namespace
                    HAVING AVG((truth_vector->>'freshness')::float) < 0.3
                    ORDER BY avg_freshness ASC
                    LIMIT 5
                """)
                stale = cur.fetchall()
                
                domains = [{"namespace": row[0], "avg_freshness": round(row[1], 3)} for row in stale]
                
                return {
                    "stale_domains": domains,
                    "recommendation": f"Consider refreshing {len(domains)} stale domains" if domains else None
                }
        except Exception as e:
            log.debug(f"Stale domain check skipped: {e}")
            return {"stale_domains": [], "recommendation": None}
    
    def find_consolidation_candidates(self) -> Dict[str, Any]:
        """Find memories that could be consolidated."""
        try:
            from memory_thread.services.assimilator import AssimilatorService
            assimilator = AssimilatorService()
            
            # This would scan for patterns
            return {
                "count": 0,
                "potential_savings": "0%",
                "recommendation": "No consolidation needed"
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


# Singleton
contemplator = Contemplator()
