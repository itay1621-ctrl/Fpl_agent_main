import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function GET() {
  const isMaintenance = process.env.NEXT_PUBLIC_MAINTENANCE_MODE === 'true';
  const bannerMessage = process.env.NEXT_PUBLIC_MAINTENANCE_BANNER || null;

  return NextResponse.json({
    maintenance: isMaintenance,
    banner: bannerMessage,
    title_he: "המערכת בעבודות שדרוג ותחזוקה",
    title_en: "System Under Maintenance & Upgrades",
    message_he: "אנו מבצעים כעת שדרוג מקיף למנוע ה-AI, מודלי ה-xP והשרתים כדי להביא לכם ביצועים והמלצות מדויקות יותר. האתר יחזור לפעילות מלאה בהקדם.",
    message_en: "We are currently rolling out a major upgrade to our AI engine, xP projection models, and infrastructure. We will be back online shortly.",
    updated_at: new Date().toISOString()
  });
}
