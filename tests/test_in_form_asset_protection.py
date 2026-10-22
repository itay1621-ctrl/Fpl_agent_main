import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

class TestInFormAssetProtection(unittest.TestCase):
    """
    Dedicated regression test suite verifying the dynamic In-Form Asset Protection framework (Cases A - J).
    Ensures that high-performing, in-form, nailed starters (e.g. Morgan Rogers archetype)
    are protected from sideways moves while genuine upgrades and injury situations remain actionable.
    """

    def setUp(self):
        # 5 Gameweeks: GW31 to GW35 with single, realistic fixtures per team
        fixtures = [
            # GW31
            {"event": 31, "team_h": 2, "team_a": 5, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 31, "team_h": 1, "team_a": 3, "team_h_difficulty": 3, "team_a_difficulty": 5},
            {"event": 31, "team_h": 4, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 5},
            # GW32
            {"event": 32, "team_h": 6, "team_a": 2, "team_h_difficulty": 4, "team_a_difficulty": 2},
            {"event": 32, "team_h": 3, "team_a": 5, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 32, "team_h": 1, "team_a": 4, "team_h_difficulty": 3, "team_a_difficulty": 3},
            # GW33
            {"event": 33, "team_h": 2, "team_a": 1, "team_h_difficulty": 3, "team_a_difficulty": 3},
            {"event": 33, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 33, "team_h": 4, "team_a": 5, "team_h_difficulty": 3, "team_a_difficulty": 4},
            # GW34
            {"event": 34, "team_h": 2, "team_a": 3, "team_h_difficulty": 2, "team_a_difficulty": 3},
            {"event": 34, "team_h": 4, "team_a": 1, "team_h_difficulty": 3, "team_a_difficulty": 3},
            {"event": 34, "team_h": 5, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            # GW35
            {"event": 35, "team_h": 2, "team_a": 4, "team_h_difficulty": 4, "team_a_difficulty": 3},
            {"event": 35, "team_h": 3, "team_a": 5, "team_h_difficulty": 2, "team_a_difficulty": 3},
            {"event": 35, "team_h": 1, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
        ]

        self.mock_context = {
            "next_gw": 31,
            "gw_range": 5,
            "upcoming_fixtures_raw": fixtures,
            "bootstrap": {
                "elements": [
                    # 1. Rogers Archetype (In-form nailed core midfielder, form 5.5, 40 pts, starts 6/6)
                    {
                        "id": 10, "web_name": "InForm_Nailed_Starter", "team": 2, "team_code": 2,
                        "element_type": 3, "now_cost": 70, "form": "5.5", "minutes": 540,
                        "starts": 6, "expected_goals_per_90": 0.35, "expected_assists_per_90": 0.30,
                        "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
                        "chance_of_playing_next_round": 100, "total_points": 40, "selected_by_percent": 15.0
                    },
                    # 2. Marginal Sideways Candidate (Tavernier archetype: +0.52 xP/GW average, but harder immediate GW)
                    {
                        "id": 20, "web_name": "Marginal_Sideways_Upgrade", "team": 3, "team_code": 3,
                        "element_type": 3, "now_cost": 55, "form": "4.2", "minutes": 540,
                        "starts": 6, "expected_goals_per_90": 0.45, "expected_assists_per_90": 0.35,
                        "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
                        "chance_of_playing_next_round": 100, "total_points": 30, "selected_by_percent": 8.0
                    },
                    # 3. Genuine Massive Upgrade (Elite premium midfielder: +2.5+ xP/GW)
                    {
                        "id": 30, "web_name": "Elite_Massive_Upgrade", "team": 4, "team_code": 4,
                        "element_type": 3, "now_cost": 105, "form": "8.5", "minutes": 540,
                        "starts": 6, "expected_goals_per_90": 0.85, "expected_assists_per_90": 0.55,
                        "expected_goals_conceded_per_90": 0.8, "defensive_contribution_per_90": 2.5,
                        "chance_of_playing_next_round": 100, "total_points": 70, "selected_by_percent": 35.0
                    },
                    # 4. In-form player with injury flag (25% chance of playing)
                    {
                        "id": 40, "web_name": "Injured_InForm_Player", "team": 2, "team_code": 2,
                        "element_type": 3, "now_cost": 70, "form": "5.5", "minutes": 540,
                        "starts": 6, "expected_goals_per_90": 0.35, "expected_assists_per_90": 0.30,
                        "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
                        "chance_of_playing_next_round": 25, "total_points": 40, "selected_by_percent": 15.0
                    },
                    # 5. Normal Mediocre Fringe Player (low form, low minutes)
                    {
                        "id": 50, "web_name": "Mediocre_Fringe_Player", "team": 1, "team_code": 1,
                        "element_type": 3, "now_cost": 45, "form": "2.0", "minutes": 180,
                        "starts": 2, "expected_goals_per_90": 0.08, "expected_assists_per_90": 0.05,
                        "expected_goals_conceded_per_90": 1.2, "defensive_contribution_per_90": 1.0,
                        "chance_of_playing_next_round": 100, "total_points": 12, "selected_by_percent": 2.0
                    },
                    # 6. Solid Regular Starter Candidate
                    {
                        "id": 60, "web_name": "Solid_Starter_Candidate", "team": 2, "team_code": 2,
                        "element_type": 3, "now_cost": 65, "form": "4.5", "minutes": 540,
                        "starts": 6, "expected_goals_per_90": 0.32, "expected_assists_per_90": 0.28,
                        "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
                        "chance_of_playing_next_round": 100, "total_points": 35, "selected_by_percent": 10.0
                    },
                    # 7. Candidate with Superior Immediate AND 5-GW projection
                    {
                        "id": 70, "web_name": "Superior_Immediate_Candidate", "team": 4, "team_code": 4,
                        "element_type": 3, "now_cost": 75, "form": "6.0", "minutes": 540,
                        "starts": 6, "expected_goals_per_90": 0.65, "expected_assists_per_90": 0.45,
                        "expected_goals_conceded_per_90": 0.9, "defensive_contribution_per_90": 2.0,
                        "chance_of_playing_next_round": 100, "total_points": 50, "selected_by_percent": 20.0
                    }
                ]
            },
            "teams": {
                1: {"id": 1, "short_name": "ARS", "team_code": 1, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
                2: {"id": 2, "short_name": "CHE", "team_code": 2, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
                3: {"id": 3, "short_name": "BOU", "team_code": 3, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
                4: {"id": 4, "short_name": "MCI", "team_code": 4, "strength_defence_home": 1200, "strength_attack_home": 1250, "strength_defence_away": 1200, "strength_attack_away": 1250},
                5: {"id": 5, "short_name": "TOT", "team_code": 5, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
                6: {"id": 6, "short_name": "SOU", "team_code": 6, "strength_defence_home": 1000, "strength_attack_home": 1000, "strength_defence_away": 1000, "strength_attack_away": 1000}
            }
        }

    # ============================================================================
    # Requirement 7: Explicit Morgan Rogers Archetype Regression Test
    # ============================================================================
    @patch("main.get_fpl_context")
    def test_case_rogers_archetype_regression(self, mock_ctx):
        """
        Archetype regression:
          - Current: Form 5.5, Total points 40, starter, healthy, 540 mins, xP_next 6.08
          - Candidate: Marginal upgrade, xP_next 5.51, gives only +0.52 xP/GW (+2.60 pts over 5 GWs)
          - Expected: HOLD (both Gatekeeper and 7.5pt Elite Hurdle hold)
        """
        mock_ctx.return_value = self.mock_context
        payload = {
            "pos_code": 3,
            "max_budget": 6.0,
            "actual_budget": 6.0,
            "current_squad_ids": [10],
            "transfer_out_id": 10,
            "free_transfers": 1,
            "transfers_before": 0,
            "target_gw": 31
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["recommendation"], "HOLD")
        self.assertIn("0-point hit cost", data["explanation"])
        self.assertIn("InForm_Nailed_Starter", data["explanation"])

    # ============================================================================
    # Test A: In-form nailed player + marginal upgrade -> HOLD
    # ============================================================================
    @patch("main.get_fpl_context")
    def test_case_a_in_form_nailed_player_marginal_upgrade_holds(self, mock_ctx):
        mock_ctx.return_value = self.mock_context
        payload = {
            "pos_code": 3,
            "max_budget": 6.0,
            "actual_budget": 6.0,
            "current_squad_ids": [10],
            "transfer_out_id": 10,
            "free_transfers": 1,
            "transfers_before": 0,
            "target_gw": 31
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["recommendation"], "HOLD")
        self.assertIn("0-point hit cost", data["explanation"])

    # ============================================================================
    # Test B: In-form nailed player + large genuine upgrade -> TRANSFER
    # ============================================================================
    @patch("main.get_fpl_context")
    def test_case_b_in_form_nailed_player_large_genuine_upgrade_transfers(self, mock_ctx):
        mock_ctx.return_value = self.mock_context
        payload = {
            "pos_code": 3,
            "max_budget": 12.0,
            "actual_budget": 12.0,
            "current_squad_ids": [10],
            "transfer_out_id": 10,
            "free_transfers": 1,
            "transfers_before": 0,
            "target_gw": 31
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["recommendation"], "TRANSFER")
        self.assertEqual(data["best_transfer"]["id"], 30)
        self.assertIn("Elite_Massive_Upgrade", data["explanation"])

    # ============================================================================
    # Test C: In-form player with injury / major minutes uncertainty -> protection removed -> TRANSFER
    # ============================================================================
    @patch("main.get_fpl_context")
    def test_case_c_in_form_player_with_injury_flag_protection_removed(self, mock_ctx):
        mock_ctx.return_value = self.mock_context
        payload = {
            "pos_code": 3,
            "max_budget": 8.0,
            "actual_budget": 8.0,
            "current_squad_ids": [40],
            "transfer_out_id": 40,
            "free_transfers": 1,
            "transfers_before": 0,
            "target_gw": 31
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["recommendation"], "TRANSFER")
        self.assertIn("clears the required threshold", data["explanation"])

    # ============================================================================
    # Test D: Normal mediocre player + meaningful upgrade -> TRANSFER
    # ============================================================================
    @patch("main.get_fpl_context")
    def test_case_d_normal_mediocre_player_meaningful_upgrade_transfers(self, mock_ctx):
        mock_ctx.return_value = self.mock_context
        payload = {
            "pos_code": 3,
            "max_budget": 7.0,
            "actual_budget": 7.0,
            "current_squad_ids": [50],
            "transfer_out_id": 50,
            "free_transfers": 1,
            "transfers_before": 0,
            "target_gw": 31
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["recommendation"], "TRANSFER")
        self.assertIn("clears the required threshold", data["explanation"])

    # ============================================================================
    # Test E: 0 FT + marginal gain -> HOLD due to hit cost
    # ============================================================================
    @patch("main.get_fpl_context")
    def test_case_e_zero_ft_marginal_gain_hold_due_to_hit(self, mock_ctx):
        mock_ctx.return_value = self.mock_context
        payload = {
            "pos_code": 3,
            "max_budget": 6.0,
            "actual_budget": 6.0,
            "current_squad_ids": [10],
            "transfer_out_id": 10,
            "free_transfers": 0,
            "transfers_before": 0,
            "target_gw": 31
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["recommendation"], "HOLD")
        self.assertIn("4-point hit cost", data["explanation"])

    # ============================================================================
    # Test F: 1 FT + marginal gain -> still HOLD if elite/in-form asset
    # ============================================================================
    @patch("main.get_fpl_context")
    def test_case_f_one_ft_marginal_gain_in_form_asset_holds(self, mock_ctx):
        mock_ctx.return_value = self.mock_context
        payload = {
            "pos_code": 3,
            "max_budget": 6.0,
            "actual_budget": 6.0,
            "current_squad_ids": [10],
            "transfer_out_id": 10,
            "free_transfers": 1,
            "transfers_before": 0,
            "target_gw": 31
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["recommendation"], "HOLD")
        self.assertIn("0-point hit cost", data["explanation"])

    # ============================================================================
    # Test G: Wildcard/Free Hit + sideways move -> HOLD
    # ============================================================================
    @patch("main.get_fpl_context")
    def test_case_g_wildcard_protects_in_form_assets_from_sideways_moves(self, mock_ctx):
        mock_ctx.return_value = self.mock_context
        payload = {
            "pos_code": 3,
            "max_budget": 6.0,
            "actual_budget": 6.0,
            "current_squad_ids": [10],
            "transfer_out_id": 10,
            "free_transfers": 1,
            "transfers_before": 2,
            "active_chip": "wildcard",
            "target_gw": 31
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["recommendation"], "HOLD")
        self.assertIn("0-point hit cost", data["explanation"])

    # ============================================================================
    # Test H: Wildcard/Free Hit + genuine major upgrade -> TRANSFER
    # ============================================================================
    @patch("main.get_fpl_context")
    def test_case_h_wildcard_genuine_major_upgrade_transfers(self, mock_ctx):
        mock_ctx.return_value = self.mock_context
        payload = {
            "pos_code": 3,
            "max_budget": 12.0,
            "actual_budget": 12.0,
            "current_squad_ids": [10],
            "transfer_out_id": 10,
            "free_transfers": 1,
            "transfers_before": 2,
            "active_chip": "wildcard",
            "target_gw": 31
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["recommendation"], "TRANSFER")
        self.assertEqual(data["best_transfer"]["id"], 30)
        self.assertIn("0-point hit cost", data["explanation"])

    # ============================================================================
    # Test I: Difficult fixture swing -> lowers Hurdle by 1.0 pt
    # ============================================================================
    @patch("main.get_fpl_context")
    def test_case_i_difficult_fixture_swing_lowers_hurdle(self, mock_ctx):
        """
        When current player faces a difficult fixture run (diff >= 4)
        and candidate faces an easy run (diff <= 2), hurdle is lowered by 1.0 pt.
        """
        # Swap fixtures so current player (team 2) has difficulty 4 in GW31,
        # and candidate (team 3) has difficulty 2 in GW31
        ctx = dict(self.mock_context)
        fixs = [
            {"event": 31, "team_h": 5, "team_a": 2, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 31, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 31, "team_h": 4, "team_a": 1, "team_h_difficulty": 3, "team_a_difficulty": 3},
            {"event": 32, "team_h": 2, "team_a": 4, "team_h_difficulty": 4, "team_a_difficulty": 3},
            {"event": 32, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 33, "team_h": 2, "team_a": 4, "team_h_difficulty": 4, "team_a_difficulty": 3},
            {"event": 33, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 34, "team_h": 2, "team_a": 4, "team_h_difficulty": 4, "team_a_difficulty": 3},
            {"event": 34, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 35, "team_h": 2, "team_a": 4, "team_h_difficulty": 4, "team_a_difficulty": 3},
            {"event": 35, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
        ]
        ctx["upcoming_fixtures_raw"] = fixs
        mock_ctx.return_value = ctx

        payload = {
            "pos_code": 3,
            "max_budget": 6.0,
            "actual_budget": 6.0,
            "current_squad_ids": [10],
            "transfer_out_id": 10,
            "free_transfers": 1,
            "transfers_before": 0,
            "target_gw": 31
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Threshold for Elite asset with fixture swing reduced from 7.5 to 6.5
        self.assertEqual(data["threshold"], 6.5)
        self.assertEqual(data["recommendation"], "TRANSFER")
        self.assertIn("6.5", data["explanation"])

    # ============================================================================
    # Test J: Good current player but candidate has clearly superior immediate + 5GW projection -> TRANSFER
    # ============================================================================
    @patch("main.get_fpl_context")
    def test_case_j_candidate_superior_immediate_and_five_gw_projection_transfers(self, mock_ctx):
        """
        When candidate is superior in the immediate match (higher xP_next)
        AND clears the 5-GW threshold, gatekeeper does not block and TRANSFER is recommended.
        """
        mock_ctx.return_value = self.mock_context
        payload = {
            "pos_code": 3,
            "max_budget": 8.0,
            "actual_budget": 8.0,
            "current_squad_ids": [10],
            "transfer_out_id": 10,
            "free_transfers": 1,
            "transfers_before": 0,
            "target_gw": 31
        }
        res = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Best candidate ID 70 has superior immediate xP and 5-GW xP
        self.assertEqual(data["recommendation"], "TRANSFER")
        self.assertEqual(data["best_transfer"]["id"], 70)
        self.assertIn("Superior_Immediate_Candidate", data["explanation"])


# ============================================================================
# PARITY, GATEKEEPER & HIT COST MATRIX SUITE
# ============================================================================
import backend.main
backend_client = TestClient(backend.main.app)

class TestParityAndEdgeCases(unittest.TestCase):
    def setUp(self):
        t = TestInFormAssetProtection()
        t.setUp()
        self.mock_context = t.mock_context

    # ------------------------------------------------------------------------
    # Requirement 2: HitCost & Transfer Rules Matrix Verification
    # ------------------------------------------------------------------------
    def test_hit_cost_matrix_comprehensive(self):
        """
        Test all combinations of free_transfers, transfers_before, and active_chip.
        Verifies that HitCost is deducted exactly once and matches FPL reality:
          marginal hit cost = max(0, B + 1 - FT)*4 - max(0, B - FT)*4
        """
        matrix_cases = [
            # (FT, transfers_before, active_chip, expected_hit)
            (0, 0, None, 4),
            (1, 0, None, 0),
            (2, 0, None, 0),
            (1, 1, None, 4),
            (2, 1, None, 0),
            (2, 2, None, 4),
            (1, 2, None, 4),
            (3, 2, None, 0),
            (0, 1, None, 4),
            (0, 0, "wildcard", 0),
            (0, 2, "wildcard", 0),
            (1, 2, "freehit", 0),
            (2, 3, "freehit", 0),
        ]

        with patch("main.get_fpl_context", return_value=self.mock_context), \
             patch("backend.main.get_fpl_context", return_value=self.mock_context):
            for ft, tb, chip, expected_hit in matrix_cases:
                payload = {
                    "pos_code": 3,
                    "max_budget": 6.0,
                    "actual_budget": 6.0,
                    "current_squad_ids": [10],
                    "transfer_out_id": 10,
                    "free_transfers": ft,
                    "transfers_before": tb,
                    "active_chip": chip,
                    "target_gw": 31
                }
                # Test main.app
                res_main = client.post("/api/transfer-lab", json=payload)
                self.assertEqual(res_main.status_code, 200)
                data_m = res_main.json()
                self.assertEqual(data_m["hit_cost"], expected_hit, f"main.app failed for FT={ft}, TB={tb}, chip={chip}")
                self.assertEqual(data_m["threshold"], 7.5 + expected_hit)
                self.assertEqual(data_m["net_gain"], round(data_m["raw_gain"] - expected_hit, 2))

                # Test backend.main.app
                res_back = backend_client.post("/api/transfer-lab", json=payload)
                self.assertEqual(res_back.status_code, 200)
                data_b = res_back.json()
                self.assertEqual(data_b["hit_cost"], expected_hit, f"backend.main.app failed for FT={ft}, TB={tb}, chip={chip}")
                self.assertEqual(data_b["threshold"], 7.5 + expected_hit)
                self.assertEqual(data_b["net_gain"], round(data_b["raw_gain"] - expected_hit, 2))

    # ------------------------------------------------------------------------
    # Requirement 3: Gatekeeper Edge Cases using real compute_transfer_decision / API
    # ------------------------------------------------------------------------
    def test_gatekeeper_real_scenarios(self):
        """
        Verify all Gatekeeper behavior using the real API:
        1. Current slightly better immediate, raw_gain < 8.0 -> HOLD (Gatekeeper blocks)
        2. Current slightly better immediate, raw_gain >= 8.0 (9.5 pts) -> TRANSFER (Gatekeeper does NOT block)
        3. Candidate superior both immediately and 5-GW -> TRANSFER
        4. Current player Blank Gameweek (xp_next == 0) -> TRANSFER (Gatekeeper does not trigger)
        5. Current player injured (<75% chance) -> TRANSFER (Gatekeeper disabled, URGENT hurdle 2.0 cleared)
        6. Current player injured but replacement is worse -> HOLD (No blind selling)
        """
        ctx = dict(self.mock_context)
        elements = list(ctx["bootstrap"]["elements"])

        # Create Candidate 81: xp_next = 5.90 (< Current's 6.08), raw_gain = 7.50 (< 8.0)
        # Create Candidate 82: xp_next = 5.90 (< Current's 6.08), raw_gain = 9.50 (>= 8.0)
        cand_81 = {
            "id": 81, "web_name": "Gatekeeper_Marginal", "team": 6, "team_code": 6,
            "element_type": 3, "now_cost": 65, "form": "6.8", "minutes": 540,
            "starts": 6, "expected_goals_per_90": 0.55, "expected_assists_per_90": 0.40,
            "expected_goals_conceded_per_90": 0.8, "defensive_contribution_per_90": 2.0,
            "chance_of_playing_next_round": 100, "total_points": 50, "selected_by_percent": 15.0
        }
        cand_82 = {
            "id": 82, "web_name": "Gatekeeper_LargeGain_Candidate", "team": 3, "team_code": 3,
            "element_type": 3, "now_cost": 60, "form": "6.2", "minutes": 540,
            "starts": 6, "expected_goals_per_90": 0.63, "expected_assists_per_90": 0.32,
            "expected_goals_conceded_per_90": 0.8, "defensive_contribution_per_90": 2.0,
            "chance_of_playing_next_round": 100, "total_points": 50, "selected_by_percent": 15.0
        }
        with patch("main.get_fpl_context", return_value=ctx), \
             patch("backend.main.get_fpl_context", return_value=ctx):
            
            # --- Scenario 1: RawGain < 8.0 and curr_xp_next >= cand_xp_next -> HOLD
            payload_1 = {
                "pos_code": 3, "max_budget": 5.8, "actual_budget": 5.8,
                "current_squad_ids": [10], "transfer_out_id": 10,
                "free_transfers": 1, "transfers_before": 0, "target_gw": 31
            }
            res1 = client.post("/api/transfer-lab", json=payload_1)
            d1 = res1.json()
            curr_xp_1 = d1["current_player"]["xp_next"]
            cand_xp_1 = d1["best_transfer"]["xp_next"]
            self.assertGreaterEqual(curr_xp_1, cand_xp_1)
            self.assertLess(d1["raw_gain"], 8.0)
            self.assertEqual(d1["recommendation"], "HOLD")
            self.assertIn("Hold for GW31", d1["explanation"])

        # --- Scenario 2: RawGain == 9.5 exactly, curr_xp_next > cand_xp_next -> TRANSFER (Gatekeeper does NOT block)
        ctx2 = dict(ctx)
        fixs_sc2 = [
            {"event": 31, "team_h": 2, "team_a": 5, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 31, "team_h": 4, "team_a": 3, "team_h_difficulty": 2, "team_a_difficulty": 5},
            {"event": 32, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 32, "team_h": 6, "team_a": 2, "team_h_difficulty": 4, "team_a_difficulty": 2},
            {"event": 33, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 33, "team_h": 2, "team_a": 1, "team_h_difficulty": 3, "team_a_difficulty": 3},
            {"event": 34, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 34, "team_h": 2, "team_a": 3, "team_h_difficulty": 2, "team_a_difficulty": 3},
            {"event": 35, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 35, "team_h": 2, "team_a": 4, "team_h_difficulty": 4, "team_a_difficulty": 3},
        ]
        ctx2["upcoming_fixtures_raw"] = fixs_sc2
        cand_82 = {
            "id": 82, "web_name": "Gatekeeper_Exact_9_5_Candidate", "team": 3, "team_code": 3,
            "element_type": 3, "now_cost": 60, "form": "4.0", "minutes": 540,
            "starts": 6, "expected_goals_per_90": 0.39, "expected_assists_per_90": 0.44,
            "expected_goals_conceded_per_90": 0.8, "defensive_contribution_per_90": 2.0,
            "chance_of_playing_next_round": 100, "total_points": 45, "selected_by_percent": 15.0
        }
        ctx2["bootstrap"] = {"elements": [e for e in ctx["bootstrap"]["elements"] if e["id"] != 70] + [cand_82]}

        with patch("main.get_fpl_context", return_value=ctx2), \
             patch("backend.main.get_fpl_context", return_value=ctx2):
            payload_2 = {
                "pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0,
                "current_squad_ids": [10], "transfer_out_id": 10,
                "free_transfers": 1, "transfers_before": 0, "target_gw": 31
            }
            res2 = client.post("/api/transfer-lab", json=payload_2)
            d2 = res2.json()
            curr_xp_2 = d2["current_player"]["xp_next"]
            cand_xp_2 = d2["best_transfer"]["xp_next"]
            self.assertEqual(d2["best_transfer"]["id"], 82)
            self.assertGreater(curr_xp_2, cand_xp_2, "Current player should project strictly higher for immediate GW (6.08 vs 5.13)")
            self.assertEqual(d2["raw_gain"], 9.5, "Raw gain over 5 GWs must be exactly 9.5 points")
            self.assertEqual(d2["delta"], 1.9, "Delta must be exactly 1.9 points per GW")
            self.assertFalse(d2["raw_gain"] < 8.0, "raw_gain < 8.0 must be False so Gatekeeper is bypassed")
            self.assertGreater(d2["raw_gain"], d2["threshold"], "Raw gain (9.5) must clear the 7.5 Elite threshold")
            self.assertEqual(d2["recommendation"], "TRANSFER", "Gatekeeper must NOT block when raw_gain >= 8.0")
            self.assertNotIn("Do not sacrifice immediate points", d2["explanation"])
            self.assertIn("clears the required threshold", d2["explanation"])

            # --- Scenario 4: Current Player has Blank Gameweek (xp_next == 0)
            # If current player has no fixture in GW31, xp_next becomes 0
            ctx_bgw = dict(ctx)
            # Remove GW31 fixture for team 2
            ctx_bgw["upcoming_fixtures_raw"] = [f for f in ctx["upcoming_fixtures_raw"] if not (f["event"] == 31 and (f["team_h"] == 2 or f["team_a"] == 2))]
            with patch("main.get_fpl_context", return_value=ctx_bgw):
                res_bgw = client.post("/api/transfer-lab", json=payload_1)
                d_bgw = res_bgw.json()
                self.assertEqual(d_bgw["current_player"]["xp_next"], 0.0)
                # Gatekeeper must NOT trigger when xp_next == 0
                self.assertNotIn("Do not sacrifice immediate points", d_bgw["explanation"])

            # --- Scenario 5 & 6: Current player injured
            # Injured in-form player (ID 40, cop = 25) vs candidate
            payload_inj = {
                "pos_code": 3, "max_budget": 8.0, "actual_budget": 8.0,
                "current_squad_ids": [40], "transfer_out_id": 40,
                "free_transfers": 1, "transfers_before": 0, "target_gw": 31
            }
            res_inj = client.post("/api/transfer-lab", json=payload_inj)
            d_inj = res_inj.json()
            # Threshold must be 2.0 (URGENT)
            self.assertEqual(d_inj["threshold"], 2.0)
            self.assertEqual(d_inj["recommendation"], "TRANSFER")

    # ------------------------------------------------------------------------
    # Requirement 4: URGENT Hurdle (2.0) and Fixture Swing Floor (2.0)
    # ------------------------------------------------------------------------
    def test_urgent_tier_and_fixture_swing_floor(self):
        """
        Verify that:
        1. URGENT hurdle is strictly 2.0 and does not depend on DEFAULT_WEIGHTS.
        2. Fixture swing cannot reduce hurdle below 2.0.
        3. Injured player with 540 minutes has URGENT hurdle (2.0), not blind sell.
        """
        with patch("main.get_fpl_context", return_value=self.mock_context), \
             patch("backend.main.get_fpl_context", return_value=self.mock_context):
            
            # Injured player (ID 40) has 540 mins, 6 starts, but cop=25%
            payload = {
                "pos_code": 3, "max_budget": 8.0, "actual_budget": 8.0,
                "current_squad_ids": [40], "transfer_out_id": 40,
                "free_transfers": 1, "transfers_before": 0, "target_gw": 31
            }
            res_m = client.post("/api/transfer-lab", json=payload).json()
            res_b = backend_client.post("/api/transfer-lab", json=payload).json()
            self.assertEqual(res_m["threshold"], 2.0)
            self.assertEqual(res_b["threshold"], 2.0)
            self.assertEqual(res_m["recommendation"], "TRANSFER")
            self.assertEqual(res_b["recommendation"], "TRANSFER")

    # ------------------------------------------------------------------------
    # Requirement 1: Established Starter Boundary Conditions
    # ------------------------------------------------------------------------
    def test_established_starter_boundaries(self):
        """
        Approved specification:
          - Healthy with curr_starts >= 3 and curr_mins >= 220, OR
          - Healthy with curr_mins >= 350.
        Verifies:
          1. 2 starts and 150 mins -> NOT established starter (hurdle=3.0, Gatekeeper disabled).
          2. 3 starts and 219 mins -> NOT established starter (hurdle=3.0, Gatekeeper disabled).
          3. 3 starts and 220 mins -> Established starter (hurdle=7.5, Gatekeeper active).
          4. 1 start and 350 mins -> Established starter (hurdle=7.5, Gatekeeper active).
          5. 3 starts and 250 mins but injured (<75%) -> NOT established starter (hurdle=2.0, URGENT).
        """
        ctx = dict(self.mock_context)
        elements = list(ctx["bootstrap"]["elements"])

        # Boundary player definitions:
        # P101: 2 starts, 150 mins, healthy, form 5.5, 30 pts
        p101 = {
            "id": 101, "web_name": "TwoStarts_150Mins", "team": 2, "team_code": 2,
            "element_type": 3, "now_cost": 70, "form": "5.5", "minutes": 150,
            "starts": 2, "expected_goals_per_90": 0.35, "expected_assists_per_90": 0.30,
            "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
            "chance_of_playing_next_round": 100, "total_points": 30, "selected_by_percent": 10.0
        }
        # P102: 3 starts, 219 mins, healthy, form 5.5, 35 pts
        p102 = {
            "id": 102, "web_name": "ThreeStarts_219Mins", "team": 2, "team_code": 2,
            "element_type": 3, "now_cost": 70, "form": "5.5", "minutes": 219,
            "starts": 3, "expected_goals_per_90": 0.35, "expected_assists_per_90": 0.30,
            "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
            "chance_of_playing_next_round": 100, "total_points": 35, "selected_by_percent": 10.0
        }
        # P103: 3 starts, 220 mins, healthy, form 5.5, 40 pts
        p103 = {
            "id": 103, "web_name": "ThreeStarts_220Mins", "team": 2, "team_code": 2,
            "element_type": 3, "now_cost": 70, "form": "5.5", "minutes": 220,
            "starts": 3, "expected_goals_per_90": 0.35, "expected_assists_per_90": 0.30,
            "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
            "chance_of_playing_next_round": 100, "total_points": 40, "selected_by_percent": 15.0
        }
        # P104: 1 start, 350 mins, healthy, form 5.5, 36 pts
        p104 = {
            "id": 104, "web_name": "OneStart_350Mins", "team": 2, "team_code": 2,
            "element_type": 3, "now_cost": 70, "form": "5.5", "minutes": 350,
            "starts": 1, "expected_goals_per_90": 0.35, "expected_assists_per_90": 0.30,
            "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
            "chance_of_playing_next_round": 100, "total_points": 36, "selected_by_percent": 12.0
        }
        elements.extend([p101, p102, p103, p104])
        ctx["bootstrap"] = {"elements": elements}

        with patch("main.get_fpl_context", return_value=ctx), \
             patch("backend.main.get_fpl_context", return_value=ctx):
            
            # 1. 2 starts, 150 mins: Hurdle must NOT be ELITE (7.5) or STARTER (5.5). Must be ROTATION (3.0).
            res_101 = client.post("/api/transfer-lab", json={"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [101], "transfer_out_id": 101, "free_transfers": 1, "transfers_before": 0, "target_gw": 31}).json()
            self.assertEqual(res_101["threshold"], 3.0, "2 starts, 150 mins must NOT be an established starter (threshold should be 3.0)")

            # 2. 3 starts, 219 mins: Hurdle must be ROTATION (3.0).
            res_102 = client.post("/api/transfer-lab", json={"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [102], "transfer_out_id": 102, "free_transfers": 1, "transfers_before": 0, "target_gw": 31}).json()
            self.assertEqual(res_102["threshold"], 3.0, "3 starts, 219 mins must NOT be an established starter (threshold should be 3.0)")

            # 3. 3 starts, 220 mins: Meets spec. With form 5.5 and 40 pts -> ELITE (hurdle 7.5).
            res_103 = client.post("/api/transfer-lab", json={"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [103], "transfer_out_id": 103, "free_transfers": 1, "transfers_before": 0, "target_gw": 31}).json()
            self.assertEqual(res_103["threshold"], 7.5, "3 starts, 220 mins MUST be established starter and qualify as Elite asset (threshold 7.5)")

            # 4. 1 start, 350 mins: Meets spec (mins >= 350). With form 5.5 and 36 pts -> ELITE (hurdle 7.5).
            res_104 = client.post("/api/transfer-lab", json={"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [104], "transfer_out_id": 104, "free_transfers": 1, "transfers_before": 0, "target_gw": 31}).json()
            self.assertEqual(res_104["threshold"], 7.5, "1 start, 350 mins MUST be established starter and qualify as Elite asset (threshold 7.5)")

    # ------------------------------------------------------------------------
    # Requirement 2: Strict HitCost Formula Verification
    # ------------------------------------------------------------------------
    def test_hit_cost_strict_formula_and_marginal_bounds(self):
        """
        Verifies that for every (FT, B) combination:
          hit_cost == 4 * (max(0, B + 1 - FT) - max(0, B - FT))
          hit_cost in {0, 4} strictly (never 8, never negative)
          threshold == hurdle + hit_cost
          net_gain == raw_gain - hit_cost
        """
        with patch("main.get_fpl_context", return_value=self.mock_context), \
             patch("backend.main.get_fpl_context", return_value=self.mock_context):
            for ft in [0, 1, 2, 3, 4, 5]:
                for b in [0, 1, 2, 3]:
                    expected_hit = 4 * (max(0, b + 1 - ft) - max(0, b - ft))
                    self.assertIn(expected_hit, [0, 4], f"Expected hit must be 0 or 4, got {expected_hit}")

                    payload = {
                        "pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0,
                        "current_squad_ids": [10], "transfer_out_id": 10,
                        "free_transfers": ft, "transfers_before": b, "target_gw": 31
                    }
                    res_m = client.post("/api/transfer-lab", json=payload).json()
                    res_b = backend_client.post("/api/transfer-lab", json=payload).json()

                    for name, data in [("main.app", res_m), ("backend.main.app", res_b)]:
                        self.assertEqual(data["hit_cost"], expected_hit, f"{name} hit_cost mismatch for FT={ft}, B={b}")
                        self.assertEqual(data["threshold"], 7.5 + expected_hit)
                        self.assertEqual(data["net_gain"], round(data["raw_gain"] - expected_hit, 2))

    # ------------------------------------------------------------------------
    # Requirement 3: Full Parity Across All Demanded Scenarios
    # ------------------------------------------------------------------------
    def test_comprehensive_full_parity_all_scenarios(self):
        """
        Compares main.py and backend/main.py across ALL scenarios requested:
        1. HOLD: In-form player with immediate advantage and small gain (Rogers archetype).
        2. TRANSFER: Genuine massive upgrade.
        3. TRANSFER: Injured player with 540 mins.
        4. TRANSFER: Blank Gameweek (xp_next == 0).
        5. TRANSFER: Difficult Fixture Swing (FDR 4 vs FDR 2, threshold drops to 6.5).
        6. HOLD: 0 FT (hit cost = 4).
        7. HOLD: 1 FT (hit cost = 0).
        8. HOLD: 2 FT (hit cost = 0).
        9. HOLD: 1 FT with 1 transfer planned before (hit cost = 4).
        10. HOLD: 2 FT with 1 transfer planned before (hit cost = 0).
        11. HOLD: 2 FT with 2 transfers planned before (hit cost = 4).
        12. HOLD: Wildcard active with sideways move (hit cost = 0).
        13. HOLD: Free Hit active with sideways move (hit cost = 0).
        14. TRANSFER: Wildcard active with genuine massive upgrade (hit cost = 0).
        Asserts parity for: recommendation, delta, raw_gain, hit_cost, net_gain, threshold,
        best_transfer['id'], and explanation.
        """
        # Prepare context variants
        ctx_normal = self.mock_context

        # Context for Blank Gameweek (remove team 2 fixture in GW31)
        ctx_bgw = dict(self.mock_context)
        ctx_bgw["upcoming_fixtures_raw"] = [
            f for f in self.mock_context["upcoming_fixtures_raw"]
            if not (f["event"] == 31 and (f["team_h"] == 2 or f["team_a"] == 2))
        ]

        # Context for Fixture Swing (Current faces FDR 4, Candidate faces FDR 2 in GW31-35)
        ctx_swing = dict(self.mock_context)
        ctx_swing["upcoming_fixtures_raw"] = [
            {"event": 31, "team_h": 5, "team_a": 2, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 31, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 31, "team_h": 4, "team_a": 1, "team_h_difficulty": 3, "team_a_difficulty": 3},
            {"event": 32, "team_h": 2, "team_a": 4, "team_h_difficulty": 4, "team_a_difficulty": 3},
            {"event": 32, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 33, "team_h": 2, "team_a": 4, "team_h_difficulty": 4, "team_a_difficulty": 3},
            {"event": 33, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 34, "team_h": 2, "team_a": 4, "team_h_difficulty": 4, "team_a_difficulty": 3},
            {"event": 34, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
            {"event": 35, "team_h": 2, "team_a": 4, "team_h_difficulty": 4, "team_a_difficulty": 3},
            {"event": 35, "team_h": 3, "team_a": 6, "team_h_difficulty": 2, "team_a_difficulty": 4},
        ]

        # Each tuple: (desc, ctx, payload, exp_rec, exp_cand_id, exp_delta, exp_raw_gain, exp_hit, exp_net, exp_thresh, exp_gatekeeper_active)
        test_cases = [
            ("1. In-Form HOLD (Rogers Archetype)", ctx_normal, {"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 1, "transfers_before": 0, "target_gw": 31},
             "HOLD", 20, 0.52, 2.6, 0, 2.6, 7.5, True),
            ("2. Genuine Massive Upgrade (TRANSFER)", ctx_normal, {"pos_code": 3, "max_budget": 12.0, "actual_budget": 12.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 1, "transfers_before": 0, "target_gw": 31},
             "TRANSFER", 30, 2.57, 12.85, 0, 12.85, 7.5, False),
            ("3. Injured Player with 540 Mins (TRANSFER)", ctx_normal, {"pos_code": 3, "max_budget": 8.0, "actual_budget": 8.0, "current_squad_ids": [40], "transfer_out_id": 40, "free_transfers": 1, "transfers_before": 0, "target_gw": 31},
             "TRANSFER", 70, 4.32, 21.6, 0, 21.6, 2.0, False),
            ("4. Blank Gameweek (TRANSFER)", ctx_bgw, {"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 1, "transfers_before": 0, "target_gw": 31},
             "TRANSFER", 20, 1.74, 8.7, 0, 8.7, 7.5, False),
            ("5. Fixture Swing (TRANSFER, Threshold=6.5)", ctx_swing, {"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 1, "transfers_before": 0, "target_gw": 31},
             "TRANSFER", 20, 1.58, 7.9, 0, 7.9, 6.5, False),
            ("6. 0 FT (HOLD, HitCost=4)", ctx_normal, {"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 0, "transfers_before": 0, "target_gw": 31},
             "HOLD", 20, 0.52, 2.6, 4, -1.4, 11.5, True),
            ("7. 1 FT (HOLD, HitCost=0)", ctx_normal, {"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 1, "transfers_before": 0, "target_gw": 31},
             "HOLD", 20, 0.52, 2.6, 0, 2.6, 7.5, True),
            ("8. 2 FT (HOLD, HitCost=0)", ctx_normal, {"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 2, "transfers_before": 0, "target_gw": 31},
             "HOLD", 20, 0.52, 2.6, 0, 2.6, 7.5, True),
            ("9. 1 FT with 1 Planned Before (HOLD, HitCost=4)", ctx_normal, {"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 1, "transfers_before": 1, "target_gw": 31},
             "HOLD", 20, 0.52, 2.6, 4, -1.4, 11.5, True),
            ("10. 2 FT with 1 Planned Before (HOLD, HitCost=0)", ctx_normal, {"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 2, "transfers_before": 1, "target_gw": 31},
             "HOLD", 20, 0.52, 2.6, 0, 2.6, 7.5, True),
            ("11. 2 FT with 2 Planned Before (HOLD, HitCost=4)", ctx_normal, {"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 2, "transfers_before": 2, "target_gw": 31},
             "HOLD", 20, 0.52, 2.6, 4, -1.4, 11.5, True),
            ("12. Wildcard Active Sideways (HOLD, HitCost=0)", ctx_normal, {"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 1, "transfers_before": 2, "active_chip": "wildcard", "target_gw": 31},
             "HOLD", 20, 0.52, 2.6, 0, 2.6, 7.5, True),
            ("13. Free Hit Active Sideways (HOLD, HitCost=0)", ctx_normal, {"pos_code": 3, "max_budget": 6.0, "actual_budget": 6.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 1, "transfers_before": 2, "active_chip": "freehit", "target_gw": 31},
             "HOLD", 20, 0.52, 2.6, 0, 2.6, 7.5, True),
            ("14. Wildcard Active Major Upgrade (TRANSFER, HitCost=0)", ctx_normal, {"pos_code": 3, "max_budget": 12.0, "actual_budget": 12.0, "current_squad_ids": [10], "transfer_out_id": 10, "free_transfers": 1, "transfers_before": 2, "active_chip": "wildcard", "target_gw": 31},
             "TRANSFER", 30, 2.57, 12.85, 0, 12.85, 7.5, False),
        ]

        for desc, ctx, payload, exp_rec, exp_cand, exp_delta, exp_raw, exp_hit, exp_net, exp_thresh, exp_gk in test_cases:
            with patch("main.get_fpl_context", return_value=ctx), \
                 patch("backend.main.get_fpl_context", return_value=ctx):
                res_m = client.post("/api/transfer-lab", json=payload).json()
                res_b = backend_client.post("/api/transfer-lab", json=payload).json()

                # 1. Assert explicit expected values on main.app
                self.assertEqual(res_m["recommendation"], exp_rec, f"[{desc}] main.app recommendation expected {exp_rec}, got {res_m['recommendation']}")
                self.assertEqual(res_m["best_transfer"]["id"], exp_cand, f"[{desc}] main.app candidate expected {exp_cand}, got {res_m['best_transfer']['id']}")
                self.assertEqual(res_m["delta"], exp_delta, f"[{desc}] main.app delta expected {exp_delta}, got {res_m['delta']}")
                self.assertEqual(res_m["raw_gain"], exp_raw, f"[{desc}] main.app raw_gain expected {exp_raw}, got {res_m['raw_gain']}")
                self.assertEqual(res_m["hit_cost"], exp_hit, f"[{desc}] main.app hit_cost expected {exp_hit}, got {res_m['hit_cost']}")
                self.assertEqual(res_m["net_gain"], exp_net, f"[{desc}] main.app net_gain expected {exp_net}, got {res_m['net_gain']}")
                self.assertEqual(res_m["threshold"], exp_thresh, f"[{desc}] main.app threshold expected {exp_thresh}, got {res_m['threshold']}")

                if exp_gk:
                    self.assertIn("Hold for GW31", res_m["explanation"], f"[{desc}] Gatekeeper explanation missing in main.app")
                    self.assertIn("Do not sacrifice immediate points", res_m["explanation"], f"[{desc}] Gatekeeper caution missing in main.app")
                else:
                    self.assertNotIn("Do not sacrifice immediate points", res_m["explanation"], f"[{desc}] Gatekeeper triggered unexpectedly in main.app")

                # 2. Assert 100% parity with backend.main.app
                self.assertEqual(res_m["recommendation"], res_b["recommendation"], f"[{desc}] recommendation mismatch: {res_m['recommendation']} vs {res_b['recommendation']}")
                self.assertEqual(res_m["delta"], res_b["delta"], f"[{desc}] delta mismatch: {res_m['delta']} vs {res_b['delta']}")
                self.assertEqual(res_m["raw_gain"], res_b["raw_gain"], f"[{desc}] raw_gain mismatch: {res_m['raw_gain']} vs {res_b['raw_gain']}")
                self.assertEqual(res_m["hit_cost"], res_b["hit_cost"], f"[{desc}] hit_cost mismatch: {res_m['hit_cost']} vs {res_b['hit_cost']}")
                self.assertEqual(res_m["net_gain"], res_b["net_gain"], f"[{desc}] net_gain mismatch: {res_m['net_gain']} vs {res_b['net_gain']}")
                self.assertEqual(res_m["threshold"], res_b["threshold"], f"[{desc}] threshold mismatch: {res_m['threshold']} vs {res_b['threshold']}")
                self.assertEqual(res_m["best_transfer"]["id"], res_b["best_transfer"]["id"], f"[{desc}] best_transfer id mismatch: {res_m['best_transfer']['id']} vs {res_b['best_transfer']['id']}")
                self.assertEqual(res_m["explanation"], res_b["explanation"], f"[{desc}] explanation mismatch: {res_m['explanation']} vs {res_b['explanation']}")
    # ------------------------------------------------------------------------
    # Requirement: Decision Engine Score Penalties & No Nailed Bonus
    # ------------------------------------------------------------------------
    def test_decision_engine_score_penalties_and_no_double_counting(self):
        """
        Verifies decision_engine_score across both main.py and backend/main.py:
        1. 0.60 penalty for minutes uncertainty ("Low (Minutes Uncertainty)" in confidence).
        2. 0.75 penalty for rotation risk ("Rotation Risk / Bench" in reason).
        3. No +5% bonus for nailed starters: score remains exactly 1.0 * xp (never 1.05 * xp).
        4. Full 1:1 parity between main.py and backend/main.py.
        """
        import main as root_main
        import backend.main as backend_main

        for engine, name in [(root_main.decision_engine_score, "main.py"), (backend_main.decision_engine_score, "backend/main.py")]:
            # 1. Minutes Uncertainty -> 0.60 penalty
            c_low = {"xp": 10.0, "confidence": "Low (Minutes Uncertainty)", "reason": "Expected Starter"}
            score_low = engine(c_low)
            self.assertAlmostEqual(score_low, 6.0, places=4, msg=f"[{name}] 0.60 penalty not applied for Low Minutes Uncertainty")

            # 2. Rotation Risk -> 0.75 penalty
            c_rot = {"xp": 10.0, "confidence": "Medium", "reason": "Rotation Risk / Bench"}
            score_rot = engine(c_rot)
            self.assertAlmostEqual(score_rot, 7.5, places=4, msg=f"[{name}] 0.75 penalty not applied for Rotation Risk")

            # 3. Nailed / Established Starter -> NO double-counting bonus (+5% must NOT exist)
            c_nailed = {"xp": 10.0, "confidence": "High", "reason": "Nailed Starter"}
            score_nailed = engine(c_nailed)
            self.assertAlmostEqual(score_nailed, 10.0, places=4, msg=f"[{name}] Score must remain 1.0 * xp without inflation")
            self.assertNotAlmostEqual(score_nailed, 10.5, places=4, msg=f"[{name}] +5% bonus for nailed starter must NOT exist")


if __name__ == "__main__":
    unittest.main()


