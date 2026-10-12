import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

class TestTransferLabBudget(unittest.TestCase):
    """
    Deterministic regression tests for Transfer Lab budget filtering and unconstrained mode.
    Mocks player projections with:
      - 1 current player: "Current Mid" (ID 1, cost £5.0m, xP 3.0)
      - 1 affordable candidate: "Rogers" (ID 2, cost £5.2m, xP 4.5)
      - 1 higher-ranked over-budget candidate: "Palmer" (ID 3, cost £10.5m, xP 8.0)
    """

    def setUp(self):
        fixtures = []
        for gw in range(31, 36):
            fixtures.append({"event": gw, "team_h": 2, "team_a": 1, "team_h_difficulty": 3, "team_a_difficulty": 3})
            fixtures.append({"event": gw, "team_h": 3, "team_a": 1, "team_h_difficulty": 2, "team_a_difficulty": 4})

        self.mock_context = {
            "next_gw": 31,
            "gw_range": 5,
            "upcoming_fixtures_raw": fixtures,
            "bootstrap": {
                "elements": [
                    {
                        "id": 1, "web_name": "Current Mid", "team": 1, "team_code": 1,
                        "element_type": 3, "now_cost": 50, "form": "3.0", "minutes": 900,
                        "starts": 10, "expected_goals_per_90": 0.1, "expected_assists_per_90": 0.1,
                        "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 1.0,
                        "chance_of_playing_next_round": 100, "total_points": 50, "selected_by_percent": 5.0
                    },
                    {
                        "id": 2, "web_name": "Rogers", "team": 2, "team_code": 2,
                        "element_type": 3, "now_cost": 52, "form": "4.5", "minutes": 900,
                        "starts": 10, "expected_goals_per_90": 0.3, "expected_assists_per_90": 0.3,
                        "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
                        "chance_of_playing_next_round": 100, "total_points": 80, "selected_by_percent": 10.0
                    },
                    {
                        "id": 3, "web_name": "Palmer", "team": 3, "team_code": 3,
                        "element_type": 3, "now_cost": 105, "form": "8.0", "minutes": 900,
                        "starts": 10, "expected_goals_per_90": 0.7, "expected_assists_per_90": 0.5,
                        "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
                        "chance_of_playing_next_round": 100, "total_points": 140, "selected_by_percent": 35.0
                    }
                ]
            },
            "teams": {
                1: {"id": 1, "short_name": "ARS", "team_code": 1, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
                2: {"id": 2, "short_name": "AVL", "team_code": 2, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
                3: {"id": 3, "short_name": "CHE", "team_code": 3, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100}
            }
        }

    @patch("main.get_fpl_context")
    def test_unlimited_budget_true_selects_over_budget_best_transfer(self, mock_ctx):
        """
        When unlimited_budget=True:
          - Top-ranked player (Palmer, £10.5m) may be over budget (£5.5m available)
          - best_transfer / best_candidate selects Palmer
          - over-budget candidate remains in candidate list
          - affordable_decision is provided for Rogers
        """
        mock_ctx.return_value = self.mock_context

        payload = {
            "pos_code": 3,
            "max_budget": 100.0,
            "actual_budget": 5.5,
            "current_squad_ids": [1],
            "transfer_out_id": 1,
            "free_transfers": 1,
            "transfers_before": 0,
            "unlimited_budget": True
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Both candidates returned
        candidate_ids = [c["id"] for c in data["candidates"]]
        self.assertIn(3, candidate_ids)
        self.assertIn(2, candidate_ids)

        # Top ranked candidate is Palmer (ID 3)
        self.assertEqual(data["candidates"][0]["id"], 3)
        self.assertFalse(data["candidates"][0]["within_budget"])

        # best_transfer must match top candidate Palmer
        self.assertIsNotNone(data["best_transfer"])
        self.assertEqual(data["best_transfer"]["id"], 3)
        self.assertEqual(data["best_transfer"]["name"], "Palmer")

        # Decision banner evaluates Palmer
        self.assertEqual(data["recommendation"], "TRANSFER")
        self.assertIn("Palmer", data["best_transfer"]["name"])

        # Affordable decision also populated for Rogers
        aff_dec = data.get("affordable_decision")
        self.assertIsNotNone(aff_dec)
        self.assertIsNotNone(aff_dec["best_transfer"])
        self.assertEqual(aff_dec["best_transfer"]["id"], 2)
        self.assertEqual(aff_dec["best_transfer"]["name"], "Rogers")

    @patch("main.get_fpl_context")
    def test_unlimited_budget_false_excludes_over_budget_candidates(self, mock_ctx):
        """
        When unlimited_budget=False:
          - Candidates above budget (£10.5m > £5.5m) are excluded from the candidate set
          - best_candidate is affordable (Rogers, £5.2m)
          - No over-budget candidate is presented in candidates
        """
        mock_ctx.return_value = self.mock_context

        payload = {
            "pos_code": 3,
            "max_budget": 5.5,
            "actual_budget": 5.5,
            "current_squad_ids": [1],
            "transfer_out_id": 1,
            "free_transfers": 1,
            "transfers_before": 0,
            "unlimited_budget": False
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Palmer must be excluded
        candidate_ids = [c["id"] for c in data["candidates"]]
        self.assertNotIn(3, candidate_ids)
        self.assertIn(2, candidate_ids)

        # Every candidate must be within budget
        for c in data["candidates"]:
            self.assertTrue(c["cost"] <= 5.5)

        # best_transfer must be Rogers
        self.assertIsNotNone(data["best_transfer"])
        self.assertEqual(data["best_transfer"]["id"], 2)
        self.assertEqual(data["best_transfer"]["name"], "Rogers")
        self.assertTrue(data["best_transfer"]["cost"] <= 5.5)

    @patch("main.get_fpl_context")
    def test_default_unlimited_budget_is_false(self, mock_ctx):
        """
        Omitting unlimited_budget must default to budget-safe behavior (unlimited_budget=False).
        """
        mock_ctx.return_value = self.mock_context

        payload = {
            "pos_code": 3,
            "max_budget": 5.5,
            "current_squad_ids": [1],
            "transfer_out_id": 1,
            "free_transfers": 1,
            "transfers_before": 0
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Palmer must be excluded by default
        candidate_ids = [c["id"] for c in data["candidates"]]
        self.assertNotIn(3, candidate_ids)
        self.assertIn(2, candidate_ids)

        # best_transfer must be the affordable player Rogers
        self.assertEqual(data["best_transfer"]["id"], 2)

    @patch("main.get_fpl_context")
    def test_strategy_consistency_between_banner_and_top_candidate(self, mock_ctx):
        """
        Strategy Decision banner and best_transfer must evaluate the EXACT candidate
        presented as #1 to the user:
          - In unconstrained mode (unlimited_budget=True): Card #1 is Palmer, decision is Palmer.
          - In constrained mode (unlimited_budget=False): Card #1 is Rogers, decision is Rogers.
          - No mismatch where Card #1 is Palmer while the banner explains Rogers.
        """
        mock_ctx.return_value = self.mock_context

        # 1. Unconstrained mode
        res_unlimited = client.post("/api/transfer-lab", json={
            "pos_code": 3,
            "max_budget": 100.0,
            "actual_budget": 5.5,
            "current_squad_ids": [1],
            "transfer_out_id": 1,
            "free_transfers": 1,
            "unlimited_budget": True
        }).json()

        top_candidate_unlimited = res_unlimited["candidates"][0]
        self.assertEqual(top_candidate_unlimited["id"], 3)  # Palmer is #1
        self.assertEqual(res_unlimited["best_transfer"]["id"], top_candidate_unlimited["id"])
        # Delta matches Palmer vs Current Mid
        expected_delta_unlimited = round(top_candidate_unlimited["xp"] - res_unlimited["current_player"]["xp"], 2)
        self.assertEqual(res_unlimited["delta"], expected_delta_unlimited)

        # 2. Constrained mode
        res_constrained = client.post("/api/transfer-lab", json={
            "pos_code": 3,
            "max_budget": 5.5,
            "actual_budget": 5.5,
            "current_squad_ids": [1],
            "transfer_out_id": 1,
            "free_transfers": 1,
            "unlimited_budget": False
        }).json()

        top_candidate_constrained = res_constrained["candidates"][0]
        self.assertEqual(top_candidate_constrained["id"], 2)  # Rogers is #1
        self.assertEqual(res_constrained["best_transfer"]["id"], top_candidate_constrained["id"])
        expected_delta_constrained = round(top_candidate_constrained["xp"] - res_constrained["current_player"]["xp"], 2)
        self.assertEqual(res_constrained["delta"], expected_delta_constrained)

    @patch("main.get_fpl_context")
    def test_budget_scenarios_does_not_leak_unconstrained_candidates(self, mock_ctx):
        """
        Simulate BudgetScenariosTab call (omitting unlimited_budget, max_budget=budget).
        Verify that over-budget candidates are never returned.
        """
        mock_ctx.return_value = self.mock_context

        payload = {
            "pos_code": 3,
            "max_budget": 5.5,
            "current_squad_ids": [1],
            "transfer_out_id": 1,
            "target_gw": 31,
            "free_transfers": 1,
            "transfers_before": 0
        }
        res = client.post("/api/transfer-lab", json=payload).json()
        candidates = res.get("candidates", [])

        # Only players with cost <= 5.5m are present
        self.assertTrue(all(c["cost"] <= 5.5 for c in candidates))
        self.assertFalse(any(c["id"] == 3 for c in candidates))

    @patch("main.get_fpl_context")
    def test_empty_affordable_pool_behavior(self, mock_ctx):
        """
        When available budget is too low (£4.0m) and NO candidate is affordable:
          - unlimited_budget=False: candidates is empty, best_transfer is None, recommendation is MONITOR
          - unlimited_budget=True: Palmer is recommended
        """
        mock_ctx.return_value = self.mock_context

        # Constrained with £4.0m budget (cheapest candidate is Rogers £5.2m)
        res_constrained = client.post("/api/transfer-lab", json={
            "pos_code": 3,
            "max_budget": 4.0,
            "actual_budget": 4.0,
            "current_squad_ids": [1],
            "transfer_out_id": 1,
            "free_transfers": 1,
            "unlimited_budget": False
        }).json()

        self.assertEqual(len(res_constrained["candidates"]), 0)
        self.assertIsNone(res_constrained["best_transfer"])
        self.assertEqual(res_constrained["recommendation"], "MONITOR")

        # Unconstrained with £4.0m budget
        res_unlimited = client.post("/api/transfer-lab", json={
            "pos_code": 3,
            "max_budget": 100.0,
            "actual_budget": 4.0,
            "current_squad_ids": [1],
            "transfer_out_id": 1,
            "free_transfers": 1,
            "unlimited_budget": True
        }).json()

        self.assertEqual(len(res_unlimited["candidates"]), 2)
        self.assertIsNotNone(res_unlimited["best_transfer"])
        self.assertEqual(res_unlimited["best_transfer"]["name"], "Palmer")


if __name__ == "__main__":
    unittest.main()
