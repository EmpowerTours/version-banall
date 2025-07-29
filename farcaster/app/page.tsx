"use client";

import SafeAreaContainer from '../components/SafeAreaContainer';
import { useEffect, useState, useRef } from 'react';
import { WagmiConfig, createConfig, useAccount, useConnect, useSwitchChain } from 'wagmi';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, createPublicClient } from 'viem';
import { farcasterMiniApp } from '@farcaster/miniapp-wagmi-connector';
import Web3 from 'web3';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';
import { Pool } from 'pg';
import debounce from 'lodash/debounce'; // For lag prevention
import { Multisynq } from '@multisynq/sdk';

// Postgres pool
const pgPool = new Pool({ connectionString: 'postgresql://postgres:ZeyMkvenyYVjKQeOmMzTlCUuHLZOUWiy@gondola.proxy.rlwy.net:5432/railway' });

// Multisynq init
const multisynq = new Multisynq({ apiKey: '2UPB8vM6BUPmKqgPaBN1Trg89GfX6qzddlZZ270GFJ' });
const room = multisynq.room('banall-chat');

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

interface Player {
  username: string;
  toursBalance: number;
  isBanned: boolean;
  isSpectator: boolean;
  farcasterFid: number;
  position: [number, number, number]; // For 3D
}

function BanallContent() {
  const { address, isConnected } = useAccount();
  const { connect, connectors } = useConnect();
  const { switchChain } = useSwitchChain();

  console.log('MONAD_RPC_URL:', process.env.NEXT_PUBLIC_MONAD_RPC_URL);
  const web3 = new Web3(process.env.NEXT_PUBLIC_MONAD_RPC_URL || 'https://rpc.ankr.com/monad_testnet');
  const contractAddress = '0xA1c0D8B252A7e58b5598A8915C9AC0e794a2eC5A';
  const toursTokenAddress = process.env.NEXT_PUBLIC_TOURS_TOKEN_ADDRESS || '0x2Da15A8B55BE310A7AB8EB0010506AB30CD6CBcf';
  const contractABI = [
    {
      "inputs": [],
      "name": "addSpectator",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "banBastral",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "string",
          "name": "_username",
          "type": "string"
        },
        {
          "internalType": "uint256",
          "name": "_farcasterFid",
          "type": "uint256"
        }
      ],
      "name": "createProfile",
      "outputs": [],
      "stateMutability": "payable",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "uint256",
          "name": "amount",
          "type": "uint256"
        }
      ],
      "name": "depositTours",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "_toursToken",
          "type": "address"
        }
      ],
      "stateMutability": "nonpayable",
      "type": "constructor"
    },
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": true,
          "internalType": "address",
          "name": "winner",
          "type": "address"
        },
        {
          "indexed": false,
          "internalType": "uint256",
          "name": "monPot",
          "type": "uint256"
        },
        {
          "indexed": false,
          "internalType": "uint256",
          "name": "toursReward",
          "type": "uint256"
        }
      ],
      "name": "GameEnded",
      "type": "event"
    },
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": false,
          "internalType": "uint256",
          "name": "startTime",
          "type": "uint256"
        }
      ],
      "name": "GameStarted",
      "type": "event"
    },
    {
      "inputs": [],
      "name": "joinGame",
      "outputs": [],
      "stateMutability": "payable",
      "type": "function"
    },
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": true,
          "internalType": "address",
          "name": "banned",
          "type": "address"
        },
        {
          "indexed": true,
          "internalType": "address",
          "name": "by",
          "type": "address"
        },
        {
          "indexed": false,
          "internalType": "uint256",
          "name": "farcasterFid",
          "type": "uint256"
        }
      ],
      "name": "PlayerBanned",
      "type": "event"
    },
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": true,
          "internalType": "address",
          "name": "user",
          "type": "address"
        },
        {
          "indexed": false,
          "internalType": "string",
          "name": "username",
          "type": "string"
        },
        {
          "indexed": false,
          "internalType": "uint256",
          "name": "farcasterFid",
          "type": "uint256"
        }
      ],
      "name": "ProfileCreated",
      "type": "event"
    },
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": true,
          "internalType": "address",
          "name": "user",
          "type": "address"
        },
        {
          "indexed": false,
          "internalType": "uint256",
          "name": "amount",
          "type": "uint256"
        }
      ],
      "name": "RewardDistributed",
      "type": "event"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "_bastral",
          "type": "address"
        }
      ],
      "name": "startGame",
      "outputs": [],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "stateMutability": "payable",
      "type": "receive"
    },
    {
      "inputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "name": "activePlayers",
      "outputs": [
        {
          "internalType": "address",
          "name": "",
          "type": "address"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "bastralPlayer",
      "outputs": [
        {
          "internalType": "address",
          "name": "",
          "type": "address"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "ENTRY_FEE",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "name": "farcasterFidToAddress",
      "outputs": [
        {
          "internalType": "address",
          "name": "",
          "type": "address"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "GAME_DURATION",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "gameStartTime",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "getGameState",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "timeLeft",
          "type": "uint256"
        },
        {
          "internalType": "address",
          "name": "bastral",
          "type": "address"
        },
        {
          "internalType": "address[]",
          "name": "playersList",
          "type": "address[]"
        },
        {
          "internalType": "string[]",
          "name": "usernames",
          "type": "string[]"
        },
        {
          "internalType": "bool[]",
          "name": "banned",
          "type": "bool[]"
        },
        {
          "internalType": "uint256[]",
          "name": "toursBalances",
          "type": "uint256[]"
        },
        {
          "internalType": "bool[]",
          "name": "spectators",
          "type": "bool[]"
        },
        {
          "internalType": "uint256[]",
          "name": "farcasterFids",
          "type": "uint256[]"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "",
          "type": "address"
        }
      ],
      "name": "hasProfile",
      "outputs": [
        {
          "internalType": "bool",
          "name": "",
          "type": "bool"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "isGameActive",
      "outputs": [
        {
          "internalType": "bool",
          "name": "",
          "type": "bool"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "lastWinner",
      "outputs": [
        {
          "internalType": "address",
          "name": "",
          "type": "address"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "LOBBY_WAIT",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "MAX_PLAYERS",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "owner",
      "outputs": [
        {
          "internalType": "address",
          "name": "",
          "type": "address"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "",
          "type": "address"
        }
      ],
      "name": "players",
      "outputs": [
        {
          "internalType": "address",
          "name": "wallet",
          "type": "address"
        },
        {
          "internalType": "string",
          "name": "username",
          "type": "string"
        },
        {
          "internalType": "bool",
          "name": "isBanned",
          "type": "bool"
        },
        {
          "internalType": "bool",
          "name": "isSpectator",
          "type": "bool"
        },
        {
          "internalType": "uint256",
          "name": "farcasterFid",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "PROFILE_REWARD",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "totalPot",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "TOURS_REWARD",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "toursToken",
      "outputs": [
        {
          "internalType": "contract IERC20",
          "name": "",
          "type": "address"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    }
  ];
  const toursABI = [
    {
      "inputs": [],
      "stateMutability": "nonpayable",
      "type": "constructor"
    },
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": true,
          "internalType": "address",
          "name": "owner",
          "type": "address"
        },
        {
          "indexed": true,
          "internalType": "address",
          "name": "spender",
          "type": "address"
        },
        {
          "indexed": false,
          "internalType": "uint256",
          "name": "value",
          "type": "uint256"
        }
      ],
      "name": "Approval",
      "type": "event"
    },
    {
      "anonymous": false,
      "inputs": [
        {
          "indexed": true,
          "internalType": "address",
          "name": "from",
          "type": "address"
        },
        {
          "indexed": true,
          "internalType": "address",
          "name": "to",
          "type": "address"
        },
        {
          "indexed": false,
          "internalType": "uint256",
          "name": "value",
          "type": "uint256"
        }
      ],
      "name": "Transfer",
      "type": "event"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "owner",
          "type": "address"
        },
        {
          "internalType": "address",
          "name": "spender",
          "type": "address"
        }
      ],
      "name": "allowance",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "spender",
          "type": "address"
        },
        {
          "internalType": "uint256",
          "name": "amount",
          "type": "uint256"
        }
      ],
      "name": "approve",
      "outputs": [
        {
          "internalType": "bool",
          "name": "",
          "type": "bool"
        }
      ],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "account",
          "type": "address"
        }
      ],
      "name": "balanceOf",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "decimals",
      "outputs": [
        {
          "internalType": "uint8",
          "name": "",
          "type": "uint8"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "spender",
          "type": "address"
        },
        {
          "internalType": "uint256",
          "name": "subtractedValue",
          "type": "uint256"
        }
      ],
      "name": "decreaseAllowance",
      "outputs": [
        {
          "internalType": "bool",
          "name": "",
          "type": "bool"
        }
      ],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "spender",
          "type": "address"
        },
        {
          "internalType": "uint256",
          "name": "addedValue",
          "type": "uint256"
        }
      ],
      "name": "increaseAllowance",
      "outputs": [
        {
          "internalType": "bool",
          "name": "",
          "type": "bool"
        }
      ],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "name",
      "outputs": [
        {
          "internalType": "string",
          "name": "",
          "type": "string"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "symbol",
      "outputs": [
        {
          "internalType": "string",
          "name": "",
          "type": "string"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [],
      "name": "totalSupply",
      "outputs": [
        {
          "internalType": "uint256",
          "name": "",
          "type": "uint256"
        }
      ],
      "stateMutability": "view",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "to",
          "type": "address"
        },
        {
          "internalType": "uint256",
          "name": "amount",
          "type": "uint256"
        }
      ],
      "name": "transfer",
      "outputs": [
        {
          "internalType": "bool",
          "name": "",
          "type": "bool"
        }
      ],
      "stateMutability": "nonpayable",
      "type": "function"
    },
    {
      "inputs": [
        {
          "internalType": "address",
          "name": "from",
          "type": "address"
        },
        {
          "internalType": "address",
          "name": "to",
          "type": "address"
        },
        {
          "internalType": "uint256",
          "name": "amount",
          "type": "uint256"
        }
      ],
      "name": "transferFrom",
      "outputs": [
        {
          "internalType": "bool",
          "name": "",
          "type": "bool"
        }
      ],
      "stateMutability": "nonpayable",
      "type": "function"
    }
  ];
  const multicallAddress = '0xcA11bde05977b3631167028862bE2a173976CA11';
  const multicallABI = [{"inputs":[{"components":[{"name":"target","type":"address"},{"name":"callData","type":"bytes"}],"name":"calls","type":"tuple[]"}],"name":"aggregate","outputs":[{"name":"blockNumber","type":"uint256"},{"name":"returnData","type":"bytes[]"}],"stateMutability":"view","type":"function"}];
  const contract = new web3.eth.Contract(contractABI, contractAddress);
  const toursContract = new web3.eth.Contract(toursABI, toursTokenAddress);
  const multicall = new web3.eth.Contract(multicallABI, multicallAddress);
  const [account, setAccount] = useState<string | null>(null);
  const [players, setPlayers] = useState<Record<string, Player>>({});
  const [messages, setMessages] = useState<string[]>([]);
  const [timeLeft, setTimeLeft] = useState(0);
  const [bastral, setBastral] = useState<string | null>(null);
  const [gameActive, setGameActive] = useState(false);
  const [botPrompted, setBotPrompted] = useState(false);
  const [username, setUsername] = useState('');
  const [farcasterFid, setFarcasterFid] = useState('0');
  const [chatInput, setChatInput] = useState('');
  const threeRef = useRef<HTMLDivElement>(null);
  const bots: NodeJS.Timeout[] = []; // For bot intervals

  useEffect(() => {
    if (isConnected && address) {
      setAccount(address);
      switchChain({ chainId: monadTestnet.id });
    }
  }, [isConnected, address, switchChain]);

  useEffect(() => {
    if (!toursTokenAddress || toursTokenAddress === '0xYOUR_TOURS_TOKEN_ADDRESS') {
      console.error('TOURS_TOKEN_ADDRESS is not set. Please configure it in Railway environment variables.');
      return;
    }
    const interval = setInterval(checkGameState, 1000);
    init3D(); // Init Three.js
    room.join();
    room.on('message', (data) => {
      if (data.type === 'state') setPlayers(data.players);
    });
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (botPrompted && !gameActive) addBots(5); // Auto-add 5 bots if prompted
  }, [botPrompted, gameActive]);

  function init3D() {
    if (!threeRef.current) return;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 10000);
    const renderer = new THREE.WebGLRenderer();
    renderer.setSize(window.innerWidth / 2, window.innerHeight / 2); // Half size for embed
    threeRef.current.appendChild(renderer.domElement);
    new OrbitControls(camera, renderer.domElement);
    camera.position.set(0, 50, 100);

    // Terrain
    const geometry = new THREE.PlaneGeometry(2000, 2000, 128, 128);
    const material = new THREE.MeshStandardMaterial({ color: 0xffffff });
    const terrain = new THREE.Mesh(geometry, material);
    for (let i = 0; i < geometry.attributes.position.count; i++) {
      const x = geometry.attributes.position.array[i * 3];
      const z = geometry.attributes.position.array[i * 3 + 2];
      geometry.attributes.position.array[i * 3 + 1] = Math.sin(x / 50) * 50 + Math.cos(z / 50) * 50;
    }
    geometry.computeVertexNormals();
    scene.add(terrain);

    // Marines (LOD stub)
    Object.entries(players).forEach(([wallet, player]) => {
      const geo = new THREE.BoxGeometry(5, 10, 5);
      const mat = new THREE.MeshStandardMaterial({ color: player.isBanned ? 0xff0000 : 0x00ff00 });
      const marine = new THREE.Mesh(geo, mat);
      marine.position.set(...player.position);
      scene.add(marine);
    });

    const animate = () => {
      requestAnimationFrame(animate);
      renderer.render(scene, camera);
    };
    animate();
  }

  async function connectWallet() {
    try {
      if (!isConnected && connectors.length > 0) {
        connect({ connector: connectors[0] });
      }
    } catch (error) {
      alert('Wallet connection failed: ' + (error as Error).message);
    }
  }

  async function createProfile() {
    if (!username) {
      alert('Please enter a username');
      return;
    }
    try {
      await contract.methods.createProfile(username, farcasterFid).send({
        from: account!,
        value: '10000',
        gas: '200000',
        maxFeePerGas: '2000000000',
        maxPriorityFeePerGas: '1000000000'
      });
      const position = [Math.random() * 2000 - 1000, 0, Math.random() * 2000 - 1000];
      setPlayers((prev) => ({
        ...prev,
        [account!]: { username, toursBalance: 0, isBanned: false, isSpectator: false, farcasterFid: Number(farcasterFid) || 0, position },
      }));
      await pgPool.query('INSERT INTO users (wallet, username) VALUES ($1, $2)', [account, username]);
      setMessages((prev) => [...prev, `${username} joined`]);
      setUsername('');
      setFarcasterFid('0');
      room.send({ type: 'state', players });
    } catch (error) {
      alert('Profile creation failed: ' + (error as Error).message);
    }
  }

  async function joinGame() {
    try {
      await contract.methods.joinGame().send({
        from: account!,
        value: web3.utils.toWei('1', 'ether'),
        gas: '200000',
        maxFeePerGas: '2000000000',
        maxPriorityFeePerGas: '1000000000'
      });
      setPlayers((prev) => ({
        ...prev,
        [account!]: { ...prev[account!], isSpectator: false },
      }));
      await pgPool.query('UPDATE users SET is_spectator = FALSE WHERE wallet = $1', [account]);
      setMessages((prev) => [...prev, `${players[account!]?.username} joined the game`]);
      room.send({ type: 'state', players });
    } catch (error) {
      alert('Join game failed: ' + (error as Error).message);
    }
  }

  async function spectateGame() {
    try {
      await contract.methods.addSpectator().send({
        from: account!,
        gas: '100000',
        maxFeePerGas: '2000000000',
        maxPriorityFeePerGas: '1000000000'
      });
      setPlayers((prev) => ({
        ...prev,
        [account!]: { ...prev[account!], isSpectator: true },
      }));
      await pgPool.query('UPDATE users SET is_spectator = TRUE WHERE wallet = $1', [account]);
      setMessages((prev) => [...prev, `${players[account!]?.username} joined as spectator`]);
      room.send({ type: 'state', players });
    } catch (error) {
      alert('Spectate failed: ' + (error as Error).message);
    }
  }

  const debouncedBan = debounce(async () => {
    if (chatInput === '/ban @bastral' && bastral) {
      try {
        await contract.methods.banBastral().send({
          from: account!,
          gas: '200000',
          maxFeePerGas: '2000000000',
          maxPriorityFeePerGas: '1000000000'
        });
        setPlayers((prev) => ({
          ...prev,
          [bastral]: {
            ...prev[bastral],
            isBanned: true,
          },
          [account!]: {
            ...prev[account!],
            toursBalance: (prev[account!]?.toursBalance || 0) + 1e18,
          },
        }));
        await pgPool.query('UPDATE users SET is_banned = TRUE WHERE wallet = $1', [bastral]);
        await pgPool.query('UPDATE users SET tours_balance = tours_balance + $1 WHERE wallet = $2', [1e18, account]);
        setMessages((prev) => [...prev, `${players[account!]?.username} banned ${players[bastral]?.username}! +1 $TOURS`]);
        const newBastral = Object.keys(players).find((w) => !players[w].isBanned && !players[w].isSpectator && w !== bastral) || null;
        setBastral(newBastral);
        setChatInput('');
        room.send({ type: 'state', players });
      } catch (error) {
        alert('Ban failed: ' + (error as Error).message);
      }
    }
  }, 1000); // Debounce for lag prevention

  function addBots(numBots: number) {
    for (let i = 0; i < numBots; i++) {
      const botAddress = `0xBot${i + 1}${Date.now()}`;
      const botUsername = `Bot${i + 1}`;
      const position = [Math.random() * 2000 - 1000, 0, Math.random() * 2000 - 1000];
      setPlayers((prev) => ({
        ...prev,
        [botAddress]: { username: botUsername, toursBalance: 0, isBanned: false, isSpectator: false, farcasterFid: 0, position },
      }));
      setMessages((prev) => [...prev, `${botUsername} (bot) joined`]);
      // Bot auto-ban interval
      bots.push(setInterval(() => {
        if (bastral && Math.random() > 0.5) {
          setPlayers((prev) => ({
            ...prev,
            [bastral]: { ...prev[bastral], isBanned: true },
            [botAddress]: { ...prev[botAddress], toursBalance: (prev[botAddress]?.toursBalance || 0) + 1e18 },
          }));
          setMessages((prev) => [...prev, `${botUsername} banned ${players[bastral]?.username}! +1 $TOURS`]);
          room.send({ type: 'state', players });
        }
      }, random(1000, 5000)));
    }
  }

  async function checkGameState() {
    try {
      const calls = [
        { target: contractAddress, callData: contract.methods.getGameState().encodeABI() },
        ...Object.keys(players).map((wallet) => ({
          target: toursTokenAddress,
          callData: toursContract.methods.balanceOf(wallet).encodeABI(),
        })),
      ];
      const results = await multicall.methods.aggregate(calls).call();
      const [timeLeft, bastral, playersList, usernames, banned, toursBalances, spectators, farcasterFids] = web3.eth.abi.decodeParameters(['uint256', 'address', 'address[]', 'string[]', 'bool[]', 'uint256[]', 'bool[]', 'uint256[]'], results.returnData[0]);
      const updatedPlayers: Record<string, Player> = {};
      for (let i = 0; i < playersList.length; i++) {
        updatedPlayers[playersList[i]] = { username: usernames[i], toursBalance: Number(toursBalances[i]), isBanned: banned[i], isSpectator: spectators[i], farcasterFid: farcasterFids[i], position: [0, 0, 0] /* Fetch from DB */ };
      }
      setPlayers(updatedPlayers);
      setBastral(bastral);
      setTimeLeft(timeLeft);
      setGameActive(timeLeft > 0);
      if (timeLeft > 0 && !gameActive) {
        setMessages((prev) => [...prev, 'Game started!']);
        setBotPrompted(false);
        setGameActive(true);
      } else if (timeLeft === 0 && gameActive) {
        const winner = playersList.find((p: string, i: number) => !banned[i] && !spectators[i]);
        if (winner) {
          setMessages((prev) => [...prev, `${updatedPlayers[winner].username} won!`]);
          setPlayers((prev) => {
            const newPlayers = { ...prev };
            Object.keys(newPlayers).forEach((w) => { newPlayers[w].isBanned = false; });
            return newPlayers;
          });
          setGameActive(false);
          setBastral(null);
          setBotPrompted(false);
        }
      }
      const activePlayers = Object.keys(updatedPlayers).filter((w) => !updatedPlayers[w].isSpectator && !updatedPlayers[w].isBanned);
      if (activePlayers.length === 1 && !botPrompted && !gameActive) {
        setBotPrompted(true);
        setMessages((prev) => [...prev, 'Alone in lobby! Add bots?']);
      }
    } catch (error) {
      console.error('Error checking game state:', error);
    }
  }

  return (
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
        {Object.keys(players).map((wallet) => (
          <div key={wallet} className={`chat-message ${players[wallet].isBanned ? 'banned' : players[wallet].isSpectator ? 'spectator' : ''}`}>
            {players[wallet].username}: {players[wallet].toursBalance / 1e18} $TOURS{players[wallet].farcasterFid ? ` (FID: ${players[wallet].farcasterFid})` : ''} ({wallet.substring(0, 6)}...)
          </div>
        ))}
      </div>
      <div ref={threeRef} style={{ height: '300px', marginBottom: '20px' }} /> {/* 3D embed */}
      <input
        type="text"
        placeholder="Set Username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        className="w-full p-2 mb-2 border rounded"
        disabled={!!players[account ?? '']}
      />
      <input
        type="text"
        placeholder="Farcaster FID (optional)"
        value={farcasterFid}
        onChange={(e) => setFarcasterFid(e.target.value)}
        className="w-full p-2 mb-2 border rounded"
        disabled={!!players[account ?? '']}
      />
      <input
        type="text"
        placeholder="Type /ban @bastral"
        value={chatInput}
        onChange={(e) => setChatInput(e.target.value)}
        onKeyPress={(e) => e.key === 'Enter' && debouncedBan()}
        className="w-full p-2 mb-2 border rounded"
        disabled={!gameActive || players[account ?? '']?.isBanned || players[account ?? '']?.isSpectator}
      />
      <button onClick={connectWallet} className="w-full bg-blue-500 text-white p-2 rounded mb-2" disabled={isConnected}>
        {isConnected ? `Connected: ${address?.substring(0, 6)}...` : 'Connect Wallet'}
      </button>
      <button onClick={createProfile} className="w-full bg-green-500 text-white p-2 rounded mb-2" disabled={!!players[account ?? '']}>
        Create Profile
      </button>
      <button onClick={joinGame} className="w-full bg-purple-500 text-white p-2 rounded mb-2" disabled={!players[account ?? ''] || players[account ?? '']?.isSpectator}>
        Join Game (1 MON)
      </button>
      <button onClick={spectateGame} className="w-full bg-gray-500 text-white p-2 rounded mb-2" disabled={!players[account ?? ''] || players[account ?? '']?.isSpectator}>
        Spectate
      </button>
      <button onClick={() => addBots(Number(prompt('How many bots (1-10)?')))} className="w-full bg-yellow-500 text-white p-2 rounded mb-2" disabled={!botPrompted || gameActive}>
        Add Bots
      </button>
    </div>
  );
}

function random(min: number, max: number) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}
