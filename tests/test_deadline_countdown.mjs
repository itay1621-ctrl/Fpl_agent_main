import test from 'node:test';
import assert from 'node:assert/strict';

/**
 * Mirror of countdown determination logic from app/page.tsx
 */
function resolveDeadline(data) {
  if (!data) return null;

  let deadline = null;

  if (data.deadline_time) {
    const parsed = new Date(data.deadline_time);
    if (!isNaN(parsed.getTime())) {
      deadline = parsed;
    }
  }

  if (!deadline) {
    if (!data.schedule || !data.schedule[data?.next_gw] || data.schedule[data?.next_gw].length === 0) return null;

    const matches = [...data.schedule[data?.next_gw]].sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
    if (matches.length === 0) return null;

    const firstMatchTime = new Date(matches[0]?.time);
    if (isNaN(firstMatchTime.getTime())) return null;

    deadline = new Date(firstMatchTime.getTime() - 90 * 60000);
  }

  return deadline;
}

/**
 * Mirror of upcoming fixtures generation logic for transfers in app/page.tsx
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

test('resolveDeadline falls back to kickoff minus 90 mins when deadline_time is missing', () => {
  const mockData = {
    next_gw: 10,
    schedule: {
      10: [
        { time: '2026-10-24T12:30:00Z', home_team: 'ARS', away_team: 'CHE' },
        { time: '2026-10-24T15:00:00Z', home_team: 'MCI', away_team: 'LIV' }
      ]
    }
  };

  const deadline = resolveDeadline(mockData);
  // 12:30 - 90 mins = 11:00
  assert.equal(deadline.toISOString(), '2026-10-24T11:00:00.000Z');
});

test('resolveDeadline falls back when deadline_time is invalid date string', () => {
  const mockData = {
    next_gw: 10,
    deadline_time: 'not-a-valid-date',
    schedule: {
      10: [
        { time: '2026-10-24T12:30:00Z', home_team: 'ARS', away_team: 'CHE' }
      ]
    }
  };

  const deadline = resolveDeadline(mockData);
  assert.equal(deadline.toISOString(), '2026-10-24T11:00:00.000Z');
});

test('resolveDeadline returns null when neither deadline_time nor valid schedule is available', () => {
  const mockData = {
    next_gw: 10,
    schedule: {}
  };

  const deadline = resolveDeadline(mockData);
  assert.equal(deadline, null);
});

test('formatUpcomingFixtures correctly formats Single Gameweek', () => {
  const schedule = {
    10: [
      { home_team: 'ARS', away_team: 'EVE', home_diff: 2, away_diff: 4 }
    ]
  };
  const fixtures = formatUpcomingFixtures('ARS', 10, schedule);
  assert.equal(fixtures[0].opponent, 'EVE (H)');
  assert.equal(fixtures[0].difficulty, 2);
});

test('formatUpcomingFixtures correctly formats Double Gameweek', () => {
  const schedule = {
    10: [
      { home_team: 'ARS', away_team: 'EVE', home_diff: 2, away_diff: 4 },
      { home_team: 'CHE', away_team: 'ARS', home_diff: 3, away_diff: 4 }
    ]
  };
  const fixtures = formatUpcomingFixtures('ARS', 10, schedule);
  assert.equal(fixtures[0].opponent, 'EVE (H), CHE (A)');
  // average of 2 and 4 = 3
  assert.equal(fixtures[0].difficulty, 3);
});

test('formatUpcomingFixtures correctly formats Blank Gameweek', () => {
  const schedule = {
    10: [
      { home_team: 'MCI', away_team: 'LIV', home_diff: 3, away_diff: 3 }
    ]
  };
  const fixtures = formatUpcomingFixtures('ARS', 10, schedule);
  assert.equal(fixtures[0].opponent, 'Blank');
  assert.equal(fixtures[0].difficulty, 5);
});
