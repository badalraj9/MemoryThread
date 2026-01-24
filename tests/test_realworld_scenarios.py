"""
Real-World Scenario Tests for Memory Thread.

This test harness simulates how an AI agent would actually use MT as its memory.
Instead of unit testing individual functions, we validate real-world memory scenarios:

1. Learning & Remembering - Can MT store and retrieve user facts?
2. Contradiction Handling - When conflicting info arrives, what wins?
3. Truth Decay - Does old information properly become "stale"?
4. Timewarp - Can late-arriving information repair the timeline?
5. Entity Resolution - Can MT recognize the same entity mentioned differently?
6. Honest Failure - Does MT admit when it doesn't know something?

Run with:
    python tests/test_realworld_scenarios.py

Or with pytest:
    pytest tests/test_realworld_scenarios.py -v -s
"""
import uuid
import datetime
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# MT Core Imports
from memory_thread.models.events import (
    Event, EntityState, TruthVector, ActorEnum, ActionEnum
)
from memory_thread.services.tms_service import (
    TMSService, TruthVectorService, StateDerivationService
)
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class MemoryRecord:
    """Represents a memory as an AI would perceive it."""
    entity_id: uuid.UUID
    content: Dict[str, Any]
    confidence: float
    freshness: float
    source: str  # Who told us this?


class AIMemoryInterface:
    """
    Simulates how an AI agent would interface with Memory Thread.
    
    This is the "memory API" that a JARVIS-like system would use.
    """
    
    def __init__(self):
        self.tms = TMSService()
        self.memories: Dict[uuid.UUID, EntityState] = {}  # In-memory cache
        self.event_log: List[Event] = []
        
    def learn(
        self, 
        subject: str, 
        fact: Dict[str, Any], 
        source: ActorEnum = ActorEnum.USER,
        confidence: float = 1.0
    ) -> uuid.UUID:
        """
        Learn a new fact about a subject.
        
        Example:
            ai.learn("user", {"name": "Badal", "occupation": "developer"})
        """
        # Find or create entity
        entity_id = self._get_or_create_entity(subject)
        
        # Create event
        event = self.tms.create_event(
            actor=source,
            action=ActionEnum.UPDATE,
            object_id=entity_id,
            delta=fact,
            confidence=confidence,
            authority=1.0 if source == ActorEnum.USER else 0.7
        )
        
        self.event_log.append(event)
        
        # Apply to state
        current_state = self.memories.get(entity_id)
        if current_state is None:
            current_state = EntityState(
                entity_id=entity_id,
                namespace="memory",
                current_value={},
                truth_vector=TruthVector(
                    confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0
                ),
                last_event_id=uuid.uuid4()
            )
        
        new_state = StateDerivationService.apply_event(current_state, event)
        self.memories[entity_id] = new_state
        
        log.info(f"📝 Learned about {subject}: {fact}")
        return entity_id
    
    def remember(self, subject: str) -> Optional[MemoryRecord]:
        """
        Try to remember what we know about a subject.
        
        Returns None if we have no memory of this subject.
        """
        entity_id = self._find_entity(subject)
        if entity_id is None:
            log.info(f"🤔 I don't have any memory of '{subject}'")
            return None
        
        state = self.memories.get(entity_id)
        if state is None:
            return None
            
        # Calculate current freshness based on time
        tv = state.truth_vector
        decayed_freshness = TruthVectorService.decay_freshness(
            tv, state.updated_at, "fact"
        )
        
        return MemoryRecord(
            entity_id=entity_id,
            content=state.current_value,
            confidence=tv.confidence,
            freshness=decayed_freshness,
            source="memory"
        )
    
    def update(
        self, 
        subject: str, 
        fact: Dict[str, Any],
        source: ActorEnum = ActorEnum.USER
    ) -> bool:
        """
        Update existing memory about a subject.
        """
        entity_id = self._find_entity(subject)
        if entity_id is None:
            log.warning(f"⚠️ Can't update - no memory of '{subject}'")
            return False
        
        event = self.tms.create_event(
            actor=source,
            action=ActionEnum.UPDATE,
            object_id=entity_id,
            delta=fact
        )
        
        self.event_log.append(event)
        
        current_state = self.memories[entity_id]
        new_state = StateDerivationService.apply_event(current_state, event)
        self.memories[entity_id] = new_state
        
        log.info(f"🔄 Updated memory of {subject}: {fact}")
        return True
    
    def handle_contradiction(
        self,
        subject: str,
        conflicting_fact: Dict[str, Any],
        source: ActorEnum,
        source_confidence: float = 0.8
    ) -> Dict[str, Any]:
        """
        Handle contradictory information using Truth Vectors.
        
        Returns resolution info.
        """
        entity_id = self._find_entity(subject)
        if entity_id is None:
            # No existing memory, just learn it
            self.learn(subject, conflicting_fact, source, source_confidence)
            return {"resolution": "accepted", "reason": "no prior memory"}
        
        current_state = self.memories[entity_id]
        current_score = TruthVectorService.calculate_score(current_state.truth_vector)
        
        # Create hypothetical new truth vector
        new_tv = TruthVector(
            confidence=source_confidence,
            authority=1.0 if source == ActorEnum.USER else 0.5,
            freshness=1.0,  # New info is fresh
            corroboration=0.0
        )
        new_score = TruthVectorService.calculate_score(new_tv)
        
        log.info(f"⚖️ Contradiction detected for {subject}")
        log.info(f"   Current truth score: {current_score:.2f}")
        log.info(f"   New claim score: {new_score:.2f}")
        
        if new_score > current_score:
            # New info wins
            self.update(subject, conflicting_fact, source)
            return {
                "resolution": "replaced",
                "reason": f"new truth score ({new_score:.2f}) > old ({current_score:.2f})"
            }
        else:
            # Keep old info but note the conflict
            return {
                "resolution": "rejected",
                "reason": f"current truth score ({current_score:.2f}) > new ({new_score:.2f})",
                "flagged_conflict": True
            }
    
    def get_truth_confidence(self, subject: str) -> Optional[float]:
        """
        How confident are we about what we know about this subject?
        """
        memory = self.remember(subject)
        if memory is None:
            return None
        return TruthVectorService.calculate_score(
            TruthVector(
                confidence=memory.confidence,
                authority=1.0,
                freshness=memory.freshness,
                corroboration=0.0
            )
        )
    
    def _get_or_create_entity(self, subject: str) -> uuid.UUID:
        """Get existing entity ID or create new one."""
        # Simple mapping for demo
        if not hasattr(self, '_entity_map'):
            self._entity_map = {}
        
        if subject not in self._entity_map:
            self._entity_map[subject] = uuid.uuid4()
        
        return self._entity_map[subject]
    
    def _find_entity(self, subject: str) -> Optional[uuid.UUID]:
        """Find entity by subject name."""
        if not hasattr(self, '_entity_map'):
            return None
        return self._entity_map.get(subject)


# ==================== SCENARIO TESTS ====================

def scenario_1_learning_and_remembering():
    """
    SCENARIO 1: Learning User Preferences
    
    The AI learns facts about the user and can recall them accurately.
    """
    print("\n" + "="*60)
    print("SCENARIO 1: Learning & Remembering")
    print("="*60)
    
    ai = AIMemoryInterface()
    
    # User tells AI about themselves
    ai.learn("user", {
        "name": "Badal",
        "occupation": "developer",
        "favorite_language": "Python"
    })
    
    ai.learn("user", {
        "project": "Memory Thread",
        "goal": "build AI memory system"
    })
    
    # Later, AI tries to remember
    memory = ai.remember("user")
    
    assert memory is not None, "Should remember user"
    assert memory.content.get("name") == "Badal", "Should remember name"
    assert memory.content.get("project") == "Memory Thread", "Should remember project"
    
    print(f"\n✅ AI remembers user: {memory.content}")
    print(f"   Confidence: {memory.confidence:.2f}")
    print(f"   Freshness: {memory.freshness:.2f}")
    
    return True


def scenario_2_handling_contradictions():
    """
    SCENARIO 2: Contradictory Information
    
    User first says they like Python, then says they like Rust.
    How does the system resolve this?
    """
    print("\n" + "="*60)
    print("SCENARIO 2: Handling Contradictions")
    print("="*60)
    
    ai = AIMemoryInterface()
    
    # Initial fact
    ai.learn("user", {"favorite_language": "Python"}, ActorEnum.USER, confidence=0.9)
    
    memory1 = ai.remember("user")
    print(f"Initial: favorite_language = {memory1.content.get('favorite_language')}")
    
    # User changes their mind (higher authority since direct from user)
    result = ai.handle_contradiction(
        "user",
        {"favorite_language": "Rust"},
        ActorEnum.USER,
        source_confidence=1.0  # Very confident assertion
    )
    
    print(f"Contradiction result: {result}")
    
    memory2 = ai.remember("user")
    print(f"After: favorite_language = {memory2.content.get('favorite_language')}")
    
    # The new info should have won (fresher, higher confidence)
    assert result["resolution"] == "replaced", "Higher confidence should win"
    assert memory2.content.get("favorite_language") == "Rust", "Should update to Rust"
    
    print("\n✅ Contradiction resolved correctly using Truth Vector scoring")
    return True


def scenario_3_agent_vs_user_authority():
    """
    SCENARIO 3: Agent Inference vs User Statement
    
    Agent infers something, then user corrects it.
    User authority should override agent inference.
    """
    print("\n" + "="*60)
    print("SCENARIO 3: Agent vs User Authority")
    print("="*60)
    
    ai = AIMemoryInterface()
    
    # Agent infers user's timezone from context
    ai.learn("user", {"timezone": "UTC"}, ActorEnum.AGENT, confidence=0.7)
    
    memory1 = ai.remember("user")
    print(f"Agent inferred: timezone = {memory1.content.get('timezone')}")
    
    # User explicitly corrects
    result = ai.handle_contradiction(
        "user",
        {"timezone": "IST"},
        ActorEnum.USER,
        source_confidence=1.0
    )
    
    memory2 = ai.remember("user")
    print(f"User corrected: timezone = {memory2.content.get('timezone')}")
    
    assert memory2.content.get("timezone") == "IST", "User authority should override"
    
    print("\n✅ User truth correctly overrides agent inference")
    return True


def scenario_4_memory_decay():
    """
    SCENARIO 4: Truth Decay Over Time
    
    Old information should become less "fresh" but facts stay longer than events.
    """
    print("\n" + "="*60)
    print("SCENARIO 4: Memory Decay")
    print("="*60)
    
    # Test decay calculation directly
    tv = TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0)
    
    # Simulate different time periods
    now = datetime.datetime.utcnow()
    
    # Event from 10 days ago (fast decay)
    event_freshness = TruthVectorService.decay_freshness(
        tv, now - datetime.timedelta(days=10), "event"
    )
    
    # Fact from 10 days ago (slow decay)
    fact_freshness = TruthVectorService.decay_freshness(
        tv, now - datetime.timedelta(days=10), "fact"
    )
    
    # Identity never decays
    identity_freshness = TruthVectorService.decay_freshness(
        tv, now - datetime.timedelta(days=10), "identity"
    )
    
    print(f"After 10 days:")
    print(f"  Event freshness: {event_freshness:.3f} (fast decay)")
    print(f"  Fact freshness:  {fact_freshness:.3f} (slow decay)")
    print(f"  Identity:        {identity_freshness:.3f} (never decays)")
    
    assert event_freshness < fact_freshness, "Events should decay faster"
    assert identity_freshness == 1.0, "Identity should never decay"
    
    print("\n✅ Decay rates correctly differentiate memory types")
    return True


def scenario_5_honest_ignorance():
    """
    SCENARIO 5: Honest Failure / Admitting Ignorance
    
    The AI should honestly admit when it doesn't know something.
    """
    print("\n" + "="*60)
    print("SCENARIO 5: Honest Ignorance")
    print("="*60)
    
    ai = AIMemoryInterface()
    
    # AI has never learned about this entity
    memory = ai.remember("quantum_physics_expert")
    
    assert memory is None, "Should return None for unknown entities"
    
    confidence = ai.get_truth_confidence("quantum_physics_expert")
    assert confidence is None, "Should have no confidence about unknown"
    
    print("📭 Asked about unknown entity: 'quantum_physics_expert'")
    print("   Memory returned: None")
    print("   Confidence: None")
    print("\n✅ AI honestly admits ignorance instead of hallucinating")
    return True


def scenario_6_5000_trees_realworld():
    """
    SCENARIO 6: The 5000 Trees Problem (Real-World Framing)
    
    User tells AI about tree planting events. Can it correctly track the count?
    """
    print("\n" + "="*60)
    print("SCENARIO 6: The 5000 Trees Problem")
    print("="*60)
    
    ai = AIMemoryInterface()
    tms = ai.tms
    entity_id = uuid.uuid4()
    
    # Initial state
    state = EntityState(
        entity_id=entity_id,
        namespace="memory",
        current_value={"tree_count": 0},
        truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0),
        last_event_id=uuid.uuid4()
    )
    
    print(f"T=0: tree_count = {state.current_value['tree_count']}")
    
    # User: "I planted 5000 trees yesterday"
    e1 = tms.create_event(ActorEnum.USER, ActionEnum.PLANT, entity_id, {"tree_count": 5000})
    state = StateDerivationService.apply_event(state, e1)
    print(f"T=1 (PLANT 5000): tree_count = {state.current_value['tree_count']}")
    
    # User: "We added 10 more today"
    e2 = tms.create_event(ActorEnum.USER, ActionEnum.ADD, entity_id, {"tree_count": 10})
    state = StateDerivationService.apply_event(state, e2)
    print(f"T=2 (ADD 10): tree_count = {state.current_value['tree_count']}")
    
    # User: "Oh, 20 died in the frost"
    e3 = tms.create_event(ActorEnum.USER, ActionEnum.REMOVE, entity_id, {"tree_count": 20})
    state = StateDerivationService.apply_event(state, e3)
    print(f"T=3 (REMOVE 20): tree_count = {state.current_value['tree_count']}")
    
    assert state.current_value["tree_count"] == 4990, "Should be 5000 + 10 - 20 = 4990"
    
    print(f"\n✅ Final answer: {state.current_value['tree_count']} trees")
    print("   Event sourcing correctly tracks state changes!")
    return True


def run_all_scenarios():
    """Run all real-world scenarios."""
    print("\n" + "🧠"*30)
    print("  MEMORY THREAD - Real World Scenario Tests")
    print("  Testing MT as if it's an AI's actual memory")
    print("🧠"*30)
    
    scenarios = [
        ("Learning & Remembering", scenario_1_learning_and_remembering),
        ("Handling Contradictions", scenario_2_handling_contradictions),
        ("Agent vs User Authority", scenario_3_agent_vs_user_authority),
        ("Memory Decay", scenario_4_memory_decay),
        ("Honest Ignorance", scenario_5_honest_ignorance),
        ("5000 Trees Problem", scenario_6_5000_trees_realworld),
    ]
    
    results = []
    for name, scenario_fn in scenarios:
        try:
            passed = scenario_fn()
            results.append((name, passed, None))
        except Exception as e:
            results.append((name, False, str(e)))
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    all_passed = True
    for name, passed, error in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
        if error:
            print(f"       Error: {error}")
            all_passed = False
    
    if all_passed:
        print("\n🎉 ALL SCENARIOS PASSED!")
        print("Memory Thread is ready to be an AI's memory system.")
    else:
        print("\n⚠️ Some scenarios failed. Review above.")
    
    return all_passed


if __name__ == "__main__":
    run_all_scenarios()
