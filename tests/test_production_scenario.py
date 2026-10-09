import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpl_api import fetch_user_team, calculate_player_prices, fetch_bootstrap
from main import app
from fastapi.testclient import TestClient

class TestProductionLikeScenario(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.bootstrap = fetch_bootstrap()
        self.elements = {p["id"]: p for p in self.bootstrap.get("elements", [])}

    def test_transition_post_deadline_public_picks(self):
        """
        Scenario 1:
        - Gameweek deadline has arrived and FPL published public picks for the current Gameweek.
        - Endpoint entry/{team_id}/event/{target_gw}/picks/ returns 200 with new squad.
        - Application automatically switches to current Gameweek squad from public API.
        - Contract check: squad_meta.is_current_gw is True, source is public_current_event.
        """
        team_id = 999999
        target_gw = 6

        # Target GW public squad (15 players)
        current_picks = [{"element": i, "position": i} for i in range(1, 16)]

        mock_event_picks = {
            "picks": current_picks,
            "entry_history": {"bank": 12},
            "active_chip": "wildcard"
        }

        with patch("requests.get") as mock_get:
            def side_effect(url, headers=None, timeout=None):
                mock_resp = MagicMock()
                if f"entry/{team_id}/event/{target_gw}/picks/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = mock_event_picks
                elif "entry/" in url and "/transfers/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = []
                elif "entry/" in url and "/history/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"chips": [{"name": "wildcard", "event": target_gw}]}
                elif "entry/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"name": "Top Manager", "summary_overall_rank": 42000}
                return mock_resp

            mock_get.side_effect = side_effect

            resp = self.client.get(f"/api/dashboard/{team_id}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

            # Contract checks:
            self.assertEqual(data["active_chip"], "wildcard")
            self.assertEqual(data["squad_meta"]["source"], "public_current_event")
            self.assertTrue(data["squad_meta"]["is_current_gw"])
            self.assertEqual(data["squad_meta"]["active_chip"], "wildcard")
            self.assertEqual(data["squad_meta"]["event"], target_gw)
            self.assertIsNone(data["squad_meta"]["pending_deadline_gw"])
            self.assertEqual(data["bank"], 1.2)
            self.assertEqual(len(data["squad"]), 15)

    def test_transition_pre_deadline_fallback(self):
        """
        Scenario 2:
        - Target Gameweek deadline has not arrived yet.
        - Endpoint entry/{team_id}/event/{target_gw}/picks/ returns 404 (FPL pre-deadline privacy).
        - Application automatically falls back to latest completed Gameweek's official squad.
        - Application operates completely without authentication or session tokens.
        - Contract check: squad_meta.is_current_gw is False, source is latest_completed_gw.
        """
        team_id = 999999
        target_gw = 6
        completed_gw = 5

        # Completed GW historical squad (15 players: IDs 1..15)
        completed_picks = [{"element": i, "position": i} for i in range(1, 16)]

        with patch("requests.get") as mock_get:
            def side_effect(url, headers=None, timeout=None):
                mock_resp = MagicMock()
                if f"entry/{team_id}/event/{target_gw}/picks/" in url:
                    mock_resp.status_code = 404 # FPL pre-deadline privacy
                elif f"entry/{team_id}/event/{completed_gw}/picks/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"picks": completed_picks, "entry_history": {"bank": 10}}
                elif "entry/" in url and "/transfers/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = []
                elif "entry/" in url and "/history/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"chips": []}
                elif "entry/" in url:
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"name": "Top Manager", "summary_overall_rank": 42000}
                return mock_resp

            mock_get.side_effect = side_effect

            resp = self.client.get(f"/api/dashboard/{team_id}")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

            # Contract checks:
            self.assertEqual(data["squad_meta"]["source"], "latest_completed_gw")
            self.assertFalse(data["squad_meta"]["is_current_gw"])
            self.assertEqual(data["squad_meta"]["event"], completed_gw)
            self.assertEqual(data["squad_meta"]["pending_deadline_gw"], target_gw)
            self.assertEqual(data["bank"], 1.0)
            self.assertEqual(len(data["squad"]), 15)

if __name__ == '__main__':
    unittest.main()
