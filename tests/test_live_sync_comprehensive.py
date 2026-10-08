import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add root directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpl_api import fetch_user_team, calculate_player_prices, fetch_bootstrap
from main import app
from fastapi.testclient import TestClient

class TestLiveSquadSync(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.bootstrap = fetch_bootstrap()
        self.elements = {p["id"]: p for p in self.bootstrap.get("elements", [])}

    def test_pre_deadline_fallback_when_no_cookie(self):
        """Pre-deadline unauthenticated query returns latest completed GW gracefully without fabricating data."""
        team_id = 3450961
        picks, bank, name, rank, chips_used, leagues, free_transfers, squad_meta = fetch_user_team(team_id, 6)
        
        self.assertEqual(len(picks), 15)
        self.assertIn("source", squad_meta)
        self.assertIn("is_live_current", squad_meta)
        # Before GW6 deadline without cookie, should be completed_gw_fallback
        self.assertEqual(squad_meta["source"], "completed_gw_fallback")
        self.assertFalse(squad_meta["is_live_current"])
        self.assertEqual(squad_meta["event"], 5)
        self.assertEqual(squad_meta["pending_deadline_gw"], 6)

    def test_live_my_team_sync_with_wildcard(self):
        """When user provides official cookie, my-team endpoint provides live GW6 Wildcard squad."""
        team_id = 3450961
        mock_my_team_data = {
            "picks": [
                {"element": 19, "position": 1, "is_captain": True, "is_vice_captain": False, "multiplier": 2, "purchase_price": 58, "selling_price": 58},
                {"element": 351, "position": 2, "is_captain": False, "is_vice_captain": False, "multiplier": 1, "purchase_price": 155, "selling_price": 155}
            ] + [{"element": i, "position": i + 1, "is_captain": False, "is_vice_captain": False, "multiplier": 1, "purchase_price": 50, "selling_price": 50} for i in range(3, 16)],
            "transfers": {
                "bank": 15,
                "limit": 1,
                "made": 5,
                "wildcard": True
            },
            "chips": [
                {"name": "wildcard", "status_for_entry": "active"}
            ]
        }

        with patch("requests.get") as mock_get:
            def side_effect(url, headers=None, timeout=None):
                mock_resp = MagicMock()
                if "my-team" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = mock_my_team_data
                elif "entry/" in url and "/history/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"chips": [{"name": "wildcard", "event": 6}]}
                elif "entry/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"name": "Test FC", "summary_overall_rank": 1000}
                return mock_resp

            mock_get.side_effect = side_effect
            picks, bank, name, rank, chips_used, leagues, free_transfers, squad_meta = fetch_user_team(team_id, 6, cookie="dummy_pl_profile")

            self.assertEqual(len(picks), 15)
            self.assertEqual(bank, 1.5)
            self.assertEqual(free_transfers, 99) # Wildcard active = unlimited
            self.assertEqual(squad_meta["source"], "live_my_team")
            self.assertTrue(squad_meta["is_live_current"])
            self.assertEqual(squad_meta["active_chip"], "wildcard")
            self.assertTrue(squad_meta["authenticated"])

    def test_purchase_price_preservation_and_selling_rules(self):
        """
        Verify:
        1. Player bought on Wildcard at 5.8m rising to 5.9m maintains purchase_price=5.8, selling_price=5.8
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
        """Verify /api/dashboard returns squad_meta, is_live_squad, and active_chip."""
        resp = self.client.get("/api/dashboard/3450961")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("squad_meta", data)
        self.assertIn("is_live_squad", data)
        self.assertIn("active_chip", data)
        self.assertEqual(data["team_id"], 3450961)
        self.assertIsInstance(data["squad"], list)
        self.assertEqual(len(data["squad"]), 15)
        # Check purchase_price and selling_price exist on every player
        for p in data["squad"]:
            self.assertIn("purchase_price", p)
            self.assertIn("selling_price", p)
            self.assertIn("cost", p)

if __name__ == '__main__':
    unittest.main()
