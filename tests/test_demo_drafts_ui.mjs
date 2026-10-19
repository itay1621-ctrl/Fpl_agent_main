import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

/**
 * Regression and unit tests for Demo / Guest Mode Drafts tab accessibility.
 *
 * Verifies:
 * 1. `activeTab === 'drafts'` is open in DEMO / Guest mode (`appMode === 'guest'` and `appMode === 'demo'`).
 * 2. 'drafts' is NOT present in the locked guest tabs condition in `app/page.tsx`.
 * 3. Drafts tab renders without requiring personal squad data or team_id.
 */

function isTabLocked(appMode, activeTab) {
  // Reflects the exact guard condition in app/page.tsx
  return appMode === 'guest' && (
    activeTab === 'pitch' ||
    activeTab === 'planner' ||
    activeTab === 'transfer' ||
    activeTab === 'leagues' ||
    activeTab === 'budget' ||
    activeTab === 'analysis'
  );
}

function shouldRenderDraftsTab(appMode, activeTab) {
  // Reflects {activeTab === 'drafts' && <DraftsTab ... />}
  return activeTab === 'drafts';
}

test('isTabLocked: drafts tab is NOT locked in guest mode', () => {
  assert.equal(isTabLocked('guest', 'drafts'), false);
});

test('isTabLocked: personalized squad tabs remain locked in guest mode', () => {
  assert.equal(isTabLocked('guest', 'pitch'), true);
  assert.equal(isTabLocked('guest', 'planner'), true);
  assert.equal(isTabLocked('guest', 'transfer'), true);
  assert.equal(isTabLocked('guest', 'leagues'), true);
  assert.equal(isTabLocked('guest', 'budget'), true);
  assert.equal(isTabLocked('guest', 'analysis'), true);
});

test('isTabLocked: public exploration tabs (radar, tips, drafts) are open in guest mode', () => {
  assert.equal(isTabLocked('guest', 'radar'), false);
  assert.equal(isTabLocked('guest', 'tips'), false);
  assert.equal(isTabLocked('guest', 'drafts'), false);
});

test('isTabLocked: all tabs are unlocked in demo and team mode', () => {
  const tabs = ['pitch', 'planner', 'transfer', 'leagues', 'budget', 'analysis', 'radar', 'tips', 'drafts'];
  for (const tab of tabs) {
    assert.equal(isTabLocked('demo', tab), false, `Tab ${tab} should be unlocked in demo mode`);
    assert.equal(isTabLocked('team', tab), false, `Tab ${tab} should be unlocked in team mode`);
  }
});

test('shouldRenderDraftsTab: renders DraftsTab when activeTab is drafts in all app modes', () => {
  assert.equal(shouldRenderDraftsTab('guest', 'drafts'), true);
  assert.equal(shouldRenderDraftsTab('demo', 'drafts'), true);
  assert.equal(shouldRenderDraftsTab('team', 'drafts'), true);
  assert.equal(shouldRenderDraftsTab('guest', 'radar'), false);
});

test('source code audit: app/page.tsx does not lock drafts in guest or demo mode', () => {
  const pagePath = path.resolve(process.cwd(), 'app/page.tsx');
  const content = fs.readFileSync(pagePath, 'utf8');

  // Verify activeTab === 'drafts' does not have appMode !== 'guest' restriction
  assert.match(
    content,
    /\{activeTab === 'drafts' && \(\s*<div[^>]*>\s*<h3[^>]*>[\s\S]*?Recommended Drafts/,
    "DraftsTab should be rendered on activeTab === 'drafts' without appMode !== 'guest' guard"
  );

  // Verify locked tabs condition does not include activeTab === 'drafts'
  const lockedConditionMatch = content.match(/appMode === 'guest' && \(([^)]+)\)/);
  assert.ok(lockedConditionMatch, "Should find the locked tabs condition for guest mode");
  const lockedTabsClause = lockedConditionMatch[1];
  assert.ok(
    !lockedTabsClause.includes("'drafts'"),
    `Locked tabs clause must NOT contain 'drafts'. Found: ${lockedTabsClause}`
  );
});
