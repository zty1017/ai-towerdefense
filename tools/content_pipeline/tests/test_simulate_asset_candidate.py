import unittest

from tools.content_pipeline import simulate_asset_candidate as simulator


class SimulateAssetCandidateTest(unittest.TestCase):
    def test_protective_tower_counts_as_playable_utility(self) -> None:
        candidate = {
            "id": "asset_wick_barrier_pylon",
            "gameplay": {
                "asset_type": "tower_blueprint",
                "base_stats": {"build_cost": 170, "range": 90, "cooldown": 2.0},
                "effect_blocks": [
                    {"type": "shield", "shield_amount": 120},
                    {"type": "repair", "repair_amount": 15},
                    {"type": "aura_buff", "radius": 80, "target": "ally"},
                    {"type": "power_cost", "power_per_second": 3.0},
                ],
            },
        }

        report = simulator.simulate(candidate, duration=30.0)

        self.assertGreaterEqual(report["utility_score"], 0.2)
        self.assertNotIn("no_direct_impact", report["balance_flags"])


if __name__ == "__main__":
    unittest.main()
