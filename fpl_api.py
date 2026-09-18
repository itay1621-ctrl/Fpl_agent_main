import requests
from typing import Dict, Any, Tuple, List
import time
from functools import wraps

API_HEADERS = {'User-Agent': 'Mozilla/5.0'}
BASE_URL = "https://fantasy.premierleague.com/api/"

def time_cache(max_age: int):
    cache = {}
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            now = time.time()
            if key in cache and now - cache[key]['time'] < max_age:
                return cache[key]['data']
            
            result = func(*args, **kwargs)
            cache[key] = {'time': now, 'data': result}
            return result
        return wrapper
    return decorator

@time_cache(max_age=300)
def fetch_bootstrap() -> Dict[str, Any]:
    url = f"{BASE_URL}bootstrap-static/"
    res = requests.get(url, headers=API_HEADERS, timeout=12)
    res.raise_for_status()
    return res.json()

def fetch_user_team(t_id: int, gw: int) -> Tuple[List[Dict[str, Any]], float, str, str, List[str], Dict[str, Any]]:
    last_gw = max(1, gw - 1)
    picks_url = f"{BASE_URL}entry/{t_id}/event/{last_gw}/picks/"
    entry_url = f"{BASE_URL}entry/{t_id}/"
    history_url = f"{BASE_URL}entry/{t_id}/history/"
    
    p_res = requests.get(picks_url, headers=API_HEADERS, timeout=12)
    p_res.raise_for_status()
    picks_res = p_res.json()
    
    e_res = requests.get(entry_url, headers=API_HEADERS, timeout=12)
    e_res.raise_for_status()
    entry_res = e_res.json()
    
    h_res = requests.get(history_url, headers=API_HEADERS, timeout=12)
    h_res.raise_for_status()
    history_res = h_res.json()
    
    if picks_res.get("active_chip") == "free_hit" and last_gw > 1:
        base_gw = last_gw - 1
        base_url = f"{BASE_URL}entry/{t_id}/event/{base_gw}/picks/"
        b_res = requests.get(base_url, headers=API_HEADERS, timeout=12)
        b_res.raise_for_status()
        picks_res = b_res.json()
        
    bank = (picks_res.get("entry_history") or {}).get("bank", 0) / 10
    picks = picks_res.get("picks", []) or []
    team_name = entry_res.get("name", f"Team {t_id}") if entry_res else f"Team {t_id}"
    rank = entry_res.get("summary_overall_rank", "N/A") if entry_res else "N/A"
    
    chips_used = [c.get("name") for c in history_res.get("chips", [])] if history_res else []
    leagues = entry_res.get("leagues", {"classic": [], "h2h": []}) if entry_res else {"classic": [], "h2h": []}
    
    return picks, bank, team_name, rank, chips_used, leagues

@time_cache(max_age=3600)
def fetch_fixtures(gw: int) -> List[Dict[str, Any]]:
    url = f"{BASE_URL}fixtures/?event={gw}"
    res = requests.get(url, headers=API_HEADERS, timeout=12)
    res.raise_for_status()
    return res.json()

@time_cache(max_age=3600)
def fetch_all_fixtures() -> List[Dict[str, Any]]:
    url = f"{BASE_URL}fixtures/"
    res = requests.get(url, headers=API_HEADERS, timeout=12)
    res.raise_for_status()
    return res.json()
