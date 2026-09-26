import { NextResponse } from 'next/server';

export async function GET() {
  try {
    const res = await fetch('https://fantasy.premierleague.com/api/bootstrap-static/', {
      next: { revalidate: 3600 } // cache for 1 hour
    });
    
    if (!res.ok) {
      return NextResponse.json({ error: 'Failed to fetch FPL data' }, { status: 500 });
    }
    
    const data = await res.json();
    
    // Create a compact dictionary of player stats
    const stats: Record<number, any> = {};
    data.elements.forEach((p: any) => {
      stats[p.id] = {
        clean_sheets: p.clean_sheets,
        goals_conceded: p.goals_conceded,
        expected_goals_conceded: parseFloat(p.expected_goals_conceded || '0'),
        expected_goals: parseFloat(p.expected_goals || '0'),
        expected_assists: parseFloat(p.expected_assists || '0'),
        form: p.form,
        defensive_contribution: p.defensive_contribution_per_90 || 0,
      };
    });
    
    return NextResponse.json({ players: stats });
  } catch (error) {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
