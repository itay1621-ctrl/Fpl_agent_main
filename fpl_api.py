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

def fetch_user_team(
    t_id: int,
    gw: int,
    cookie: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], float, str, str, List[str], Dict[str, Any], int, Dict[str, Any]]:
    entry_url = f"{BASE_URL}entry/{t_id}/"
    history_url = f"{BASE_URL}entry/{t_id}/history/"
    
    e_res = requests.get(entry_url, headers=API_HEADERS, timeout=12)
    entry_res = e_res.json() if e_res.status_code == 200 else {}
    
    h_res = requests.get(history_url, headers=API_HEADERS, timeout=12)
    history_res = h_res.json() if h_res.status_code == 200 else {}
    
    team_name = entry_res.get("name", f"Team {t_id}") if entry_res else f"Team {t_id}"
    rank = entry_res.get("summary_overall_rank", "N/A") if entry_res else "N/A"
    chips_used = [c.get("name") for c in history_res.get("chips", [])] if history_res else []
    leagues = entry_res.get("leagues", {"classic": [], "h2h": []}) if entry_res else {"classic": [], "h2h": []}
    free_transfers = calculate_free_transfers(history_res)
    
    # Layer 1: Authenticated my-team endpoint if cookie provided
    if cookie:
        cookie_clean = cookie.strip()
        auth_headers = dict(API_HEADERS)
        if "pl_profile=" in cookie_clean or "=" in cookie_clean:
            auth_headers["Cookie"] = cookie_clean
        else:
            auth_headers["Cookie"] = f"pl_profile={cookie_clean}"
            
        try:
            mt_res = requests.get(f"{BASE_URL}my-team/{t_id}/", headers=auth_headers, timeout=12)
            if mt_res.status_code == 200:
                mt_data = mt_res.json()
                picks = mt_data.get("picks", []) or []
                transfers_dict = mt_data.get("transfers", {})
                bank = transfers_dict.get("bank", 0) / 10.0
                
                # Active chip detection
                active_chip = None
                for c in mt_data.get("chips", []):
                    if c.get("status_for_entry") == "active" or c.get("status") == "active" or c.get("is_active"):
                        active_chip = c.get("name")
                if not active_chip:
                    if transfers_dict.get("wildcard"):
                        active_chip = "wildcard"
                    elif transfers_dict.get("freehit"):
                        active_chip = "freehit"
                        
                if active_chip and active_chip not in chips_used:
                    chips_used.append(active_chip)
                    
                limit = transfers_dict.get("limit", 1)
                made = transfers_dict.get("made", 0)
                if active_chip in ["wildcard", "freehit"]:
                    free_transfers = 99
                else:
                    free_transfers = max(0, limit - made)
                    
                squad_meta = {
                    "source": "live_my_team",
                    "is_live_current": True,
                    "event": gw,
                    "active_chip": active_chip,
                    "pending_deadline_gw": None,
                    "authenticated": True
                }
                return picks, bank, team_name, rank, chips_used, leagues, free_transfers, squad_meta
        except Exception:
            pass # Fall through to public layers

    # Layer 2: Public Current Event picks (e.g. if deadline passed or publicly published)
    curr_picks_url = f"{BASE_URL}entry/{t_id}/event/{gw}/picks/"
    try:
        curr_res = requests.get(curr_picks_url, headers=API_HEADERS, timeout=12)
        if curr_res.status_code == 200:
            picks_res = curr_res.json()
            bank = (picks_res.get("entry_history") or {}).get("bank", 0) / 10
            picks = picks_res.get("picks", []) or []
            active_chip = picks_res.get("active_chip")
            if active_chip and active_chip not in chips_used:
                chips_used.append(active_chip)
            squad_meta = {
                "source": "public_current_event",
                "is_live_current": True,
                "event": gw,
                "active_chip": active_chip,
                "pending_deadline_gw": None,
                "authenticated": False
            }
            return picks, bank, team_name, rank, chips_used, leagues, free_transfers, squad_meta
    except Exception:
        pass

    # Layer 3: Completed GW fallback (pre-deadline public privacy)
    last_gw = max(1, gw - 1)
    fallback_url = f"{BASE_URL}entry/{t_id}/event/{last_gw}/picks/"
    fb_res = requests.get(fallback_url, headers=API_HEADERS, timeout=12)
    fb_res.raise_for_status()
    picks_res = fb_res.json()
    
    if picks_res.get("active_chip") == "free_hit" and last_gw > 1:
        base_gw = last_gw - 1
        base_url = f"{BASE_URL}entry/{t_id}/event/{base_gw}/picks/"
        b_res = requests.get(base_url, headers=API_HEADERS, timeout=12)
        if b_res.status_code == 200:
            picks_res = b_res.json()
            
    bank = (picks_res.get("entry_history") or {}).get("bank", 0) / 10
    picks = picks_res.get("picks", []) or []
    active_chip = picks_res.get("active_chip")
    
    squad_meta = {
        "source": "completed_gw_fallback",
        "is_live_current": False,
        "event": last_gw,
        "pending_deadline_gw": gw,
        "active_chip": active_chip,
        "authenticated": False
    }
    return picks, bank, team_name, rank, chips_used, leagues, free_transfers, squad_meta

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
    if not isinstance(transfers, list):
        transfers = []
        
    if history_res is None:
        history_res = fetch_user_history(team_id)
        
    # Free Hit Gameweeks: exclude temporary transfers so they don't corrupt the permanent squad
    chips = history_res.get("chips", []) if isinstance(history_res, dict) else []
    if not isinstance(chips, list):
        chips = []
    fh_events = {
        int(c.get("event"))
        for c in chips
        if isinstance(c, dict) and c.get("name") == "freehit" and c.get("event") is not None
    }
    
    target_gw = next_gw if next_gw else 38
    
    valid_transfers = []
    for t in transfers:
        if not isinstance(t, dict):
            continue
        ev = t.get("event")
        if ev is not None:
            ev = int(ev)
            if ev in fh_events:
                continue
            if ev <= target_gw:
                valid_transfers.append(t)
                
    # Sort chronologically by transfer time ascending so the latest purchase overwrites older ones
    valid_transfers.sort(key=lambda x: str(x.get("time", "")))
    
    purchase_lookup = {}
    for t in valid_transfers:
        if not isinstance(t, dict):
            continue
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
        
        raw_pp = pick.get("purchase_price")
        raw_sp = pick.get("selling_price")
        
        if raw_pp is not None:
            purch_cost = raw_pp if raw_pp > 30 else int(round(raw_pp * 10))
            if raw_sp is not None:
                sell_cost = raw_sp if raw_sp > 30 else int(round(raw_sp * 10))
            else:
                if now_cost > purch_cost:
                    sell_cost = purch_cost + ((now_cost - purch_cost) // 2)
                else:
                    sell_cost = now_cost
        else:
            cost_change_start = el.get("cost_change_start", 0)
            initial_cost = now_cost - cost_change_start
            purch_cost = purchase_lookup.get(el_id, initial_cost)
            if now_cost > purch_cost:
                sell_cost = purch_cost + ((now_cost - purch_cost) // 2)
            else:
                sell_cost = now_cost
            
        result[el_id] = {
            "purchase_price": round(purch_cost / 10.0, 1),
            "selling_price": round(sell_cost / 10.0, 1)
        }
        
    return result
