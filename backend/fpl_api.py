import requests
from typing import Dict, Any, Tuple, List
import time
from functools import wraps

API_HEADERS = {'User-Agent': 'Mozilla/5.0'}
BASE_URL = "https://fantasy.premierleague.com/api/"


def calculate_free_transfers(history_res: Dict[str, Any]) -> int:
    """
    Reconstruct the manager's current free-transfer balance from their
    own FPL history.

    FPL gives managers 1 free transfer per Gameweek, which can roll over
    up to a maximum of 5. Wildcard and Free Hit preserve already banked
    transfers, but the free transfer for the chip Gameweek is consumed
    rather than creating an additional transfer.

    The history endpoint is manager-specific, so this calculation is
    performed independently for each team_id.
    """
    if not history_res:
        return 1

    current = history_res.get("current", []) or []
    chips = history_res.get("chips", []) or []

    # Chip usage is recorded separately from current[]. Build a lookup
    # by Gameweek so Wildcard/Free Hit can be handled correctly.
    chip_by_event = {
        int(chip.get("event")): chip.get("name")
        for chip in chips
        if chip.get("event") is not None
    }

    # After the GW1 deadline, every manager starts GW2 with 1 FT.
    # GW1 itself had unlimited transfers, so it must not add another FT.
    ft = 1

    for row in sorted(current, key=lambda item: item.get("event", 0)):
        event = row.get("event")
        if event is None or event <= 1:
            continue

        event = int(event)
        transfers = max(0, int(row.get("event_transfers", 0) or 0))
        chip = chip_by_event.get(event)

        # Wildcard and Free Hit do not consume banked FTs.
        # The FT granted for the chip GW is effectively used by the chip,
        # so the balance carries forward unchanged.
        if chip in {"wildcard", "freehit"}:
            continue

        # Normal Gameweek:
        # 1) spend available free transfers on the transfers made
        # 2) receive the next Gameweek's free transfer
        ft = max(0, ft - transfers)
        ft = min(5, ft + 1)

    return max(1, min(5, ft))
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

def fetch_user_team(t_id: int, gw: int) -> Tuple[List[Dict[str, Any]], float, str, str, List[str], Dict[str, Any], int]:
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
    free_transfers = calculate_free_transfers(history_res)
    
    return picks, bank, team_name, rank, chips_used, leagues, free_transfers

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
