import test from 'node:test';
import assert from 'node:assert/strict';

/**
 * Mirror of countdown determination logic from app/page.tsx
 */
function resolveDeadline(data) {
  if (!data) return null;

  let deadline = null;

  if (data.deadline_time && typeof data.deadline_time === 'string') {
    const parsed = new Date(data.deadline_time);
    if (!isNaN(parsed.getTime())) {
      deadline = parsed;
    }
  }

  if (!deadline) {
    const rawMatches = data.schedule?.[data?.next_gw] || [];
    const validMatches = (Array.isArray(rawMatches) ? rawMatches : [])
      .filter((m) => m && m.time && typeof m.time === 'string' && !isNaN(new Date(m.time).getTime()))
      .sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());

    if (validMatches.length === 0) {
      return null; // sets "Time unknown"
    }

    const firstMatchTime = new Date(validMatches[0].time);
    deadline = new Date(firstMatchTime.getTime() - 90 * 60000);
  }

  return deadline;
}

/**
 * Mirror of upcoming fixtures generation logic for transfers and drafts in app/page.tsx
 */
function formatUpcomingFixtures(playerTeam, nextGw, schedule) {
  const upcoming_fixtures = [];
  for (let offset = 0; offset <= 38 - nextGw; offset++) {
    const gw = nextGw + offset;
    const gwFixtures = schedule[gw] || [];
    const teamOpponents = [];
    const teamDiffs = [];
    for (const match of gwFixtures) {
      if (match.home_team === playerTeam) {
        teamOpponents.push(`${match.away_team} (H)`);
        teamDiffs.push(match.home_diff);
      } else if (match.away_team === playerTeam) {
        teamOpponents.push(`${match.home_team} (A)`);
        teamDiffs.push(match.away_diff);
      }
    }
    if (teamOpponents.length === 0) {
      upcoming_fixtures.push({ gw, opponent: "Blank", difficulty: 5 });
    } else if (teamOpponents.length === 1) {
      upcoming_fixtures.push({ gw, opponent: teamOpponents[0], difficulty: teamDiffs[0] });
    } else {
      const avgDiff = Math.round(teamDiffs.reduce((a, b) => a + b, 0) / teamDiffs.length);
      upcoming_fixtures.push({ gw, opponent: teamOpponents.join(', '), difficulty: avgDiff });
    }
  }
  return upcoming_fixtures;
}

/**
 * Mirror of renderPlayer mapping logic from app/page.tsx
 */
function mapPlayerForPitch(p, selectedGwOffset) {
  const fix0 = p.upcoming_fixtures?.[selectedGwOffset];
  return {
    ...p,
    fixture: fix0 ? fix0.opponent : (selectedGwOffset === 0 ? (p.fixture || 'Blank') : 'Blank'),
    fixture_diff: fix0 ? fix0.difficulty : (selectedGwOffset === 0 ? (p.fixture_diff ?? 5) : 5),
  };
}

/**
 * Mirror of savedPlan sync logic from fetchTeam in app/page.tsx
 */
function syncSavedPlanDeadline(savedPlan, result) {
  if (result.deadline_time && typeof result.deadline_time === 'string' && !isNaN(new Date(result.deadline_time).getTime()) && savedPlan.next_gw === result.next_gw) {
    savedPlan.deadline_time = result.deadline_time;
  }
  if (result.schedule && savedPlan.next_gw === result.next_gw) {
    savedPlan.schedule = result.schedule;
  }
  return savedPlan;
}

// -------------------------------------------------------------
// Test 1: Deadline resolution and fallback behavior
// -------------------------------------------------------------

test('resolveDeadline uses official deadline_time when present', () => {
  const mockData = {
    next_gw: 10,
    deadline_time: '2026-10-24T10:00:00Z',
    schedule: {
      10: [
        { time: '2026-10-24T12:00:00Z', home_team: 'ARS', away_team: 'CHE' }
      ]
    }
  };

  const deadline = resolveDeadline(mockData);
  assert.equal(deadline.toISOString(), '2026-10-24T10:00:00.000Z');
});

test('resolveDeadline falls back to earliest kickoff with valid time when deadline_time is missing', () => {
  const mockData = {
    next_gw: 10,
    schedule: {
      10: [
        { time: '2026-10-24T15:00:00Z', home_team: 'MCI', away_team: 'LIV' },
        { time: '2026-10-24T12:30:00Z', home_team: 'ARS', away_team: 'CHE' }
      ]
    }
  };

  const deadline = resolveDeadline(mockData);
  // 12:30 - 90 mins = 11:00
  assert.equal(deadline.toISOString(), '2026-10-24T11:00:00.000Z');
});

test('resolveDeadline ignores null or invalid match times in fallback and does not falsely trigger 1970 epoch', () => {
  const mockData = {
    next_gw: 10,
    schedule: {
      10: [
        { time: null, home_team: 'EVE', away_team: 'AVL' },
        { time: '', home_team: 'MUN', away_team: 'NEW' },
        { time: 'TBD', home_team: 'BHA', away_team: 'BRE' },
        { time: '2026-10-24T12:30:00Z', home_team: 'ARS', away_team: 'CHE' }
      ]
    }
  };

  const deadline = resolveDeadline(mockData);
  assert.notEqual(deadline, null);
  // Must use 12:30 kickoff minus 90 mins, not 1970
  assert.equal(deadline.toISOString(), '2026-10-24T11:00:00.000Z');
});

test('resolveDeadline returns null (Time unknown) when all matches have null or unconfirmed kickoff times', () => {
  const mockData = {
    next_gw: 10,
    schedule: {
      10: [
        { time: null, home_team: 'EVE', away_team: 'AVL' },
        { time: null, home_team: 'MUN', away_team: 'NEW' }
      ]
    }
  };

  const deadline = resolveDeadline(mockData);
  assert.equal(deadline, null);
});

test('resolveDeadline returns null (Time unknown) when schedule is empty or missing', () => {
  const mockData = {
    next_gw: 10,
    schedule: {}
  };

  const deadline = resolveDeadline(mockData);
  assert.equal(deadline, null);
});

// -------------------------------------------------------------
// Test 2: AI Draft to Planner and renderPlayer fallback
// -------------------------------------------------------------

test('renderPlayer fallback: draft player with p.fixture displays fixture when upcoming_fixtures is absent at offset 0', () => {
  const draftPlayer = {
    id: 10,
    name: 'Saka',
    team: 'ARS',
    fixture: 'AVL (H), CHE (A)',
    fixture_diff: 3
    // upcoming_fixtures is absent
  };

  const mapped = mapPlayerForPitch(draftPlayer, 0);
  assert.equal(mapped.fixture, 'AVL (H), CHE (A)');
  assert.equal(mapped.fixture_diff, 3);
});

test('renderPlayer fallback: future gameweeks without fixtures display Blank without inventing data', () => {
  const draftPlayer = {
    id: 10,
    name: 'Saka',
    team: 'ARS',
    fixture: 'AVL (H), CHE (A)',
    fixture_diff: 3
  };

  const mappedGw1 = mapPlayerForPitch(draftPlayer, 1);
  assert.equal(mappedGw1.fixture, 'Blank');
  assert.equal(mappedGw1.fixture_diff, 5);
});

test('formatUpcomingFixtures correctly formats Single, Double and Blank Gameweeks for draft players', () => {
  const schedule = {
    10: [
      { home_team: 'ARS', away_team: 'AVL', home_diff: 2, away_diff: 4 },
      { home_team: 'CHE', away_team: 'ARS', home_diff: 3, away_diff: 4 }
    ],
    11: [
      { home_team: 'ARS', away_team: 'LIV', home_diff: 4, away_diff: 2 }
    ],
    12: [] // Blank
  };

  const fixtures = formatUpcomingFixtures('ARS', 10, schedule);
  // GW10: DGW
  assert.equal(fixtures[0].opponent, 'AVL (H), CHE (A)');
  assert.equal(fixtures[0].difficulty, 3);

  // GW11: Single GW
  assert.equal(fixtures[1].opponent, 'LIV (H)');
  assert.equal(fixtures[1].difficulty, 4);

  // GW12: Blank
  assert.equal(fixtures[2].opponent, 'Blank');
  assert.equal(fixtures[2].difficulty, 5);
});

// -------------------------------------------------------------
// Test 3: Saved plan deadline synchronization
// -------------------------------------------------------------

test('syncSavedPlanDeadline updates savedPlan deadline when server returns fresh valid deadline for matching GW', () => {
  const savedPlan = {
    next_gw: 10,
    deadline_time: '2026-10-24T10:00:00Z',
    squad: []
  };

  const serverResult = {
    next_gw: 10,
    deadline_time: '2026-10-24T11:00:00Z', // rescheduled official deadline
    schedule: { 10: [] }
  };

  const synced = syncSavedPlanDeadline(savedPlan, serverResult);
  assert.equal(synced.deadline_time, '2026-10-24T11:00:00Z');
  assert.deepEqual(synced.schedule, { 10: [] });
});

test('syncSavedPlanDeadline does NOT update deadline if gameweeks do not match', () => {
  const savedPlan = {
    next_gw: 9,
    deadline_time: '2026-10-17T10:00:00Z',
    squad: []
  };

  const serverResult = {
    next_gw: 10,
    deadline_time: '2026-10-24T10:00:00Z'
  };

  const synced = syncSavedPlanDeadline(savedPlan, serverResult);
  assert.equal(synced.deadline_time, '2026-10-17T10:00:00Z');
});

test('syncSavedPlanDeadline does NOT overwrite with invalid or empty deadline string', () => {
  const savedPlan = {
    next_gw: 10,
    deadline_time: '2026-10-24T10:00:00Z',
    squad: []
  };

  const serverResult = {
    next_gw: 10,
    deadline_time: 'invalid-date'
  };

  const synced = syncSavedPlanDeadline(savedPlan, serverResult);
  assert.equal(synced.deadline_time, '2026-10-24T10:00:00Z');
});
