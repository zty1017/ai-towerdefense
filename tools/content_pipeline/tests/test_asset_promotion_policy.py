import unittest

from tools.content_pipeline import asset_promotion_policy as policy


def _candidate() -> dict:
    return {
        "id": "asset_test_tower",
        "gameplay": {
            "asset_type": "tower_blueprint",
            "base_stats": {"build_cost": 100, "range": 4, "cooldown": 1.2},
            "type_specific": {"tower_slot": "ground"},
            "effect_blocks": [{"type": "damage", "amount": 25}],
        },
    }


def _validation() -> dict:
    return {"status": "passed", "errors": []}


def _simulation(flags: list[str] | None = None) -> dict:
    return {
        "utility_score": 0.45,
        "estimated_dps": 40,
        "balance_flags": flags or [],
    }


def _score(recommendation: str = "promote_candidate") -> dict:
    return {
        "recommendation": recommendation,
        "dimension_scores": {
            "validation": 100,
            "gameplay_fit": 92,
            "simulation": 76,
        },
    }


def _runtime_readiness(status: str = "passed") -> dict:
    return {"status": status}


class AssetPromotionPolicyTest(unittest.TestCase):
    def test_runtime_ready_when_core_and_media_pass(self) -> None:
        report = policy.evaluate_promotion(
            _candidate(),
            validation=_validation(),
            simulation=_simulation(),
            candidate_score=_score(),
            runtime_readiness=_runtime_readiness("passed"),
        )
        self.assertEqual(report["promotion_state"], "runtime_ready")
        self.assertTrue(report["playable"])
        self.assertFalse(report["uses_fallback_media"])

    def test_fallback_ready_when_media_missing_but_gameplay_passes(self) -> None:
        report = policy.evaluate_promotion(
            _candidate(),
            validation=_validation(),
            simulation=_simulation(),
            candidate_score=_score("generate_media"),
            runtime_readiness=None,
        )
        self.assertEqual(report["promotion_state"], "fallback_ready")
        self.assertTrue(report["playable"])
        self.assertTrue(report["uses_fallback_media"])
        self.assertIn("attach_deterministic_fallback_skin", report["required_next_actions"])

    def test_low_simulation_score_warns_but_does_not_block_delivery(self) -> None:
        score = _score("generate_media")
        score["dimension_scores"]["simulation"] = 21
        report = policy.evaluate_promotion(
            _candidate(),
            validation=_validation(),
            simulation=_simulation(["pure_control_requires_damage_partner"]),
            candidate_score=score,
            runtime_readiness=None,
        )
        self.assertEqual(report["promotion_state"], "fallback_ready")
        self.assertTrue(report["playable"])
        self.assertIn("candidate_score_simulation_low", report["warnings"])

    def test_failed_when_gameplay_core_fails(self) -> None:
        report = policy.evaluate_promotion(
            _candidate(),
            validation={"status": "failed", "errors": ["bad effect"]},
            simulation=_simulation(),
            candidate_score=_score("reject"),
            runtime_readiness=_runtime_readiness("passed"),
        )
        self.assertEqual(report["promotion_state"], "failed")
        self.assertFalse(report["playable"])
        self.assertIn("candidate_validation_failed", report["blockers"])


if __name__ == "__main__":
    unittest.main()
