import { NextResponse } from 'next/server';
import { Pool } from 'pg';

const pool = new Pool({ connectionString: 'postgresql://postgres:ZeyMkvenyYVjKQeOmMzTlCUuHLZOUWiy@gondola.proxy.rlwy.net:5432/railway' });

export async function POST(req: Request) {
  const { action, wallet } = await req.json();
  if (action === 'join') {
    await pool.query('INSERT INTO users (wallet) VALUES ($1) ON CONFLICT DO NOTHING', [wallet]);
    // Start bots simulation (in-memory; use setInterval for banning)
    setInterval(() => {
      // Bot ban logic...
    }, random(1000, 5000));
    return NextResponse.json({ status: 'joined' });
  }
  return NextResponse.json({ error: 'Invalid action' });
}
