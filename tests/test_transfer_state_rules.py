import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Ensure root directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import fpl_api
import main
from main import app, TransferRequest

client = TestClient(app)


class TestTransferStateRules(unittest.TestCase):
    """
    Deterministic test suite for FPL transfer state rules, chip isolation, and hit calculations.
    """

    # ============================================================================
    # 1. calculate_free_transfers unit tests (2024/25 FPL rules)
    # ============================================================================

    def test_ft_starts_at_one_for_gw2(self):
        history_res = {"current": [{"event": 1, "event_transfers": 10}], "chips": []}
        self.assertEqual(fpl_api.calculate_free_transfers(history_res), 1)

    def test_ft_normal_banking_up_to_five(self):
        # GW1 -> starts GW2 with 1
        # GW2: 0 transfers -> GW3 starts with 2
        # GW3: 0 transfers -> GW4 starts with 3
        # GW4: 0 transfers -> GW5 starts with 4
        # GW5: 0 transfers -> GW6 starts with 5
        # GW6: 0 transfers -> GW7 capped at 5
        history_res = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0},
                {"event": 3, "event_transfers": 0},
                {"event": 4, "event_transfers": 0},
                {"event": 5, "event_transfers": 0},
                {"event": 6, "event_transfers": 0},
            ],
            "chips": []
        }
        self.assertEqual(fpl_api.calculate_free_transfers(history_res), 5)

    def test_ft_spending_and_hit_resets_bank(self):
        # GW2 starts with 1 FT. Manager makes 3 transfers (takes hit).
        # Remaining banked FT is 0. GW3 receives 1 FT.
        history_res = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 3},
            ],
            "chips": []
        }
        self.assertEqual(fpl_api.calculate_free_transfers(history_res), 1)

    def test_ft_wildcard_preserves_banked_transfers(self):
        # Manager banks 3 FTs by GW4.
        # In GW4, manager plays Wildcard and makes 8 transfers.
        # 2024/25 rule: Wildcard preserves banked FT balance without consumption.
        # GW5 starts with 3 FTs.
        history_res = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0},
                {"event": 3, "event_transfers": 0},
                {"event": 4, "event_transfers": 8},
            ],
            "chips": [{"name": "wildcard", "event": 4}]
        }
        self.assertEqual(fpl_api.calculate_free_transfers(history_res), 3)

    def test_ft_free_hit_preserves_banked_transfers_normalized_name(self):
        # Test both 'freehit' and 'free_hit' with underscore
        history_res_underscore = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0},
                {"event": 3, "event_transfers": 5},
            ],
            "chips": [{"name": "free_hit", "event": 3}]
        }
        self.assertEqual(fpl_api.calculate_free_transfers(history_res_underscore), 2)

        history_res_standard = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0},
                {"event": 3, "event_transfers": 5},
            ],
            "chips": [{"name": "freehit", "event": 3}]
        }
        self.assertEqual(fpl_api.calculate_free_transfers(history_res_standard), 2)

    # ============================================================================
    # 2. fetch_user_team: squad_meta chip isolation (Layer 1 vs Layer 2)
    # ============================================================================

    @patch("fpl_api.requests.get")
    def test_previous_gw_wildcard_does_not_leak_into_upcoming_gw(self, mock_get):
        """
        When next_gw is upcoming (deadline not passed), Layer 1 returns 404.
        Layer 2 falls back to last_gw (where Wildcard was played).
        squad_meta['active_chip'] must be None for the upcoming GW,
        and squad_meta['last_gw_chip'] must record 'wildcard'.
        """
        def mock_requests(url, **kwargs):
            resp = MagicMock()
            if "entry/123/history/" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "current": [{"event": 1, "event_transfers": 0}, {"event": 30, "event_transfers": 10}],
                    "chips": [{"name": "wildcard", "event": 30}]
                }
            elif "entry/123/event/31/picks/" in url:
                # Deadline not reached yet for GW 31
                resp.status_code = 404
            elif "entry/123/event/30/picks/" in url:
                # Last GW 30 picks where Wildcard was used
                resp.status_code = 200
                resp.json.return_value = {
                    "picks": [{"element": 1, "position": 1, "multiplier": 1, "is_captain": False, "is_vice_captain": False}],
                    "entry_history": {"bank": 10},
                    "active_chip": "wildcard"
                }
            elif "entry/123/" in url:
                resp.status_code = 200
                resp.json.return_value = {"name": "Test FC", "summary_overall_rank": 100, "leagues": {}}
            else:
                resp.status_code = 404
            return resp

        mock_get.side_effect = mock_requests

        picks, bank, name, rank, chips_used, leagues, free_transfers, squad_meta = fpl_api.fetch_user_team(123, 31)

        self.assertEqual(free_transfers, 1)
        self.assertFalse(squad_meta["is_current_gw"])
        self.assertEqual(squad_meta["event"], 30)
        self.assertEqual(squad_meta["pending_deadline_gw"], 31)
        self.assertEqual(squad_meta["last_gw_chip"], "wildcard")
        self.assertIsNone(squad_meta["active_chip"])  # MUST NOT LEAK!

    @patch("fpl_api.requests.get")
    def test_previous_gw_free_hit_does_not_leak_and_reverts_squad(self, mock_get):
        """
        When last_gw was Free Hit, Layer 2 reverts squad to base_gw (last_gw - 1),
        and squad_meta['active_chip'] must be None for the upcoming GW.
        """
        def mock_requests(url, **kwargs):
            resp = MagicMock()
            if "entry/123/history/" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "current": [{"event": 1, "event_transfers": 0}, {"event": 29, "event_transfers": 0}, {"event": 30, "event_transfers": 5}],
                    "chips": [{"name": "free_hit", "event": 30}]
                }
            elif "entry/123/event/31/picks/" in url:
                resp.status_code = 404
            elif "entry/123/event/30/picks/" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "picks": [{"element": 99, "position": 1, "multiplier": 1}],
                    "entry_history": {"bank": 5},
                    "active_chip": "free_hit"
                }
            elif "entry/123/event/29/picks/" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "picks": [{"element": 1, "position": 1, "multiplier": 1}],
                    "entry_history": {"bank": 10},
                    "active_chip": None
                }
            elif "entry/123/" in url:
                resp.status_code = 200
                resp.json.return_value = {"name": "Test FC", "summary_overall_rank": 100, "leagues": {}}
            return resp

        mock_get.side_effect = mock_requests

        picks, bank, name, rank, chips_used, leagues, free_transfers, squad_meta = fpl_api.fetch_user_team(123, 31)

        self.assertIsNone(squad_meta["active_chip"])  # MUST NOT LEAK!
        self.assertEqual(squad_meta["last_gw_chip"], "free_hit")
        self.assertEqual(picks[0]["element"], 1)  # Reverted to base_gw 29!

    @patch("fpl_api.requests.get")
    def test_live_gw_deadline_passed_reports_live_chip(self, mock_get):
        """
        When viewing a live Gameweek whose deadline passed (Layer 1),
        active_chip is reported for that live GW.
        """
        def mock_requests(url, **kwargs):
            resp = MagicMock()
            if "entry/123/event/30/picks/" in url:
                resp.status_code = 200
                resp.json.return_value = {
                    "picks": [{"element": 1, "position": 1, "multiplier": 1}],
                    "entry_history": {"bank": 10},
                    "active_chip": "wildcard"
                }
            elif "entry/123/history/" in url:
                resp.status_code = 200
                resp.json.return_value = {"current": [], "chips": []}
            elif "entry/123/" in url:
                resp.status_code = 200
                resp.json.return_value = {"name": "Test FC", "summary_overall_rank": 100}
            return resp

        mock_get.side_effect = mock_requests

        picks, bank, name, rank, chips_used, leagues, free_transfers, squad_meta = fpl_api.fetch_user_team(123, 30)

        self.assertTrue(squad_meta["is_current_gw"])
        self.assertEqual(squad_meta["active_chip"], "wildcard")
        self.assertIsNone(squad_meta["last_gw_chip"])

    # ============================================================================
    # 3. /api/dashboard endpoint integration contract
    # ============================================================================

    @patch("main.fetch_user_team")
    @patch("main.calculate_player_prices")
    @patch("main.get_fpl_context")
    def test_dashboard_endpoint_isolates_previous_gw_chip(self, mock_ctx, mock_prices, mock_fetch):
        mock_ctx.return_value = {
            "next_gw": 31,
            "gw_range": 5,
            "upcoming_fixtures_raw": [],
            "elements": {
                1: {
                    "id": 1, "web_name": "Haaland", "team": 1, "team_code": 43,
                    "element_type": 4, "now_cost": 140, "minutes": 900, "starts": 10,
                    "form": "5.0", "expected_goals_per_90": 0.8, "expected_assists_per_90": 0.2,
                    "expected_goals_conceded_per_90": 0.9, "defensive_contribution_per_90": 0.0,
                    "chance_of_playing_next_round": 100, "total_points": 150, "selected_by_percent": 60.0
                }
            },
            "teams": {1: {"id": 1, "short_name": "MCI", "team_code": 43}}
        }
        mock_prices.return_value = {1: {"selling_price": 14.0, "purchase_price": 14.0}}
        mock_fetch.return_value = (
            [{"element": 1, "position": 1, "multiplier": 1}],
            1.5,
            "Test Team",
            1000,
            ["wildcard"],
            {},
            1,  # 1 FT
            {
                "source": "latest_completed_gw",
                "is_current_gw": False,
                "event": 30,
                "pending_deadline_gw": 31,
                "last_gw_chip": "wildcard",
                "active_chip": None  # Scoped
            }
        )

        resp = client.get("/api/dashboard/123")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["free_transfers"], 1)
        self.assertIsNone(data["active_chip"])
        self.assertEqual(data["last_gw_chip"], "wildcard")
        self.assertIsNone(data["squad_meta"]["active_chip"])

    # ============================================================================
    # 4. /api/transfer-lab hit calculations
    # ============================================================================

    @patch("main.get_fpl_context")
    def test_transfer_lab_one_ft_two_transfers_incurs_four_point_hit(self, mock_ctx):
        """
        1 FT available, 2 transfers total:
        - 1st transfer (transfers_before=0): hit_cost = 0
        - 2nd transfer (transfers_before=1): hit_cost = 4
        """
        mock_ctx.return_value = {
            "next_gw": 31,
            "gw_range": 5,
            "upcoming_fixtures_raw": [],
            "bootstrap": {
                "elements": [
                    {
                        "id": 10, "web_name": "Player A", "team": 1, "team_code": 1,
                        "element_type": 3, "now_cost": 80, "form": "5.0", "minutes": 900,
                        "starts": 10, "expected_goals_per_90": 0.3, "expected_assists_per_90": 0.2,
                        "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
                        "chance_of_playing_next_round": 100, "total_points": 80, "selected_by_percent": 10.0
                    },
                    {
                        "id": 20, "web_name": "Player B", "team": 2, "team_code": 2,
                        "element_type": 3, "now_cost": 80, "form": "8.0", "minutes": 900,
                        "starts": 10, "expected_goals_per_90": 0.6, "expected_assists_per_90": 0.4,
                        "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
                        "chance_of_playing_next_round": 100, "total_points": 100, "selected_by_percent": 20.0
                    }
                ]
            },
            "teams": {
                1: {"id": 1, "short_name": "ARS", "team_code": 1, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
                2: {"id": 2, "short_name": "LIV", "team_code": 2, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100}
            }
        }

        # 1st transfer: transfers_before = 0, free_transfers = 1 -> hit_cost must be 0
        payload_1st = {
            "pos_code": 3,
            "max_budget": 8.5,
            "current_squad_ids": [10],
            "transfer_out_id": 10,
            "free_transfers": 1,
            "transfers_before": 0,
            "active_chip": None,
            "target_gw": 31
        }
        r1 = client.post("/api/transfer-lab", json=payload_1st)
        self.assertEqual(r1.status_code, 200)
        res1 = r1.json()
        self.assertIn("0-point hit cost", res1["explanation"])

        # 2nd transfer: transfers_before = 1, free_transfers = 1 -> hit_cost must be 4
        payload_2nd = {
            "pos_code": 3,
            "max_budget": 8.5,
            "current_squad_ids": [10],
            "transfer_out_id": 10,
            "free_transfers": 1,
            "transfers_before": 1,
            "active_chip": None,
            "target_gw": 31
        }
        r2 = client.post("/api/transfer-lab", json=payload_2nd)
        self.assertEqual(r2.status_code, 200)
        res2 = r2.json()
        self.assertIn("4-point hit cost", res2["explanation"])

    @patch("main.get_fpl_context")
    def test_transfer_lab_explicit_wildcard_simulation_suppresses_hit(self, mock_ctx):
        """
        When active_chip='wildcard' is explicitly simulated, hit_cost is 0.
        """
        mock_ctx.return_value = {
            "next_gw": 31,
            "gw_range": 5,
            "upcoming_fixtures_raw": [],
            "bootstrap": {
                "elements": [
                    {
                        "id": 10, "web_name": "Player A", "team": 1, "team_code": 1,
                        "element_type": 3, "now_cost": 80, "form": "5.0", "minutes": 900,
                        "starts": 10, "expected_goals_per_90": 0.3, "expected_assists_per_90": 0.2,
                        "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
                        "chance_of_playing_next_round": 100, "total_points": 80, "selected_by_percent": 10.0
                    },
                    {
                        "id": 20, "web_name": "Player B", "team": 2, "team_code": 2,
                        "element_type": 3, "now_cost": 80, "form": "8.0", "minutes": 900,
                        "starts": 10, "expected_goals_per_90": 0.6, "expected_assists_per_90": 0.4,
                        "expected_goals_conceded_per_90": 1.0, "defensive_contribution_per_90": 2.0,
                        "chance_of_playing_next_round": 100, "total_points": 100, "selected_by_percent": 20.0
                    }
                ]
            },
            "teams": {
                1: {"id": 1, "short_name": "ARS", "team_code": 1, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
                2: {"id": 2, "short_name": "LIV", "team_code": 2, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100}
            }
        }

        payload = {
            "pos_code": 3,
            "max_budget": 8.5,
            "current_squad_ids": [10],
            "transfer_out_id": 10,
            "free_transfers": 1,
            "transfers_before": 2,  # 3rd transfer
            "active_chip": "wildcard",
            "target_gw": 31
        }
        r = client.post("/api/transfer-lab", json=payload)
        self.assertEqual(r.status_code, 200)
        res = r.json()
        self.assertIn("0-point hit cost", res["explanation"])


if __name__ == "__main__":
    unittest.main()
