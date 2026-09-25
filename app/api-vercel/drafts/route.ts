import { NextResponse } from 'next/server';

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

  squad.sort((a, b) => a.element_type - b.element_type || b.now_cost - a.now_cost);
  return { squad, cost };
}

export async function GET() {
  try {
    const res = await fetch('https://fantasy.premierleague.com/api/bootstrap-static/', { next: { revalidate: 3600 } });
    if (!res.ok) throw new Error("Failed to fetch FPL data");
    const data = await res.json();
    
    const elements = data.elements.filter((p: any) => p.status !== 'u' && p.status !== 'i' && p.status !== 's');
    const teamsArray = data.teams;
    const teams: Record<number, any> = {};
    teamsArray.forEach((t: any) => { teams[t.id] = t; });

    const enriched = elements.map((p: any) => {
      const ep_next = parseFloat(p.ep_next) || 0;
      const form = parseFloat(p.form) || 0;
      const xp = (ep_next * 0.7) + (form * 0.3);
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
        form: form,
        ep_next: ep_next,
        xp: xp,
        selected_by_percent: parseFloat(p.selected_by_percent) || 0,
        total_points: p.total_points
      };
    });

    const premiums = [...enriched].filter(p => p.now_cost >= 100).sort((a, b) => b.xp - a.xp).slice(0, 2);
    const othersForPremium = [...enriched].sort((a, b) => (b.xp / b.now_cost) - (a.xp / a.now_cost));
    const premiumDraft = buildSquad(othersForPremium, premiums);

    const balancedPlayers = [...enriched].filter(p => p.now_cost <= 95).sort((a, b) => (b.xp * 0.6 + b.form * 0.4) - (a.xp * 0.6 + a.form * 0.4));
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
