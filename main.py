from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
from fpl_api import fetch_bootstrap, fetch_user_team, fetch_fixtures, fetch_all_fixtures
import math

app = FastAPI(title="FPL Elite Scout API")

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

import datetime
import os

def log_prediction(player_id, player_name, gw, xp, context, recommendation=""):
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "predictions_log.jsonl")
        
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "gw": gw,
            "player_id": player_id,
            "player_name": player_name,
            "xp": round(xp, 2),
            "context": context,
            "recommendation": recommendation
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        print(f"Failed to log prediction: {e}")

def calculate_player_projection(p, next_gw, upcoming_fixtures_raw, teams, weights=None):
    if weights is None:
        weights = DEFAULT_WEIGHTS
        
    team_id_fpl = p["team"]
    pos_code = p["element_type"]
    
    # 1. Availability
    chance = p.get("chance_of_playing_next_round")
    availability_prob = 1.0 if chance is None else float(chance) / 100.0
    
    # 2. Expected Minutes (Basic rotation model)
    total_mins = p.get("minutes", 0)
    starts = p.get("starts", 0)
    mins_per_start = total_mins / starts if starts > 0 else 0
    if mins_per_start == 0 and float(p.get("form", 0) or 0) > 0:
        mins_per_start = 60 # Default for non-starters getting minutes
        
    expected_minutes = mins_per_start * availability_prob
    if expected_minutes > 90: expected_minutes = 90
    x_90s = expected_minutes / 90.0
    
    # 3. Base Per-90 Stats
    xg_90 = float(p.get("expected_goals_per_90", 0) or 0) * weights["xg_weight"]
    xa_90 = float(p.get("expected_assists_per_90", 0) or 0) * weights["xa_weight"]
    xgc_90 = float(p.get("expected_goals_conceded_per_90", 0) or 0)
    defcon_90 = float(p.get("defensive_contribution_per_90", 0) or 0)

    # סף הגנתי אמיתי לפי חוקי FPL: 10 פעולות למגנים, 12 לקשרים/חלוצים
    defcon_threshold = 10 if pos_code == 2 else 12
    # קירוב נורמלי: סטיית תקן ~35% מהממוצע (הערכה שמרנית לשונות בין משחקים)
    defcon_std = max(defcon_90 * 0.35, 1.0)
    z = (defcon_90 - defcon_threshold) / defcon_std
    # פונקציית לוגיסטיק כקירוב מהיר ל-CDF נורמלי
    prob_cross_threshold = 1 / (1 + math.exp(-1.7 * z))
    
    # Goal / Assist Points
    goal_pts = {1: 6, 2: 6, 3: 5, 4: 4}.get(pos_code, 4)
    assist_pts = 3
    
    # Base expectations
    xAtt_90 = (xg_90 * goal_pts) + (xa_90 * assist_pts)
    
    cs_pts = {1: 4, 2: 4, 3: 1, 4: 0}.get(pos_code, 0)
    cs_prob_90 = math.exp(-xgc_90) if xgc_90 > 0 else 0.5
    xDef_90 = cs_prob_90 * cs_pts
    
    xSave_90 = 0
    if pos_code == 1:
        saves_90 = float(p.get("saves_per_90", 0) or 0)
        xSave_90 = (saves_90 / 3.0) * 1
        
    xBPS_90 = prob_cross_threshold * 2.0  # 2 נקודות FPL על מעבר סף
    
    gw_range = min(5, 38 - next_gw + 1)
    
    next_gw_opponent = "Blank"
    next_gw_diff = 5
    fixtures_found = 0
    
    total_5gw_projection = 0.0
    
    for gw_inc in range(gw_range):
        target_gw = next_gw + gw_inc
        gw_fixs = [f for f in upcoming_fixtures_raw if f.get("event") == target_gw]
        player_fixs = [f for f in gw_fixs if f["team_h"] == team_id_fpl or f["team_a"] == team_id_fpl]
        
        gw_proj = 0.0
        
        for f in player_fixs:
            fixtures_found += 1
            is_home = (f["team_h"] == team_id_fpl)
            diff = f["team_h_difficulty"] if is_home else f["team_a_difficulty"]
            
            if gw_inc == 0 and fixtures_found == 1:
                opp_id = f["team_a"] if is_home else f["team_h"]
                next_gw_opponent = f"{teams.get(opp_id, 'UNK')} ({'H' if is_home else 'A'})"
                next_gw_diff = diff
            
            # FDR Multiplier
            # We scale the FDR intensity using fdr_scale
            fdr_multiplier = 1.0
            if diff == 1: fdr_multiplier = 1.0 + (0.3 * weights["fdr_scale"])
            elif diff == 2: fdr_multiplier = 1.0 + (0.15 * weights["fdr_scale"])
            elif diff == 3: fdr_multiplier = 1.0
            elif diff == 4: fdr_multiplier = 1.0 - (0.15 * weights["fdr_scale"])
            elif diff == 5: fdr_multiplier = 1.0 - (0.3 * weights["fdr_scale"])
            
            # FIX: FDR ONLY applies to attacking and defensive potential, NOT appearance or saves
            match_xAtt = xAtt_90 * x_90s * fdr_multiplier
            match_xDef = xDef_90 * x_90s * fdr_multiplier
            match_xSave = xSave_90 * x_90s
            match_xBPS = xBPS_90 * x_90s
            
            appearance_pts = 0
            if expected_minutes >= 60: appearance_pts = 2 * availability_prob
            elif expected_minutes > 0: appearance_pts = 1 * availability_prob
            
            gw_proj += match_xAtt + match_xDef + match_xSave + match_xBPS + appearance_pts
            
        total_5gw_projection += gw_proj
        
    form_val = float(p.get("form", 0) or 0)
    total_5gw_projection += (form_val * weights["form_weight"] * gw_range)
    total_5gw_projection = max(0.0, total_5gw_projection)
    
    # Confidence metrics based on uncertainty, not just DGW
    confidence = "Medium"
    if availability_prob < 0.9 or expected_minutes < 45:
        confidence = "Low (Minutes Uncertainty)"
    elif total_mins > 500 and availability_prob == 1.0 and fixtures_found >= gw_range:
        confidence = "High"
        
    reasons = []
    reasons.append(f"Expected Minutes: {int(expected_minutes)}/match")
    if form_val > 0:
        reasons.append(f"Form Adjustment: +{round(form_val * weights['form_weight'], 2)} pts")
    if xg_90 > 0.3 or xa_90 > 0.3:
        reasons.append(f"Strong attacking threat (xG/90: {xg_90}, xA/90: {xa_90})")
    if cs_prob_90 > 0.4 and pos_code in [1, 2]:
        reasons.append(f"High Clean Sheet probability ({int(cs_prob_90*100)}%)")
        
    reason_str = "\n".join(reasons)
    
    return {
        "id": p["id"],
        "name": p["web_name"],
        "team": teams.get(p["team"], "UNK"),
        "team_code": p["team_code"],
        "pos_code": pos_code,
        "cost": p["now_cost"] / 10,
        "xp": round(total_5gw_projection / max(1, gw_range), 2),
        "form": form_val,
        "total_points": p.get("total_points", 0),
        "selected_by_percent": float(p.get("selected_by_percent", 0) or 0),
        "fixture": next_gw_opponent,
        "fixture_diff": next_gw_diff,
        "confidence": confidence,
        "reason": reason_str,
        "prob": availability_prob,
        "xg": float(p.get("expected_goals", 0) or 0),
        "xa": float(p.get("expected_assists", 0) or 0)
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
def get_fpl_context(gw_limit: int = 5):
    """מחזיר bootstrap, teams, elements, next_gw ו-fixtures לטווח נתון — משותף לכל ה-endpoints."""
    bootstrap = fetch_bootstrap()
    events = bootstrap.get("events", [])
    current_gw = next((e["id"] for e in events if e["is_current"]), None)
    next_gw = next((e["id"] for e in events if e["is_next"]), None)
    if not next_gw and current_gw:
        next_gw = current_gw + 1
    elif not next_gw:
        next_gw = 1
    all_fixtures = fetch_all_fixtures()
    max_gw = 38
    gw_range = min(gw_limit, max_gw - next_gw + 1) if gw_limit else max(1, max_gw - next_gw + 1)
    upper_bound = next_gw + gw_range - 1 if gw_limit else max_gw
    upcoming_fixtures_raw = [
        f for f in all_fixtures
        if f.get("event") and next_gw <= f["event"] <= upper_bound
    ]
    teams = {t["id"]: t["short_name"] for t in bootstrap.get("teams", [])}
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
@app.get("/api/dashboard/{team_id}")
def get_dashboard_data(team_id: int):
    try:
        ctx = get_fpl_context(gw_limit=None)
        next_gw = ctx["next_gw"]
        gw_range = ctx["gw_range"]
        upcoming_fixtures_raw = ctx["upcoming_fixtures_raw"]
        elements = ctx["elements"]
        teams = ctx["teams"]

        picks, bank, team_name, rank, chips_used, leagues = fetch_user_team(team_id, next_gw)

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
                            opp = teams.get(f["team_a"], "UNK")
                            upcoming_fixtures.append({"gw": target_gw, "opponent": f"{opp} (H)", "difficulty": f["team_h_difficulty"]})
                            found = True
                            break
                        elif f["team_a"] == player["team"]:
                            opp = teams.get(f["team_h"], "UNK")
                            upcoming_fixtures.append({"gw": target_gw, "opponent": f"{opp} (A)", "difficulty": f["team_a_difficulty"]})
                            found = True
                            break
                    if not found:
                        upcoming_fixtures.append({"gw": target_gw, "opponent": "Blank", "difficulty": 5})

                enriched_picks.append({
                    "id": player["id"],
                    "name": player["web_name"],
                    "team": teams.get(player["team"], "UNK"),
                    "team_code": player.get("team_code", 1),
                    "pos_code": player["element_type"],
                    "position": pick.get("position"),
                    "cost": player["now_cost"] / 10,
                    "is_captain": pick.get("is_captain", False),
                    "is_vice_captain": pick.get("is_vice_captain", False),
                    "multiplier": pick.get("multiplier", 1),
                    "xp": proj["xp"],
                    "form": float(player.get("form", 0) or 0),
                    "chance_of_playing": player.get("chance_of_playing_next_round"),
                    "news": player.get("news"),
                    "upcoming_fixtures": upcoming_fixtures,
                    "total_points": player.get("total_points", 0),
                    "selected_by_percent": float(player.get("selected_by_percent", 0) or 0),
                    "expected_goals": float(player.get("expected_goals", 0) or 0),
                    "expected_assists": float(player.get("expected_assists", 0) or 0),
                    "expected_goals_conceded": float(player.get("expected_goals_conceded", 0) or 0),
                    "defensive_contribution": float(player.get("defensive_contribution", 0) or 0),
                    "minutes": player.get("minutes", 0)
                })
                
        schedule = {}
        for gw_inc in range(gw_range):
            target_gw = next_gw + gw_inc
            gw_fixs = [f for f in upcoming_fixtures_raw if f.get("event") == target_gw]
            formatted_fixs = []
            for f in gw_fixs:
                formatted_fixs.append({
                    "home": teams.get(f["team_h"], "UNK"),
                    "away": teams.get(f["team_a"], "UNK"),
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
            "next_gw": next_gw,
            "squad": enriched_picks,
            "schedule": schedule,
            "chips_used": chips_used,
            "leagues": leagues
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
        
        a_picks, a_bank, _, _, _, _ = fetch_user_team(team_a, next_gw)
        b_picks, b_bank, _, _, _, _ = fetch_user_team(team_b, next_gw)
        
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
        teams = {t["id"]: t["short_name"] for t in bootstrap.get("teams", [])}
        
        def hydrate(pick_list):
            res = []
            for pick in pick_list:
                player = elements.get(pick["element"])
                if player:
                    res.append({
                        "id": player["id"],
                        "name": player["web_name"],
                        "team": teams.get(player["team"], "UNK"),
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
    pos_code: int
    max_budget: float
    current_squad_ids: List[int]
    transfer_out_id: Optional[int] = None

@app.post("/api/transfer-lab")
def get_transfer_recommendations(req: TransferRequest):
    try:
        ctx = get_fpl_context(gw_limit=5)
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
        for p in elements:
            if p["id"] in req.current_squad_ids and p["id"] != req.transfer_out_id:
                t = p["team"]
                team_counts[t] = team_counts.get(t, 0) + 1

        candidates = []
        for p in elements:
            if p["element_type"] == req.pos_code and p["id"] not in req.current_squad_ids:
                if (p["now_cost"] / 10) <= req.max_budget:
                    if team_counts.get(p["team"], 0) < 3:
                        c = calculate_player_projection(p, next_gw, upcoming_fixtures_raw, teams)
                        candidates.append(c)
                    
        candidates = sorted(candidates, key=lambda x: x["xp"], reverse=True)
        best_candidate = candidates[0] if candidates else None
        
        recommendation = "TRANSFER"
        delta = 0.0
        
        transfer_cost = 0.0
        opportunity_cost = DEFAULT_WEIGHTS["opportunity_cost"]
        threshold = transfer_cost + opportunity_cost
        
        if current_player and best_candidate:
            raw_gain = round(best_candidate["xp"] - current_player["xp"], 2)
            delta = raw_gain
            net_gain = raw_gain - threshold
            
            if net_gain <= 0:
                recommendation = "HOLD"
                
        if current_player:
            log_prediction(current_player["id"], current_player["name"], next_gw, current_player["xp"], "Transfer Lab - Current", "HOLD" if recommendation == "HOLD" else "SELL")
        if best_candidate:
            log_prediction(best_candidate["id"], best_candidate["name"], next_gw, best_candidate["xp"], "Transfer Lab - Candidate", recommendation)

        return {
            "recommendation": recommendation,
            "delta": delta,
            "threshold": threshold,
            "current_player": current_player,
            "best_transfer": best_candidate,
            "candidates": candidates
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/radar")
def get_radar():
    try:
        bootstrap = fetch_bootstrap()
        elements = bootstrap.get("elements", [])
        teams = {t["id"]: t["short_name"] for t in bootstrap.get("teams", [])}
        
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

@app.get("/api/budget-scenarios/{team_id}")
def get_budget_scenarios(team_id: int):
    try:
        dashboard_data = get_dashboard_data(team_id)
        squad = dashboard_data["squad"]
        bank = dashboard_data["bank"]
        next_gw = dashboard_data["next_gw"]
        
        bootstrap = fetch_bootstrap()
        all_fixtures = fetch_all_fixtures()
        elements = bootstrap.get("elements", [])
        teams = {t["id"]: t["short_name"] for t in bootstrap.get("teams", [])}
        
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
                
                candidates = sorted(candidates, key=lambda x: x["xp"], reverse=True)
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
