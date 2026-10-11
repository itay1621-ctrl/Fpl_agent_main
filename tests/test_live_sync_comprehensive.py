import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpl_api import fetch_user_team, calculate_player_prices, fetch_bootstrap
from main import app
from fastapi.testclient import TestClient

MOCK_EVENTS = [
    {"id": i, "name": f"Gameweek {i}", "is_current": (i == 5), "is_next": (i == 6), "finished": (i < 6)}
    for i in range(1, 39)
]

MOCK_ELEMENTS = [
    {
        "id": i,
        "web_name": f"Player {i}",
        "team": 1,
        "team_code": 1,
        "element_type": 1 if i <= 2 else (2 if i <= 7 else (3 if i <= 12 else 4)),
        "now_cost": 50 + i,
        "status": "a",
        "form": "4.5",
        "minutes": 90,
        "starts": 1,
        "total_points": 10,
        "chance_of_playing_next_round": 100,
        "selected_by_percent": "10.0",
        "expected_goals_per_90": 0.2,
        "expected_assists_per_90": 0.1,
        "expected_goals_conceded_per_90": 1.0,
        "defensive_contribution_per_90": 2.0,
        "news": "",
    }
    for i in range(1, 16)
]

MOCK_TEAMS = [
    {"id": i, "name": f"Team {i}", "short_name": f"T{i}", "code": i}
    for i in range(1, 21)
]

MOCK_BOOTSTRAP = {
    "events": MOCK_EVENTS,
    "elements": MOCK_ELEMENTS,
    "teams": MOCK_TEAMS,
}

MOCK_FIXTURES = [
    {
        "id": 1,
        "event": 6,
        "team_h": 1,
        "team_a": 2,
        "team_h_difficulty": 2,
        "team_a_difficulty": 3,
        "kickoff_time": "2026-10-17T14:00:00Z"
    }
]

class TestPublicFPLSquadFlow(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.bootstrap = MOCK_BOOTSTRAP
        self.elements = {p["id"]: p for p in self.bootstrap.get("elements", [])}

    def test_pre_deadline_public_fallback(self):
        """Before deadline when current GW picks return 404, fallback to latest completed GW."""
        team_id = 3450961
        gw_target = 6
        completed_picks = [{"element": i, "position": i} for i in range(1, 16)]

        with patch("requests.get") as mock_get:
            def side_effect(url, headers=None, timeout=None):
                mock_resp = MagicMock()
                if f"entry/{team_id}/event/{gw_target}/picks/" in url:
                    mock_resp.status_code = 404  # Pre-deadline privacy
                elif f"entry/{team_id}/event/{gw_target - 1}/picks/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"picks": completed_picks, "entry_history": {"bank": 10}}
                elif f"entry/{team_id}/history/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"chips": []}
                elif f"entry/{team_id}/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"name": "Test FC", "summary_overall_rank": 500}
                return mock_resp

            mock_get.side_effect = side_effect
            picks, bank, name, rank, chips_used, leagues, free_transfers, squad_meta = fetch_user_team(team_id, gw_target)
        
        self.assertEqual(len(picks), 15)
        self.assertIn("source", squad_meta)
        self.assertIn("is_current_gw", squad_meta)
        self.assertEqual(squad_meta["source"], "latest_completed_gw")
        self.assertFalse(squad_meta["is_current_gw"])
        self.assertEqual(squad_meta["event"], gw_target - 1)
        self.assertEqual(squad_meta["pending_deadline_gw"], gw_target)

    def test_post_deadline_public_picks_transition(self):
        """After deadline when current GW picks return 200, use current GW picks directly."""
        team_id = 3450961
        gw_target = 6
        mock_current_picks = {
            "picks": [{"element": i, "position": i} for i in range(1, 16)],
            "entry_history": {"bank": 15},
            "active_chip": "bboost"
        }

        with patch("requests.get") as mock_get:
            def side_effect(url, headers=None, timeout=None):
                mock_resp = MagicMock()
                if f"entry/{team_id}/event/{gw_target}/picks/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = mock_current_picks
                elif f"entry/{team_id}/history/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"chips": []}
                elif f"entry/{team_id}/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"name": "Test FC", "summary_overall_rank": 500}
                return mock_resp

            mock_get.side_effect = side_effect
            picks, bank, name, rank, chips_used, leagues, free_transfers, squad_meta = fetch_user_team(team_id, gw_target)

            self.assertEqual(len(picks), 15)
            self.assertEqual(bank, 1.5)
            self.assertEqual(squad_meta["source"], "public_current_event")
            self.assertTrue(squad_meta["is_current_gw"])
            self.assertEqual(squad_meta["event"], gw_target)
            self.assertIsNone(squad_meta["pending_deadline_gw"])
            self.assertEqual(squad_meta["active_chip"], "bboost")

    def test_purchase_price_preservation_and_selling_rules(self):
        """
        Verify official FPL price rules:
        1. Player bought at 5.8m rising to 5.9m maintains purchase_price=5.8, selling_price=5.8
        2. Player rising to 6.0m yields selling_price=5.9 (50% profit rule)
        3. Player dropping to 5.7m yields selling_price=5.7 (100% loss rule)
        """
        picks = [
            {"element": 1001, "position": 1, "purchase_price": 58, "selling_price": 58},
            {"element": 1002, "position": 2, "purchase_price": 58},
            {"element": 1003, "position": 3, "purchase_price": 58}
        ]
        elements = {
            1001: {"id": 1001, "now_cost": 59, "cost_change_start": 1},
            1002: {"id": 1002, "now_cost": 60, "cost_change_start": 2},
            1003: {"id": 1003, "now_cost": 57, "cost_change_start": -1}
        }

        prices = calculate_player_prices(1, picks, elements, 6, history_res={}, transfers=[])
        
        # 1001: bought at 5.8, now 5.9 -> sell at 5.8
        self.assertEqual(prices[1001]["purchase_price"], 5.8)
        self.assertEqual(prices[1001]["selling_price"], 5.8)

        # 1002: bought at 5.8, now 6.0 -> sell at 5.8 + floor((6.0 - 5.8)/2) = 5.9
        self.assertEqual(prices[1002]["purchase_price"], 5.8)
        self.assertEqual(prices[1002]["selling_price"], 5.9)

        # 1003: bought at 5.8, now 5.7 -> sell at 5.7 (full loss)
        self.assertEqual(prices[1003]["purchase_price"], 5.8)
        self.assertEqual(prices[1003]["selling_price"], 5.7)

    def test_dashboard_api_data_contract(self):
        """Verify /api/dashboard returns squad_meta, active_chip and complete squad."""
        team_id = 3450961
        gw_target = 6
        mock_picks = [{"element": i, "position": i} for i in range(1, 16)]

        with patch("requests.get") as mock_get:
            def side_effect(url, headers=None, timeout=None):
                mock_resp = MagicMock()
                if "bootstrap-static" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = MOCK_BOOTSTRAP
                elif "fixtures" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = MOCK_FIXTURES
                elif f"entry/{team_id}/event/{gw_target}/picks/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {
                        "picks": mock_picks,
                        "entry_history": {"bank": 10},
                        "active_chip": None
                    }
                elif f"entry/{team_id}/transfers/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = []
                elif f"entry/{team_id}/history/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"chips": []}
                elif f"entry/{team_id}/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {
                        "name": "Test FC",
                        "summary_overall_rank": 500,
                        "leagues": {"classic": [], "h2h": []}
                    }
                return mock_resp

            mock_get.side_effect = side_effect
            resp = self.client.get(f"/api/dashboard/{team_id}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("squad_meta", data)
            self.assertIn("active_chip", data)
            self.assertEqual(data["team_id"], team_id)
            self.assertIsInstance(data["squad"], list)
            self.assertEqual(len(data["squad"]), 15)
            for p in data["squad"]:
                self.assertIn("purchase_price", p)
                self.assertIn("selling_price", p)
                self.assertIn("cost", p)

    def test_defensive_transfer_handling(self):
        """Verify calculate_player_prices safely handles non-list transfers and malformed entries."""
        picks = [{"element": 1001, "position": 1}]
        elements = {1001: {"id": 1001, "now_cost": 60, "cost_change_start": 0}}

        # Case 1: transfers is not a list (e.g. dict, string, None)
        prices_str = calculate_player_prices(1, picks, elements, 6, history_res={}, transfers="invalid_string")
        self.assertIn(1001, prices_str)

        # Case 2: transfers contains None, numbers, strings, and a valid entry
        corrupted_transfers = [
            None,
            "corrupt_entry",
            123,
            [],
            {"element_in": 1001, "element_in_cost": 55, "event": 5, "time": "2026-09-01T12:00:00Z"}
        ]
        prices_corrupt = calculate_player_prices(1, picks, elements, 6, history_res={"chips": "invalid_chips"}, transfers=corrupted_transfers)
        self.assertEqual(prices_corrupt[1001]["purchase_price"], 5.5)

    def test_dashboard_no_authentication_needed(self):
        """Verify that dashboard works cleanly without cookies or special authentication headers."""
        with patch("main.fetch_user_team") as mock_fetch, patch("requests.get") as mock_get:
            def side_effect(url, headers=None, timeout=None):
                mock_resp = MagicMock()
                if "bootstrap-static" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = MOCK_BOOTSTRAP
                elif "fixtures" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = MOCK_FIXTURES
                elif "transfers" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = []
                return mock_resp

            mock_get.side_effect = side_effect
            mock_fetch.return_value = (
                [{"element": 1, "position": 1}],
                1.0,
                "Test",
                100,
                [],
                [],
                1,
                {"source": "latest_completed_gw", "is_current_gw": False, "active_chip": None, "event": 5, "pending_deadline_gw": 6}
            )
            resp = self.client.get("/api/dashboard/3450961")
            self.assertEqual(resp.status_code, 200)
            mock_fetch.assert_called_with(3450961, 6)

if __name__ == '__main__':
    unittest.main()
