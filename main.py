from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from fpl_api import fetch_bootstrap, fetch_user_team, fetch_fixtures, fetch_all_fixtures

app = FastAPI(title="FPL Elite Scout API")

# Update CORS to be more secure
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://fpl-agent-main-five.vercel.app", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

def calculate_player_projection(p, next_gw, upcoming_fixtures_raw, teams):
    team_id_fpl = p["team"]
    pos_code = p["element_type"]
    
    base_xp = float(p.get("ep_next", 0) or 0)
    chance = p.get("chance_of_playing_next_round")
    prob = 1.0
    if chance is not None:
        prob = float(chance) / 100.0
        
    form_val = float(p.get("form", 0) or 0)
    xg = float(p.get("expected_goals", 0) or 0)
    xa = float(p.get("expected_assists", 0) or 0)
    xgc = float(p.get("expected_goals_conceded", 0) or 0)
    defcon = float(p.get("defensive_contribution", 0) or 0)
    
    underlying_adj = 0.0
    if pos_code in [3, 4]:
        underlying_adj = (xg + xa) * 0.2
    else:
        underlying_adj = (defcon * 0.02) - (xgc * 0.2)
        
    gw_range = min(5, 38 - next_gw + 1)
    weights = [0.4, 0.25, 0.15, 0.1, 0.1]
    weighted_multiplier = 0
    fixtures_found = 0
    
    next_gw_opponent = "Blank"
    next_gw_diff = 5
    
    for gw_inc in range(gw_range):
        target_gw = next_gw + gw_inc
        gw_fixs = [f for f in upcoming_fixtures_raw if f.get("event") == target_gw]
        player_fixs = [f for f in gw_fixs if f["team_h"] == team_id_fpl or f["team_a"] == team_id_fpl]
        
        gw_mult = 0
        if len(player_fixs) == 0:
            gw_mult = 0
        else:
            for f in player_fixs:
                is_home = f["team_h"] == team_id_fpl
                diff = f["team_h_difficulty"] if is_home else f["team_a_difficulty"]
                
                if gw_inc == 0 and fixtures_found == 0:
                    opp_id = f["team_a"] if is_home else f["team_h"]
                    next_gw_opponent = f"{teams.get(opp_id, 'UNK')} ({'H' if is_home else 'A'})"
                    next_gw_diff = diff
                    
                if diff >= 4:
                    gw_mult += 0.8
                elif diff <= 2:
                    gw_mult += 1.2
                else:
                    gw_mult += 1.0
                    
        fixtures_found += len(player_fixs)
        weighted_multiplier += gw_mult * weights[gw_inc]
        
    if fixtures_found == 0:
        weighted_multiplier = 0
        
    core_score = (base_xp * 0.5 + form_val * 0.3 + underlying_adj) * prob * weighted_multiplier
    core_score = max(0.0, core_score)
    
    confidence = "Medium"
    if prob < 1.0:
        confidence = "Low"
    elif fixtures_found > 0 and len(player_fixs) > 1:
        confidence = "High (DGW)"
    elif base_xp > 5.0 and prob == 1.0:
        confidence = "High"
        
    reasons = []
    if core_score > 4.5:
        reasons.append("+ Strong 5GW projection")
    if prob < 1.0:
        reasons.append(f"- Rotation/Injury risk ({int(prob*100)}% chance)")
    if underlying_adj > 0.5:
        reasons.append("+ Elite underlying stats")
    elif underlying_adj < -0.3:
        reasons.append("- Poor underlying stats")
    if weighted_multiplier > 1.05:
        reasons.append("+ Favorable upcoming fixtures")
    elif weighted_multiplier < 0.9:
        reasons.append("- Difficult upcoming fixtures")
        
    reason_str = "\n".join(reasons) if reasons else "Average overall profile."
        
    return {
        "id": p["id"],
        "name": p["web_name"],
        "team": teams.get(p["team"], "UNK"),
        "team_code": p["team_code"],
        "pos_code": pos_code,
        "cost": p["now_cost"] / 10,
        "xp": round(core_score, 2),
        "form": form_val,
        "total_points": p.get("total_points", 0),
        "selected_by_percent": float(p.get("selected_by_percent", 0) or 0),
        "fixture": next_gw_opponent,
        "fixture_diff": next_gw_diff,
        "confidence": confidence,
        "reason": reason_str,
        "prob": prob,
        "xg": xg,
        "xa": xa
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

@app.get("/api/dashboard/{team_id}")
def get_dashboard_data(team_id: int):
    try:
        bootstrap = fetch_bootstrap()
        
        events = bootstrap.get("events", [])
        current_gw = next((e["id"] for e in events if e["is_current"]), None)
        next_gw = next((e["id"] for e in events if e["is_next"]), None)
        if not next_gw and current_gw:
            next_gw = current_gw + 1
        elif not next_gw:
            next_gw = 1
            
        picks, bank, team_name, rank, chips_used, leagues = fetch_user_team(team_id, next_gw)
        gw_fixtures = fetch_fixtures(next_gw)
        
        elements = {p["id"]: p for p in bootstrap.get("elements", [])}
        teams = {t["id"]: t["short_name"] for t in bootstrap.get("teams", [])}
        
        all_fixtures = fetch_all_fixtures()
        max_gw = 38
        gw_range = max(1, max_gw - next_gw + 1)
        upcoming_fixtures_raw = [f for f in all_fixtures if f.get("event") and next_gw <= f["event"] <= max_gw]

        enriched_picks = []
        for pick in picks:
            player = elements.get(pick["element"])
            if player:
                # Use the new projection core to enrich dashboard data
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
                    "pos_code": player["element_type"],
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
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
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
        a_info = requests.get(f"https://fantasy.premierleague.com/api/entry/{team_a}/", headers={'User-Agent': 'Mozilla/5.0'})
        b_info = requests.get(f"https://fantasy.premierleague.com/api/entry/{team_b}/", headers={'User-Agent': 'Mozilla/5.0'})
        
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
                        "pos_code": player["element_type"],
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
        bootstrap = fetch_bootstrap()
        events = bootstrap.get("events", [])
        next_gw = next((e["id"] for e in events if e["is_next"]), 1)
        all_fixtures = fetch_all_fixtures()
        
        gw_range = min(5, 38 - next_gw + 1)
        upcoming_fixtures_raw = [f for f in all_fixtures if f.get("event") and next_gw <= f["event"] <= next_gw + gw_range - 1]
        
        elements = bootstrap.get("elements", [])
        teams = {t["id"]: t["short_name"] for t in bootstrap.get("teams", [])}
        
        current_player = None
        if req.transfer_out_id:
            curr_p_raw = next((p for p in elements if p["id"] == req.transfer_out_id), None)
            if curr_p_raw:
                current_player = calculate_player_projection(curr_p_raw, next_gw, upcoming_fixtures_raw, teams)
                
        candidates = []
        for p in elements:
            if p["element_type"] == req.pos_code and p["id"] not in req.current_squad_ids:
                if (p["now_cost"] / 10) <= req.max_budget:
                    c = calculate_player_projection(p, next_gw, upcoming_fixtures_raw, teams)
                    candidates.append(c)
                    
        candidates = sorted(candidates, key=lambda x: x["xp"], reverse=True)
        best_candidate = candidates[0] if candidates else None
        
        recommendation = "TRANSFER"
        delta = 0.0
        threshold = 2.0
        
        if current_player and best_candidate:
            delta = round(best_candidate["xp"] - current_player["xp"], 2)
            if delta < threshold:
                recommendation = "HOLD"
                
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
                reason = "Poor Output (Low Form & V2 Projection)"
            elif sp.get("xp", 0) < 2.0:
                reason = "Tough Upcoming Run (Low V2 Projection)"
                
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
