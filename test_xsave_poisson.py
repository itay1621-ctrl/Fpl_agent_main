import math
import sys
import unittest

sys.path.insert(0, ".")
import main

class TestPoissonXSave(unittest.TestCase):
    """
    Focused regression test suite for production goalkeeper save-point prediction
    using Poisson expectation: E[floor(S / 3)] where S ~ Poisson(lambda).
    """

    def setUp(self):
        # Neutral teams where strength multipliers evaluate cleanly
        self.teams_neutral = {
            1: {"id": 1, "short_name": "ARS", "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1100, "strength_attack_away": 1100},
            2: {"id": 2, "short_name": "CHE", "strength_defence_home": 1100, "strength_attack_home": 1100, "strength_defence_away": 1155, "strength_attack_away": 1155}
            # For home match (is_home=True), opp_attack_away=1155 gives def_multiplier = (1100 / 1155) * 1.05 = 1.0 exactly
        }
        self.fixture_sgw = [
            {"event": 38, "team_h": 1, "team_a": 2, "team_h_difficulty": 3, "team_a_difficulty": 3}
        ]

    def make_player(self, pos, mins=900, starts=10, saves_90=0.0, xg_90=0.0, xa_90=0.0, xgc_90=0.0, defcon_90=0.0, cop=100):
        return {
            "id": 1000 + pos,
            "web_name": f"Player_Pos{pos}",
            "team": 1,
            "team_code": 1,
            "element_type": pos,
            "now_cost": 50,
            "minutes": mins,
            "starts": starts,
            "expected_goals_per_90": xg_90,
            "expected_assists_per_90": xa_90,
            "expected_goals_conceded_per_90": xgc_90,
            "defensive_contribution_per_90": defcon_90,
            "saves_per_90": saves_90,
            "chance_of_playing_next_round": cop,
            "form": "0.0",
            "total_points": 50
        }

    # -------------------------------------------------------------
    # 1. Lambda target checks (Requirements 1 - 7)
    # -------------------------------------------------------------
    def test_poisson_xsave_values_at_integer_lambdas(self):
        """
        Verify exact Poisson expected save points at integer lambdas:
        1. lambda = 0 -> 0.0000
        2. lambda = 1 -> approx 0.0809
        3. lambda = 2 -> approx 0.3401
        4. lambda = 3 -> approx 0.6646
        5. lambda = 4 -> approx 0.9991
        6. lambda = 5 -> approx 1.3332
        7. lambda = 6 -> approx 1.6667
        """
        expected_targets = {
            0.0: 0.0000,
            1.0: 0.0809,
            2.0: 0.3401,
            3.0: 0.6646,
            4.0: 0.9991,
            5.0: 1.3332,
            6.0: 1.6667,
        }
        for lam, exp_val in expected_targets.items():
            actual_val = main.calculate_poisson_xsave(lam)
            self.assertAlmostEqual(
                actual_val, exp_val, places=4,
                msg=f"Mismatch at lambda = {lam}: got {actual_val:.6f}, expected {exp_val:.4f}"
            )

    def test_poisson_xsave_edge_cases(self):
        """Verify negative, zero, and non-finite inputs return exactly 0.0."""
        self.assertEqual(main.calculate_poisson_xsave(-1.0), 0.0)
        self.assertEqual(main.calculate_poisson_xsave(0.0), 0.0)
        self.assertEqual(main.calculate_poisson_xsave(float("nan")), 0.0)
        self.assertEqual(main.calculate_poisson_xsave(float("inf")), 0.0)

    # -------------------------------------------------------------
    # 2. Zero-minute requirement (Requirement 8)
    # -------------------------------------------------------------
    def test_zero_expected_minutes_has_zero_xsave(self):
        """
        When dyn_expected_minutes == 0, goalkeeper save points must remain exactly 0.
        """
        # Case A: Goalkeeper with 0 appearances/minutes
        gkp_bench = self.make_player(pos=1, mins=0, starts=0, saves_90=4.5)
        proj_bench = main.calculate_player_projection(gkp_bench, 38, self.fixture_sgw, self.teams_neutral)
        self.assertEqual(proj_bench["expected_minutes"], 0.0)
        self.assertEqual(proj_bench["xp"], 0.0)

        # Case B: Goalkeeper with 0% chance of playing (injured / red card)
        gkp_injured = self.make_player(pos=1, mins=900, starts=10, saves_90=4.5, cop=0)
        proj_injured = main.calculate_player_projection(gkp_injured, 38, self.fixture_sgw, self.teams_neutral)
        self.assertEqual(proj_injured["expected_minutes"], 0.0)
        self.assertEqual(proj_injured["xp"], 0.0)

    # -------------------------------------------------------------
    # 3. DGW independent calculation requirement (Requirement 9)
    # -------------------------------------------------------------
    def test_dgw_fixtures_calculated_independently(self):
        """
        In a Double Gameweek, each fixture must calculate its own Poisson xSave
        using that fixture's lambda, rather than calculating Poisson over the sum of lambdas.
        """
        # Opponent with def_multiplier = 1.0 (home_adv cancels)
        teams_dgw = {
            1: {"id": 1, "short_name": "ARS"},
            2: {"id": 2, "short_name": "CHE", "strength_defence_away": 1155, "strength_attack_away": 1155},
            3: {"id": 3, "short_name": "LIV", "strength_defence_away": 1155, "strength_attack_away": 1155}
        }
        # Two home fixtures in same GW (GW 38)
        fixture_dgw = [
            {"event": 38, "team_h": 1, "team_a": 2, "team_h_difficulty": 3, "team_a_difficulty": 3},
            {"event": 38, "team_h": 1, "team_a": 3, "team_h_difficulty": 3, "team_a_difficulty": 3}
        ]

        # Goalkeeper with 3.0 saves/90 -> lambda = 3.0 per fixture, xgc_90 = 1.0
        gkp = self.make_player(pos=1, mins=900, starts=10, saves_90=3.0, xgc_90=1.0)
        proj_dgw = main.calculate_player_projection(gkp, 38, fixture_dgw, teams_dgw)

        # Each fixture components:
        # Appearance = 2.0
        # Clean sheet at xgc=1.0: 4.0 * exp(-1.0)
        # GC penalty: - ((1.0 / 2) - (1 - exp(-2)) / 4)
        # Save points: Poisson(3.0) ~ 0.6646
        fix_xp = 2.0 + 4.0 * math.exp(-1.0) - ((0.5) - (1.0 - math.exp(-2.0)) / 4.0) + main.calculate_poisson_xsave(3.0)
        
        # Verify that independently summing 2 fixtures yields 2 * fix_xp
        expected_dgw_xp = round(2.0 * fix_xp, 2)
        self.assertEqual(proj_dgw["xp"], expected_dgw_xp)

        # Verify that independent calculation does NOT equal aggregating lambda to 6.0
        # If incorrectly aggregated over sum(lambda)=6.0: Poisson(6.0) ~ 1.6667 vs 2 * Poisson(3.0) ~ 1.3292
        xsave_indep = 2 * main.calculate_poisson_xsave(3.0)
        xsave_agg = main.calculate_poisson_xsave(6.0)
        self.assertNotEqual(round(xsave_indep, 3), round(xsave_agg, 3))

    # -------------------------------------------------------------
    # 4. Non-GK positions requirement (Requirement 10)
    # -------------------------------------------------------------
    def test_non_gk_positions_have_zero_xsave(self):
        """DEF, MID, and FWD players must always have xSave = 0.0 even if saves_per_90 is set."""
        for pos in [2, 3, 4]:
            p_with_saves = self.make_player(pos=pos, mins=900, starts=10, saves_90=5.0, xg_90=0.2, xa_90=0.1, xgc_90=1.0)
            p_zero_saves = self.make_player(pos=pos, mins=900, starts=10, saves_90=0.0, xg_90=0.2, xa_90=0.1, xgc_90=1.0)
            
            proj_with = main.calculate_player_projection(p_with_saves, 38, self.fixture_sgw, self.teams_neutral)
            proj_zero = main.calculate_player_projection(p_zero_saves, 38, self.fixture_sgw, self.teams_neutral)
            
            self.assertEqual(
                proj_with["xp"], proj_zero["xp"],
                msg=f"Position {pos} projection differed when saves_per_90 was present!"
            )

    # -------------------------------------------------------------
    # 5. Non-xSave components unchanged (Requirement 11)
    # -------------------------------------------------------------
    def test_non_xsave_components_remain_unchanged(self):
        """
        Verify that expected minutes, xAtt, clean sheet, DefCon, goals-conceded penalty,
        and appearances remain exactly as intended.
        """
        # Goalkeeper with xgc_90 = 1.0 (triggers clean sheet and goals conceded penalty)
        gkp = self.make_player(pos=1, mins=900, starts=10, saves_90=3.0, xgc_90=1.0)
        proj = main.calculate_player_projection(gkp, 38, self.fixture_sgw, self.teams_neutral)

        # Expected mathematical components:
        # 1. Expected minutes: 90.0
        self.assertEqual(proj["expected_minutes"], 90.0)
        # 2. Appearance: 2.0
        exp_app = 2.0
        # 3. Clean sheet at xgc=1.0, cs_pts=4: 4 * exp(-1.0) ~ 1.471518
        exp_cs = 4.0 * math.exp(-1.0)
        # 4. DefCon: 0.0 (GK exemption)
        exp_defcon = 0.0
        # 5. Goals conceded penalty: - ((1.0 / 2) - (1 - exp(-2)) / 4) ~ -0.283834
        exp_gc_pen = - ((1.0 / 2.0) - (1.0 - math.exp(-2.0)) / 4.0)
        # 6. Poisson xSave at lambda=3.0: ~ 0.664603
        exp_xsave = main.calculate_poisson_xsave(3.0)

        total_expected = exp_app + exp_cs + exp_defcon + exp_gc_pen + exp_xsave
        self.assertEqual(proj["xp"], round(total_expected, 2))

    # -------------------------------------------------------------
    # 6. Comparison against Linear Baseline
    # -------------------------------------------------------------
    def test_debiasing_effect_relative_to_linear(self):
        """
        Demonstrate that Poisson removes the systematic overprediction from Linear:
        At lambda = 3.0: Linear was 1.0000, Poisson is 0.6646 (-0.3354 delta).
        At lambda = 1.0: Linear was 0.3333, Poisson is 0.0809 (-0.2524 delta).
        """
        gkp_lam3 = self.make_player(pos=1, mins=900, starts=10, saves_90=3.0, xgc_90=1.0)
        proj = main.calculate_player_projection(gkp_lam3, 38, self.fixture_sgw, self.teams_neutral)

        linear_xsave = 3.0 / 3.0  # 1.0
        poisson_xsave = main.calculate_poisson_xsave(3.0)  # ~ 0.6646

        # Base components without saves:
        base_components = 2.0 + 4.0 * math.exp(-1.0) - ((0.5) - (1.0 - math.exp(-2.0)) / 4.0)
        self.assertEqual(proj["xp"], round(base_components + poisson_xsave, 2))
        self.assertAlmostEqual(linear_xsave - poisson_xsave, 0.3354, places=4)


if __name__ == "__main__":
    unittest.main()
