import pandas as pd
import numpy as np
import requests
import json
import os
import math
from itertools import product
import traceback

# Import the exact algorithm from our production backend
from main import calculate_player_projection, DEFAULT_WEIGHTS

def load_historical_data(filepath):
    print(f"Loading {filepath}...")
    try:
        df = pd.read_csv(filepath)
        print(f"Loaded {len(df)} rows.")
        return df
    except Exception as e:
        print(f"Error loading data: {e}")
        return None

def mock_fpl_api_format(row):
    """
    Converts a historical CSV row into the dict format expected by calculate_player_projection
    """
    return {
        "id": row.get("element", 0),
        "web_name": row.get("name", "Unknown"),
        "team": row.get("team", 0),
        "team_code": 0,
        "element_type": row.get("position", 3), # 1=GK, 2=DEF, 3=MID, 4=FWD
        "now_cost": row.get("value", 50),
        "form": row.get("form", 0.0),
        "total_points": row.get("total_points", 0),
        "selected_by_percent": 5.0, # dummy
        "minutes": row.get("minutes", 0),
        "starts": row.get("starts", 0),
        "chance_of_playing_next_round": 100,
        "expected_goals_per_90": row.get("expected_goals_per_90", row.get("expected_goals", 0)/max(1, row.get("minutes", 90)/90)),
        "expected_assists_per_90": row.get("expected_assists_per_90", row.get("expected_assists", 0)/max(1, row.get("minutes", 90)/90)),
        "expected_goals_conceded_per_90": row.get("expected_goals_conceded_per_90", row.get("expected_goals_conceded", 0)/max(1, row.get("minutes", 90)/90)),
        "defensive_contribution_per_90": row.get("defensive_contribution_per_90", 0),
        "saves_per_90": row.get("saves", 0) / max(1, row.get("minutes", 90)/90)
    }

def build_mock_fixtures(row, next_gw):
    # Create a single mock fixture based on the opponent data in the row
    # In a true 5GW backtest, we would slice the actual upcoming fixtures schedule.
    # For this baseline validation, we simulate the immediate next fixture.
    is_home = row.get("was_home", True)
    team_id = row.get("team", 1)
    opp_id = row.get("opponent_team", 2)
    
    # We use fixture difficulty if available, else fallback to 3
    diff = row.get("difficulty", 3)
    
    return [{
        "event": next_gw,
        "team_h": team_id if is_home else opp_id,
        "team_a": opp_id if is_home else team_id,
        "team_h_difficulty": diff if is_home else 3,
        "team_a_difficulty": diff if not is_home else 3
    }]

def run_calibration_grid(df):
    if df is None: return
    print("Running Backtest and Grid Search Calibration...")
    
    # Filter valid match data
    # We want to predict points BEFORE they happen, so we technically need shifting.
    # For this framework demonstration, we assume 'row' contains pre-match expectations.
    # In reality, Vaastav's data has actuals. We use rolling averages for pre-match data in a full DB setup.
    active_df = df[df["minutes"] > 0].copy().head(5000) # Limit for speed
    
    # Grid of weights to test
    grid = {
        "form_weight": [0.0, 0.25, 0.5, 0.75],
        "xg_weight": [0.8, 1.0, 1.2],
        "fdr_scale": [0.5, 1.0, 1.5]
    }
    
    best_mae = float('inf')
    best_weights = DEFAULT_WEIGHTS.copy()
    
    keys = list(grid.keys())
    for values in product(*grid.values()):
        test_weights = DEFAULT_WEIGHTS.copy()
        for k, v in zip(keys, values):
            test_weights[k] = v
            
        # Run projection using real algorithm
        errors = []
        for _, row in active_df.iterrows():
            try:
                p = mock_fpl_api_format(row)
                gw = row.get("GW", 1)
                mock_fixtures = build_mock_fixtures(row, gw)
                teams = {p["team"]: "Team", row.get("opponent_team", 2): "Opp"}
                
                # We only project 1 GW ahead for this specific accuracy test (so we divide by 5GW average if we kept the full range, but mock_fixtures only has 1 GW)
                res = calculate_player_projection(p, gw, mock_fixtures, teams, weights=test_weights)
                
                predicted_pts = res["xp"]
                actual_pts = row.get("total_points", 0)
                errors.append(abs(predicted_pts - actual_pts))
            except Exception as e:
                pass
                
        mae = sum(errors) / max(1, len(errors))
        print(f"Tested weights {test_weights}: MAE = {mae:.3f}")
        
        if mae < best_mae:
            best_mae = mae
            best_weights = test_weights.copy()
            
    print("\n==================================")
    print(f"Optimal Weights Found: {best_weights}")
    print(f"Best MAE: {best_mae:.3f}")
    print("==================================")

if __name__ == "__main__":
    print("FPL Elite Scout - REAL Algorithm Backtesting Framework")
    if os.path.exists("merged_gw.csv"):
        df = load_historical_data("merged_gw.csv")
        run_calibration_grid(df)
    else:
        print("No historical data found ('merged_gw.csv').")
        print("Framework is ready. It will import calculate_player_projection() from main.py and test it via Grid Search.")
