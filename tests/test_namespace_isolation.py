def test_namespace_isolation_blocks_cross_namespace_reads_direct_lookup_and_deletes(memory_client_factory):
    alpha = memory_client_factory("alpha", use_db=False)
    beta = memory_client_factory("beta", use_db=False)

    alpha_ids = [alpha.remember(f"agent_alpha memory {i} alpha_only_token_{i}", source="agent") for i in range(50)]
    beta_ids = [beta.remember(f"agent_beta memory {i} beta_only_token_{i}", source="agent") for i in range(50)]

    alpha_results = alpha.recall("beta_only_token_7", top_k=10, min_truth_score=0.0)
    beta_results = beta.recall("alpha_only_token_7", top_k=10, min_truth_score=0.0)

    assert alpha_results.total_found == 0
    assert beta_results.total_found == 0
    assert alpha.get_truth_score(beta_ids[0]) is None
    assert beta.get_truth_score(alpha_ids[0]) is None
    assert beta_ids[0] not in alpha._memories
    assert alpha_ids[0] not in beta._memories

    shared_content = "cross namespace identical content"
    alpha_shared = alpha.remember(shared_content, source="agent", authority=0.9, confidence=0.9)
    beta_shared = beta.remember(shared_content, source="agent", authority=0.2, confidence=0.2)

    assert alpha_shared != beta_shared
    assert alpha.get_truth_score(alpha_shared) != beta.get_truth_score(beta_shared)
    assert alpha._memories[alpha_shared].namespace != beta._memories[beta_shared].namespace

    for entity_id in alpha_ids + [alpha_shared]:
        assert alpha.forget(entity_id) is True

    assert beta.get_stats()["total_memories"] == 51
    assert all(beta.get_truth_score(entity_id) is not None for entity_id in beta_ids + [beta_shared])
