import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app, get_fpl_context, calculate_player_projection
from fastapi.testclient import TestClient

MOCK_BOOTSTRAP = {
    "events": [
        {
            "id": 1,
            "name": "Gameweek 1",
            "is_current": False,
            "is_next": False,
            "deadline_time": "2026-08-15T10:00:00Z",
        },
        {
            "id": 2,
            "name": "Gameweek 2",
            "is_current": True,
            "is_next": False,
            "deadline_time": "2026-08-22T10:00:00Z",
        },
        {
            "id": 3,
            "name": "Gameweek 3",
            "is_current": False,
            "is_next": True,
            "deadline_time": "2026-08-29T10:00:00Z",
        },
    ],
    "teams": [
        {"id": 1, "name": "Arsenal", "short_name": "ARS", "code": 3, "strength_defence_away": 1050, "strength_attack_away": 1150, "strength_defence_home": 1000, "strength_attack_home": 1200},
        {"id": 2, "name": "Aston Villa", "short_name": "AVL", "code": 7, "strength_defence_away": 1100, "strength_attack_away": 1100, "strength_defence_home": 1050, "strength_attack_home": 1100},
        {"id": 3, "name": "Chelsea", "short_name": "CHE", "code": 8, "strength_defence_away": 1100, "strength_attack_away": 1100, "strength_defence_home": 1050, "strength_attack_home": 1100},
        {"id": 4, "name": "Liverpool", "short_name": "LIV", "code": 14, "strength_defence_away": 1000, "strength_attack_away": 1250, "strength_defence_home": 950, "strength_attack_home": 1300},
    ],
    "elements": [
        {
            "id": 10,
            "web_name": "Saka",
            "team": 1,
            "team_code": 3,
            "element_type": 3,
            "now_cost": 100,
            "form": "6.0",
            "status": "a",
            "minutes": 90,
            "starts": 1,
            "total_points": 15,
            "chance_of_playing_next_round": 100,
            "selected_by_percent": "30.0",
            "expected_goals_per_90": 0.4,
            "expected_assists_per_90": 0.3,
            "expected_goals_conceded_per_90": 0.9,
            "defensive_contribution_per_90": 1.5,
            "news": "",
        }
    ]
}


class TestDeadlineAndDGW(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.teams_dict = {t["id"]: t for t in MOCK_BOOTSTRAP["teams"]}

    @patch("main.fetch_all_fixtures", return_value=[])
    @patch("main.fetch_bootstrap", return_value=MOCK_BOOTSTRAP)
    def test_get_fpl_context_exposes_official_deadline_time(self, mock_bootstrap, mock_fixtures):
        ctx = get_fpl_context(gw_limit=5)
        self.assertEqual(ctx["next_gw"], 3)
        self.assertEqual(ctx["deadline_time"], "2026-08-29T10:00:00Z")

    @patch("main.fetch_all_fixtures", return_value=[])
    @patch("main.fetch_bootstrap", return_value=MOCK_BOOTSTRAP)
    def test_get_fpl_context_with_override_gw(self, mock_bootstrap, mock_fixtures):
        ctx = get_fpl_context(gw_limit=5, override_next_gw=2)
        self.assertEqual(ctx["next_gw"], 2)
        self.assertEqual(ctx["deadline_time"], "2026-08-22T10:00:00Z")

    @patch("main.fetch_user_team")
    @patch("main.calculate_player_prices", return_value={})
    @patch("main.fetch_all_fixtures")
    @patch("main.fetch_bootstrap", return_value=MOCK_BOOTSTRAP)
    def test_dashboard_endpoint_includes_deadline_time(self, mock_bootstrap, mock_fixtures, mock_prices, mock_user_team):
        mock_fixtures.return_value = [
            {
                "id": 101,
                "event": 3,
                "team_h": 1,
                "team_a": 2,
                "team_h_difficulty": 2,
                "team_a_difficulty": 4,
                "kickoff_time": "2026-08-29T11:30:00Z",
            }
        ]
        mock_user_team.return_value = (
            [{"element": 10, "position": 1, "is_captain": True, "is_vice_captain": False, "multiplier": 2}],
            1.5,
            "Test FC",
            1000,
            [],
            [],
            2,
            {"active_chip": None, "last_gw_chip": None, "is_current_gw": False}
        )

        resp = self.client.get("/api/dashboard/12345")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("deadline_time", data)
        self.assertEqual(data["deadline_time"], "2026-08-29T10:00:00Z")

    def test_single_gameweek_fixture_display(self):
        player = MOCK_BOOTSTRAP["elements"][0]  # Team 1 (Arsenal)
        fixtures = [
            {
                "id": 1,
                "event": 3,
                "team_h": 1,
                "team_a": 2,  # AVL
                "team_h_difficulty": 2,
                "team_a_difficulty": 4,
            }
        ]
        proj = calculate_player_projection(player, 3, fixtures, self.teams_dict)
        self.assertEqual(proj["fixture"], "AVL (H)")
        self.assertEqual(proj["fixture_diff"], 2)

    def test_double_gameweek_fixture_display(self):
        player = MOCK_BOOTSTRAP["elements"][0]  # Team 1 (Arsenal)
        fixtures = [
            {
                "id": 1,
                "event": 3,
                "team_h": 1,
                "team_a": 2,  # AVL
                "team_h_difficulty": 2,
                "team_a_difficulty": 4,
            },
            {
                "id": 2,
                "event": 3,
                "team_h": 3,  # CHE
                "team_a": 1,  # ARS away
                "team_h_difficulty": 3,
                "team_a_difficulty": 4,
            }
        ]
        proj = calculate_player_projection(player, 3, fixtures, self.teams_dict)
        self.assertEqual(proj["fixture"], "AVL (H), CHE (A)")
        # diff average: round((2 + 4) / 2) = 3
        self.assertEqual(proj["fixture_diff"], 3)
        self.assertIsInstance(proj["fixture_diff"], int)

    def test_blank_gameweek_fixture_display(self):
        player = MOCK_BOOTSTRAP["elements"][0]  # Team 1 (Arsenal)
        fixtures = [
            {
                "id": 1,
                "event": 3,
                "team_h": 2,  # AVL
                "team_a": 4,  # LIV (Arsenal not playing)
                "team_h_difficulty": 3,
                "team_a_difficulty": 3,
            }
        ]
        proj = calculate_player_projection(player, 3, fixtures, self.teams_dict)
        self.assertEqual(proj["fixture"], "Blank")
        self.assertEqual(proj["fixture_diff"], 5)

    @patch("main.fetch_user_team")
    @patch("main.calculate_player_prices", return_value={})
    @patch("main.fetch_all_fixtures")
    @patch("main.fetch_bootstrap", return_value=MOCK_BOOTSTRAP)
    def test_dashboard_upcoming_fixtures_handles_dgw(self, mock_bootstrap, mock_fixtures, mock_prices, mock_user_team):
        mock_fixtures.return_value = [
            {
                "id": 1,
                "event": 3,
                "team_h": 1,
                "team_a": 2,  # AVL
                "team_h_difficulty": 2,
                "team_a_difficulty": 4,
            },
            {
                "id": 2,
                "event": 3,
                "team_h": 3,  # CHE
                "team_a": 1,  # ARS away
                "team_h_difficulty": 3,
                "team_a_difficulty": 4,
            }
        ]
        mock_user_team.return_value = (
            [{"element": 10, "position": 1, "is_captain": True, "is_vice_captain": False, "multiplier": 2}],
            1.5,
            "Test FC",
            1000,
            [],
            [],
            2,
            {"active_chip": None, "last_gw_chip": None, "is_current_gw": False}
        )

        resp = self.client.get("/api/dashboard/12345")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        squad = data["squad"]
        self.assertEqual(len(squad), 1)
        player_pick = squad[0]
        self.assertEqual(player_pick["fixture"], "AVL (H), CHE (A)")
        self.assertEqual(player_pick["fixture_diff"], 3)
        self.assertEqual(player_pick["upcoming_fixtures"][0]["opponent"], "AVL (H), CHE (A)")
        self.assertEqual(player_pick["upcoming_fixtures"][0]["difficulty"], 3)


if __name__ == "__main__":
    unittest.main()
