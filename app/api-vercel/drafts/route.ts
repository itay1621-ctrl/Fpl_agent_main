import { NextResponse } from 'next/server';

function calculatePlayerProjection(p: any, nextGw: number, upcomingFixturesRaw: any[], teams: Record<number, any>) {
  const teamIdFpl = p.team;
  const posCode = p.element_type;
  
  const chance = p.chance_of_playing_next_round;
  const availabilityProb = chance === null || chance === undefined ? 1.0 : parseFloat(chance) / 100.0;
  
  const totalMins = p.minutes || 0;
  const starts = p.starts || 0;
  
  let minsPerApp = 0;
  if (starts > 0) {
    minsPerApp = Math.min(90, totalMins / starts);
  } else if (totalMins > 0) {
    minsPerApp = 20;
  }
  
  const formVal = parseFloat(p.form) || 0;
  if (formVal > 3.0 && minsPerApp < 45 && starts > 0) {
    minsPerApp = Math.min(75, minsPerApp + 15);
  }
  
  let baseExpectedMinutes = minsPerApp > 90 ? 90 : minsPerApp;
  const baseCop = availabilityProb;
  
  const rawXg90 = parseFloat(p.expected_goals_per_90) || 0;
  const rawXa90 = parseFloat(p.expected_assists_per_90) || 0;
  const rawXgc90 = parseFloat(p.expected_goals_conceded_per_90) || 0;
  const rawDefcon90 = parseFloat(p.defensive_contribution_per_90) || 0;
  
  const weight = Math.min(1.0, totalMins / 450.0);
  
  const baselineXg = posCode === 1 || posCode === 2 ? 0.05 : (posCode === 3 ? 0.15 : 0.3);
  const baselineXa = posCode === 1 ? 0.05 : 0.1;
  const baselineXgc = 1.5;
  const baselineDefcon = posCode === 1 || posCode === 2 ? 4.0 : 2.0;
  
  let xg90 = (weight * rawXg90 + (1 - weight) * baselineXg) * 1.0;
  let xa90 = (weight * rawXa90 + (1 - weight) * baselineXa) * 1.0;
  let xgc90 = weight * rawXgc90 + (1 - weight) * baselineXgc;
  let defcon90 = weight * rawDefcon90 + (1 - weight) * baselineDefcon;
  
  const formMultiplier = 1.0 + (Math.min(6.0, Math.max(0, formVal)) / 30.0);
  xg90 *= formMultiplier;
  xa90 *= formMultiplier;
  
  const defconThreshold = posCode === 2 ? 10 : 12;
  const defconStd = Math.max(defcon90 * 0.35, 1.0);
  const z = (defcon90 - defconThreshold) / defconStd;
  const probCrossThreshold = defcon90 > 0 ? 1 / (1 + Math.exp(-1.7 * z)) : 0;
  
  const goalPts = { 1: 6, 2: 6, 3: 5, 4: 4 }[posCode as 1|2|3|4] || 4;
  const assistPts = 3;
  
  const xAtt90 = (xg90 * goalPts) + (xa90 * assistPts);
  const csPts = { 1: 4, 2: 4, 3: 1, 4: 0 }[posCode as 1|2|3|4] || 0;
  const xSave90 = posCode === 1 ? ((parseFloat(p.saves_per_90) || 0) / 3.0) * 1 : 0;
  const xDefcon90 = probCrossThreshold * 2.0;
  
  const gwRange = Math.min(5, 38 - nextGw + 1);
  let total5GwProjection = 0.0;
  
  for (let gwInc = 0; gwInc < gwRange; gwInc++) {
    const currentCop = Math.min(1.0, baseCop + (gwInc * 0.25));
    const dynExpectedMinutes = baseExpectedMinutes * currentCop;
    const targetGw = nextGw + gwInc;
    
    const playerFixs = upcomingFixturesRaw.filter(f => f.event === targetGw && (f.team_h === teamIdFpl || f.team_a === teamIdFpl));
    
    let gwProj = 0.0;
    
    for (const f of playerFixs) {
      const isHome = f.team_h === teamIdFpl;
      const oppId = isHome ? f.team_a : f.team_h;
      const oppTeam = teams[oppId] || {};
      const avgStrength = 1100.0;
      
      let oppDefenceStrength, oppAttackStrength, homeAdv;
      if (isHome) {
        oppDefenceStrength = oppTeam.strength_defence_away || avgStrength;
        oppAttackStrength = oppTeam.strength_attack_away || avgStrength;
        homeAdv = 1.05;
      } else {
        oppDefenceStrength = oppTeam.strength_defence_home || avgStrength;
        oppAttackStrength = oppTeam.strength_attack_home || avgStrength;
        homeAdv = 0.95;
      }
      
      const attMultiplier = oppDefenceStrength > 0 ? (avgStrength / oppDefenceStrength) * homeAdv : 1.0;
      const defMultiplier = oppAttackStrength > 0 ? (avgStrength / oppAttackStrength) * homeAdv : 1.0;
      
      const matchXAtt = xAtt90 * (dynExpectedMinutes / 90.0) * attMultiplier;
      
      const matchXgc = (xgc90 * (dynExpectedMinutes / 90.0)) / defMultiplier;
      const matchCsProb = matchXgc > 0 ? Math.exp(-matchXgc) : 0.5;
      const matchXDef = matchCsProb * csPts;
      
      const matchXSave = xSave90 * (dynExpectedMinutes / 90.0) * defMultiplier;
      const matchXDefcon = xDefcon90 * (dynExpectedMinutes / 90.0);
      
      let appearancePts = 0;
      if (dynExpectedMinutes >= 60) appearancePts = 2 * currentCop;
      else if (dynExpectedMinutes > 0) appearancePts = 1 * currentCop;
      
      gwProj += matchXAtt + matchXDef + matchXSave + matchXDefcon + appearancePts;
    }
    
    total5GwProjection += gwProj;
  }
  
  total5GwProjection = Math.max(0.0, total5GwProjection);
  return parseFloat((total5GwProjection / Math.max(1, gwRange)).toFixed(2));
}

function buildSquad(players: any[], forcedPlayers: any[] = []) {
  const squad = [...forcedPlayers];
  let cost = squad.reduce((c, p) => c + p.now_cost, 0);
  const teamCounts: Record<number, number> = {};
  const posCounts: Record<number, number> = { 1: 0, 2: 0, 3: 0, 4: 0 };
  
  squad.forEach(p => { 
    teamCounts[p.team] = (teamCounts[p.team] || 0) + 1; 
    posCounts[p.element_type]++;
  });

  const minCosts: Record<number, number> = { 1: 40, 2: 40, 3: 45, 4: 45 };

  // 1. Initial Greedy Pick
  for (const p of players) {
    if (squad.length === 15) break;
    if (squad.find(x => x.id === p.id)) continue;
    
    let needed = false;
    if (p.element_type === 1 && posCounts[1] < 2) needed = true;
    if (p.element_type === 2 && posCounts[2] < 5) needed = true;
    if (p.element_type === 3 && posCounts[3] < 5) needed = true;
    if (p.element_type === 4 && posCounts[4] < 3) needed = true;
    
    if (!needed) continue;
    if ((teamCounts[p.team] || 0) >= 3) continue;

    let remSlotsBudget = 0;
    for (let t = 1; t <= 4; t++) {
      let neededCount = (t === 1 ? 2 : t === 2 ? 5 : t === 3 ? 5 : 3) - posCounts[t];
      if (t === p.element_type) neededCount--;
      if (neededCount > 0) remSlotsBudget += neededCount * minCosts[t];
    }
    
    if (cost + p.now_cost + remSlotsBudget <= 1000) {
      squad.push(p);
      cost += p.now_cost;
      teamCounts[p.team] = (teamCounts[p.team] || 0) + 1;
      posCounts[p.element_type]++;
    }
  }

  // 2. Upgrade Loop to utilize remaining budget
  // We want to replace existing squad members with higher XP available players if we have budget.
  let upgraded = true;
  const availablePlayers = players.filter(p => !squad.find(x => x.id === p.id)).sort((a, b) => b.xp - a.xp);
  
  while (upgraded && cost < 1000) {
    upgraded = false;
    
    // Sort squad so we try to upgrade our LOWEST XP players first
    const upgradeCandidates = squad.map((p, index) => ({ p, index }))
                                   .filter(item => !forcedPlayers.find(x => x.id === item.p.id))
                                   .sort((a, b) => a.p.xp - b.p.xp);
                                   
    for (const { p: current, index } of upgradeCandidates) {
      const pos = current.element_type;
      const currentTeam = current.team;
      
      // Find a better player in the same position
      for (const candidate of availablePlayers) {
        if (squad.find(x => x.id === candidate.id)) continue; // Already upgraded into squad
        if (candidate.element_type !== pos) continue;
        if (candidate.xp <= current.xp) continue; // must be an upgrade
        
        const costDiff = candidate.now_cost - current.now_cost;
        if (costDiff <= 0 && candidate.xp > current.xp) {
           // Free upgrade
        } else if (costDiff > 0 && cost + costDiff <= 1000) {
           // Affordable upgrade
        } else {
           continue; // Cannot afford
        }
        
        // Check team limits
        if (candidate.team !== currentTeam) {
           if ((teamCounts[candidate.team] || 0) >= 3) continue;
           teamCounts[currentTeam]--;
           teamCounts[candidate.team] = (teamCounts[candidate.team] || 0) + 1;
        }
        
        cost += costDiff;
        squad[index] = candidate;
        upgraded = true;
        break; // Break the candidate loop, restart squad loop
      }
      if (upgraded) break;
    }
  }

  squad.sort((a, b) => a.element_type - b.element_type || b.now_cost - a.now_cost);
  return { squad, cost };
}

export async function GET() {
  try {
    const res = await fetch('https://fantasy.premierleague.com/api/bootstrap-static/', { next: { revalidate: 3600 } });
    if (!res.ok) throw new Error("Failed to fetch FPL data");
    const data = await res.json();

    const fixRes = await fetch('https://fantasy.premierleague.com/api/fixtures/', { next: { revalidate: 3600 } });
    if (!fixRes.ok) throw new Error("Failed to fetch fixtures");
    const fixtures = await fixRes.json();
    
    const events = data.events;
    const nextGwObj = events.find((e: any) => e.is_next) || events.find((e: any) => !e.finished);
    const nextGw = nextGwObj ? nextGwObj.id : 1;
    
    const elements = data.elements.filter((p: any) => p.status !== 'u' && p.status !== 'i' && p.status !== 's');
    const teams: Record<number, any> = {};
    data.teams.forEach((t: any) => { teams[t.id] = t; });

    const enriched = elements.map((p: any) => {
      const xp = calculatePlayerProjection(p, nextGw, fixtures, teams);
      
      return {
        id: p.id,
        name: p.web_name,
        first_name: p.first_name,
        second_name: p.second_name,
        team: p.team,
        team_name: teams[p.team]?.short_name || "UNK",
        team_code: p.team_code,
        element_type: p.element_type,
        now_cost: p.now_cost,
        form: parseFloat(p.form) || 0,
        ep_next: parseFloat(p.ep_next) || 0,
        xp: xp,
        selected_by_percent: parseFloat(p.selected_by_percent) || 0,
        total_points: p.total_points
      };
    });

    const premiums = [...enriched].filter(p => p.now_cost >= 100).sort((a, b) => b.xp - a.xp).slice(0, 2);
    const othersForPremium = [...enriched].sort((a, b) => (b.xp / b.now_cost) - (a.xp / a.now_cost));
    const premiumDraft = buildSquad(othersForPremium, premiums);

    const balancedPlayers = [...enriched].filter(p => p.now_cost <= 95).sort((a, b) => b.xp - a.xp);
    const balancedDraft = buildSquad(balancedPlayers, []);

    const differentialPlayers = [...enriched].sort((a, b) => {
      const diffBonusA = a.selected_by_percent < 10 ? 2 : (a.selected_by_percent < 15 ? 1 : 0);
      const diffBonusB = b.selected_by_percent < 10 ? 2 : (b.selected_by_percent < 15 ? 1 : 0);
      return (b.xp + diffBonusB) - (a.xp + diffBonusA);
    });
    const diffDraft = buildSquad(differentialPlayers, []);

    return NextResponse.json({
      drafts: [
        { id: 1, name: "Premium Heavies (כוכבים יקרים)", description: "הרכב מבוסס על שחקני פרימיום חזקים יחד עם שחקנים זולים משלימים.", data: premiumDraft },
        { id: 2, name: "Balanced Spread (הרכב מאוזן)", description: "ללא שחקנים יקרים מדי, מאפשר עומק חזק מאוד בכל העמדות במגרש.", data: balancedDraft },
        { id: 3, name: "Differentials (פנינים נסתרות)", description: "שחקנים בכושר שיא שאחוזי הבחירה שלהם נמוכים, כדי לעקוף מתחרים.", data: diffDraft }
      ]
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
