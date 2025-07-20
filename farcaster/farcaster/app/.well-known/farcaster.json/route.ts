import { NextResponse } from 'next';
import { env } from 'process';

const appUrl = env.NEXT_PUBLIC_URL || 'https://banall-farcaster.up.railway.app';
const farcasterConfig = {
  accountAssociation: {
    header: '',
    payload: '',
    signature: ''
  },
  frame: {
    version: '1',
    name: 'BAN@LL - EmpowerTours',
    iconUrl: `${appUrl}/images/icon.png`,
    homeUrl: `${appUrl}`,
    imageUrl: `${appUrl}/images/feed.png`,
    screenshotUrls: [`${appUrl}/images/screenshot1.png`, `${appUrl}/images/screenshot2.png`],
    tags: ['monad', 'farcaster', 'miniapp', 'game', 'empowertours'],
    primaryCategory: 'gaming',
    buttonTitle: 'Launch BAN@LL',
    splashImageUrl: `${appUrl}/images/splash.png`,
    splashBackgroundColor: '#ffffff'
  }
};

export async function GET() {
  return NextResponse.json(farcasterConfig);
}
