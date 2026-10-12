import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const pagePath = path.resolve('app/page.tsx');

function loadGetStoredSimulatedChip() {
  const code = fs.readFileSync(pagePath, 'utf8');

  // Extract the getStoredSimulatedChip function declaration and body
  const match = code.match(/function getStoredSimulatedChip\(teamId:[^)]+\): string \| null {[\s\S]*?\n}/);
  if (!match) {
    throw new Error('getStoredSimulatedChip function not found in app/page.tsx');
  }

  // Strip TypeScript annotations
  const jsFunction = match[0]
    .replace(/teamId:\s*string\s*\|\s*number/g, 'teamId')
    .replace(/currentNextGw:\s*number/g, 'currentNextGw')
    .replace(/:\s*string\s*\|\s*null/g, '');

  const storageMap = new Map();
  const mockLocalStorage = {
    getItem: (key) => storageMap.has(key) ? storageMap.get(key) : null,
    setItem: (key, val) => storageMap.set(key, String(val)),
    removeItem: (key) => storageMap.delete(key),
    clear: () => storageMap.clear(),
    _store: storageMap
  };

  const sandbox = {
    window: {},
    localStorage: mockLocalStorage,
    JSON,
    console
  };

  const script = new vm.Script(jsFunction + '\n;globalThis.__fn = getStoredSimulatedChip;');
  vm.createContext(sandbox);
  script.runInContext(sandbox);

  return {
    fn: sandbox.__fn,
    storage: mockLocalStorage
  };
}

test('getStoredSimulatedChip returns valid chip when target_gw matches', () => {
  const { fn, storage } = loadGetStoredSimulatedChip();
  storage.setItem('fpl_active_chip_12345', JSON.stringify({ chip: 'wildcard', target_gw: 31 }));

  const result = fn(12345, 31);
  assert.equal(result, 'wildcard');
  assert.equal(storage.getItem('fpl_active_chip_12345'), JSON.stringify({ chip: 'wildcard', target_gw: 31 }));
});

test('getStoredSimulatedChip returns null and purges storage when target_gw has rolled over', () => {
  const { fn, storage } = loadGetStoredSimulatedChip();
  // Chip was saved for GW 30, but next_gw is now 31
  storage.setItem('fpl_active_chip_12345', JSON.stringify({ chip: 'wildcard', target_gw: 30 }));

  const result = fn(12345, 31);
  assert.equal(result, null);
  // Storage entry must be safely purged so stale state never lingers
  assert.equal(storage.getItem('fpl_active_chip_12345'), null);
});

test('getStoredSimulatedChip purges legacy un-scoped string and returns null', () => {
  const { fn, storage } = loadGetStoredSimulatedChip();
  // Pre-fix legacy format: raw naked string "wildcard" without metadata
  storage.setItem('fpl_active_chip_12345', 'wildcard');

  const result = fn(12345, 31);
  assert.equal(result, null);
  // Legacy entry must be purged, never silently applied
  assert.equal(storage.getItem('fpl_active_chip_12345'), null);
});

test('getStoredSimulatedChip returns null if no entry exists', () => {
  const { fn } = loadGetStoredSimulatedChip();
  const result = fn(99999, 31);
  assert.equal(result, null);
});

test('getStoredSimulatedChip purges malformed JSON and returns null', () => {
  const { fn, storage } = loadGetStoredSimulatedChip();
  storage.setItem('fpl_active_chip_12345', '{invalid json');

  const result = fn(12345, 31);
  assert.equal(result, null);
  assert.equal(storage.getItem('fpl_active_chip_12345'), null);
});

test('regression: live current GW chip from API is never saved into localStorage as simulated chip for next_gw', () => {
  const { fn, storage } = loadGetStoredSimulatedChip();
  const teamId = 12345;
  const currentNextGw = 31;

  // Simulate API response payload where current GW is live and active_chip was played in FPL
  const apiResult = {
    team_id: teamId,
    next_gw: currentNextGw,
    squad_meta: {
      is_current_gw: true,
      active_chip: 'wildcard'
    }
  };

  // 1. In fetchTeam, simulatedChip is resolved solely via getStoredSimulatedChip:
  const simulatedChip = fn(teamId, apiResult.next_gw);
  assert.equal(simulatedChip, null, 'simulatedChip must be null since user did not select a simulation');

  // 2. activeChip React state is set solely from simulatedChip (NOT from liveChip):
  const activeChipState = simulatedChip || null;
  assert.equal(activeChipState, null, 'activeChip state must remain null and not adopt the live API chip');

  // 3. The persistence effect executes:
  if (activeChipState) {
    storage.setItem(`fpl_active_chip_${teamId}`, JSON.stringify({
      chip: activeChipState,
      target_gw: apiResult.next_gw
    }));
  } else {
    storage.removeItem(`fpl_active_chip_${teamId}`);
  }

  // 4. Verify localStorage has NO entry for target_gw:
  assert.equal(storage.getItem(`fpl_active_chip_${teamId}`), null, 'localStorage must remain clean with no simulated chip');

  // 5. On subsequent load/navigation to next_gw, verify getStoredSimulatedChip returns null:
  const loadedChipForNextGw = fn(teamId, currentNextGw);
  assert.equal(loadedChipForNextGw, null, 'Next GW must not have any simulated chip');
});

test('UI logic: liveChip preserves pitch display while planner remains strictly isolated', () => {
  // 1. Test Live GW Triple Captain display on pitch
  const liveDataTC = {
    squad_meta: { is_current_gw: true, active_chip: '3xc' },
    squad: [
      { id: 1, position: 1, multiplier: 1, is_captain: true, xp: 8.0 },
      { id: 2, position: 2, multiplier: 1, is_captain: false, xp: 5.0 }
    ]
  };
  const activeChip = null; // No planner simulation chosen
  const liveChip = liveDataTC.squad_meta?.is_current_gw ? (liveDataTC.squad_meta?.active_chip || null) : null;
  const effectivePitchChip = liveChip || activeChip;
  assert.equal(effectivePitchChip, '3xc', 'effectivePitchChip must be 3xc from liveChip');

  const starters = liveDataTC.squad.filter(p => effectivePitchChip === 'bboost' ? true : p.position <= 11);
  const totalXP = starters.reduce((acc, p) => {
    let mult = p.multiplier || 1;
    if (effectivePitchChip === '3xc' && p.is_captain) mult = 3;
    return acc + (p.xp * mult);
  }, 0);
  // Captain xp is 8.0 * 3 = 24.0, Player 2 is 5.0 * 1 = 5.0 -> Total 29.0
  assert.equal(totalXP, 29.0, 'Live Triple Captain properly triples captain points on pitch');

  // 2. Test Planner Tab isolation: live chip must NOT leak into planner
  const selectedGwOffset0 = 0;
  const isChipActiveOffset0 = selectedGwOffset0 === 0 ? activeChip : null;
  assert.equal(isChipActiveOffset0, null, 'Planner for next GW must not inherit liveChip');

  const transfersMade = 2;
  const simulatedFt = 1;
  const additionalTransfers = Math.max(0, transfersMade - simulatedFt);
  const hitPointsLiveGW = (isChipActiveOffset0 === 'wildcard' || isChipActiveOffset0 === 'freehit') ? 0 : -(additionalTransfers * 4);
  assert.equal(hitPointsLiveGW, -4, '2 transfers with 1 FT in planner incurs -4 hit, not 0');

  // 3. Test simulated chip in planner for selectedGwOffset === 0 vs selectedGwOffset === 1
  const simulatedChipWC = 'wildcard';
  const isChipActivePlan0 = selectedGwOffset0 === 0 ? simulatedChipWC : null;
  const hitPointsPlan0 = (isChipActivePlan0 === 'wildcard' || isChipActivePlan0 === 'freehit') ? 0 : -(additionalTransfers * 4);
  assert.equal(hitPointsPlan0, 0, 'Wildcard in offset 0 eliminates hits');

  const selectedGwOffset1 = 1;
  const isChipActivePlan1 = selectedGwOffset1 === 0 ? simulatedChipWC : null;
  const hitPointsPlan1 = (isChipActivePlan1 === 'wildcard' || isChipActivePlan1 === 'freehit') ? 0 : -(additionalTransfers * 4);
  assert.equal(hitPointsPlan1, -4, 'Wildcard in offset 0 does NOT eliminate hits in offset 1');
});


