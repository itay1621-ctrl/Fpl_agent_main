import pandas as pd
import numpy as np
import requests
import json
import os
import math

# FPL Elite Scout - Historical Backtesting Engine (V3)
# This script is designed to run against historical FPL datasets

def load_historical_data(filepath):
    print(f"Loading {filepath}...")
    try:
        df = pd.read_csv(filepath)
        print(f"Loaded {len(df)} rows.")
        return df
    except Exception as e:
        print(f"Error loading data: {e}")
        return None

def simulate_projection(row):
    try:
        minutes = row.get("minutes", 0)
        expected_goals = row.get("expected_goals", 0)
        expected_assists = row.get("expected_assists", 0)
        
        predicted_pts = (expected_goals * 5) + (expected_assists * 3)
        if minutes > 60:
            predicted_pts += 2
        elif minutes > 0:
            predicted_pts += 1
            
        return max(0.0, predicted_pts)
    except:
        return 0.0

def run_backtest(df):
    if df is None: return
    print("Running Backtest on historical data...")
    active_df = df[df["minutes"] > 0].copy()
    active_df["v3_projection"] = active_df.apply(simulate_projection, axis=1)
    active_df["error"] = active_df["v3_projection"] - active_df["total_points"]
    mae = active_df["error"].abs().mean()
    rmse = math.sqrt((active_df["error"] ** 2).mean())
    print("\n--- BACKTEST RESULTS ---")
    print(f"Sample Size: {len(active_df)} player-matches")
    print(f"Mean Absolute Error (MAE): {mae:.2f} pts/match")
    print(f"Root Mean Square Error (RMSE): {rmse:.2f} pts/match")

if __name__ == "__main__":
    print("FPL Elite Scout - Backtesting Framework")
    if os.path.exists("merged_gw.csv"):
        df = load_historical_data("merged_gw.csv")
        run_backtest(df)
    else:
        print("No historical data found. Framework ready for execution.")
