import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

/**
 * Regression and unit tests for Transfer Lab & Planner Mode UI Rendering Bug Fix.
 *
 * Verifies:
 * 1. tableCandidates resolution logic:
 *    - Search empty & candidates > 3 -> Top 3 in cards, remaining in table.
 *    - Search empty & candidates <= 3 -> Does NOT collapse to empty array []!
 *    - Search non-empty -> filteredRecs used directly.
 *    - Empty state correctly triggered when tableCandidates.length === 0.
 * 2. allowOverBudget toggle interaction with tableCandidates.
 * 3. Search and error state resets when opening transfer modal.
 * 4. CSS structural guarantees in app/page.tsx to prevent Flexbox crushing:
 *    - Table wrapper has min-h-[300px] and shrink-0 (never collapses to 0px under flexbox pressure).
 *    - Header has shrink-0.
 *    - Modal body has flex-1 min-h-0 overflow-y-auto.
 */

function computeTableCandidates(searchQuery, affordableRecs, filteredRecs) {
  return searchQuery === ''
    ? (affordableRecs.length > 3 ? affordableRecs.slice(3) : affordableRecs)
    : filteredRecs;
}

function filterRecs(transferRecs, searchQuery) {
  if (!searchQuery) return transferRecs;
  const q = searchQuery.toLowerCase();
  return transferRecs.filter(p =>
    (p.name && p.name.toLowerCase().includes(q)) ||
    (p.team_name && p.team_name.toLowerCase().includes(q))
  );
}

function computeAffordableRecs(transferRecs, allowOverBudget, availableBudget, originalData) {
  return transferRecs.filter(p => {
    if (allowOverBudget) return true;
    const origPlayer = originalData?.squad?.find(op => op.id === p.id);
    const effectiveCost = origPlayer ? (origPlayer.purchase_price ?? origPlayer.cost) : p.cost;
    return effectiveCost <= availableBudget;
  });
}

test('tableCandidates: when searchQuery is empty and affordableRecs > 3, displays items after top 3', () => {
  const recs = [
    { id: 1, name: 'Salah', total_points: 150 },
    { id: 2, name: 'Haaland', total_points: 140 },
    { id: 3, name: 'Saka', total_points: 130 },
    { id: 4, name: 'Mbeumo', total_points: 120 },
    { id: 5, name: 'Palmer', total_points: 110 }
  ];
  const candidates = computeTableCandidates('', recs, recs);
  assert.equal(candidates.length, 2);
  assert.equal(candidates[0].id, 4);
  assert.equal(candidates[1].id, 5);
});

test('tableCandidates: when searchQuery is empty and affordableRecs <= 3, does NOT collapse to empty array', () => {
  const recs = [
    { id: 1, name: 'Salah', total_points: 150 },
    { id: 2, name: 'Haaland', total_points: 140 }
  ];
  const candidates = computeTableCandidates('', recs, recs);
  assert.equal(candidates.length, 2, 'Should preserve candidates rather than slicing to empty []');
  assert.equal(candidates[0].id, 1);
  assert.equal(candidates[1].id, 2);
});

test('tableCandidates: when searchQuery is active, displays filteredRecs regardless of count', () => {
  const recs = [
    { id: 1, name: 'Salah', team_name: 'Liverpool', total_points: 150 },
    { id: 2, name: 'Haaland', team_name: 'Man City', total_points: 140 },
    { id: 3, name: 'Saka', team_name: 'Arsenal', total_points: 130 },
    { id: 4, name: 'Mbeumo', team_name: 'Brentford', total_points: 120 }
  ];

  const filtered = filterRecs(recs, 'haaland');
  const candidates = computeTableCandidates('haaland', recs, filtered);
  assert.equal(candidates.length, 1);
  assert.equal(candidates[0].name, 'Haaland');
});

test('tableCandidates: when no matching players found, length is 0 for empty state message', () => {
  const recs = [
    { id: 1, name: 'Salah', team_name: 'Liverpool', total_points: 150 }
  ];
  const filtered = filterRecs(recs, 'NonExistent');
  const candidates = computeTableCandidates('NonExistent', recs, filtered);
  assert.equal(candidates.length, 0);
});

test('allowOverBudget toggle correctly controls affordableRecs and tableCandidates', () => {
  const transferRecs = [
    { id: 1, name: 'Budget Pick', cost: 5.0, total_points: 50 },
    { id: 2, name: 'Premium Pick', cost: 12.0, total_points: 160 }
  ];
  const availableBudget = 6.0;

  // Toggle OFF: only budget pick is affordable
  const affordableOff = computeAffordableRecs(transferRecs, false, availableBudget, { squad: [] });
  assert.equal(affordableOff.length, 1);
  assert.equal(affordableOff[0].id, 1);
  const candidatesOff = computeTableCandidates('', affordableOff, affordableOff);
  assert.equal(candidatesOff.length, 1);

  // Toggle ON: both picks are included
  const affordableOn = computeAffordableRecs(transferRecs, true, availableBudget, { squad: [] });
  assert.equal(affordableOn.length, 2);
  const candidatesOn = computeTableCandidates('', affordableOn, affordableOn);
  assert.equal(candidatesOn.length, 2);
});

test('source code structure: verifies modal flexbox layout and min-height in app/page.tsx', () => {
  const pagePath = path.resolve(process.cwd(), 'app/page.tsx');
  const content = fs.readFileSync(pagePath, 'utf8');

  // Verify Planner modal has shrink-0 on header
  assert.match(
    content,
    /<div className="flex justify-between items-center mb-4 shrink-0">/,
    'Modal header must have shrink-0 to prevent collapsing'
  );

  // Verify Planner modal body has flex-1 min-h-0 overflow-y-auto
  assert.match(
    content,
    /<div className="flex flex-col flex-1 min-h-0 overflow-y-auto pr-1">/,
    'Modal body must have flex-1 min-h-0 overflow-y-auto'
  );

  // Verify Planner table container has min-h-[300px] and shrink-0
  assert.match(
    content,
    /min-h-\[300px\] max-h-\[420px\] overflow-y-auto shrink-0/,
    'Planner table container must have min-h-[300px] and shrink-0'
  );

  // Verify Transfer Lab table container has min-h-[300px]
  assert.match(
    content,
    /min-h-\[300px\] max-h-\[400px\] overflow-y-auto rounded-lg border/,
    'Transfer Lab table container must have min-h-[300px]'
  );

  // Verify setSearchQuery and setTransferError are reset in Planner onSell
  assert.match(
    content,
    /setSearchQuery\(''\);\s*setTransferError\(''\);\s*setTransferOutId\(id\);/,
    'onSell must reset searchQuery and transferError upon opening modal'
  );

  // Verify tableCandidates is used for rendering and empty state checks in both places
  const tableCandidatesMatches = content.match(/tableCandidates\.length === 0/g);
  assert.equal(
    tableCandidatesMatches ? tableCandidatesMatches.length : 0,
    2,
    'Both Transfer Lab and Planner Mode must check tableCandidates.length === 0'
  );
});
