from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from fpl_api import fetch_bootstrap, fetch_user_team, fetch_fixtures, fetch_all_fixtures
import httpx

app = FastAPI(title="FPL Elite Scout API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
                team_id_fpl = player["team"]
                team_code = player["team_code"]
                is_gk = player["element_type"] == 1
                
                upcoming_fixtures = []
                for gw_inc in range(gw_range):
                    target_gw = next_gw + gw_inc
                    gw_fixs = [f for f in upcoming_fixtures_raw if f.get("event") == target_gw]
                    
                    found = False
                    for f in gw_fixs:
                        if f["team_h"] == team_id_fpl:
                            opp = teams.get(f["team_a"], "UNK")
                            upcoming_fixtures.append({
                                "gw": target_gw,
                                "opponent": f"{opp} (H)",
                                "difficulty": f["team_h_difficulty"]
                            })
                            found = True
                            break
                        elif f["team_a"] == team_id_fpl:
                            opp = teams.get(f["team_h"], "UNK")
                            upcoming_fixtures.append({
                                "gw": target_gw,
                                "opponent": f"{opp} (A)",
                                "difficulty": f["team_a_difficulty"]
                            })
                            found = True
                            break
                    if not found:
                        upcoming_fixtures.append({
                            "gw": target_gw,
                            "opponent": "Blank",
                            "difficulty": 5 # Blank GW penalty
                        })
                
                opponent = upcoming_fixtures[0]["opponent"] if upcoming_fixtures else "Blank"
                difficulty = upcoming_fixtures[0]["difficulty"] if upcoming_fixtures else 5
                
                enriched_picks.append({
                    "id": player["id"],
                    "name": player["web_name"],
                    "team": teams.get(team_id_fpl, "UNK"),
                    "team_code": team_code,
                    "pos_code": player["element_type"],
                    "is_gk": is_gk,
                    "cost": player["now_cost"] / 10,
                    "xp": float(player.get("ep_next", 0)),
                    "multiplier": pick["multiplier"],
                    "is_captain": pick["is_captain"],
                    "is_vice_captain": pick["is_vice_captain"],
                    "position": pick["position"],
                    "fixture": opponent,
                    "fixture_diff": difficulty,
                    "upcoming_fixtures": upcoming_fixtures,
                    "xg": float(player.get("expected_goals", 0) or 0),
                    "xa": float(player.get("expected_assists", 0) or 0),
                    "xgc": float(player.get("expected_goals_conceded", 0) or 0),
                    "form": float(player.get("form", 0) or 0),
                    "cs": player.get("clean_sheets", 0),
                    "gc": player.get("goals_conceded", 0),
                    "chance_of_playing": player.get("chance_of_playing_next_round"),
                    "news": player.get("news", ""),
                    "defcon": round(float(player.get("defensive_contribution", 0) or 0) / (player.get("minutes", 0) / 90.0), 2) if player.get("minutes", 0) > 0 else 0
                })
                
        schedule = {}
        for gw_inc in range(gw_range):
            target_gw = next_gw + gw_inc
            gw_fixs = [f for f in upcoming_fixtures_raw if f.get("event") == target_gw]
            formatted_fixs = []
            for f in gw_fixs:
                formatted_fixs.append({
                    "home_team": teams.get(f["team_h"], "UNK"),
                    "away_team": teams.get(f["team_a"], "UNK"),
                    "home_diff": f["team_h_difficulty"],
                    "away_diff": f["team_a_difficulty"],
                    "kickoff": f.get("kickoff_time", "")
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

class TransferRequest(BaseModel):
    pos_code: int
    max_budget: float
    current_squad_ids: List[int]

@app.get("/api/league/{league_id}")
async def get_league_standings(league_id: int, type: str = "classic"):
    # Determine the endpoint based on league type
    base_url = "https://fantasy.premierleague.com/api"
    endpoint = f"{base_url}/leagues-classic/{league_id}/standings/" if type == "classic" else f"{base_url}/leagues-h2h/{league_id}/standings/"
    
    async with httpx.AsyncClient() as client:
        res = await client.get(endpoint, headers={'User-Agent': 'Mozilla/5.0'})
        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail="League not found or unsupported")
        return res.json()

@app.get("/api/compare/{team_a}/{team_b}")
async def compare_teams(team_a: int, team_b: int, gw: int):
    base_url = "https://fantasy.premierleague.com/api"
    
    # We fetch their picks for the given GW
    async with httpx.AsyncClient() as client:
        a_res = await client.get(f"{base_url}/entry/{team_a}/event/{gw}/picks/", headers={'User-Agent': 'Mozilla/5.0'})
        b_res = await client.get(f"{base_url}/entry/{team_b}/event/{gw}/picks/", headers={'User-Agent': 'Mozilla/5.0'})
        
        a_info = await client.get(f"{base_url}/entry/{team_a}/", headers={'User-Agent': 'Mozilla/5.0'})
        b_info = await client.get(f"{base_url}/entry/{team_b}/", headers={'User-Agent': 'Mozilla/5.0'})
        
        if a_res.status_code != 200 or b_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Could not fetch picks. GW might be updating.")
            
        a_data = a_res.json()
        b_data = b_res.json()
        
        a_picks = a_data.get("picks", [])
        b_picks = b_data.get("picks", [])
        
        a_elements = {p["element"]: p for p in a_picks}
        b_elements = {p["element"]: p for p in b_picks}
        
        # Calculate differentials
        a_unique = [pid for pid in a_elements.keys() if pid not in b_elements]
        b_unique = [pid for pid in b_elements.keys() if pid not in a_elements]
        shared = [pid for pid in a_elements.keys() if pid in b_elements]
        
        # Enrich with bootstrap
        bootstrap = fetch_bootstrap()
        all_players = {p["id"]: {"name": p["web_name"], "team_code": p["team_code"]} for p in bootstrap.get("elements", [])}
        
        def enrich_picks(unique_ids, picks):
            res = []
            for pid in unique_ids:
                p_info = all_players.get(pid, {"name": f"Player {pid}", "team_code": 0})
                is_cap = a_elements.get(pid, {}).get("is_captain", False) if pid in a_elements else b_elements.get(pid, {}).get("is_captain", False)
                res.append({
                    "id": pid,
                    "name": p_info["name"],
                    "team_code": p_info["team_code"],
                    "is_captain": is_cap
                })
            return res

        def enrich_shared(shared_ids):
            res = []
            for pid in shared_ids:
                p_info = all_players.get(pid, {"name": f"Player {pid}", "team_code": 0})
                a_cap = a_elements.get(pid, {}).get("is_captain", False)
                b_cap = b_elements.get(pid, {}).get("is_captain", False)
                res.append({
                    "id": pid,
                    "name": p_info["name"],
                    "team_code": p_info["team_code"],
                    "a_captain": a_cap,
                    "b_captain": b_cap
                })
            return res

        return {
            "team_a": {
                "name": a_info.json().get("name", f"Team {team_a}") if a_info.status_code==200 else str(team_a),
                "manager": f"{a_info.json().get('player_first_name', '')} {a_info.json().get('player_last_name', '')}" if a_info.status_code==200 else "",
                "unique": enrich_picks(a_unique, a_picks),
                "picks": a_picks,
                "active_chip": a_data.get("active_chip")
            },
            "team_b": {
                "name": b_info.json().get("name", f"Team {team_b}") if b_info.status_code==200 else str(team_b),
                "manager": f"{b_info.json().get('player_first_name', '')} {b_info.json().get('player_last_name', '')}" if b_info.status_code==200 else "",
                "unique": enrich_picks(b_unique, b_picks),
                "picks": b_picks,
                "active_chip": b_data.get("active_chip")
            },
            "shared": enrich_shared(shared)
        }

@app.post("/api/transfer-lab")
def get_transfer_recommendations(req: TransferRequest):
    try:
        bootstrap = fetch_bootstrap()
        events = bootstrap.get("events", [])
        current_gw = next((e["id"] for e in events if e["is_current"]), None)
        next_gw = next((e["id"] for e in events if e["is_next"]), None)
        if not next_gw and current_gw:
            next_gw = current_gw + 1
        elif not next_gw:
            next_gw = 1
            
        gw_fixtures = fetch_fixtures(next_gw)
        
        elements = bootstrap.get("elements", [])
        teams = {t["id"]: t["short_name"] for t in bootstrap.get("teams", [])}
        
        candidates = []
        for p in elements:
            if p["element_type"] == req.pos_code and p["id"] not in req.current_squad_ids:
                team_id_fpl = p["team"]
                difficulty = 3
                for f in gw_fixtures:
                    if f["team_h"] == team_id_fpl:
                        difficulty = f["team_h_difficulty"]
                        break
                    elif f["team_a"] == team_id_fpl:
                        difficulty = f["team_a_difficulty"]
                        break
                
                xp = float(p.get("ep_next", 0) or 0)
                # Adjust xp based on fixture difficulty to avoid recommending players with hard fixtures
                if difficulty >= 4:
                    xp *= 0.6  # Penalize hard fixtures heavily
                elif difficulty <= 2:
                    xp *= 1.2  # Reward easy fixtures

                cost = p["now_cost"] / 10
                candidates.append({
                    "id": p["id"],
                    "name": p["web_name"],
                    "team": teams.get(p["team"], "UNK"),
                    "team_code": p["team_code"],
                    "pos_code": p["element_type"],
                    "cost": cost,
                    "xp": xp,
                    "total_points": p.get("total_points", 0)
                })
        # Sort by XP descending and return all (frontend will slice top 3 and allow searching the rest)
        candidates = sorted(candidates, key=lambda x: x["xp"], reverse=True)
        return candidates
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/radar")
def get_elite_radar():
    try:
        bootstrap = fetch_bootstrap()
        events = bootstrap.get("events", [])
        current_gw = next((e["id"] for e in events if e["is_current"]), None)
        next_gw = next((e["id"] for e in events if e["is_next"]), None)
        if not next_gw and current_gw:
            next_gw = current_gw + 1
        elif not next_gw:
            next_gw = 1
            
        gw_fixtures = fetch_fixtures(next_gw)
        
        elements = bootstrap.get("elements", [])
        teams = {t["id"]: t["short_name"] for t in bootstrap.get("teams", [])}
        
        all_players = []
        for p in elements:
            # Only consider players who are active
            if p["status"] == "a":
                team_id_fpl = p["team"]
                difficulty = 3
                for f in gw_fixtures:
                    if f["team_h"] == team_id_fpl:
                        difficulty = f["team_h_difficulty"]
                        break
                    elif f["team_a"] == team_id_fpl:
                        difficulty = f["team_a_difficulty"]
                        break
                
                xp = float(p.get("ep_next", 0) or 0)
                # Adjust xp based on fixture difficulty to avoid recommending players with hard fixtures
                if difficulty >= 4:
                    xp *= 0.6
                elif difficulty <= 2:
                    xp *= 1.2
                    
                cost = p["now_cost"] / 10
                all_players.append({
                    "id": p["id"],
                    "name": p["web_name"],
                    "team": teams.get(p["team"], "UNK"),
                    "pos_code": p["element_type"],
                    "cost": cost,
                    "xp": xp,
                    "form": float(p.get("form", 0) or 0),
                    "selected_by_percent": float(p.get("selected_by_percent", 0) or 0),
                    "total_points": p.get("total_points", 0),
                    "xg": float(p.get("expected_goals", 0) or 0),
                    "xa": float(p.get("expected_assists", 0) or 0)
                })
        
        # 1. Scout Picks (Top XP)
        scout_picks = sorted(all_players, key=lambda x: x["xp"], reverse=True)[:10]
        
        # 2. Hot Form (Top Form)
        hot_form = sorted(all_players, key=lambda x: x["form"], reverse=True)[:10]
        
        # 3. Differentials (Ownership < 10%, Top XP)
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
        
        team_difficulty = {}
        for t_id in teams.keys():
            team_fixtures = [f for f in all_fixtures if (f["team_h"] == t_id or f["team_a"] == t_id) and f.get("event") and next_gw <= f["event"] < next_gw + 5]
            if team_fixtures:
                diff_sum = sum(f["team_h_difficulty"] if f["team_h"] == t_id else f["team_a_difficulty"] for f in team_fixtures)
                team_difficulty[t_id] = diff_sum / len(team_fixtures)
            else:
                team_difficulty[t_id] = 3.0
            
        all_players = []
        for p in elements:
            if p["status"] == "a":
                team_id_fpl = p["team"]
                difficulty = team_difficulty.get(team_id_fpl, 3)
                
                xp = float(p.get("ep_next", 0) or 0)
                if difficulty >= 4:
                    xp *= 0.6
                elif difficulty <= 2:
                    xp *= 1.2
                    
                games_played = p.get("minutes", 0) / 90.0 if p.get("minutes", 0) > 0 else 0
                cbi = float(p.get("defensive_contribution", 0) or 0)
                
                all_players.append({
                    "id": p["id"],
                    "name": p["web_name"],
                    "team": teams.get(p["team"], "UNK"),
                    "team_code": p["team_code"],
                    "pos_code": p["element_type"],
                    "cost": p["now_cost"] / 10,
                    "xp": xp,
                    "form": float(p.get("form", 0) or 0),
                    "difficulty": difficulty,
                    "defcon": round(cbi / games_played, 2) if games_played > 0 else 0
                })
        
        team_name_to_id = {v: k for k, v in teams.items()}
        current_squad_ids = [p["id"] for p in squad]
        suggestions = []
        
        for sp in squad:
            reason = None
            sp_team_id = team_name_to_id.get(sp.get("team"))
            avg_diff = team_difficulty.get(sp_team_id, 3) if sp_team_id else 3
            form_val = float(sp.get("form", 0))
            
            if sp.get("chance_of_playing") is not None and sp.get("chance_of_playing") < 75:
                reason = "Injury / Doubtful"
            elif form_val < 2.0 and avg_diff >= 3.5:
                reason = f"Poor Form & Tough Fixtures (Avg FDR {avg_diff:.1f})"
            elif avg_diff >= 4.0 and form_val < 4.5:  # Don't sell if form is elite (>=4.5) even if fixtures are hard
                reason = f"Tough Fixtures & No Momentum (FDR {avg_diff:.1f})"
            elif form_val < 2.5 and sp.get("xp", 0) < 2.5:
                reason = "Poor Output (Low Form & xP)"
                
            if reason:
                budget = bank + sp["cost"]
                candidates = [p for p in all_players if p["pos_code"] == sp["pos_code"] and p["id"] not in current_squad_ids and p["cost"] <= budget]
                
                for cand in candidates:
                    # Appeal = Base xP + (Form * 1.2) - (Difficulty penalty)
                    # This puts heavy emphasis on players with high form/momentum
                    cand_score = cand["xp"] + (cand["form"] * 1.2) + ((3 - cand["difficulty"]) * 0.8)
                    if cand["pos_code"] in [1, 2]: # GK / DEF
                        cand_score += (cand["defcon"] / 15.0)
                    cand["appeal"] = cand_score
                
                candidates = sorted(candidates, key=lambda x: x["appeal"], reverse=True)
                
                top_candidates = candidates[:3]
                
                if top_candidates:
                    suggestions.append({
                        "sell": sp,
                        "reason": reason,
                        "buys": top_candidates
                    })
                    
        return suggestions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

