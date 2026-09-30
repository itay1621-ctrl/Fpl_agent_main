import requests
from typing import Dict, Any, Tuple, List, Optional
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

@time_cache(max_age=300)
def fetch_user_transfers(t_id: int) -> List[Dict[str, Any]]:
    url = f"{BASE_URL}entry/{t_id}/transfers/"
    try:
        res = requests.get(url, headers=API_HEADERS, timeout=12)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return []

@time_cache(max_age=300)
def fetch_user_history(t_id: int) -> Dict[str, Any]:
    url = f"{BASE_URL}entry/{t_id}/history/"
    try:
        res = requests.get(url, headers=API_HEADERS, timeout=12)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return {}

def calculate_player_prices(
    team_id: int,
    picks: List[Dict[str, Any]],
    elements: Dict[int, Dict[str, Any]],
    next_gw: int,
    history_res: Optional[Dict[str, Any]] = None,
    transfers: Optional[List[Dict[str, Any]]] = None
) -> Dict[int, Dict[str, float]]:
    """
    Reconstructs the true purchase_price and selling_price for each player in picks
    in accordance with official FPL rules.
    Returns: {element_id: {"purchase_price": float, "selling_price": float}} in millions of £.
    """
    if transfers is None:
        transfers = fetch_user_transfers(team_id)
        
    if history_res is None:
        history_res = fetch_user_history(team_id)
        
    # Free Hit Gameweeks: exclude temporary transfers so they don't corrupt the permanent squad
    chips = history_res.get("chips", []) if history_res else []
    fh_events = {
        int(c.get("event"))
        for c in chips
        if c.get("name") == "freehit" and c.get("event") is not None
    }
    
    last_gw = max(1, (next_gw or 1) - 1)
    
    valid_transfers = []
    for t in transfers:
        ev = t.get("event")
        if ev is not None:
            ev = int(ev)
            if ev in fh_events:
                continue
            if ev <= last_gw:
                valid_transfers.append(t)
                
    # Sort chronologically by transfer time ascending so the latest purchase overwrites older ones
    valid_transfers.sort(key=lambda x: str(x.get("time", "")))
    
    purchase_lookup = {}
    for t in valid_transfers:
        el_in = t.get("element_in")
        in_cost = t.get("element_in_cost")
        if el_in is not None and in_cost is not None:
            purchase_lookup[el_in] = in_cost
            
    result = {}
    for pick in picks:
        el_id = pick.get("element")
        if not el_id:
            continue
        el = elements.get(el_id, {})
        now_cost = el.get("now_cost", 0)
        cost_change_start = el.get("cost_change_start", 0)
        
        # Player in squad since GW1 was purchased at initial cost: now_cost - cost_change_start
        initial_cost = now_cost - cost_change_start
        purch_cost = purchase_lookup.get(el_id, initial_cost)
        
        # FPL official selling price formula:
        if now_cost > purch_cost:
            sell_cost = purch_cost + ((now_cost - purch_cost) // 2)
        else:
            sell_cost = now_cost
            
        result[el_id] = {
            "purchase_price": round(purch_cost / 10.0, 1),
            "selling_price": round(sell_cost / 10.0, 1)
        }
        
    return result
