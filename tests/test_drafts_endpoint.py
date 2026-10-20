import unittest
from unittest.mock import patch
import os
import sys

# Ensure root directory is on python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
import main
from main import app, calculate_player_projection, build_draft_squad


class TestDraftsEndpoint(unittest.TestCase):
    """
    Focused, deterministic regression tests for the consolidated Drafts projection endpoint
    in root main.py and verification of the thin adapter in app/api-vercel/drafts/route.ts.
    """

    def setUp(self):
        self.client = TestClient(app)

        # 8 deterministic teams to allow full 15-man squad within 3-per-team constraint
        self.mock_teams = [
            {"id": 1, "short_name": "ARS", "team_code": 3, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
            {"id": 2, "short_name": "CHE", "team_code": 8, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
            {"id": 3, "short_name": "LIV", "team_code": 14, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
            {"id": 4, "short_name": "MCI", "team_code": 43, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
            {"id": 5, "short_name": "MUN", "team_code": 1, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
            {"id": 6, "short_name": "TOT", "team_code": 6, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
            {"id": 7, "short_name": "NEW", "team_code": 4, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
            {"id": 8, "short_name": "AVL", "team_code": 7, "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
        ]

        # 5 Gameweeks of fixtures for all 8 teams
        self.mock_fixtures = []
        for gw in range(1, 6):
            self.mock_fixtures.append({"event": gw, "team_h": 1, "team_a": 2, "team_h_difficulty": 3, "team_a_difficulty": 3})
            self.mock_fixtures.append({"event": gw, "team_h": 3, "team_a": 4, "team_h_difficulty": 3, "team_a_difficulty": 3})
            self.mock_fixtures.append({"event": gw, "team_h": 5, "team_a": 6, "team_h_difficulty": 3, "team_a_difficulty": 3})
            self.mock_fixtures.append({"event": gw, "team_h": 7, "team_a": 8, "team_h_difficulty": 3, "team_a_difficulty": 3})

        self.mock_events = [
            {"id": 1, "is_current": True, "is_next": False, "finished": True},
            {"id": 2, "is_current": False, "is_next": True, "finished": False},
            {"id": 3, "is_current": False, "is_next": False, "finished": False},
            {"id": 4, "is_current": False, "is_next": False, "finished": False},
            {"id": 5, "is_current": False, "is_next": False, "finished": False},
        ]

        # Deterministic universe of 40 players across 8 teams and 4 positions
        # Pos 1: 6 GKPs
        # Pos 2: 16 DEFs
        # Pos 3: 12 MIDs
        # Pos 4: 8 FWDs
        self.mock_elements = []
        pid = 1

        # GKPs (pos 1)
        for i in range(6):
            t_id = (i % 8) + 1
            self.mock_elements.append({
                "id": pid, "web_name": f"GKP_{pid}", "first_name": "GKP", "second_name": f"Player_{pid}",
                "team": t_id, "team_code": self.mock_teams[t_id-1]["team_code"], "element_type": 1,
                "now_cost": 40 if i < 4 else 45, "minutes": 900, "starts": 10, "form": "3.5",
                "expected_goals_per_90": 0.0, "expected_assists_per_90": 0.0,
                "expected_goals_conceded_per_90": 1.0, "saves_per_90": 3.0 + i * 0.5,
                "defensive_contribution_per_90": 0.0, "chance_of_playing_next_round": 100,
                "selected_by_percent": 3.0 + i * 2.0, "total_points": 50 + i * 10, "status": "a"
            })
            pid += 1

        # DEFs (pos 2)
        for i in range(16):
            t_id = (i % 8) + 1
            self.mock_elements.append({
                "id": pid, "web_name": f"DEF_{pid}", "first_name": "DEF", "second_name": f"Player_{pid}",
                "team": t_id, "team_code": self.mock_teams[t_id-1]["team_code"], "element_type": 2,
                "now_cost": 40 + (i % 5) * 5, "minutes": 900, "starts": 10, "form": "4.0",
                "expected_goals_per_90": 0.05 + (i * 0.01), "expected_assists_per_90": 0.1,
                "expected_goals_conceded_per_90": 0.9, "saves_per_90": 0.0,
                "defensive_contribution_per_90": 6.0, "chance_of_playing_next_round": 100,
                "selected_by_percent": 3.0 + i * 1.5, "total_points": 60 + i * 5, "status": "a"
            })
            pid += 1

        # MIDs (pos 3)
        for i in range(12):
            t_id = (i % 8) + 1
            cost = 45 if i < 4 else (60 + i * 6)  # includes premiums (cost >= 100)
            self.mock_elements.append({
                "id": pid, "web_name": f"MID_{pid}", "first_name": "MID", "second_name": f"Player_{pid}",
                "team": t_id, "team_code": self.mock_teams[t_id-1]["team_code"], "element_type": 3,
                "now_cost": cost, "minutes": 900, "starts": 10, "form": "5.0",
                "expected_goals_per_90": 0.3 + (i * 0.05), "expected_assists_per_90": 0.25,
                "expected_goals_conceded_per_90": 1.2, "saves_per_90": 0.0,
                "defensive_contribution_per_90": 4.0, "chance_of_playing_next_round": 100,
                "selected_by_percent": 3.0 + i * 2.0, "total_points": 70 + i * 10, "status": "a"
            })
            pid += 1

        # FWDs (pos 4)
        for i in range(8):
            t_id = (i % 8) + 1
            cost = 50 if i < 3 else (70 + i * 10)  # includes premium forwards
            self.mock_elements.append({
                "id": pid, "web_name": f"FWD_{pid}", "first_name": "FWD", "second_name": f"Player_{pid}",
                "team": t_id, "team_code": self.mock_teams[t_id-1]["team_code"], "element_type": 4,
                "now_cost": cost, "minutes": 900, "starts": 10, "form": "6.0",
                "expected_goals_per_90": 0.5 + (i * 0.1), "expected_assists_per_90": 0.15,
                "expected_goals_conceded_per_90": 1.5, "saves_per_90": 0.0,
                "defensive_contribution_per_90": 2.0, "chance_of_playing_next_round": 100,
                "selected_by_percent": 4.0 + i * 3.0, "total_points": 80 + i * 15, "status": "a"
            })
            pid += 1

        # Ineligible players to verify filtering
        self.mock_elements.append({
            "id": 991, "web_name": "Injured_Guy", "element_type": 3, "team": 1, "team_code": 3,
            "now_cost": 80, "status": "i", "minutes": 900, "starts": 10
        })
        self.mock_elements.append({
            "id": 992, "web_name": "Suspended_Guy", "element_type": 2, "team": 2, "team_code": 8,
            "now_cost": 50, "status": "s", "minutes": 900, "starts": 10
        })
        self.mock_elements.append({
            "id": 993, "web_name": "Unavailable_Guy", "element_type": 4, "team": 3, "team_code": 14,
            "now_cost": 60, "status": "u", "minutes": 900, "starts": 10
        })

        self.mock_bootstrap = {
            "events": self.mock_events,
            "teams": self.mock_teams,
            "elements": self.mock_elements
        }

    # -------------------------------------------------------------
    # 1. Endpoint Success & 3 Draft Definitions
    # -------------------------------------------------------------
    @patch("main.fetch_bootstrap")
    @patch("main.fetch_all_fixtures")
    def test_drafts_endpoint_success_and_draft_definitions(self, mock_fixtures, mock_bootstrap):
        mock_bootstrap.return_value = self.mock_bootstrap
        mock_fixtures.return_value = self.mock_fixtures

        res = self.client.get("/api/drafts")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertIn("drafts", data)
        drafts = data["drafts"]
        self.assertEqual(len(drafts), 3)

        # Expected draft definitions & ordering
        self.assertEqual(drafts[0]["id"], 1)
        self.assertEqual(drafts[0]["name_en"], "Premium Build")
        self.assertEqual(drafts[0]["name_he"], "כוכבים יקרים")

        self.assertEqual(drafts[1]["id"], 2)
        self.assertEqual(drafts[1]["name_en"], "Balanced Spread")
        self.assertEqual(drafts[1]["name_he"], "הרכב מאוזן")

        self.assertEqual(drafts[2]["id"], 3)
        self.assertEqual(drafts[2]["name_en"], "Differentials")
        self.assertEqual(drafts[2]["name_he"], "פנינים נסתרות")

    # -------------------------------------------------------------
    # 2. Squad Constraints: 15 Unique Players, Positional & Club Quotas, Budget
    # -------------------------------------------------------------
    @patch("main.fetch_bootstrap")
    @patch("main.fetch_all_fixtures")
    def test_squad_composition_and_constraints(self, mock_fixtures, mock_bootstrap):
        mock_bootstrap.return_value = self.mock_bootstrap
        mock_fixtures.return_value = self.mock_fixtures

        res = self.client.get("/api/drafts")
        self.assertEqual(res.status_code, 200)
        drafts = res.json()["drafts"]

        for draft in drafts:
            squad_data = draft["data"]
            squad = squad_data["squad"]
            cost = squad_data["cost"]

            # 1. Exactly 15 players
            self.assertEqual(len(squad), 15, msg=f"Draft {draft['id']} has {len(squad)} players instead of 15")

            # 2. 15 unique player IDs
            ids = [p["id"] for p in squad]
            self.assertEqual(len(set(ids)), 15, msg=f"Draft {draft['id']} has duplicate player IDs")

            # 3. Positional quotas: 2 GKP, 5 DEF, 5 MID, 3 FWD
            pos_counts = {1: 0, 2: 0, 3: 0, 4: 0}
            team_counts = {}
            for p in squad:
                pos_counts[p["element_type"]] += 1
                team_counts[p["team"]] = team_counts.get(p["team"], 0) + 1

            self.assertEqual(pos_counts[1], 2, f"Draft {draft['id']} must have exactly 2 GKPs")
            self.assertEqual(pos_counts[2], 5, f"Draft {draft['id']} must have exactly 5 DEFs")
            self.assertEqual(pos_counts[3], 5, f"Draft {draft['id']} must have exactly 5 MIDs")
            self.assertEqual(pos_counts[4], 3, f"Draft {draft['id']} must have exactly 3 FWDs")

            # 4. Club quota: at most 3 players per club
            for t_id, cnt in team_counts.items():
                self.assertLessEqual(cnt, 3, f"Draft {draft['id']} has {cnt} players from team {t_id} (max is 3)")

            # 5. Budget limit: cost <= 1000 (£100.0m)
            self.assertLessEqual(cost, 1000, f"Draft {draft['id']} cost {cost} exceeds 1000")
            computed_cost = sum(p["now_cost"] for p in squad)
            self.assertEqual(cost, computed_cost, f"Draft {draft['id']} reported cost does not match sum of now_cost")

    # -------------------------------------------------------------
    # 3. Required Player Fields and Correct Numeric Units
    # -------------------------------------------------------------
    @patch("main.fetch_bootstrap")
    @patch("main.fetch_all_fixtures")
    def test_required_player_fields_and_units(self, mock_fixtures, mock_bootstrap):
        mock_bootstrap.return_value = self.mock_bootstrap
        mock_fixtures.return_value = self.mock_fixtures

        res = self.client.get("/api/drafts")
        drafts = res.json()["drafts"]

        required_fields = [
            "id", "name", "team_code", "element_type", "now_cost",
            "xp", "team_name", "fixture", "fixture_diff"
        ]

        for draft in drafts:
            for p in draft["data"]["squad"]:
                for field in required_fields:
                    self.assertIn(field, p, f"Player {p.get('id')} missing field {field} in draft {draft['id']}")

                # Verify numeric types and units
                self.assertIsInstance(p["now_cost"], int, "now_cost must be integer tenths (e.g. 50)")
                self.assertGreater(p["now_cost"], 30, "now_cost in tenths should be >= 30 (>= £3.0m)")
                self.assertIsInstance(p["xp"], float, "xp must be float")
                self.assertIn(p["element_type"], [1, 2, 3, 4], "element_type must be in 1..4")
                self.assertTrue(isinstance(p["fixture"], str) and len(p["fixture"]) > 0, "fixture must be non-empty string")
                self.assertIn(p["fixture_diff"], [1, 2, 3, 4, 5], "fixture_diff must be between 1 and 5")

    # -------------------------------------------------------------
    # 4. Guest Operation: No User Team ID Dependency
    # -------------------------------------------------------------
    @patch("main.fetch_bootstrap")
    @patch("main.fetch_all_fixtures")
    def test_guest_operation_no_team_id_required(self, mock_fixtures, mock_bootstrap):
        mock_bootstrap.return_value = self.mock_bootstrap
        mock_fixtures.return_value = self.mock_fixtures

        # Request with zero headers, cookies, or query parameters
        res = self.client.get("/api/drafts")
        self.assertEqual(res.status_code, 200)

    # -------------------------------------------------------------
    # 5. Authoritative Projection Consistency
    # -------------------------------------------------------------
    @patch("main.fetch_bootstrap")
    @patch("main.fetch_all_fixtures")
    def test_projection_consistency_with_authoritative_engine(self, mock_fixtures, mock_bootstrap):
        mock_bootstrap.return_value = self.mock_bootstrap
        mock_fixtures.return_value = self.mock_fixtures

        res = self.client.get("/api/drafts")
        drafts = res.json()["drafts"]

        teams_dict = {t["id"]: t for t in self.mock_teams}
        raw_elements_dict = {p["id"]: p for p in self.mock_elements}

        # Verify that for any player in the squads, their squad xp exactly matches calculate_player_projection
        for draft in drafts:
            for p in draft["data"]["squad"]:
                raw_p = raw_elements_dict[p["id"]]
                direct_proj = calculate_player_projection(
                    raw_p, 2, self.mock_fixtures, teams_dict
                )
                self.assertAlmostEqual(
                    p["xp"], direct_proj["xp"], places=2,
                    msg=f"Draft player {p['name']} xp ({p['xp']}) differs from authoritative engine ({direct_proj['xp']})"
                )

    # -------------------------------------------------------------
    # 6. Player Ineligibility & Status Filtering
    # -------------------------------------------------------------
    @patch("main.fetch_bootstrap")
    @patch("main.fetch_all_fixtures")
    def test_ineligible_players_excluded(self, mock_fixtures, mock_bootstrap):
        mock_bootstrap.return_value = self.mock_bootstrap
        mock_fixtures.return_value = self.mock_fixtures

        res = self.client.get("/api/drafts")
        drafts = res.json()["drafts"]

        ineligible_ids = {991, 992, 993}
        for draft in drafts:
            squad_ids = {p["id"] for p in draft["data"]["squad"]}
            overlap = squad_ids.intersection(ineligible_ids)
            self.assertEqual(len(overlap), 0, f"Draft {draft['id']} contains ineligible players: {overlap}")

    # -------------------------------------------------------------
    # 7. Graceful Upstream Error Handling
    # -------------------------------------------------------------
    @patch("main.fetch_bootstrap")
    def test_graceful_error_handling_on_upstream_failure(self, mock_bootstrap):
        mock_bootstrap.side_effect = Exception("FPL API Connection Timeout")

        res = self.client.get("/api/drafts")
        self.assertEqual(res.status_code, 500)
        self.assertIn("FPL API Connection Timeout", res.json()["detail"])

    # -------------------------------------------------------------
    # 8. Differentials Universe & Distinction from Balanced Spread
    # -------------------------------------------------------------
    @patch("main.fetch_bootstrap")
    @patch("main.fetch_all_fixtures")
    def test_differentials_squad_distinct_from_balanced_spread(self, mock_fixtures, mock_bootstrap):
        mock_bootstrap.return_value = self.mock_bootstrap
        mock_fixtures.return_value = self.mock_fixtures

        res = self.client.get("/api/drafts")
        self.assertEqual(res.status_code, 200)
        drafts = res.json()["drafts"]

        balanced_squad = drafts[1]["data"]["squad"]
        diff_squad = drafts[2]["data"]["squad"]

        balanced_ids = set(p["id"] for p in balanced_squad)
        diff_ids = set(p["id"] for p in diff_squad)

        # Asserts Balanced Spread and Differentials are NOT identical
        self.assertNotEqual(balanced_ids, diff_ids, "Balanced Spread and Differentials must not have identical 15 players")
        overlap = balanced_ids.intersection(diff_ids)
        self.assertLess(len(overlap), 15, "Differentials squad must contain unique differential players not in Balanced Spread")

    @patch("main.fetch_bootstrap")
    @patch("main.fetch_all_fixtures")
    def test_differentials_squad_respects_differential_universe_threshold(self, mock_fixtures, mock_bootstrap):
        mock_bootstrap.return_value = self.mock_bootstrap
        mock_fixtures.return_value = self.mock_fixtures

        res = self.client.get("/api/drafts")
        self.assertEqual(res.status_code, 200)
        diff_squad = res.json()["drafts"][2]["data"]["squad"]

        from main import DIFFERENTIAL_OWNERSHIP_THRESHOLD
        self.assertEqual(DIFFERENTIAL_OWNERSHIP_THRESHOLD, 15.0)

        for p in diff_squad:
            self.assertLessEqual(
                p["selected_by_percent"], DIFFERENTIAL_OWNERSHIP_THRESHOLD,
                f"Player {p['name']} has ownership {p['selected_by_percent']}% exceeding {DIFFERENTIAL_OWNERSHIP_THRESHOLD}%"
            )

    @patch("main.fetch_bootstrap")
    @patch("main.fetch_all_fixtures")
    def test_differentials_strictly_enforces_threshold_even_if_pool_is_starved(self, mock_fixtures, mock_bootstrap):
        # Artificially set all MIDs to high ownership (> 20%) so under-15% pool cannot form 5 MIDs
        starved_elements = []
        for el in self.mock_elements:
            copied = dict(el)
            if copied.get("element_type") == 3:
                copied["selected_by_percent"] = 25.0
            starved_elements.append(copied)

        starved_bootstrap = {
            "events": self.mock_events,
            "teams": self.mock_teams,
            "elements": starved_elements
        }
        mock_bootstrap.return_value = starved_bootstrap
        mock_fixtures.return_value = self.mock_fixtures

        res = self.client.get("/api/drafts")
        self.assertEqual(res.status_code, 200)
        drafts = res.json()["drafts"]

        # Product Rule: Under NO circumstances may any player above 15.0% enter Differentials
        from main import DIFFERENTIAL_OWNERSHIP_THRESHOLD
        diff_squad = drafts[2]["data"]["squad"]
        for p in diff_squad:
            self.assertLessEqual(
                p["selected_by_percent"], DIFFERENTIAL_OWNERSHIP_THRESHOLD,
                f"Player {p['name']} has ownership {p['selected_by_percent']}% exceeding strict ceiling {DIFFERENTIAL_OWNERSHIP_THRESHOLD}%"
            )

    # -------------------------------------------------------------
    # 9. Vercel Adapter Static Integrity Verification
    # -------------------------------------------------------------
    def test_vercel_adapter_contains_no_duplicate_math(self):
        adapter_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "app", "api-vercel", "drafts", "route.ts")
        )
        self.assertTrue(os.path.exists(adapter_path), "app/api-vercel/drafts/route.ts must exist")

        with open(adapter_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Prohibit duplicate projection math and duplicate squad builder
        self.assertNotIn("calculatePlayerProjection", content, "calculatePlayerProjection must be removed from route.ts")
        self.assertNotIn("buildSquad", content, "buildSquad must be removed from route.ts")
        self.assertNotIn("saves_per_90", content, "saves_per_90 linear calculation must be removed from route.ts")
        self.assertNotIn("defcon_per_90", content, "defcon calculation must be removed from route.ts")

        # Verify it forwards to /api/drafts
        self.assertIn("/api/drafts", content, "route.ts must forward to /api/drafts")


if __name__ == "__main__":
    unittest.main()
