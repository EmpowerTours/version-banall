// farcaster/pages/frame.js
import Head from 'next/head';

export default function Frame() {
  return (
    <div>
      <Head>
        {/* Farcaster Frame Metadata */}
        <meta property="fc:frame" content="vNext" />
        <meta property="fc:frame:image" content="https://web-production-5f438.up.railway.app/images/splash.png" />
        <meta property="fc:frame:image:aspect_ratio" content="1.91:1" />
        <meta property="fc:frame:button:1" content="Join BAN@LL" />
        <meta property="fc:frame:button:1:action" content="link" />
        <meta property="fc:frame:button:1:target" content="https://web-production-5f438.up.railway.app/public/banall.html" />
        <meta property="og:title" content="BAN@LL by EmpowerTours" />
        <meta property="og:description" content="Join the Web3 rock climbing adventure game!" />
        <meta property="og:image" content="https://web-production-5f438.up.railway.app/images/splash.png" />
      </Head>
      <div>
        <h1>BAN@LL Frame</h1>
        <p>This is a Farcaster Frame for BAN@LL. Open in Warpcast to interact.</p>
      </div>
    </div>
  );
}
