import requests

def test_fpl_api():
    r = requests.get('https://fantasy.premierleague.com/api/bootstrap-static/', headers={'User-Agent': 'Mozilla/5.0'}).json()
    events = r.get('events', [])
    current_event = next((e for e in events if e.get('is_current')), None)
    next_event = next((e for e in events if e.get('is_next')), None)
    print('Current GW:', current_event['id'] if current_event else 'None')
    print('Next GW:', next_event['id'] if next_event else 'None')

    team_id = 3450961
    if next_event:
        res = requests.get(f"https://fantasy.premierleague.com/api/entry/{team_id}/event/{next_event['id']}/picks/", headers={'User-Agent': 'Mozilla/5.0'})
        print(f"Picks for next GW ({next_event['id']}): Status {res.status_code}")

    if current_event:
        res = requests.get(f"https://fantasy.premierleague.com/api/entry/{team_id}/event/{current_event['id']}/picks/", headers={'User-Agent': 'Mozilla/5.0'})
        print(f"Picks for current GW ({current_event['id']}): Status {res.status_code}")

    res_t = requests.get(f"https://fantasy.premierleague.com/api/entry/{team_id}/transfers/", headers={'User-Agent': 'Mozilla/5.0'})
    print('Transfers endpoint status:', res_t.status_code)
    if res_t.status_code == 200:
        t_list = res_t.json()
        print('Total transfers count:', len(t_list))
        if t_list:
            print('Latest transfer event:', t_list[0].get('event'), 'time:', t_list[0].get('time'))

    res_my = requests.get(f"https://fantasy.premierleague.com/api/my-team/{team_id}/", headers={'User-Agent': 'Mozilla/5.0'})
    print('my-team endpoint (no auth): Status', res_my.status_code)

if __name__ == '__main__':
    test_fpl_api()
