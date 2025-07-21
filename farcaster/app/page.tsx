import { useMiniAppContext } from '@farcaster/miniapp-client';
import SafeAreaContainer from '../components/SafeAreaContainer';
import { useEffect, useState } from 'react';
import { WagmiConfig, createConfig, useAccount, useConnect, useSwitchChain } from 'wagmi';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, createPublicClient } from 'viem';
import { farcasterMiniApp } from '@farcaster/miniapp-wagmi-connector';

// Custom Monad Testnet chain
const monadTestnet = {
  id: Number(process.env.NEXT_PUBLIC_MONAD_CHAIN_ID) || 10143,
  name: 'Monad Testnet',
  network: 'monad-testnet',
  nativeCurrency: { decimals: 18, name: 'Monad', symbol: 'MON' },
  rpcUrls: {
    default: { http: [process.env.NEXT_PUBLIC_MONAD_RPC_URL || 'https://rpc.ankr.com/monad_testnet'] },
    public: { http: [process.env.NEXT_PUBLIC_MONAD_RPC_URL || 'https://rpc.ankr.com/monad_testnet'] },
  },
  blockExplorers: {
    default: { name: 'Monad Explorer', url: 'https://testnet.monadexplorer.com' },
  },
};

// Wagmi config
const queryClient = new QueryClient();
const config = createConfig({
  chains: [monadTestnet],
  connectors: [farcasterMiniApp()],
  client({ chain }) {
    return createPublicClient({ chain, transport: http() });
  },
});

export default function Banall() {
  return (
    <WagmiConfig config={config}>
      <QueryClientProvider client={queryClient}>
        <BanallContent />
      </QueryClientProvider>
    </WagmiConfig>
  );
}

function BanallContent() {
  const { context, actions } = useMiniAppContext();
  const { address, isConnected } = useAccount();
  const { connect, connectors } = useConnect();
  const { switchChain } = useSwitchChain();
  const [account, setAccount] = useState(null);
  const [players, setPlayers] = useState({});
  const [messages, setMessages] = useState([]);
  const [timeLeft, setTimeLeft] = useState(0);
  const [bastral, setBastral] = useState(null);
  const [gameActive, setGameActive] = useState(false);
  const [botPrompted, setBotPrompted] = useState(false);
  const [username, setUsername] = useState(context?.user?.username || '');
  const [farcasterFid, setFarcasterFid] = useState(context?.user?.fid || '0');
  const [chatInput, setChatInput] = useState('');

  // Use Wagmi address as account
  useEffect(() => {
    if (isConnected && address) {
      setAccount(address);
      switchChain({ chainId: monadTestnet.id });  // Ensure on correct chain
    }
  }, [isConnected, address, switchChain]);

  // Existing useEffect for game logic (unchanged, but use web3 as before)
  useEffect(() => {
    // ... (Multisynq setup, checkGameState interval, etc. - unchanged)
  }, []);

  async function connectWallet() {
    try {
      if (!isConnected && connectors.length > 0) {
        connect({ connector: connectors[0] });
      }
    } catch (error) {
      alert('Wallet connection failed: ' + error.message);
    }
  }

  // ... (Rest of functions: createProfile, joinGame, spectateGame, banBastral, addBots, checkGameState - unchanged, using 'account')

  return (
    <SafeAreaContainer insets={context?.client.safeAreaInsets}>
      <div className="max-w-md mx-auto bg-white rounded-lg shadow-lg p-4">
        <img src="/images/empowertours_logo.svg" alt="EmpowerTours Logo" className="animate-pulse mx-auto max-w-[200px]" />
        <h1 className="text-2xl font-bold text-center">BAN@LL</h1>
        <p className="text-center mb-4">
          Join the Web3 Rock Climbing Adventure! <a href="https://t.me/empowertourschat" className="text-blue-500">EmpowerTours Chat</a>
        </p>
        <div className="text-center mb-4" style={{ fontSize: '1.5em', fontWeight: 'bold', color: timeLeft <= 5 && timeLeft > 0 ? 'red' : 'black' }}>
          {timeLeft > 0 ? `Game Time: ${Math.floor(timeLeft / 60)}:${(timeLeft % 60).toString().padStart(2, '0')}` : 'Waiting for game...'}
        </div>
        <div className="text-center mb-4">{bastral ? `Bastral: ${players[bastral]?.username || 'None'}` : 'No Bastral assigned'}</div>
        <div className="border p-2 mb-4 h-[60vh] overflow-y-auto">
          {messages.slice(-50).map((msg, i) => (
            <div key={i} className="chat-message">{msg}</div>
          ))}
          {Object.keys(players).map(wallet => (
            <div key={wallet} className={`chat-message ${players[wallet].isBanned ? 'banned' : players[wallet].isSpectator ? 'spectator' : ''}`}>
              {players[wallet].username}: {players[wallet].toursBalance / 1e18} $TOURS{players[wallet].farcasterFid ? ` (FID: ${players[wallet].farcasterFid})` : ''} ({wallet.substring(0, 6)}...)
            </div>
          ))}
        </div>
        <input
          type="text"
          placeholder="Set Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full p-2 mb-2 border rounded"
          disabled={!!players[account]}
        />
        <input
          type="text"
          placeholder="Farcaster FID (optional)"
          value={farcasterFid}
          onChange={(e) => setFarcasterFid(e.target.value)}
          className="w-full p-2 mb-2 border rounded"
          disabled={!!players[account]}
        />
        <input
          type="text"
          placeholder="Type /ban @bastral"
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && banBastral()}
          className="w-full p-2 mb-2 border rounded"
          disabled={!gameActive || players[account]?.isBanned || players[account]?.isSpectator}
        />
        <button onClick={connectWallet} className="w-full bg-blue-500 text-white p-2 rounded mb-2" disabled={isConnected}>
          {isConnected ? `Connected: ${account?.substring(0, 6)}...` : 'Connect Wallet'}
        </button>
        <button onClick={createProfile} className="w-full bg-green-500 text-white p-2 rounded mb-2" disabled={!!players[account]}>
          Create Profile
        </button>
        <button onClick={joinGame} className="w-full bg-purple-500 text-white p-2 rounded mb-2" disabled={!players[account] || players[account]?.isSpectator}>
          Join Game (1 MON)
        </button>
        <button onClick={spectateGame} className="w-full bg-gray-500 text-white p-2 rounded mb-2" disabled={!players[account] || players[account]?.isSpectator}>
          Spectate
        </button>
        <button onClick={addBots} className="w-full bg-yellow-500 text-white p-2 rounded mb-2" disabled={!botPrompted || gameActive}>
          Add Bots
        </button>
      </div>
    </SafeAreaContainer>
  );
}
