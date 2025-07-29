import { NextResponse } from 'next/server';
import { Pool } from 'pg';

const pool = new Pool({ connectionString: 'postgresql://postgres:ZeyMkvenyYVjKQeOmMzTlCUuHLZOUWiy@gondola.proxy.rlwy.net:5432/railway' });

export async function POST(req: Request) {
  const { action, wallet, username, isBanned, toursBalance } = await req.json();
  try {
    if (action === 'createProfile') {
      await pool.query('INSERT INTO users (wallet, username) VALUES ($1, $2) ON CONFLICT (wallet) DO UPDATE SET username = $2', [wallet, username]);
      return NextResponse.json({ success: true });
    } else if (action === 'updateBan') {
      await pool.query('UPDATE users SET is_banned = $1 WHERE wallet = $2', [isBanned, wallet]);
      return NextResponse.json({ success: true });
    } else if (action === 'updateBalance') {
      await pool.query('UPDATE users SET tours_balance = $1 WHERE wallet = $2', [toursBalance, wallet]);
      return NextResponse.json({ success: true });
    } else if (action === 'updateSpectator') {
      await pool.query('UPDATE users SET is_spectator = $1 WHERE wallet = $2', [true, wallet]); // Example
      return NextResponse.json({ success: true });
    }
    return NextResponse.json({ error: 'Invalid action' });
  } catch (error) {
    return NextResponse.json({ error: (error as Error).message });
  }
}
