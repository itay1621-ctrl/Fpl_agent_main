import os
import sys
import unittest

# Ensure the root directory containing fpl_api.py is in the module search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fpl_api import calculate_player_prices, calculate_free_transfers


class TestFPLPricingRules(unittest.TestCase):
    """
    Offline deterministic test suite for official FPL selling price calculations.
    
    Official Rule (RUL-01 & RUL-02 - premierleague.com/news/1252610):
    - When current price (CP) > purchase price (PP):
        selling_price = PP + floor((CP - PP) / 2)
      A sell-on fee of 50% (rounded down to the nearest £0.1m) applies to any profit.
    - When current price (CP) <= purchase price (PP):
        selling_price = CP (full 100% loss absorbed, no fee protection).
    - Invariant: selling_price <= current_price ALWAYS.
    """

    def test_selling_price_no_price_change(self):
        """Player price remains unchanged: selling price equals purchase price."""
        picks = [{"element": 101, "position": 1, "purchase_price": 50}]
        elements = {101: {"id": 101, "now_cost": 50, "cost_change_start": 0}}
        prices = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=[])
        
        self.assertEqual(prices[101]["purchase_price"], 5.0)
        self.assertEqual(prices[101]["selling_price"], 5.0)

    def test_selling_price_odd_rise_0_1m(self):
        """
        Rise of +£0.1m (odd rise):
        Bought at £5.0m, now £5.1m.
        Profit is £0.1m. 50% of £0.1m = £0.05m, which rounds DOWN to £0.0m.
        Selling price must remain £5.0m.
        """
        picks = [{"element": 101, "position": 1, "purchase_price": 50}]
        elements = {101: {"id": 101, "now_cost": 51, "cost_change_start": 1}}
        prices = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=[])
        
        self.assertEqual(prices[101]["purchase_price"], 5.0)
        self.assertEqual(prices[101]["selling_price"], 5.0)

    def test_selling_price_even_rise_0_2m(self):
        """
        Rise of +£0.2m (even rise):
        Bought at £5.0m, now £5.2m.
        Profit is £0.2m. 50% of £0.2m = £0.1m.
        Selling price becomes £5.1m.
        """
        picks = [{"element": 101, "position": 1, "purchase_price": 50}]
        elements = {101: {"id": 101, "now_cost": 52, "cost_change_start": 2}}
        prices = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=[])
        
        self.assertEqual(prices[101]["purchase_price"], 5.0)
        self.assertEqual(prices[101]["selling_price"], 5.1)

    def test_selling_price_odd_rise_0_3m(self):
        """
        Official Premier League Example (premierleague.com):
        Bought at £7.5m, now £7.8m.
        Profit is £0.3m. 50% of £0.3m = £0.15m, which rounds DOWN to £0.1m.
        Selling price becomes £7.6m (£7.5m + £0.1m).
        """
        picks = [{"element": 102, "position": 2, "purchase_price": 75}]
        elements = {102: {"id": 102, "now_cost": 78, "cost_change_start": 3}}
        prices = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=[])
        
        self.assertEqual(prices[102]["purchase_price"], 7.5)
        self.assertEqual(prices[102]["selling_price"], 7.6)

    def test_selling_price_even_rise_0_4m(self):
        """
        Rise of +£0.4m:
        Bought at £5.0m, now £5.4m.
        Profit is £0.4m. 50% of £0.4m = £0.2m.
        Selling price becomes £5.2m.
        """
        picks = [{"element": 103, "position": 3, "purchase_price": 50}]
        elements = {103: {"id": 103, "now_cost": 54, "cost_change_start": 4}}
        prices = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=[])
        
        self.assertEqual(prices[103]["purchase_price"], 5.0)
        self.assertEqual(prices[103]["selling_price"], 5.2)

    def test_selling_price_large_rise_0_5m(self):
        """
        Rise of +£0.5m:
        Bought at £6.0m, now £6.5m.
        Profit is £0.5m. 50% of £0.5m = £0.25m -> rounds DOWN to £0.2m.
        Selling price becomes £6.2m.
        """
        picks = [{"element": 104, "position": 4, "purchase_price": 60}]
        elements = {104: {"id": 104, "now_cost": 65, "cost_change_start": 5}}
        prices = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=[])
        
        self.assertEqual(prices[104]["purchase_price"], 6.0)
        self.assertEqual(prices[104]["selling_price"], 6.2)

    def test_selling_price_loss_0_1m(self):
        """
        Loss of -£0.1m:
        Bought at £5.8m, now £5.7m.
        Full loss absorbed: selling price drops to £5.7m.
        """
        picks = [{"element": 105, "position": 5, "purchase_price": 58}]
        elements = {105: {"id": 105, "now_cost": 57, "cost_change_start": -1}}
        prices = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=[])
        
        self.assertEqual(prices[105]["purchase_price"], 5.8)
        self.assertEqual(prices[105]["selling_price"], 5.7)

    def test_selling_price_large_loss_0_5m(self):
        """
        Loss of -£0.5m:
        Bought at £6.0m, now £5.5m.
        Full loss absorbed: selling price drops to £5.5m.
        """
        picks = [{"element": 106, "position": 6, "purchase_price": 60}]
        elements = {106: {"id": 106, "now_cost": 55, "cost_change_start": -5}}
        prices = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=[])
        
        self.assertEqual(prices[106]["purchase_price"], 6.0)
        self.assertEqual(prices[106]["selling_price"], 5.5)

    def test_selling_price_initial_squad_player_reconstruction(self):
        """
        Player in squad from GW1 with no transfers history entry:
        now_cost = 60 (£6.0m), cost_change_start = 2 (+£0.2m).
        Derived initial purchase price = 60 - 2 = 58 (£5.8m).
        Selling price = 58 + floor((60 - 58)/2) = 59 (£5.9m).
        """
        picks = [{"element": 107, "position": 7}]
        elements = {107: {"id": 107, "now_cost": 60, "cost_change_start": 2}}
        prices = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=[])
        
        self.assertEqual(prices[107]["purchase_price"], 5.8)
        self.assertEqual(prices[107]["selling_price"], 5.9)

    def test_selling_price_transfer_history_override(self):
        """
        Player transferred in during season:
        Transfer record indicates element_in_cost = 52 (£5.2m) at GW3.
        Current now_cost = 56 (£5.6m).
        Profit = 4 -> half = 2 -> selling price = 54 (£5.4m).
        """
        picks = [{"element": 108, "position": 8}]
        elements = {108: {"id": 108, "now_cost": 56, "cost_change_start": 6}}
        transfers = [
            {"element_in": 108, "element_in_cost": 52, "event": 3, "time": "2026-09-01T10:00:00Z"}
        ]
        prices = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=transfers)
        
        self.assertEqual(prices[108]["purchase_price"], 5.2)
        self.assertEqual(prices[108]["selling_price"], 5.4)

    def test_selling_price_free_hit_transfer_isolation(self):
        """
        Transfers made during a Free Hit gameweek must be excluded from permanent purchase price.
        GW4 was a Free Hit where player 109 was transferred in at 55 (£5.5m).
        Permanent purchase price must not be corrupted by the temporary FH transfer.
        """
        picks = [{"element": 109, "position": 9}]
        elements = {109: {"id": 109, "now_cost": 50, "cost_change_start": 0}}
        history_res = {
            "chips": [{"name": "freehit", "event": 4}]
        }
        transfers = [
            {"element_in": 109, "element_in_cost": 55, "event": 4, "time": "2026-09-10T10:00:00Z"}
        ]
        prices = calculate_player_prices(1, picks, elements, next_gw=6, history_res=history_res, transfers=transfers)
        
        # Free Hit transfer excluded; falls back to initial cost 50 - 0 = 50 (£5.0m)
        self.assertEqual(prices[109]["purchase_price"], 5.0)
        self.assertEqual(prices[109]["selling_price"], 5.0)

    def test_selling_price_defensive_against_corrupted_transfers(self):
        """calculate_player_prices safely handles non-list and malformed transfer inputs."""
        picks = [{"element": 110, "position": 10}]
        elements = {110: {"id": 110, "now_cost": 50, "cost_change_start": 0}}
        
        # Case A: transfers is a string or None
        prices_none = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=None)
        self.assertIn(110, prices_none)
        
        # Case B: transfers list contains non-dict junk
        corrupted = [None, "invalid", 123, [], {"valid": False}]
        prices_corrupt = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=corrupted)
        self.assertEqual(prices_corrupt[110]["purchase_price"], 5.0)
        self.assertEqual(prices_corrupt[110]["selling_price"], 5.0)

    def test_selling_price_invariant_never_exceeds_now_cost(self):
        """System Invariant: Selling price can never be greater than current market price."""
        test_cases = [(50, 48), (50, 50), (50, 51), (50, 52), (50, 60), (75, 78), (60, 55)]
        for purch, now in test_cases:
            picks = [{"element": 999, "position": 1, "purchase_price": purch}]
            elements = {999: {"id": 999, "now_cost": now, "cost_change_start": now - purch}}
            prices = calculate_player_prices(1, picks, elements, next_gw=6, history_res={}, transfers=[])
            sp = prices[999]["selling_price"]
            cp = round(now / 10.0, 1)
            self.assertLessEqual(sp, cp, f"Selling price {sp} exceeded market cost {cp}")


class TestFPLFreeTransfers(unittest.TestCase):
    """
    Offline deterministic test suite for Free Transfer accumulation and chip preservation.
    
    Official Rule (RUL-03 & RUL-04 - premierleague.com/news/1252610):
    - 1 Free Transfer granted per Gameweek.
    - Free transfers roll over up to a MAXIMUM CAP OF 5 (1 <= FT <= 5).
    - Playing Wildcard or Free Hit retains previously banked free transfers.
    """

    def test_empty_or_none_history_defaults_to_one(self):
        """New or missing history defaults safely to 1 free transfer."""
        self.assertEqual(calculate_free_transfers({}), 1)
        self.assertEqual(calculate_free_transfers(None), 1)

    def test_gw2_starting_free_transfers(self):
        """After GW1, managers enter GW2 with exactly 1 free transfer."""
        history = {
            "current": [{"event": 1, "event_transfers": 0, "event_transfers_cost": 0}],
            "chips": []
        }
        self.assertEqual(calculate_free_transfers(history), 1)

    def test_ft_accumulation_no_transfers_up_to_five_cap(self):
        """
        No transfers made across consecutive Gameweeks:
        - GW1: starts GW2 with 1 FT.
        - GW2 (0 transfers): enters GW3 with 2 FT.
        - GW3 (0 transfers): enters GW4 with 3 FT.
        - GW4 (0 transfers): enters GW5 with 4 FT.
        - GW5 (0 transfers): enters GW6 with 5 FT.
        - GW6 (0 transfers): enters GW7 with 5 FT (capped at 5).
        """
        history_gw3 = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0}
            ],
            "chips": []
        }
        self.assertEqual(calculate_free_transfers(history_gw3), 2)

        history_gw4 = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0},
                {"event": 3, "event_transfers": 0}
            ],
            "chips": []
        }
        self.assertEqual(calculate_free_transfers(history_gw4), 3)

        history_gw5 = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0},
                {"event": 3, "event_transfers": 0},
                {"event": 4, "event_transfers": 0}
            ],
            "chips": []
        }
        self.assertEqual(calculate_free_transfers(history_gw5), 4)

        history_gw6 = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0},
                {"event": 3, "event_transfers": 0},
                {"event": 4, "event_transfers": 0},
                {"event": 5, "event_transfers": 0}
            ],
            "chips": []
        }
        self.assertEqual(calculate_free_transfers(history_gw6), 5)

        # Capped at 5 in GW7:
        history_gw7 = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0},
                {"event": 3, "event_transfers": 0},
                {"event": 4, "event_transfers": 0},
                {"event": 5, "event_transfers": 0},
                {"event": 6, "event_transfers": 0}
            ],
            "chips": []
        }
        self.assertEqual(calculate_free_transfers(history_gw7), 5)

    def test_ft_consumption_single_transfer(self):
        """Making 1 transfer when holding 1 FT leaves 0 banked + 1 new = 1 FT for next GW."""
        history = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 1}
            ],
            "chips": []
        }
        self.assertEqual(calculate_free_transfers(history), 1)

    def test_ft_consumption_multiple_transfers_with_hits(self):
        """Making 3 transfers (taking hits) consumes all available FTs, leaving 1 FT for next GW."""
        history = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 3}
            ],
            "chips": []
        }
        self.assertEqual(calculate_free_transfers(history), 1)

    def test_ft_partial_consumption_from_bank(self):
        """
        Manager holds 3 FTs in GW4:
        Makes 1 transfer in GW4:
        Remaining = 3 - 1 = 2 banked + 1 awarded for GW5 = 3 FTs entering GW5.
        """
        history = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0}, # enters GW3 with 2 FT
                {"event": 3, "event_transfers": 0}, # enters GW4 with 3 FT
                {"event": 4, "event_transfers": 1}  # spends 1 of 3 -> enters GW5 with 3 FT
            ],
            "chips": []
        }
        self.assertEqual(calculate_free_transfers(history), 3)

    def test_ft_wildcard_preserves_banked_transfers(self):
        """
        Official 2026/27 Rule: Banked free transfers are preserved when Wildcard is played.
        Manager accumulated 3 FTs entering GW4.
        Plays Wildcard in GW4 (making 12 transfers).
        Enters GW5 with 3 FTs preserved!
        """
        history = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0}, # 2 FT
                {"event": 3, "event_transfers": 0}, # 3 FT
                {"event": 4, "event_transfers": 12} # Wildcard event
            ],
            "chips": [
                {"name": "wildcard", "event": 4}
            ]
        }
        self.assertEqual(calculate_free_transfers(history), 3)

    def test_ft_free_hit_preserves_banked_transfers(self):
        """
        Official 2026/27 Rule: Banked free transfers are preserved when Free Hit is played.
        Manager accumulated 2 FTs entering GW3.
        Plays Free Hit in GW3 (making 8 transfers).
        Enters GW4 with 2 FTs preserved!
        """
        history = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0}, # 2 FT
                {"event": 3, "event_transfers": 8}  # Free Hit event
            ],
            "chips": [
                {"name": "freehit", "event": 3}
            ]
        }
        self.assertEqual(calculate_free_transfers(history), 2)

    def test_ft_triple_captain_and_bench_boost_follow_normal_rules(self):
        """
        Triple Captain and Bench Boost do NOT grant free transfers.
        Transfers made count normally against available FTs.
        """
        history = {
            "current": [
                {"event": 1, "event_transfers": 0},
                {"event": 2, "event_transfers": 0}, # 2 FT entering GW3
                {"event": 3, "event_transfers": 1}  # Bench Boost played in GW3, 1 transfer made
            ],
            "chips": [
                {"name": "bboost", "event": 3}
            ]
        }
        # 2 FT - 1 used + 1 awarded = 2 FT entering GW4
        self.assertEqual(calculate_free_transfers(history), 2)

    def test_ft_invariant_always_between_one_and_five(self):
        """System Invariant: calculate_free_transfers always returns an integer in [1, 5]."""
        extreme_histories = [
            {"current": [{"event": e, "event_transfers": 20} for e in range(1, 25)], "chips": []},
            {"current": [{"event": e, "event_transfers": 0} for e in range(1, 38)], "chips": []},
            {"current": [], "chips": []}
        ]
        for h in extreme_histories:
            ft = calculate_free_transfers(h)
            self.assertGreaterEqual(ft, 1)
            self.assertLessEqual(ft, 5)


if __name__ == "__main__":
    unittest.main()
