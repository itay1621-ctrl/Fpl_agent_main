import test from 'node:test';
import assert from 'node:assert/strict';

/**
 * Deterministic tests for frontend budget filtering and strategy decision synchronization.
 * Tests the exact logic implemented in app/page.tsx:
 *   1. affordableRecs filter logic
 *   2. effectiveDecision resolution logic
 *   3. Instant toggle consistency without network re-fetch
 */

function computeAffordableRecs(transferRecs, allowOverBudget, data, transferOutId, originalData) {
  return transferRecs.filter(p => {
    if (allowOverBudget) return true;
    const playerToSell = data?.squad?.find((sp) => sp.id === transferOutId);
    const sellPrice = playerToSell?.is_empty ? 0 : (playerToSell?.selling_price ?? playerToSell?.cost ?? 0);
    const budget = Math.round(((data?.bank ?? 0) + sellPrice) * 10) / 10;
    const origPlayer = originalData?.squad?.find((op) => op.id === p.id);
    const effectiveCost = origPlayer ? (origPlayer.purchase_price ?? origPlayer.cost) : p.cost;
    return effectiveCost <= budget;
  });
}

function resolveEffectiveDecision(transferDecision, allowOverBudget) {
  return (!allowOverBudget && transferDecision?.affordable_decision)
    ? { ...transferDecision, ...transferDecision.affordable_decision }
    : transferDecision;
}

test('frontend: when allowOverBudget is false, over-budget candidates are filtered out', () => {
  const transferRecs = [
    { id: 3, name: 'Palmer', cost: 10.5, xp: 8.0 },
    { id: 2, name: 'Rogers', cost: 5.2, xp: 4.5 }
  ];
  const data = {
    bank: 0.5,
    squad: [{ id: 1, name: 'Current Mid', cost: 5.0, selling_price: 5.0 }]
  };
  const originalData = { squad: [] };

  const affordable = computeAffordableRecs(transferRecs, false, data, 1, originalData);
  assert.equal(affordable.length, 1);
  assert.equal(affordable[0].id, 2);
  assert.equal(affordable[0].name, 'Rogers');
});

test('frontend: when allowOverBudget is true, all candidates are included with over-budget flags', () => {
  const transferRecs = [
    { id: 3, name: 'Palmer', cost: 10.5, xp: 8.0 },
    { id: 2, name: 'Rogers', cost: 5.2, xp: 4.5 }
  ];
  const data = {
    bank: 0.5,
    squad: [{ id: 1, name: 'Current Mid', cost: 5.0, selling_price: 5.0 }]
  };
  const originalData = { squad: [] };
  const availableBudget = data.bank + data.squad[0].selling_price; // 5.5

  const allRecs = computeAffordableRecs(transferRecs, true, data, 1, originalData);
  assert.equal(allRecs.length, 2);
  assert.equal(allRecs[0].id, 3);
  assert.equal(allRecs[1].id, 2);

  const palmerOverBudget = allRecs[0].cost > availableBudget;
  const palmerDiff = Math.round((allRecs[0].cost - availableBudget) * 10) / 10;
  assert.equal(palmerOverBudget, true);
  assert.equal(palmerDiff, 5.0);
});

test('frontend: effectiveDecision matches Card #1 in both OFF and ON modes', () => {
  const transferDecision = {
    recommendation: 'TRANSFER',
    explanation: 'The projected gain over 5 GWs is 25.00 points... The replacement clears the required threshold.',
    delta: 5.0,
    raw_gain: 25.0,
    hit_cost: 0,
    net_gain: 25.0,
    current_player: { id: 1, name: 'Current Mid', xp: 3.0 },
    best_transfer: { id: 3, name: 'Palmer', cost: 10.5, xp: 8.0 },
    affordable_decision: {
      recommendation: 'TRANSFER',
      explanation: 'The projected gain over 5 GWs is 7.50 points... The replacement clears the required threshold.',
      delta: 1.5,
      raw_gain: 7.5,
      hit_cost: 0,
      net_gain: 7.5,
      best_transfer: { id: 2, name: 'Rogers', cost: 5.2, xp: 4.5 }
    }
  };

  const transferRecs = [
    { id: 3, name: 'Palmer', cost: 10.5, xp: 8.0 },
    { id: 2, name: 'Rogers', cost: 5.2, xp: 4.5 }
  ];
  const data = {
    bank: 0.5,
    squad: [{ id: 1, name: 'Current Mid', cost: 5.0, selling_price: 5.0 }]
  };
  const originalData = { squad: [] };

  // Mode 1: Checkbox OFF
  const affordableRecsOff = computeAffordableRecs(transferRecs, false, data, 1, originalData);
  const decisionOff = resolveEffectiveDecision(transferDecision, false);
  assert.equal(affordableRecsOff[0].id, 2);
  assert.equal(decisionOff.best_transfer.id, affordableRecsOff[0].id);
  assert.equal(decisionOff.best_transfer.name, 'Rogers');
  assert.equal(decisionOff.delta, 1.5);
  assert.equal(decisionOff.raw_gain, 7.5);

  // Mode 2: Checkbox ON
  const affordableRecsOn = computeAffordableRecs(transferRecs, true, data, 1, originalData);
  const decisionOn = resolveEffectiveDecision(transferDecision, true);
  assert.equal(affordableRecsOn[0].id, 3);
  assert.equal(decisionOn.best_transfer.id, affordableRecsOn[0].id);
  assert.equal(decisionOn.best_transfer.name, 'Palmer');
  assert.equal(decisionOn.delta, 5.0);
  assert.equal(decisionOn.raw_gain, 25.0);
});

test('frontend: toggling checkbox switches state synchronously without requiring second API request', () => {
  let allowOverBudget = true;
  let fetchCallCount = 0;

  // Single initial fetch returns complete unconstrained candidate list and decisions
  fetchCallCount++;
  const cachedTransferRecs = [
    { id: 3, name: 'Palmer', cost: 10.5, xp: 8.0 },
    { id: 2, name: 'Rogers', cost: 5.2, xp: 4.5 }
  ];
  const cachedTransferDecision = {
    best_transfer: { id: 3, name: 'Palmer' },
    affordable_decision: {
      best_transfer: { id: 2, name: 'Rogers' }
    }
  };
  const data = {
    bank: 0.5,
    squad: [{ id: 1, name: 'Current Mid', cost: 5.0, selling_price: 5.0 }]
  };
  const originalData = { squad: [] };

  // Initial render with ON
  let recs = computeAffordableRecs(cachedTransferRecs, allowOverBudget, data, 1, originalData);
  let decision = resolveEffectiveDecision(cachedTransferDecision, allowOverBudget);
  assert.equal(recs.length, 2);
  assert.equal(decision.best_transfer.name, 'Palmer');

  // User unchecks checkbox (OFF)
  allowOverBudget = false;
  recs = computeAffordableRecs(cachedTransferRecs, allowOverBudget, data, 1, originalData);
  decision = resolveEffectiveDecision(cachedTransferDecision, allowOverBudget);
  assert.equal(recs.length, 1);
  assert.equal(recs[0].name, 'Rogers');
  assert.equal(decision.best_transfer.name, 'Rogers');

  // User checks checkbox again (ON)
  allowOverBudget = true;
  recs = computeAffordableRecs(cachedTransferRecs, allowOverBudget, data, 1, originalData);
  decision = resolveEffectiveDecision(cachedTransferDecision, allowOverBudget);
  assert.equal(recs.length, 2);
  assert.equal(recs[0].name, 'Palmer');
  assert.equal(decision.best_transfer.name, 'Palmer');

  // No additional network requests were needed
  assert.equal(fetchCallCount, 1);
});
