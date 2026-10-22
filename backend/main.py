from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
from fpl_api import fetch_bootstrap, fetch_user_team, fetch_fixtures, fetch_all_fixtures
import math
import requests
import os
import json
import logging
import traceback
import time
from fastapi import Request
import datetime

app = FastAPI(title="FPL Elite Scout API")

# Setup Error Monitoring Logger
os.makedirs("logs", exist_ok=True)
import sys
logging.basicConfig(
    level=logging.ERROR, 
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/error_log.txt'),
        logging.StreamHandler(sys.stdout)
    ]
)

@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        if response.status_code >= 500:
            logging.error(f"{request.method} {request.url.path} | Status: {response.status_code} | Time: {time.time() - start_time:.3f}s")
        return response
    except Exception as e:
        logging.error(f"FATAL {request.method} {request.url.path} | Exception: {str(e)}\n{traceback.format_exc()}")
        raise

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Default calibrated weights (to be updated by Backtest findings)
DEFAULT_WEIGHTS = {
    "form_weight": 0.5,
    "defcon_weight": 0.033,  # 1/30
    "xg_weight": 1.0,
    "xa_weight": 1.0,
    "fdr_scale": 1.0,
    "opportunity_cost": 2.0
}

# --- DECISION ENGINE LAYER ---
def decision_engine_score(c):
    score = c["xp"]
    if "Low (Minutes Uncertainty)" in c.get("confidence", ""):
        score *= 0.60
    elif "Rotation Risk / Bench" in c.get("reason", ""):
        score *= 0.75
    return score

import datetime
import os
import json

_prediction_cache = set()
_transfer_cache = set()

def log_prediction(player_data, gw, context=""):
    try:
        today = str(datetime.date.today())
        player_id = player_data["id"]
        cache_key = (player_id, gw, today)
        if cache_key in _prediction_cache:
            return
            
        _prediction_cache.add(cache_key)
        
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "predictions_log.jsonl")
        
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "gw": gw,
            "player_id": player_id,
            "player_name": player_data["name"],
            "team": player_data["team"],
            "position": player_data["pos_code"],
            "price": player_data["cost"],
            "xp": player_data["xp"],
            "expected_minutes": player_data.get("expected_minutes", 0),
            "rotation_risk": "Rotation Risk / Bench" in player_data.get("reason", ""),
            "start_probability": player_data.get("prob", 1.0),
            "fixture_diff": player_data.get("fixture_diff", 0),
            "confidence": player_data.get("confidence", ""),
            "decision_score": decision_engine_score(player_data),
            "context": context
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"Failed to log prediction: {e}")

def log_transfer_decision(gw, player_sold, player_bought, net_gain, recommendation):
    try:
        today = str(datetime.date.today())
        cache_key = (player_sold["id"] if player_sold else 0, player_bought["id"] if player_bought else 0, gw, today)
        if cache_key in _transfer_cache:
            return
            
        _transfer_cache.add(cache_key)
        
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "transfers_log.jsonl")
        
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "gw": gw,
            "player_sold": player_sold["name"] if player_sold else None,
            "player_sold_id": player_sold["id"] if player_sold else None,
            "player_bought": player_bought["name"] if player_bought else None,
            "player_bought_id": player_bought["id"] if player_bought else None,
            "predicted_5gw_gain": round(net_gain, 2),
            "decision_score_sold": decision_engine_score(player_sold) if player_sold else 0,
            "decision_score_bought": decision_engine_score(player_bought) if player_bought else 0,
            "recommendation": recommendation
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"Failed to log transfer: {e}")

def calculate_poisson_xsave(lambda_val: float) -> float:
    """
    Computes expected FPL goalkeeper save points:
    E[floor(S / 3)] where S ~ Poisson(lambda_val).
    Equivalently: sum_{k=3}^60 floor(k / 3) * P(S = k).
    Uses a numerically stable recurrence avoiding large factorials or exponents.
    """
    if lambda_val <= 0.0 or math.isnan(lambda_val) or math.isinf(lambda_val):
        return 0.0
    prob = math.exp(-lambda_val)
    expected_save_pts = 0.0
    for k in range(1, 61):
        prob *= lambda_val / k
        if k >= 3:
            pts = k // 3
            expected_save_pts += pts * prob
        if prob < 1e-12 and k > lambda_val:
            break
    return expected_save_pts

def calculate_player_projection(p, next_gw, upcoming_fixtures_raw, teams, weights=None):
    if weights is None:
        weights = DEFAULT_WEIGHTS
        
    team_id_fpl = p["team"]
    pos_code = p["element_type"]
    
    # 1. Availability
    chance = p.get("chance_of_playing_next_round")
    availability_prob = 1.0 if chance is None else float(chance) / 100.0
    
    # 2. Expected Minutes (Realistic Model)
    total_mins = p.get("minutes", 0)
    starts = p.get("starts", 0)
    cost = p.get("now_cost", 0) / 10.0
    own_pct = float(p.get("selected_by_percent", 0) or 0)
    
    # Safe calculation for xMins
    if starts > 0:
        mins_per_app = min(90, total_mins / starts)
        # If very low sample size (<180 mins / 1-2 starts) and NOT a premium proven asset (cost < 7.0 and own < 5.0%):
        # temper minutes toward ~60 mins to account for bench/rotation volatility
        if total_mins < 180 and cost < 7.0 and own_pct < 5.0:
            mins_per_app = min(mins_per_app, 60.0)
    elif total_mins > 0:
        mins_per_app = 20 # sub appearances only
    else:
        mins_per_app = 0
        
    form_val = float(p.get("form", 0) or 0)
    
    # Only upgrade minutes if they actually have some solid playing time or starts
    # A single goal in 10 mins shouldn't make them a starter.
    if form_val > 3.0 and mins_per_app < 45 and starts > 0:
        mins_per_app = min(75, mins_per_app + 15) # Momentum / breaking into team


    base_expected_minutes = mins_per_app
    if base_expected_minutes > 90: base_expected_minutes = 90
    base_cop = availability_prob
    expected_minutes = base_expected_minutes * base_cop # Store for confidence metric
    
    # 3. Base Per-90 Stats with Regression to the Mean (Shrinkage)
    raw_xg_90 = float(p.get("expected_goals_per_90", 0) or 0)
    raw_xa_90 = float(p.get("expected_assists_per_90", 0) or 0)
    raw_xgc_90 = float(p.get("expected_goals_conceded_per_90", 0) or 0)
    raw_defcon_90 = float(p.get("defensive_contribution_per_90", 0) or 0)

    # Reality caps: Prevent extreme small-sample noise from exceeding world-class ceilings
    max_xg_cap = 0.30 if pos_code in [1, 2] else (0.65 if pos_code == 3 else 0.95)
    max_xa_cap = 0.50
    raw_xg_90 = min(raw_xg_90, max_xg_cap)
    raw_xa_90 = min(raw_xa_90, max_xa_cap)
    
    # Shrinkage factor based on total_mins to avoid SSS (Small Sample Size) bias
    # If a player played < 180 mins (<2 full games), use a smooth progressive curve
    if total_mins < 180:
        weight = (total_mins / 450.0) ** 1.4
    else:
        weight = min(1.0, total_mins / 450.0)
    
    baseline_xg = 0.05 if pos_code in [1, 2] else (0.15 if pos_code == 3 else 0.3)
    baseline_xa = 0.05 if pos_code == 1 else 0.1
    baseline_xgc = 1.5
    baseline_defcon = 4.0 if pos_code in [1, 2] else 2.0
    
    xg_90 = (weight * raw_xg_90 + (1 - weight) * baseline_xg) * weights["xg_weight"]
    xa_90 = (weight * raw_xa_90 + (1 - weight) * baseline_xa) * weights["xa_weight"]
    xgc_90 = weight * raw_xgc_90 + (1 - weight) * baseline_xgc
    defcon_90 = weight * raw_defcon_90 + (1 - weight) * baseline_defcon

    # 4. Form / Momentum Proxy
    # Cap form multiplier to avoid insane spikes from a single haul
    form_multiplier = 1.0 + (min(6.0, max(0, form_val)) / 30.0) 
    xg_90 *= form_multiplier
    xa_90 *= form_multiplier

    # FPL Rule 2024/2025: Defensive Contributions points
    # Goalkeepers do NOT earn Defensive Contribution points (FPL Rule).
    # Defenders need 10 actions (CBIT), Mid/Fwd need 12 actions (CBIRT) for +2 points.
    import math
    if pos_code == 1:
        xDefcon_90 = 0.0
    else:
        defcon_threshold = 10 if pos_code == 2 else 12
        defcon_std = max(defcon_90 * 0.35, 1.0)
        z = (defcon_90 - defcon_threshold) / defcon_std
        prob_cross_threshold = 1 / (1 + math.exp(-1.7 * z)) if defcon_90 > 0 else 0
        xDefcon_90 = prob_cross_threshold * 2.0
    
    goal_pts = {1: 6, 2: 6, 3: 5, 4: 4}.get(pos_code, 4)
    assist_pts = 3
    
    xAtt_90 = (xg_90 * goal_pts) + (xa_90 * assist_pts)
    cs_pts = {1: 4, 2: 4, 3: 1, 4: 0}.get(pos_code, 0)
    cs_prob_90 = math.exp(-xgc_90) if xgc_90 > 0 else 0.5
    saves_per_90 = float(p.get("saves_per_90", 0) or 0) if pos_code == 1 else 0.0
    
    gw_range = min(5, 38 - next_gw + 1)
    
    next_gw_opponents = []
    next_gw_diffs = []
    fixtures_found = 0
    
    total_5gw_projection = 0.0
    next_gw_projection = 0.0
    
    for gw_inc in range(gw_range):

        # Dynamic Expected Minutes & Injury Recovery Model
        # Immediate GW uses base_cop; subsequent gameweeks model gradual recovery
        if gw_inc == 0:
            current_cop = base_cop
        else:
            current_cop = min(1.0, base_cop + (gw_inc * 0.25)) if base_cop > 0 else 0.0
        dyn_expected_minutes = base_expected_minutes * current_cop
        target_gw = next_gw + gw_inc
        gw_fixs = [f for f in upcoming_fixtures_raw if f.get("event") == target_gw]
        player_fixs = [f for f in gw_fixs if f["team_h"] == team_id_fpl or f["team_a"] == team_id_fpl]
        
        gw_proj = 0.0
        
        for f in player_fixs:
            fixtures_found += 1
            is_home = (f["team_h"] == team_id_fpl)
            diff = f["team_h_difficulty"] if is_home else f["team_a_difficulty"]
            
            opp_id = f["team_a"] if is_home else f["team_h"]
            
            if gw_inc == 0:
                opp_name = teams.get(opp_id, {}).get('short_name', 'UNK')
                next_gw_opponents.append(f"{opp_name} ({'H' if is_home else 'A'})")
                next_gw_diffs.append(diff)
            
            # Robust FDR-based Opponent Strength & Home Advantage
            home_adv = 1.05 if is_home else 0.95
            
            # Attacking multiplier: baseline FDR 3 = 1.0 (FDR 2 -> +10%, FDR 4 -> -10%, FDR 5 -> -20%)
            fdr_att_factor = 1.0 + (3 - diff) * 0.10
            att_multiplier = max(0.65, min(1.40, fdr_att_factor * home_adv))
            
            # Defending multiplier on opponent goal threat (FDR 2 -> 0.82, FDR 4 -> 1.18, FDR 5 -> 1.36)
            fdr_def_factor = 1.0 + (diff - 3) * 0.18
            def_multiplier = max(0.65, min(1.60, fdr_def_factor / home_adv))
            
            match_xAtt = xAtt_90 * (dyn_expected_minutes / 90.0) * att_multiplier
            
            # Clean sheet
            match_xgc = (xgc_90 * (dyn_expected_minutes / 90.0)) * def_multiplier
            team_match_xgc = xgc_90 * def_multiplier
            team_cs_prob = (
                math.exp(-team_match_xgc)
                if team_match_xgc > 0
                else 0.5
            )
            prob_60_mins = (
                max(
                    0.0,
                    min(
                        1.0,
                        (dyn_expected_minutes - 30.0) / 60.0
                    )
                )
                if dyn_expected_minutes > 30
                else 0.0
            )
            match_xDef = prob_60_mins * team_cs_prob * cs_pts
            
            # Goalkeeper Expected Saves (Poisson model: E[floor(S / 3)])
            match_lambda_saves = (
                saves_per_90 * (dyn_expected_minutes / 90.0) * def_multiplier
                if (pos_code == 1 and dyn_expected_minutes > 0)
                else 0.0
            )
            match_xSave = calculate_poisson_xsave(match_lambda_saves)
            match_xDefcon = xDefcon_90 * (dyn_expected_minutes / 90.0)
            
            match_gc_penalty = 0.0
            if pos_code in [1, 2] and match_xgc > 0:
                match_gc_penalty = -(
                    (match_xgc / 2.0)
                    - (1.0 - math.exp(-2.0 * match_xgc)) / 4.0
                )
            
            appearance_pts = 0
            if dyn_expected_minutes >= 60: appearance_pts = 2 * current_cop
            elif dyn_expected_minutes > 0: appearance_pts = 1 * current_cop
            
            gw_proj += (
                match_xAtt
                + match_xDef
                + match_xSave
                + match_xDefcon
                + match_gc_penalty
                + appearance_pts
            )
            
        if gw_inc == 0:
            next_gw_projection = gw_proj
        total_5gw_projection += gw_proj
        
    total_5gw_projection = max(0.0, total_5gw_projection)
    
    if not next_gw_opponents:
        next_gw_opponent = "Blank"
        next_gw_diff = 5
    elif len(next_gw_opponents) == 1:
        next_gw_opponent = next_gw_opponents[0]
        next_gw_diff = next_gw_diffs[0]
    else:
        next_gw_opponent = ", ".join(next_gw_opponents)
        next_gw_diff = int(round(sum(next_gw_diffs) / len(next_gw_diffs)))
    
    # Confidence metrics based on uncertainty
    past_gws = max(0, (next_gw or 1) - 1)
    available_minutes_so_far = past_gws * 90
    minutes_ratio = (total_mins / available_minutes_so_far) if available_minutes_so_far > 0 else 0.0

    confidence = "Medium"
    if availability_prob < 0.9 or expected_minutes < 45:
        confidence = "Low (Minutes Uncertainty)"
    elif minutes_ratio >= 0.75 and availability_prob == 1.0 and fixtures_found >= gw_range:
        confidence = "High (Nailed Starter)"
        
    reasons = []
    if expected_minutes > 60:
        reasons.append("Nailed Starter")
    else:
        reasons.append("Rotation Risk / Bench")
        
    if form_multiplier > 1.1:
        reasons.append(f"Form Momentum: +{int((form_multiplier - 1)*100)}% to expected returns")
    if xg_90 > 0.3 or xa_90 > 0.3:
        reasons.append(f"Strong attacking threat (xG/90: {round(xg_90, 2)}, xA/90: {round(xa_90, 2)})")
    if cs_prob_90 > 0.4 and pos_code in [1, 2]:
        reasons.append(f"High Clean Sheet probability ({int(cs_prob_90*100)}%)")
        
    reason_str = "\n".join(reasons)
    
    return {
        "id": p["id"],
        "name": p["web_name"],
        "team": teams.get(p["team"], {}).get("short_name", "UNK"),
        "team_code": p["team_code"],
        "pos_code": pos_code,
        "cost": p["now_cost"] / 10,
        "xp": round(total_5gw_projection / max(1, gw_range), 2),
        "xp_next": round(next_gw_projection, 2),
        "form": form_val,
        "total_points": p.get("total_points", 0),
        "selected_by_percent": float(p.get("selected_by_percent", 0) or 0),
        "fixture": next_gw_opponent,
        "fixture_diff": next_gw_diff,
        "confidence": confidence,
        "reason": reason_str,
        "prob": availability_prob,
        "news": p.get("news", ""),
        "xg": float(p.get("expected_goals", 0) or 0),
        "xa": float(p.get("expected_assists", 0) or 0),
        "expected_goals": float(p.get("expected_goals", 0) or 0),
        "expected_assists": float(p.get("expected_assists", 0) or 0),
        "expected_goals_conceded": float(p.get("expected_goals_conceded", 0) or 0),
        "xgc": float(p.get("expected_goals_conceded", 0) or 0),
        "defensive_contribution": p.get("defensive_contribution_per_90", 0.0),
        "clean_sheets": p.get("clean_sheets", 0),
        "goals_conceded": p.get("goals_conceded", 0),
        "minutes": p.get("minutes", 0),
        "expected_minutes": round(expected_minutes, 1),
        "start_probability": round(base_cop * 100, 1)
    }

def enrich_picks(picks_ids, squad):
    enriched = []
    for pid in picks_ids:
        player = next((p for p in squad if p["id"] == pid), None)
        if player:
            enriched.append(player)
    return enriched

def enrich_shared(shared_ids, squad_a, squad_b):
    enriched = []
    for pid in shared_ids:
        player = next((p for p in squad_a if p["id"] == pid), next((p for p in squad_b if p["id"] == pid), None))
        if player:
            enriched.append(player)
    return enriched
def get_fpl_context(gw_limit: int = 5, override_next_gw: int = None):
    """מחזיר bootstrap, teams, elements, next_gw ו-fixtures לטווח נתון — משותף לכל ה-endpoints."""
    bootstrap = fetch_bootstrap()
    events = bootstrap.get("events", [])
    current_gw = next((e["id"] for e in events if e["is_current"]), None)
    next_gw = next((e["id"] for e in events if e["is_next"]), None)
    if not next_gw and current_gw:
        next_gw = current_gw + 1
    elif not next_gw:
        next_gw = 1
    if override_next_gw:
        next_gw = override_next_gw
    all_fixtures = fetch_all_fixtures()
    max_gw = 38
    gw_range = min(gw_limit, max_gw - next_gw + 1) if gw_limit else max(1, max_gw - next_gw + 1)
    upper_bound = next_gw + gw_range - 1 if gw_limit else max_gw
    upcoming_fixtures_raw = [
        f for f in all_fixtures
        if f.get("event") and next_gw <= f["event"] <= upper_bound
    ]
    teams = {t["id"]: t for t in bootstrap.get("teams", [])}
    elements = {p["id"]: p for p in bootstrap.get("elements", [])}
    return {
        "bootstrap": bootstrap,
        "teams": teams,
        "elements": elements,
        "next_gw": next_gw,
        "gw_range": gw_range,
        "upcoming_fixtures_raw": upcoming_fixtures_raw,
    }


@app.get("/api/dashboard/{team_id}")
def get_dashboard_data(team_id: int):
    try:
        ctx = get_fpl_context(gw_limit=None)
        next_gw = ctx["next_gw"]
        gw_range = ctx["gw_range"]
        upcoming_fixtures_raw = ctx["upcoming_fixtures_raw"]
        elements = ctx["elements"]
        teams = ctx["teams"]

        picks, bank, team_name, rank, chips_used, leagues, free_transfers = fetch_user_team(team_id, next_gw)

        enriched_picks = []
        for pick in picks:
            player = elements.get(pick["element"])
            if player:
                proj = calculate_player_projection(player, next_gw, upcoming_fixtures_raw, teams)
                
                upcoming_fixtures = []
                for gw_inc in range(gw_range):
                    target_gw = next_gw + gw_inc
                    gw_fixs = [f for f in upcoming_fixtures_raw if f.get("event") == target_gw]
                    
                    found = False
                    for f in gw_fixs:
                        if f["team_h"] == player["team"]:
                            opp = teams.get(f["team_a"], {}).get("short_name", "UNK")
                            upcoming_fixtures.append({"gw": target_gw, "opponent": f"{opp} (H)", "difficulty": f["team_h_difficulty"]})
                            found = True
                            break
                        elif f["team_a"] == player["team"]:
                            opp = teams.get(f["team_h"], {}).get("short_name", "UNK")
                            upcoming_fixtures.append({"gw": target_gw, "opponent": f"{opp} (A)", "difficulty": f["team_a_difficulty"]})
                            found = True
                            break
                    if not found:
                        upcoming_fixtures.append({"gw": target_gw, "opponent": "Blank", "difficulty": 5})

                enriched_picks.append({
                    "id": player["id"],
                    "name": player["web_name"],
                    "team": teams.get(player["team"], {}).get("short_name", "UNK"),
                    "team_code": player.get("team_code", 1),
                    "pos_code": player["element_type"],
                    "position": pick.get("position"),
                    "cost": player["now_cost"] / 10,
                    "is_captain": pick.get("is_captain", False),
                    "is_vice_captain": pick.get("is_vice_captain", False),
                    "multiplier": pick.get("multiplier", 1),
                    "xp": proj["xp"],
                    "xp_next": proj.get("xp_next", proj["xp"]),
                    "form": float(player.get("form", 0) or 0),
                    "chance_of_playing": player.get("chance_of_playing_next_round"),
                    "news": player.get("news"),
                    "upcoming_fixtures": upcoming_fixtures,
                    "total_points": player.get("total_points", 0),
                    "selected_by_percent": float(player.get("selected_by_percent", 0) or 0),
                    "expected_goals": float(player.get("expected_goals", 0) or 0),
                    "expected_assists": float(player.get("expected_assists", 0) or 0),
                    "expected_goals_conceded": float(player.get("expected_goals_conceded", 0) or 0),
                    "defensive_contribution": player.get("defensive_contribution_per_90", 0.0),
                    "clean_sheets": player.get("clean_sheets", 0),
                    "goals_conceded": player.get("goals_conceded", 0),
                    "fixture": proj.get("fixture", ""),
                    "fixture_diff": proj.get("fixture_diff", 3),
                    "minutes": player.get("minutes", 0)
                })
                
        schedule = {}
        for gw_inc in range(gw_range):
            target_gw = next_gw + gw_inc
            gw_fixs = [f for f in upcoming_fixtures_raw if f.get("event") == target_gw]
            formatted_fixs = []
            for f in gw_fixs:
                formatted_fixs.append({
                    "home": teams.get(f["team_h"], {}).get("short_name", "UNK"),
                    "away": teams.get(f["team_a"], {}).get("short_name", "UNK"),
                    "h_diff": f["team_h_difficulty"],
                    "a_diff": f["team_a_difficulty"],
                    "time": f.get("kickoff_time")
                })
            schedule[str(target_gw)] = formatted_fixs

        return {
            "team_id": team_id,
            "team_name": team_name,
            "rank": rank,
            "bank": bank,
            "free_transfers": free_transfers,
            "next_gw": next_gw,
            "squad": enriched_picks,
            "schedule": schedule,
            "chips_used": chips_used,
        "leagues": leagues,
        "teams": teams
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/league/{league_id}")
def get_league_data(league_id: int):
    try:
        url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/"
        import requests
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
        if res.status_code != 200:
            raise Exception("League not found")
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/compare/{team_a}/{team_b}")
def compare_teams(team_a: int, team_b: int):
    try:
        bootstrap = fetch_bootstrap()
        events = bootstrap.get("events", [])
        next_gw = next((e["id"] for e in events if e["is_next"]), 1)
        
        a_picks, a_bank, *rest_a = fetch_user_team(team_a, next_gw)
        b_picks, b_bank, *rest_b = fetch_user_team(team_b, next_gw)
        
        import requests
        a_info = requests.get(f"https://fantasy.premierleague.com/api/entry/{team_a}/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
        b_info = requests.get(f"https://fantasy.premierleague.com/api/entry/{team_b}/", headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
        
        a_data = {}
        b_data = {}
        
        if a_info.status_code == 200:
            a_data = a_info.json()
        if b_info.status_code == 200:
            b_data = b_info.json()
            
        a_ids = set([p["element"] for p in a_picks])
        b_ids = set([p["element"] for p in b_picks])
        
        shared = list(a_ids.intersection(b_ids))
        a_unique = list(a_ids - b_ids)
        b_unique = list(b_ids - a_ids)
        
        elements = {p["id"]: p for p in bootstrap.get("elements", [])}
        teams = {t["id"]: t for t in bootstrap.get("teams", [])}
        
        def hydrate(pick_list):
            res = []
            for pick in pick_list:
                player = elements.get(pick["element"])
                if player:
                    res.append({
                        "id": player["id"],
                        "name": player["web_name"],
                        "team": teams.get(player["team"], {}).get("short_name", "UNK"),
                        "team_code": player.get("team_code", 1),
                        "pos_code": player["element_type"],
                        "position": pick.get("position"),
                        "is_captain": pick.get("is_captain", False),
                        "multiplier": pick.get("multiplier", 1)
                    })
            return res
            
        a_squad = hydrate(a_picks)
        b_squad = hydrate(b_picks)
        
        return {
            "team_a": {
                "name": a_data.get("name", f"Team {team_a}"),
                "manager": f"{a_data.get('player_first_name', '')} {a_data.get('player_last_name', '')}",
                "unique": enrich_picks(a_unique, a_squad),
                "picks": a_squad,
                "active_chip": a_data.get("active_chip")
            },
            "team_b": {
                "name": b_data.get("name", f"Team {team_b}"),
                "manager": f"{b_data.get('player_first_name', '')} {b_data.get('player_last_name', '')}",
                "unique": enrich_picks(b_unique, b_squad),
                "picks": b_squad,
                "active_chip": b_data.get("active_chip")
            },
            "shared": enrich_shared(shared, a_squad, b_squad)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TransferRequest(BaseModel):
    free_transfers: Optional[int] = 1
    transfers_before: int = 0
    active_chip: Optional[str] = None
    pos_code: int
    max_budget: float
    actual_budget: Optional[float] = None
    current_squad_ids: Optional[List[int]] = []
    transfer_out_id: Optional[int] = None
    target_gw: Optional[int] = None
    unlimited_budget: Optional[bool] = False

@app.post("/api/transfer-lab")
def get_transfer_recommendations(req: TransferRequest):
    try:
        ctx = get_fpl_context(gw_limit=5, override_next_gw=req.target_gw)
        next_gw = ctx["next_gw"]
        upcoming_fixtures_raw = ctx["upcoming_fixtures_raw"]
        elements = ctx["bootstrap"].get("elements", [])
        teams = ctx["teams"]
        
        current_player = None
        if req.transfer_out_id:
            curr_p_raw = next((p for p in elements if p["id"] == req.transfer_out_id), None)
            if curr_p_raw:
                current_player = calculate_player_projection(curr_p_raw, next_gw, upcoming_fixtures_raw, teams)
                
        team_counts = {}
        current_squad_set = set(req.current_squad_ids or [])
        for p in elements:
            if p["id"] in current_squad_set and p["id"] != req.transfer_out_id:
                t = p["team"]
                team_counts[t] = team_counts.get(t, 0) + 1

        candidates = []
        all_evaluations = []
        eval_budget = req.actual_budget if req.actual_budget is not None else req.max_budget
        
        for p in elements:
            if p["element_type"] == req.pos_code:
                if p["id"] not in current_squad_set or p["id"] == req.transfer_out_id:
                    within_budget = (p["now_cost"] / 10) <= eval_budget
                    if within_budget or req.unlimited_budget:
                        c_team_count = team_counts.get(p["team"], 0)
                        if c_team_count < 3 or p["id"] == req.transfer_out_id:
                            c = calculate_player_projection(p, next_gw, upcoming_fixtures_raw, teams)
                            if c:
                                all_evaluations.append(c)

        all_evaluations = sorted(all_evaluations, key=decision_engine_score, reverse=True)
        
        current_player_rank = None
        total_relevant = len(all_evaluations)
        
        for idx, c in enumerate(all_evaluations):
            if current_player and c["id"] == current_player["id"]:
                current_player_rank = idx + 1
            if c["id"] != req.transfer_out_id:
                c["within_budget"] = (c["cost"] <= eval_budget)
                c["budget_diff"] = round(eval_budget - c["cost"], 1)
                candidates.append(c)
                
        candidates = sorted(candidates, key=decision_engine_score, reverse=True)
        affordable_candidates = [c for c in candidates if c["cost"] <= eval_budget]

        unconstrained_best = candidates[0] if candidates else None
        affordable_best = affordable_candidates[0] if affordable_candidates else None
        best_candidate = unconstrained_best if req.unlimited_budget else affordable_best

        def compute_transfer_decision(candidate):
            recommendation = "HOLD"
            explanation = ""
            delta = 0.0
            raw_gain = None
            hit_cost = 0
            net_gain = None
            threshold = 0.0

            if current_player and candidate:
                delta = round(
                    candidate["xp"] - current_player["xp"], 2
                )
                raw_gain = round(delta * ctx["gw_range"], 2)

                chip = (req.active_chip or "").lower().replace("_", "").replace(" ", "")
                chip_active = chip in {"wildcard", "freehit"}

                free_transfers = max(0, min(5, int(req.free_transfers or 0)))
                transfers_before = max(0, int(req.transfers_before or 0))

                hits_before = max(0, transfers_before - free_transfers)
                hits_after = max(0, transfers_before + 1 - free_transfers)
                hit_cost = 0 if chip_active else (hits_after - hits_before) * 4

                net_gain = raw_gain - hit_cost

                # Universal Player Vitality Metrics
                curr_p_raw = next((p for p in elements if p["id"] == req.transfer_out_id), None)
                curr_form = float(curr_p_raw.get("form", 0) or 0) if curr_p_raw else 0.0
                curr_pts = int(curr_p_raw.get("total_points", 0) or 0) if curr_p_raw else 0
                curr_starts = int(curr_p_raw.get("starts", 0) or 0) if curr_p_raw else 0
                curr_mins = int(curr_p_raw.get("minutes", 0) or 0) if curr_p_raw else 0
                curr_cop = curr_p_raw.get("chance_of_playing_next_round") if curr_p_raw else None
                curr_cost = current_player.get("cost", 0.0)
                curr_diff = current_player.get("fixture_diff", 3)
                cand_diff = candidate.get("fixture_diff", 3)

                is_flagged = curr_cop is not None and curr_cop < 75
                is_healthy = curr_cop is None or curr_cop >= 75

                is_established_starter = is_healthy and (
                    (curr_starts >= 3 and curr_mins >= 220) or
                    (curr_mins >= 350)
                )

                is_elite_asset = is_established_starter and (
                    (curr_form >= 4.5 and (curr_pts >= 35 or curr_cost >= 8.0)) or
                    (curr_form >= 5.5 and curr_pts >= 28) or
                    (curr_form >= 6.0)
                )

                is_in_form_starter = is_established_starter and (
                    curr_form >= 3.5 or
                    (curr_form >= 3.0 and curr_pts >= 25)
                )

                curr_xp_next = current_player.get("xp_next", current_player["xp"])
                cand_xp_next = candidate.get("xp_next", candidate["xp"])

                # 1. IMMEDIATE FIXTURE GATEKEEPER
                has_immediate_match_advantage = (
                    is_healthy and
                    is_established_starter and
                    curr_xp_next > 0 and
                    (curr_xp_next >= cand_xp_next) and
                    raw_gain < 8.0
                )

                # 2. STATUS-BASED DYNAMIC HURDLE RATE
                if is_flagged or (curr_mins < 120 and curr_starts == 0):
                    hurdle = 2.0
                    tier = "URGENT"
                elif is_elite_asset:
                    hurdle = 7.5
                    tier = "ELITE"
                elif is_in_form_starter:
                    hurdle = 5.5
                    tier = "STARTER"
                elif is_established_starter:
                    hurdle = 4.0
                    tier = "REGULAR"
                else:
                    hurdle = 3.0
                    tier = "ROTATION"

                # Fixture swing adjustment: if current player faces severe run (diff >= 4) vs easy candidate (diff <= 2)
                if curr_diff >= 4 and cand_diff <= 2:
                    hurdle = max(2.0, hurdle - 1.0)

                threshold = hurdle + hit_cost

                if has_immediate_match_advantage:
                    recommendation = "HOLD"
                    explanation = (
                        f"The projected gain over {ctx['gw_range']} GWs is {raw_gain:.2f} points, "
                        f"with a {hit_cost}-point hit cost. "
                        f"Hold for GW{ctx['next_gw']}: {current_player['name']} projects higher or equal for the immediate match "
                        f"({curr_xp_next:.1f} vs {candidate['name']}'s {cand_xp_next:.1f} xP). "
                        "Do not sacrifice immediate points for a speculative medium-term move."
                    )
                elif raw_gain <= threshold:
                    recommendation = "HOLD"
                    if tier == "ELITE":
                        explanation = (
                            f"The projected gain over {ctx['gw_range']} GWs is {raw_gain:.2f} points, "
                            f"with a {hit_cost}-point hit cost. "
                            f"{current_player['name']} is in elite form ({curr_form:.1f}, {curr_pts} pts). "
                            f"A 5-GW difference does not justify transferring out a firing talisman for a threshold of {threshold:.1f} points. "
                            "Hold your transfer or target weaker squad positions."
                        )
                    elif tier == "STARTER":
                        explanation = (
                            f"The projected gain over {ctx['gw_range']} GWs is {raw_gain:.2f} points, "
                            f"with a {hit_cost}-point hit cost. "
                            f"{current_player['name']} is an established starter in solid form ({curr_form:.1f}). "
                            f"The projected gain is too marginal to clear the required threshold of {threshold:.1f} points."
                        )
                    else:
                        explanation = (
                            f"The projected gain over {ctx['gw_range']} GWs is {raw_gain:.2f} points, "
                            f"with a {hit_cost}-point hit cost. "
                            f"The transfer does not clear the required threshold of {threshold:.1f} points."
                        )
                else:
                    recommendation = "TRANSFER"
                    explanation = (
                        f"The projected gain over {ctx['gw_range']} GWs is {raw_gain:.2f} points, "
                        f"with a {hit_cost}-point hit cost. "
                        f"Replacing with {candidate['name']} clears the required threshold of {threshold:.1f} points."
                    )
            else:
                recommendation = "MONITOR"
                explanation = "Not enough data to form a definitive transfer decision."

            return {
                "recommendation": recommendation,
                "explanation": explanation,
                "delta": delta,
                "raw_gain": raw_gain,
                "hit_cost": hit_cost,
                "net_gain": net_gain,
                "threshold": threshold,
                "best_transfer": candidate
            }

        main_decision = compute_transfer_decision(best_candidate)
        affordable_decision = compute_transfer_decision(affordable_best)

        if current_player:
            log_prediction(current_player, next_gw, "Transfer Lab - Current")
        if best_candidate:
            log_prediction(best_candidate, next_gw, "Transfer Lab - Candidate")

        return {
            "recommendation": main_decision["recommendation"],
            "explanation": main_decision["explanation"],
            "delta": main_decision["delta"],
            "raw_gain": main_decision["raw_gain"],
            "hit_cost": main_decision["hit_cost"],
            "net_gain": main_decision["net_gain"],
            "threshold": main_decision["threshold"],
            "current_player": current_player,
            "current_player_rank": current_player_rank,
            "total_relevant": total_relevant,
            "best_transfer": best_candidate,
            "candidates": candidates,
            "affordable_decision": affordable_decision
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def build_squad(players, forced_players=[]):
    squad = list(forced_players)
    cost = sum(p['cost'] for p in squad)
    team_counts = {}
    pos_counts = {1: 0, 2: 0, 3: 0, 4: 0}
    
    for p in squad:
        team_counts[p['team']] = team_counts.get(p['team'], 0) + 1
        pos_counts[p['pos_code']] += 1
        
    min_costs = {1: 4.0, 2: 4.0, 3: 4.5, 4: 4.5}
    
    for p in players:
        if len(squad) == 15:
            break
        if any(x['id'] == p['id'] for x in squad):
            continue
            
        needed = False
        if p['pos_code'] == 1 and pos_counts[1] < 2: needed = True
        if p['pos_code'] == 2 and pos_counts[2] < 5: needed = True
        if p['pos_code'] == 3 and pos_counts[3] < 5: needed = True
        if p['pos_code'] == 4 and pos_counts[4] < 3: needed = True
        
        if not needed:
            continue
        if team_counts.get(p['team'], 0) >= 3:
            continue
            
        rem_slots_budget = 0
        for t in range(1, 5):
            needed_count = (2 if t == 1 else 5 if t == 2 else 5 if t == 3 else 3) - pos_counts[t]
            if t == p['pos_code']:
                needed_count -= 1
            if needed_count > 0:
                rem_slots_budget += needed_count * min_costs[t]
                
        if cost + p['cost'] + rem_slots_budget <= 100.0:
            squad.append(p)
            cost += p['cost']
            team_counts[p['team']] = team_counts.get(p['team'], 0) + 1
            pos_counts[p['pos_code']] += 1
            
    squad.sort(key=lambda x: (x['pos_code'], -x['cost']))
    
    # map to frontend format
    formatted = []
    for p in squad:
        formatted.append({
            "id": p["id"],
            "name": p["name"],
            "team_code": p.get("team_code", p.get("team")),
            "element_type": p["pos_code"],
            "now_cost": int(p["cost"] * 10),
            "xp": p["xp"],
            "xp_next": p.get("xp_next", p["xp"])
        })
    return {"squad": formatted, "cost": int(cost * 10)}

@app.get("/api/drafts")
def get_drafts():
    try:
        bootstrap = fetch_bootstrap()
        elements = bootstrap.get("elements", [])
        teams = {t["id"]: t for t in bootstrap.get("teams", [])}
        
        events = bootstrap.get("events", [])
        next_gw = next((e["id"] for e in events if e["is_next"]), 1)
        all_fixtures = fetch_all_fixtures()
        
        gw_range = min(5, 38 - next_gw + 1)
        upcoming_fixtures_raw = [f for f in all_fixtures if f.get("event") and next_gw <= f["event"] <= next_gw + gw_range - 1]
        
        all_players = []
        for p in elements:
            if p["status"] not in ["u", "i", "s"]:
                proj = calculate_player_projection(p, next_gw, upcoming_fixtures_raw, teams)
                # Ensure we have team_code for shirt image
                proj["team_code"] = p.get("team_code")
                all_players.append(proj)
                
        premiums = sorted([p for p in all_players if p["cost"] >= 10.0], key=lambda x: x["xp"], reverse=True)[:2]
        others_for_premium = sorted(all_players, key=lambda x: x["xp"]/max(0.1, x["cost"]), reverse=True)
        premium_draft = build_squad(others_for_premium, premiums)
        
        balanced_players = sorted([p for p in all_players if p["cost"] <= 9.5], key=lambda x: x["xp"], reverse=True)
        balanced_draft = build_squad(balanced_players, [])
        
        DIFFERENTIAL_OWNERSHIP_THRESHOLD = 15.0

        def diff_score(p):
            bonus = 2 if p["selected_by_percent"] < 10.0 else 1
            return p["xp"] + bonus

        diff_universe = [
            p for p in all_players
            if p["selected_by_percent"] <= DIFFERENTIAL_OWNERSHIP_THRESHOLD
        ]
        differential_players = sorted(diff_universe, key=diff_score, reverse=True)
        diff_draft = build_squad(differential_players, [])

        # If greedy ordering encountered club limits, perform a secondary fill pass strictly within diff_universe
        if len(diff_draft["squad"]) < 15:
            budget_fillers = sorted(diff_universe, key=lambda p: (p.get("cost", 0), -p.get("xp", 0)))
            diff_draft = build_squad(differential_players + budget_fillers, [])
        
        return {
            "drafts": [
                {"id": 1, "name": "Premium Heavies (כוכבים יקרים)", "description": "הרכב מבוסס על שחקני פרימיום חזקים יחד עם שחקנים זולים משלימים.", "data": premium_draft},
                {"id": 2, "name": "Balanced Spread (הרכב מאוזן)", "description": "ללא שחקנים יקרים מדי, מאפשר עומק חזק מאוד בכל העמדות במגרש.", "data": balanced_draft},
                {"id": 3, "name": "Differentials (פנינים נסתרות)", "description": "שחקנים בכושר שיא שאחוזי הבחירה שלהם נמוכים, כדי לעקוף מתחרים.", "data": diff_draft}
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/radar")
def get_radar():
    try:
        bootstrap = fetch_bootstrap()
        elements = bootstrap.get("elements", [])
        teams = {t["id"]: t for t in bootstrap.get("teams", [])}
        
        events = bootstrap.get("events", [])
        next_gw = next((e["id"] for e in events if e["is_next"]), 1)
        all_fixtures = fetch_all_fixtures()
        
        gw_range = min(5, 38 - next_gw + 1)
        upcoming_fixtures_raw = [f for f in all_fixtures if f.get("event") and next_gw <= f["event"] <= next_gw + gw_range - 1]
        
        all_players = []
        for p in elements:
            if p["status"] != "u":
                proj = calculate_player_projection(p, next_gw, upcoming_fixtures_raw, teams)
                all_players.append(proj)
        
        scout_picks = sorted(all_players, key=lambda x: x["xp"], reverse=True)[:10]
        hot_form = sorted(all_players, key=lambda x: x["form"], reverse=True)[:10]
        
        differentials = sorted([p for p in all_players if p["selected_by_percent"] < 10.0 and p["xp"] > 3.0], key=lambda x: x["xp"], reverse=True)[:10]
        if not differentials:
            differentials = sorted([p for p in all_players if p["selected_by_percent"] < 10.0], key=lambda x: x["xp"], reverse=True)[:10]
            
        return {
            "scout_picks": scout_picks,
            "hot_form": hot_form,
            "differentials": differentials
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class BudgetScenariosRequest(BaseModel):
    squad: List[dict]
    bank: float
    next_gw: int

@app.post("/api/budget-scenarios")
def get_budget_scenarios(req: BudgetScenariosRequest):
    try:
        squad = req.squad
        bank = req.bank
        next_gw = req.next_gw
        
        bootstrap = fetch_bootstrap()
        all_fixtures = fetch_all_fixtures()
        elements = bootstrap.get("elements", [])
        teams = {t["id"]: t for t in bootstrap.get("teams", [])}
        
        gw_range = min(5, 38 - next_gw + 1)
        upcoming_fixtures_raw = [f for f in all_fixtures if f.get("event") and next_gw <= f["event"] <= next_gw + gw_range - 1]
        
        all_players = []
        for p in elements:
            if p["status"] == "a":
                proj = calculate_player_projection(p, next_gw, upcoming_fixtures_raw, teams)
                all_players.append(proj)
        
        current_squad_ids = [p["id"] for p in squad]
        suggestions = []
        
        for sp in squad:
            reason = None
            if sp.get("chance_of_playing") is not None and sp.get("chance_of_playing") < 75:
                reason = "Injury / Doubtful"
            elif sp.get("form", 0) < 2.0 and sp.get("xp", 0) < 3.0:
                reason = "Poor Output (Low Form & Projection)"
            elif sp.get("xp", 0) < 3.0:
                reason = "Tough Upcoming Run (Low 5GW Projection)"
                
            if reason:
                budget = bank + sp["cost"]
                candidates = [p for p in all_players if p["pos_code"] == sp["pos_code"] and p["id"] not in current_squad_ids and p["cost"] <= budget]
                
                candidates = sorted(candidates, key=decision_engine_score, reverse=True)
                top_candidates = candidates[:3]
                
                if top_candidates:
                    suggestions.append({
                        "sell": sp,
                        "reason": reason,
                        "buys": top_candidates
                    })
                    
        return suggestions
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/player/{player_id}")
def get_player_details(player_id: int):
    try:
        url = f"https://fantasy.premierleague.com/api/element-summary/{player_id}/"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        ctx = get_fpl_context(gw_limit=5)
        elements = ctx["elements"]
        p = elements.get(player_id, {})
        
        
        # Calculate projection just to get all the rich stats
        from fpl_api import fetch_all_fixtures
        all_fixtures = fetch_all_fixtures()
        events = ctx["bootstrap"].get("events", [])
        next_gw = next((e["id"] for e in events if e["is_next"]), 1)
        gw_range = min(5, 38 - next_gw + 1)
        upcoming_fixtures_raw = [f for f in all_fixtures if f.get("event") and next_gw <= f["event"] <= next_gw + gw_range - 1]
        
        proj = calculate_player_projection(p, next_gw, upcoming_fixtures_raw, ctx["teams"])
        
        return {
            "id": player_id,
            "name": p.get("web_name", "Unknown"),
            "team_code": p.get("team_code", 1),
            "pos_code": p.get("element_type", 1),
            "cost": p.get("now_cost", 0) / 10,
            "form": p.get("form", "0.0"),
            "points": p.get("total_points", 0),
            "xg": p.get("expected_goals", "0.0"),
            "xa": p.get("expected_assists", "0.0"),
            "xgc": p.get("expected_goals_conceded", "0.0"),
            "defcon": p.get("defensive_contribution_per_90", 0.0),
            "history": data.get("history", [])[-5:], # last 5 GWs
            "fixtures": data.get("fixtures", [])[:5], # next 5 GWs
            "expected_goals": proj["expected_goals"],
            "expected_assists": proj["expected_assists"],
            "expected_goals_conceded": proj["expected_goals_conceded"],
            "defensive_contribution": proj["defensive_contribution"],
            "clean_sheets": proj["clean_sheets"],
            "goals_conceded": proj["goals_conceded"],
            "xp": proj["xp"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
