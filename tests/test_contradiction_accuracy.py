from dataclasses import dataclass

from memory_thread.models.events import EntityState, TruthVector
from memory_thread.services.meta_stability_service import MetaStabilityService


@dataclass(frozen=True)
class ContradictionCase:
    name: str
    current_value: dict
    new_delta: dict
    expected_contradiction: bool


def _state_for(case: ContradictionCase) -> EntityState:
    return EntityState(
        entity_id="00000000-0000-0000-0000-000000000001",
        namespace="accuracy",
        current_value=case.current_value,
        truth_vector=TruthVector(confidence=1.0, authority=1.0, freshness=1.0, corroboration=0.0),
        last_event_id="00000000-0000-0000-0000-000000000002",
    )


def _dataset():
    contradictions = [
        ContradictionCase("bool_enabled", {"enabled": True}, {"enabled": False}, True),
        ContradictionCase("bool_verified", {"verified": False}, {"verified": True}, True),
        ContradictionCase("bool_active", {"active": True}, {"active": False}, True),
        ContradictionCase("bool_premium", {"premium": False}, {"premium": True}, True),
        ContradictionCase("bool_public", {"public": True}, {"public": False}, True),
        ContradictionCase("bool_remote", {"remote": False}, {"remote": True}, True),
        ContradictionCase("bool_opted_in", {"opted_in": True}, {"opted_in": False}, True),
        ContradictionCase("bool_archived", {"archived": False}, {"archived": True}, True),
        ContradictionCase("bool_admin", {"admin": True}, {"admin": False}, True),
        ContradictionCase("bool_locked", {"locked": False}, {"locked": True}, True),
        ContradictionCase("semantic_like_hate", {"likes": "likes"}, {"likes": "hates"}, True),
        ContradictionCase("semantic_prefer_avoid", {"prefers": "prefers"}, {"prefers": "avoids"}, True),
        ContradictionCase("semantic_love_dislike", {"loves": "loves"}, {"loves": "dislikes"}, True),
        ContradictionCase("semantic_happy_sad", {"happy": "happy"}, {"happy": "sad"}, True),
        ContradictionCase("semantic_support_oppose", {"supports": "supports"}, {"supports": "opposes"}, True),
        ContradictionCase("semantic_true_false", {"true": "true"}, {"true": "false"}, True),
        ContradictionCase("semantic_yes_no", {"yes": "yes"}, {"yes": "no"}, True),
        ContradictionCase("semantic_enable_disable", {"enable": "enable"}, {"enable": "disable"}, True),
        ContradictionCase("semantic_accept_reject", {"accept": "accept"}, {"accept": "reject"}, True),
        ContradictionCase("semantic_trust_distrust", {"trusts": "trusts"}, {"trusts": "distrusts"}, True),
        ContradictionCase("sign_positive_negative", {"balance": 12}, {"balance": -12}, True),
        ContradictionCase("sign_negative_positive", {"sentiment": -3}, {"sentiment": 5}, True),
        ContradictionCase("age_mismatch", {"age": 25}, {"age": 30}, True),
        ContradictionCase("salary_mismatch", {"salary": 100000}, {"salary": 120000}, True),
        ContradictionCase("year_mismatch", {"birth_year": 1995}, {"birth_year": 1998}, True),
    ]
    non_contradictions = [
        ContradictionCase("same_bool", {"enabled": True}, {"enabled": True}, False),
        ContradictionCase("same_number", {"balance": 12}, {"balance": 12}, False),
        ContradictionCase("incrementing_count", {"visits": 5}, {"visits": 6}, False),
        ContradictionCase("decrement_same_sign", {"temperature": 8}, {"temperature": 3}, False),
        ContradictionCase("semantic_related", {"likes": "pizza"}, {"likes": "pasta"}, False),
        ContradictionCase("semantic_related_2", {"supports": "team_a"}, {"supports": "team_b"}, False),
        ContradictionCase("semantic_related_3", {"true": "statement_a"}, {"true": "statement_b"}, False),
        ContradictionCase("metadata_add", {"city": "Delhi"}, {"country": "India"}, False),
        ContradictionCase("metadata_add_2", {"name": "Ava"}, {"timezone": "UTC"}, False),
        ContradictionCase("same_preference", {"prefers": "tea"}, {"prefers": "tea"}, False),
        ContradictionCase("mood_update", {"happy": "content"}, {"happy": "calm"}, False),
        ContradictionCase("no_overlap", {"role": "engineer"}, {"team": "platform"}, False),
        ContradictionCase("positive_growth", {"revenue": 10}, {"revenue": 15}, False),
        ContradictionCase("negative_growth", {"debt": -10}, {"debt": -20}, False),
        ContradictionCase("same_status", {"public": False}, {"public": False}, False),
        ContradictionCase("same_verification", {"verified": True}, {"verified": True}, False),
        ContradictionCase("same_lock", {"locked": True}, {"locked": True}, False),
        ContradictionCase("same_archive", {"archived": False}, {"archived": False}, False),
        ContradictionCase("same_opt_in", {"opted_in": True}, {"opted_in": True}, False),
        ContradictionCase("same_remote", {"remote": True}, {"remote": True}, False),
        ContradictionCase("compatible_relation", {"manager": "alice"}, {"mentor": "alice"}, False),
        ContradictionCase("compatible_identity", {"age": 25}, {"nickname": "aj"}, False),
        ContradictionCase("compatible_employment", {"salary": 100000}, {"title": "staff"}, False),
        ContradictionCase("compatible_schedule", {"year": 2026}, {"quarter": 2}, False),
        ContradictionCase("compatible_location", {"city": "Paris"}, {"office": "HQ"}, False),
    ]
    return contradictions + non_contradictions


def test_contradiction_accuracy_precision_and_recall():
    service = MetaStabilityService()
    dataset = _dataset()
    tp = fp = fn = 0

    for case in dataset:
        predicted = service.check_contradiction(_state_for(case), case.new_delta)
        if predicted and case.expected_contradiction:
            tp += 1
        elif predicted and not case.expected_contradiction:
            fp += 1
        elif not predicted and case.expected_contradiction:
            fn += 1

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)

    assert tp >= 18
    assert fp <= 1
    assert precision >= 0.95
    assert recall >= 0.70
