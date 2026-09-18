import os
import json
import time
import requests
import pandas as pd
import numpy as np

# Cache directory to avoid spamming the FPL API and speeding up iterations
CACHE_DIR = "backtest_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def get_bootstrap():
    cache_path = os.path.join(CACHE_DIR, "bootstrap.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    print("Fetching Bootstrap data...")
    resp = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/")
    data = resp.json()
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data

def get_element_summary(element_id):
    cache_path = os.path.join(CACHE_DIR, f"element_{element_id}.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    resp = requests.get(f"https://fantasy.premierleague.com/api/element-summary/{element_id}/")
    data = resp.json()
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    time.sleep(0.05)  # Slight delay to respect FPL API rate limits
    return data

def build_historical_dataset():
    bootstrap = get_bootstrap()
    elements = bootstrap.get("elements", [])
    
    all_histories = []
    
    print(f"Fetching history for {len(elements)} players...")
    for i, el in enumerate(elements):
        if i > 0 and i % 100 == 0:
            print(f"Processed {i}/{len(elements)} players...")
            
        summary = get_element_summary(el["id"])
        history = summary.get("history", [])
        for gw_stats in history:
            gw_stats["element"] = el["id"]
            gw_stats["element_type"] = el["element_type"]
            all_histories.append(gw_stats)
            
    df = pd.DataFrame(all_histories)
    # Ensure chronologically sorted per player to avoid data leakage
    df = df.sort_values(by=["element", "round"])
    return df

def generate_targets(df):
    """
    Creates target variables for 1GW, 3GW, and 5GW horizons to avoid leakage.
    We need to know what the player ACTUALLY scored in the FUTURE, based ONLY on past data.
    """
    # Next GW points
    df['target_1gw'] = df.groupby('element')['total_points'].shift(-1)
    
    # Next 3 GWs total points
    df['target_3gw'] = (df.groupby('element')['total_points'].shift(-1) + 
                        df.groupby('element')['total_points'].shift(-2) + 
                        df.groupby('element')['total_points'].shift(-3))
    
    # Next 5 GWs total points
    df['target_5gw'] = (df.groupby('element')['total_points'].shift(-1) + 
                        df.groupby('element')['total_points'].shift(-2) + 
                        df.groupby('element')['total_points'].shift(-3) +
                        df.groupby('element')['total_points'].shift(-4) +
                        df.groupby('element')['total_points'].shift(-5))
                        
    return df

def run_baseline_backtest():
    print("Building historical dataset...")
    df = build_historical_dataset()
    if df.empty:
        print("No historical data found. Season might not have started yet.")
        return

    df = generate_targets(df)
    
    print("\nCalculating Baseline Model...")
    # Baseline Model: "What the player averaged in the last 4 GWs is what they will score next."
    # We use expanding mean up to the last 4 games, STRICTLY BEFORE the target GW.
    df['baseline_pred_1gw'] = df.groupby('element')['total_points'].transform(lambda x: x.rolling(4, min_periods=1).mean())
    df['baseline_pred_3gw'] = df['baseline_pred_1gw'] * 3
    df['baseline_pred_5gw'] = df['baseline_pred_1gw'] * 5
    
    # Filter only rows where we have targets to evaluate (ignoring players with 0 minutes to test pure predictive power? 
    # No, as the report said: DO NOT filter 0 minutes. We must predict 0 minutes as well.)
    
    eval_df_1 = df.dropna(subset=['target_1gw', 'baseline_pred_1gw'])
    mae_1gw = np.mean(np.abs(eval_df_1['target_1gw'] - eval_df_1['baseline_pred_1gw'])) if not eval_df_1.empty else 0
    
    eval_df_3 = df.dropna(subset=['target_3gw', 'baseline_pred_3gw'])
    mae_3gw = np.mean(np.abs(eval_df_3['target_3gw'] - eval_df_3['baseline_pred_3gw'])) if not eval_df_3.empty else 0
    
    eval_df_5 = df.dropna(subset=['target_5gw', 'baseline_pred_5gw'])
    mae_5gw = np.mean(np.abs(eval_df_5['target_5gw'] - eval_df_5['baseline_pred_5gw'])) if not eval_df_5.empty else 0
    
    print("\n" + "="*40)
    print("  BASELINE BACKTEST RESULTS  ")
    print("="*40)
    print("Model: 4-GW Simple Moving Average (Baseline)")
    print(f"1GW MAE (Mean Absolute Error): {mae_1gw:.2f} points")
    print(f"3GW MAE (Mean Absolute Error): {mae_3gw:.2f} points")
    print(f"5GW MAE (Mean Absolute Error): {mae_5gw:.2f} points")
    print("="*40)
    print("Goal: Our new AI Recommendation Engine MUST beat these numbers")
    print("to prove it actually adds value over simple guessing.")

if __name__ == "__main__":
    run_baseline_backtest()
