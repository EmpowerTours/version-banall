import logging
import os
import asyncio
import time
import math
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from fastapi import FastAPI, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, FileResponse, RedirectResponse
from contextlib import asynccontextmanager
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import aiohttp
from web3 import AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider
from dotenv import load_dotenv
import html
import uvicorn
import socket
import subprocess
from datetime import datetime
import asyncpg
from tenacity import retry, wait_exponential, stop_after_attempt

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 3D Game Classes
@dataclass
class PlayerPosition:
    x: float
    y: float
    z: float
    rotation_y: float

@dataclass
class Player:
    id: str
    username: str
    wallet_address: str
    position: PlayerPosition
    is_banned: bool = False
    is_bastral: bool = False
    is_spectator: bool = False
    last_updated: float = 0.0
    animation_state: str = "idle"

@dataclass
class GameRoom:
    id: str
    players: Dict[str, Player]
    is_active: bool = False
    game_start_time: float = 0.0
    bastral_id: Optional[str] = None
    chat_messages: List[Dict] = None
    
    def __post_init__(self):
        if self.chat_messages is None:
            self.chat_messages = []

class GameManager:
    def __init__(self):
        self.rooms: Dict[str, GameRoom] = {}
        self.connections: Dict[str, WebSocket] = {}
        self.player_to_room: Dict[str, str] = {}
        
    async def add_player(self, player_id: str, websocket: WebSocket, room_id: str = "main"):
        self.connections[player_id] = websocket
        self.player_to_room[player_id] = room_id
        
        if room_id not in self.rooms:
            self.rooms[room_id] = GameRoom(id=room_id, players={})
            
        spawn_position = PlayerPosition(
            x=float(len(self.rooms[room_id].players) * 2 - 10),
            y=0.0,
            z=-2.0,
            rotation_y=0.0
        )
        
        player = Player(
            id=player_id,
            username=f"Player_{player_id}",
            wallet_address="",
            position=spawn_position,
            last_updated=time.time()
        )
        
        self.rooms[room_id].players[player_id] = player
        
        await self.broadcast_to_room(room_id, {
            "type": "player_joined",
            "player": asdict(player),
            "room_state": self.get_room_state(room_id)
        })
        
    async def remove_player(self, player_id: str):
        if player_id in self.connections:
            del self.connections[player_id]
            
        if player_id in self.player_to_room:
            room_id = self.player_to_room[player_id]
            del self.player_to_room[player_id]
            
            if room_id in self.rooms and player_id in self.rooms[room_id].players:
                del self.rooms[room_id].players[player_id]
                
                await self.broadcast_to_room(room_id, {
                    "type": "player_left",
                    "player_id": player_id,
                    "room_state": self.get_room_state(room_id)
                })
                
    async def handle_chat_message(self, player_id: str, message: str):
        if player_id not in self.player_to_room:
            return
            
        room_id = self.player_to_room[player_id]
        room = self.rooms.get(room_id)
        if not room:
            return
            
        player = room.players.get(player_id)
        if not player:
            return
            
        if message.strip().lower() == "/ban @bastral":
            await self.handle_ban_attempt(player_id, room_id)
        else:
            chat_msg = {
                "type": "chat_message",
                "player_id": player_id,
                "username": player.username,
                "message": message,
                "timestamp": time.time()
            }
            
            room.chat_messages.append(chat_msg)
            await self.broadcast_to_room(room_id, chat_msg)
            
    async def handle_ban_attempt(self, player_id: str, room_id: str):
        room = self.rooms.get(room_id)
        if not room or not room.is_active:
            return
            
        player = room.players.get(player_id)
        bastral = room.players.get(room.bastral_id) if room.bastral_id else None
        
        if not player or not bastral or player.is_banned or bastral.is_banned:
            return
            
        if player_id == room.bastral_id:
            await self.send_to_player(player_id, {
                "type": "ban_failed",
                "reason": "Cannot ban yourself!"
            })
            return
            
        # Check proximity
        distance = math.sqrt(
            (player.position.x - bastral.position.x) ** 2 +
            (player.position.y - bastral.position.y) ** 2 +
            (player.position.z - bastral.position.z) ** 2
        )
        
        if distance > 3.0:
            await self.send_to_player(player_id, {
                "type": "ban_failed",
                "reason": "Too far from @bastral! Get closer to kick."
            })
            return
            
        bastral.is_banned = True
        player.animation_state = "kicking"
        bastral.animation_state = "falling"
        
        ban_event = {
            "type": "player_banned",
            "banner_id": player_id,
            "banned_id": room.bastral_id,
            "banner_username": player.username,
            "banned_username": bastral.username,
            "position": asdict(bastral.position)
        }
        
        await self.broadcast_to_room(room_id, ban_event)
        
    def get_room_state(self, room_id: str) -> dict:
        room = self.rooms.get(room_id)
        if not room:
            return {}
            
        return {
            "room_id": room_id,
            "is_active": room.is_active,
            "player_count": len(room.players),
            "players": {pid: asdict(player) for pid, player in room.players.items()},
            "bastral_id": room.bastral_id,
            "game_start_time": room.game_start_time
        }
        
    async def send_to_player(self, player_id: str, message: dict):
        if player_id in self.connections:
            try:
                await self.connections[player_id].send_text(json.dumps(message))
            except:
                pass
                
    async def broadcast_to_room(self, room_id: str, message: dict, exclude_player: str = None):
        room = self.rooms.get(room_id)
        if not room:
            return
            
        for player_id in room.players.keys():
            if player_id != exclude_player:
                await self.send_to_player(player_id, message)

# Global variables
application = None
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "https://web-production-5f438.up.railway.app")
CHAT_HANDLE = os.getenv("CHAT_HANDLE")
MONAD_RPC_URL = os.getenv("MONAD_RPC_URL")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")
BANALL_CONTRACT_ADDRESS = os.getenv("BANALL_CONTRACT_ADDRESS")
TOURS_TOKEN_ADDRESS = os.getenv("TOURS_TOKEN_ADDRESS")
OWNER_ADDRESS = os.getenv("OWNER_ADDRESS")
LEGACY_ADDRESS = os.getenv("LEGACY_ADDRESS")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_CONNECT_PROJECT_ID = os.getenv("WALLET_CONNECT_PROJECT_ID")
EXPLORER_URL = "https://testnet.monadexplorer.com"
DATABASE_URL = os.getenv("DATABASE_URL", "none")

# Log environment variables
logger.info("Environment variables:")
logger.info(f"TELEGRAM_TOKEN: {'Set' if TELEGRAM_TOKEN else 'Missing'}")
logger.info(f"API_BASE_URL: {API_BASE_URL}")
logger.info(f"CHAT_HANDLE: {'Set' if CHAT_HANDLE else 'Missing'}")
logger.info(f"MONAD_RPC_URL: {'Set' if MONAD_RPC_URL else 'Missing'}")
logger.info(f"CONTRACT_ADDRESS: {'Set' if CONTRACT_ADDRESS else 'Missing'}")
logger.info(f"BANALL_CONTRACT_ADDRESS: {'Set' if BANALL_CONTRACT_ADDRESS else 'Missing'}")
logger.info(f"TOURS_TOKEN_ADDRESS: {'Set' if TOURS_TOKEN_ADDRESS else 'Missing'}")
logger.info(f"OWNER_ADDRESS: {'Set' if OWNER_ADDRESS else 'Missing'}")
logger.info(f"LEGACY_ADDRESS: {'Set' if LEGACY_ADDRESS else 'Missing'}")
logger.info(f"PRIVATE_KEY: {'Set' if PRIVATE_KEY else 'Missing'}")
logger.info(f"WALLET_CONNECT_PROJECT_ID: {'Set' if WALLET_CONNECT_PROJECT_ID else 'Missing'}")
logger.info(f"DATABASE_URL: {DATABASE_URL}")

missing_vars = []
if not TELEGRAM_TOKEN: missing_vars.append("TELEGRAM_TOKEN")
if not CHAT_HANDLE: missing_vars.append("CHAT_HANDLE")
if not MONAD_RPC_URL: missing_vars.append("MONAD_RPC_URL")
if not CONTRACT_ADDRESS: missing_vars.append("CONTRACT_ADDRESS")
if not BANALL_CONTRACT_ADDRESS: missing_vars.append("BANALL_CONTRACT_ADDRESS")
if not TOURS_TOKEN_ADDRESS: missing_vars.append("TOURS_TOKEN_ADDRESS")
if not OWNER_ADDRESS: missing_vars.append("OWNER_ADDRESS")
if not LEGACY_ADDRESS: missing_vars.append("LEGACY_ADDRESS")
if not PRIVATE_KEY: missing_vars.append("PRIVATE_KEY")
if not WALLET_CONNECT_PROJECT_ID: missing_vars.append("WALLET_CONNECT_PROJECT_ID")
if missing_vars:
    logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
    logger.warning("Proceeding with limited functionality")
else:
    logger.info("All required environment variables are set")

# BAN@LL Contract ABI
BANALL_CONTRACT_ABI = [
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
            {"internalType": "string", "name": "_username", "type": "string"},
            {"internalType": "uint256", "name": "_farcasterFid", "type": "uint256"}
        ],
        "name": "createProfile",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "depositTours",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "_toursToken", "type": "address"}
        ],
        "stateMutability": "nonpayable",
        "type": "constructor"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "winner", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "monPot", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "toursReward", "type": "uint256"}
        ],
        "name": "GameEnded",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": False, "internalType": "uint256", "name": "startTime", "type": "uint256"}
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
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "banned", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "by", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "farcasterFid", "type": "uint256"}
        ],
        "name": "PlayerBanned",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "user", "type": "address"},
            {"indexed": False, "internalType": "string", "name": "username", "type": "string"},
            {"indexed": False, "internalType": "uint256", "name": "farcasterFid", "type": "uint256"}
        ],
        "name": "ProfileCreated",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "address", "name": "user", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "RewardDistributed",
        "type": "event"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "_bastral", "type": "address"}
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
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "name": "activePlayers",
        "outputs": [
            {"internalType": "address", "name": "", "type": "address"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "bastralPlayer",
        "outputs": [
            {"internalType": "address", "name": "", "type": "address"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "ENTRY_FEE",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "name": "farcasterFidToAddress",
        "outputs": [
            {"internalType": "address", "name": "", "type": "address"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "GAME_DURATION",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "gameStartTime",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "getGameState",
        "outputs": [
            {"internalType": "uint256", "name": "timeLeft", "type": "uint256"},
            {"internalType": "address", "name": "bastral", "type": "address"},
            {"internalType": "address[]", "name": "playersList", "type": "address[]"},
            {"internalType": "string[]", "name": "usernames", "type": "string[]"},
            {"internalType": "bool[]", "name": "banned", "type": "bool[]"},
            {"internalType": "uint256[]", "name": "toursBalances", "type": "uint256[]"},
            {"internalType": "bool[]", "name": "spectators", "type": "bool[]"},
            {"internalType": "uint256[]", "name": "farcasterFids", "type": "uint256[]"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "", "type": "address"}
        ],
        "name": "hasProfile",
        "outputs": [
            {"internalType": "bool", "name": "", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "isGameActive",
        "outputs": [
            {"internalType": "bool", "name": "", "type": "bool"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "lastWinner",
        "outputs": [
            {"internalType": "address", "name": "", "type": "address"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "LOBBY_WAIT",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "MAX_PLAYERS",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [
            {"internalType": "address", "name": "", "type": "address"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "", "type": "address"}
        ],
        "name": "players",
        "outputs": [
            {"internalType": "address", "name": "wallet", "type": "address"},
            {"internalType": "string", "name": "username", "type": "string"},
            {"internalType": "bool", "name": "isBanned", "type": "bool"},
            {"internalType": "bool", "name": "isSpectator", "type": "bool"},
            {"internalType": "uint256", "name": "farcasterFid", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "PROFILE_REWARD",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalPot",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "TOURS_REWARD",
        "outputs": [
            {"internalType": "uint256", "name": "", "type": "uint256"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "toursToken",
        "outputs": [
            {"internalType": "contract IERC20", "type": "address"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

# TOURS Token ABI
TOURS_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Global blockchain variables
w3 = None
banall_contract = None
tours_contract = None
pool = None
sessions = {}
pending_wallets = {}
reverse_sessions = {}
webhook_failed = False
last_processed_block = 0
processed_updates = set()

@retry(wait=wait_exponential(multiplier=1, min=4, max=10), stop=stop_after_attempt(5))
async def initialize_web3():
    global w3, banall_contract, tours_contract
    if not MONAD_RPC_URL or not BANALL_CONTRACT_ADDRESS or not TOURS_TOKEN_ADDRESS:
        logger.error("Cannot initialize Web3: missing blockchain-related environment variables")
        return False
    try:
        w3 = AsyncWeb3(AsyncHTTPProvider(MONAD_RPC_URL))
        is_connected = await w3.is_connected()
        if is_connected:
            logger.info("AsyncWeb3 initialized successfully")
            banall_contract = w3.eth.contract(address=w3.to_checksum_address(BANALL_CONTRACT_ADDRESS), abi=BANALL_CONTRACT_ABI)
            tours_contract = w3.eth.contract(address=w3.to_checksum_address(TOURS_TOKEN_ADDRESS), abi=TOURS_ABI)
            logger.info("Contracts initialized successfully")
            return True
        else:
            raise Exception("Web3 not connected")
    except Exception as e:
        logger.error(f"Error initializing Web3: {str(e)}")
        raise

def escape_html(text):
    if not text:
        return ""
    return html.escape(str(text))

async def send_notification(chat_id, message):
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        try:
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            async with session.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json=payload
            ) as response:
                response_data = await response.json()
                logger.info(f"Sent notification to chat {chat_id}: payload={json.dumps(payload, default=str)}, response={response_data}")
                return response_data
        except Exception as e:
            logger.error(f"Error in send_notification to chat {chat_id}: {str(e)}")
            return {"ok": False, "error": str(e)}

async def check_webhook():
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        try:
            async with session.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo") as response:
                status = response.status
                data = await response.json()
                logger.info(f"Webhook info: status={status}, response={data}")
                return data.get("ok") and data.get("result", {}).get("url") == f"{API_BASE_URL.rstrip('/')}/webhook"
        except Exception as e:
            logger.error(f"Error checking webhook: {str(e)}")
            return False

async def reset_webhook():
    await asyncio.sleep(0.5)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        retries = 5
        for attempt in range(1, retries + 1):
            try:
                logger.info(f"Webhook reset attempt {attempt}/{retries}")
                async with session.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
                    json={"drop_pending_updates": True}
                ) as response:
                    status = response.status
                    delete_data = await response.json()
                    logger.info(f"Webhook cleared: status={status}, response={delete_data}")
                    if not delete_data.get("ok"):
                        logger.error(f"Failed to delete webhook: status={status}, response={delete_data}")
                        continue
                webhook_url = f"{API_BASE_URL.rstrip('/')}/webhook"
                logger.info(f"Setting webhook to {webhook_url}")
                async with session.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
                    json={"url": webhook_url, "max_connections": 100, "drop_pending_updates": True}
                ) as response:
                    status = response.status
                    set_data = await response.json()
                    logger.info(f"Webhook set: status={status}, response={set_data}")
                    if set_data.get("ok"):
                        logger.info("Verifying webhook after setting")
                        webhook_ok = await check_webhook()
                        if webhook_ok:
                            logger.info("Webhook verified successfully")
                            return True
                        else:
                            logger.error("Webhook verification failed after setting")
                    if set_data.get("error_code") == 429:
                        retry_after = set_data.get("parameters", {}).get("retry_after", 1)
                        logger.warning(f"Rate limited by Telegram, retrying after {retry_after} seconds")
                        await asyncio.sleep(retry_after)
                        continue
                    logger.error(f"Failed to set webhook: status={status}, response={set_data}")
            except Exception as e:
                logger.error(f"Error resetting webhook on attempt {attempt}/{retries}: {str(e)}")
                if attempt < retries:
                    await asyncio.sleep(2 ** attempt)
        logger.error("All webhook reset attempts failed. Forcing polling mode.")
        global webhook_failed
        webhook_failed = True
        return False

async def get_session(user_id: str):
    if DATABASE_URL == "none":
        return sessions.get(user_id, {})
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM sessions WHERE user_id = $1", user_id)
        return dict(row) if row else {}

async def set_session(user_id: str, wallet_address: str):
    if DATABASE_URL == "none":
        sessions[user_id] = {"user_id": user_id, "wallet_address": wallet_address}
        reverse_sessions[wallet_address.lower()] = user_id
    else:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO sessions (user_id, wallet_address) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET wallet_address = EXCLUDED.wallet_address",
                user_id, wallet_address
            )

async def delete_session(user_id: str):
    if DATABASE_URL == "none":
        if user_id in sessions:
            wallet_address = sessions[user_id].get("wallet_address")
            if wallet_address and wallet_address.lower() in reverse_sessions:
                del reverse_sessions[wallet_address.lower()]
            del sessions[user_id]
    else:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM sessions WHERE user_id = $1", user_id)

async def get_pending_wallet(user_id: str):
    if DATABASE_URL == "none":
        return pending_wallets.get(user_id, {})
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM pending_wallets WHERE user_id = $1", user_id)
        return dict(row) if row else {}

async def set_pending_wallet(user_id: str, data: dict):
    if DATABASE_URL == "none":
        pending_wallets[user_id] = data
    else:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO pending_wallets (user_id, data, timestamp) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO UPDATE SET data = EXCLUDED.data, timestamp = EXCLUDED.timestamp",
                user_id, json.dumps(data, default=str), data.get('timestamp', time.time())
            )

async def delete_pending_wallet(user_id: str):
    if DATABASE_URL == "none":
        if user_id in pending_wallets:
            del pending_wallets[user_id]
    else:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM pending_wallets WHERE user_id = $1", user_id)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /start command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    try:
        welcome_message = (
            f"Welcome to EmpowerTours! 🧗\n"
            f"Join our community at <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a> to connect with climbers.\n"
            f"Use /connectwallet to link your wallet, then /createprofile to get started.\n"
            f"Play BAN@LL with /banall!\n"
            f"Run /help for all commands."
        )
        await update.message.reply_text(welcome_message, parse_mode="HTML")
        logger.info(f"Sent /start response to user {update.effective_user.id}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in /start: {str(e)}, took {time.time() - start_time:.2f} seconds")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact support at <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /help command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    try:
        help_text = (
            "<b>EmpowerTours Commands</b>\n"
            "/start - Welcome message\n"
            "/connectwallet - Connect your wallet\n"
            "/createprofile - Create profile (1 $MON, receive 1 $TOURS)\n"
            "/banall - Launch BAN@LL Web3 rock climbing game\n"
            "/addbots [number] - Add bot players to BAN@LL (1-10)\n"
            "/buyTours [amount] - Buy $TOURS tokens with $MON\n"
            "/sendTours [recipient] [amount] - Send $TOURS to another wallet\n"
            "/balance - Check wallet balance ($MON, $TOURS, profile status)\n"
            "/debug - Check webhook status\n"
            "/forcewebhook - Force reset webhook\n"
            "/clearcache - Clear Telegram cache\n"
            "/ping - Check bot status\n"
            "Join our community at <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a> for support!"
        )
        await update.message.reply_text(help_text, parse_mode="HTML")
        logger.info(f"Sent /help response to user {update.effective_user.id}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in /help: {str(e)}, took {time.time() - start_time:.2f} seconds")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact support at <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def connect_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /connectwallet command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    if not API_BASE_URL:
        await update.message.reply_text("Wallet connection unavailable. Try again later! 😅")
        return
    try:
        user_id = str(update.effective_user.id)
        connect_url = f"{API_BASE_URL.rstrip('/')}/public/connect.html?userId={user_id}"
        keyboard = [[InlineKeyboardButton("Connect with MetaMask/WalletConnect", url=connect_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Click to connect your wallet via MetaMask or WalletConnect. On mobile, copy the link and open in MetaMask’s browser. After connecting, use /createprofile. If issues, contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>.",
            reply_markup=reply_markup, parse_mode="HTML"
        )
        await set_pending_wallet(user_id, {"awaiting_wallet": True, "timestamp": time.time()})
        logger.info(f"Sent /connectwallet response to user {user_id}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in /connectwallet: {str(e)}")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def create_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /createprofile command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    if not w3 or not banall_contract or not tours_contract:
        await update.message.reply_text("Blockchain unavailable. Try again later! 😅")
        return
    try:
        user_id = str(update.effective_user.id)
        session = await get_session(user_id)
        wallet_address = session.get("wallet_address")
        if not wallet_address:
            await update.message.reply_text("No wallet connected. Use /connectwallet first! 🪙")
            return
        checksum_address = w3.to_checksum_address(wallet_address)
        profile = await banall_contract.functions.hasProfile(checksum_address).call()
        if profile:
            await update.message.reply_text(
                f"Profile already exists for wallet [{checksum_address[:6]}...]({EXPLORER_URL}/address/{checksum_address})! Try /banall or /balance.",
                parse_mode="Markdown"
            )
            return
        entry_fee = await banall_contract.functions.ENTRY_FEE().call()
        mon_balance = await w3.eth.get_balance(checksum_address)
        if mon_balance < entry_fee + (300000 * await w3.eth.gas_price):
            await update.message.reply_text(
                f"Insufficient $MON. Need {entry_fee / 10**18} $MON plus gas (~0.015 $MON). Top up at https://testnet.monad.xyz/faucet."
            )
            return
        username = update.effective_user.username or update.effective_user.first_name
        nonce = await w3.eth.get_transaction_count(checksum_address)
        tx = await banall_contract.functions.createProfile(username, 0).build_transaction({
            'from': checksum_address,
            'nonce': nonce,
            'gas': await banall_contract.functions.createProfile(username, 0).estimate_gas({
                'from': checksum_address,
                'value': entry_fee
            }),
            'gas_price': await w3.eth.gas_price,
            'value': entry_fee,
            'chain_id': await w3.eth.chain_id
        })
        await set_pending_wallet(user_id, {
            "awaiting_tx": True,
            "tx_data": tx,
            "wallet_address": checksum_address,
            "timestamp": time.time()
        })
        await update.message.reply_text(
            f"Please open {API_BASE_URL.rstrip('/')}/public/connect.html?userId={user_id} to sign the transaction for profile creation (1 $MON).",
            parse_mode="Markdown"
        )
        logger.info(f"/createprofile transaction built for user {user_id}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in /createprofile: {str(e)}")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def banall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /banall command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    try:
        webapp_url = f"{API_BASE_URL.rstrip('/')}/public/banall.html"
        keyboard = [[InlineKeyboardButton("Play BAN@LL", web_app={"url": webapp_url})]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Launch BAN@LL, the Web3 rock climbing adventure game! Connect your wallet and join the game.",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        logger.info(f"Sent /banall response to user {update.effective_user.id}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in /banall: {str(e)}")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def addbots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /addbots command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    if not banall_contract:
        await update.message.reply_text("Game unavailable due to blockchain issues. Try again later! 😅")
        return
    try:
        args = context.args
        if len(args) < 1:
            await update.message.reply_text("Use: /addbots [number] (1-10)")
            return
        num_bots = int(args[0])
        if not 1 <= num_bots <= 10:
            await update.message.reply_text("Number of bots must be between 1 and 10.")
            return
        user_id = str(update.effective_user.id)
        session = await get_session(user_id)
        wallet_address = session.get("wallet_address") if session else None
        if not wallet_address:
            await update.message.reply_text("No wallet connected. Use /connectwallet first!")
            return
        checksum_address = w3.to_checksum_address(wallet_address)
        profile = await banall_contract.functions.hasProfile(checksum_address).call()
        if not profile:
            await update.message.reply_text(
                f"No profile exists for wallet [{checksum_address[:6]}...]({EXPLORER_URL}/address/{checksum_address})! Use /createprofile first.",
                parse_mode="Markdown"
            )
            return
        game_active = await banall_contract.functions.isGameActive().call()
        if game_active:
            await update.message.reply_text("Game is already active. Join or spectate via /banall!")
            return
        active_players = await banall_contract.functions.getGameState().call()
        if len([p for p, b, s in zip(active_players[2], active_players[4], active_players[6]) if not b and not s]) > 1:
            await update.message.reply_text("Multiple players already in lobby. Join via /banall!")
            return
        bot_addresses = [w3.eth.account.create().address for _ in range(num_bots)]
        for i, bot_address in enumerate(bot_addresses):
            bot_username = f"Bot{i+1}"
            bot_fid = 0
            nonce = await w3.eth.get_transaction_count(checksum_address)
            tx = await banall_contract.functions.createProfile(bot_username, bot_fid).build_transaction({
                'from': checksum_address,
                'nonce': nonce,
                'gas': await banall_contract.functions.createProfile(bot_username, bot_fid).estimate_gas({
                    'from': checksum_address,
                    'value': w3.to_wei(0.00001, 'ether')
                }),
                'gas_price': await w3.eth.gas_price,
                'value': w3.to_wei(0.00001, 'ether'),
                'chain_id': await w3.eth.chain_id
            })
            await set_pending_wallet(user_id, {
                "awaiting_tx": True,
                "tx_data": tx,
                "wallet_address": checksum_address,
                "timestamp": time.time(),
                "bot_address": bot_address,
                "bot_username": bot_username
            })
            await update.message.reply_text(
                f"Please sign transaction to create profile for {bot_username} at {API_BASE_URL.rstrip('/')}/public/connect.html?userId={user_id}"
            )
            logger.info(f"/addbots initiated for {num_bots} bots for user {user_id}, took {time.time() - start_time:.2f} seconds")
            break  # Process one bot at a time to avoid nonce issues
    except Exception as e:
        logger.error(f"Error in /addbots: {str(e)}")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def buy_tours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /buyTours command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    if not API_BASE_URL or not w3 or not tours_contract:
        await update.message.reply_text("Buying $TOURS unavailable. Try again later! 😅")
        return
    try:
        user_id = str(update.effective_user.id)
        args = context.args
        if len(args) < 1:
            await update.message.reply_text("Use: /buyTours [amount] 🪙 (e.g., /buyTours 10)")
            return
        amount = int(float(args[0]) * 10**18)
        if amount <= 0:
            await update.message.reply_text("Invalid amount. Use a positive number (e.g., /buyTours 10). 😅")
            return
        session = await get_session(user_id)
        wallet_address = session.get("wallet_address")
        if not wallet_address:
            await update.message.reply_text("No wallet connected. Use /connectwallet first! 🪙")
            return
        checksum_address = w3.to_checksum_address(wallet_address)
        profile = await banall_contract.functions.hasProfile(checksum_address).call()
        if not profile:
            await update.message.reply_text(
                f"No profile exists for wallet [{checksum_address[:6]}...]({EXPLORER_URL}/address/{checksum_address})! Use /createprofile first.",
                parse_mode="Markdown"
            )
            return
        mon_balance = await w3.eth.get_balance(checksum_address)
        if mon_balance < w3.to_wei(0.1, 'ether') + (300000 * await w3.eth.gas_price):
            await update.message.reply_text(
                f"Insufficient $MON. Need ~0.1 $MON plus gas. Top up at https://testnet.monad.xyz/faucet."
            )
            return
        nonce = await w3.eth.get_transaction_count(checksum_address)
        tx = await tours_contract.functions.depositTours(amount).build_transaction({
            'from': checksum_address,
            'nonce': nonce,
            'gas': await tours_contract.functions.depositTours(amount).estimate_gas({'from': checksum_address}),
            'gas_price': await w3.eth.gas_price,
            'value': w3.to_wei(0.1, 'ether'),
            'chain_id': await w3.eth.chain_id
        })
        await set_pending_wallet(user_id, {
            "awaiting_tx": True,
            "tx_data": tx,
            "wallet_address": checksum_address,
            "timestamp": time.time()
        })
        await update.message.reply_text(
            f"Please open {API_BASE_URL.rstrip('/')}/public/connect.html?userId={user_id} to sign the transaction to buy {args[0]} $TOURS.",
            parse_mode="Markdown"
        )
        logger.info(f"/buyTours transaction built for user {user_id}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in /buyTours: {str(e)}")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def send_tours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /sendTours command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    if not API_BASE_URL or not w3 or not tours_contract:
        await update.message.reply_text("Sending $TOURS unavailable. Try again later! 😅")
        return
    try:
        user_id = str(update.effective_user.id)
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Use: /sendTours [recipient] [amount] 🪙 (e.g., /sendTours 0x123...456 10)")
            return
        recipient = args[0]
        amount = int(float(args[1]) * 10**18)
        session = await get_session(user_id)
        wallet_address = session.get("wallet_address")
        if not wallet_address:
            await update.message.reply_text("No wallet connected. Use /connectwallet first! 🪙")
            return
        checksum_address = w3.to_checksum_address(wallet_address)
        recipient_checksum_address = w3.to_checksum_address(recipient)
        balance = await tours_contract.functions.balanceOf(checksum_address).call()
        if balance < amount:
            await update.message.reply_text(f"Insufficient $TOURS. You have {balance / 10**18} $TOURS, need {amount / 10**18}. Use /buyTours.")
            return
        nonce = await w3.eth.get_transaction_count(checksum_address)
        tx = await tours_contract.functions.transfer(recipient_checksum_address, amount).build_transaction({
            'from': checksum_address,
            'nonce': nonce,
            'gas': await tours_contract.functions.transfer(recipient_checksum_address, amount).estimate_gas({'from': checksum_address}),
            'gas_price': await w3.eth.gas_price,
            'chain_id': await w3.eth.chain_id
        })
        await set_pending_wallet(user_id, {
            "awaiting_tx": True,
            "tx_data": tx,
            "wallet_address": checksum_address,
            "timestamp": time.time()
        })
        await update.message.reply_text(
            f"Please open {API_BASE_URL.rstrip('/')}/public/connect.html?userId={user_id} to sign the transaction to send {args[1]} $TOURS to [{recipient_checksum_address[:6]}...]({EXPLORER_URL}/address/{recipient_checksum_address}).",
            parse_mode="Markdown"
        )
        logger.info(f"/sendTours transaction built for user {user_id}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in /sendTours: {str(e)}")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /balance command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    try:
        user_id = str(update.effective_user.id)
        session = await get_session(user_id)
        wallet_address = session.get("wallet_address")
        if not wallet_address:
            await update.message.reply_text("No wallet connected. Use /connectwallet first! 🪙")
            return
        checksum_address = w3.to_checksum_address(wallet_address)
        profile = await banall_contract.functions.hasProfile(checksum_address).call()
        mon_balance = await w3.eth.get_balance(checksum_address)
        tours_balance = await tours_contract.functions.balanceOf(checksum_address).call()
        await update.message.reply_text(
            f"Wallet Balance:\n"
            f"- {mon_balance / 10**18} $MON\n"
            f"- {tours_balance / 10**18} $TOURS\n"
            f"Address: [{checksum_address}]({EXPLORER_URL}/address/{checksum_address})\n"
            f"Profile Status: {'Exists' if profile else 'No profile'}\n"
            f"Top up $MON at https://testnet.monad.xyz/faucet",
            parse_mode="Markdown"
        )
        logger.info(f"/balance retrieved for user {user_id}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in /balance: {str(e)}")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /ping command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    try:
        webhook_ok = await check_webhook()
        status = "Webhook OK" if webhook_ok else "Webhook failed, using polling"
        await update.message.reply_text(f"Pong! Bot is running. {status}. Try /banall.")
        logger.info(f"Sent /ping response to user {update.effective_user.id}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in /ping: {str(e)}")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def clearcache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /clearcache command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    try:
        await update.message.reply_text("Clearing cache with dummy messages.")
        await send_notification(update.effective_chat.id, "Dummy message 1 to clear Telegram cache.")
        if CHAT_HANDLE:
            await send_notification(CHAT_HANDLE, "Dummy message 2 to clear Telegram cache.")
        await reset_webhook()
        await update.message.reply_text("Cache cleared. Try /banall again.")
        logger.info(f"Sent /clearcache response to user {update.effective_user.id}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in /clearcache: {str(e)}")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def forcewebhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /forcewebhook command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    try:
        await update.message.reply_text("Attempting to force reset webhook...")
        webhook_success = await reset_webhook()
        await update.message.reply_text("Webhook reset successful!" if webhook_success else "Webhook reset failed. Check logs.")
        logger.info(f"Sent /forcewebhook response to user {update.effective_user.id}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in /forcewebhook: {str(e)}")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    logger.info(f"Received /debug command from user {update.effective_user.id} in chat {update.effective_chat.id}")
    try:
        webhook_ok = await check_webhook()
        await update.effective_message.reply_text(
            f"Webhook is correctly set to {API_BASE_URL.rstrip('/')}/webhook" if webhook_ok else "Webhook not set. Use /forcewebhook."
        )
        logger.info(f"Sent /debug response to user {update.effective_user.id}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in /debug: {str(e)}")
        await update.effective_message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def handle_wallet_address(user_id: str, wallet_address: str, context: ContextTypes.DEFAULT_TYPE):
    start_time = time.time()
    logger.info(f"Handling wallet address for user {user_id}: {wallet_address}")
    pending = await get_pending_wallet(user_id)
    if not pending or not pending.get("awaiting_wallet"):
        logger.warning(f"No pending wallet connection for user {user_id}")
        return
    try:
        if w3 and w3.is_address(wallet_address):
            checksum_address = w3.to_checksum_address(wallet_address)
            await set_session(user_id, checksum_address)
            await context.bot.send_message(user_id, f"Wallet [{checksum_address[:6]}...]({EXPLORER_URL}/address/{checksum_address}) connected! Try /createprofile. 🪙", parse_mode="Markdown")
            await delete_pending_wallet(user_id)
            logger.info(f"Wallet connected for user {user_id}: {checksum_address}, took {time.time() - start_time:.2f} seconds")
        else:
            await context.bot.send_message(user_id, "Invalid wallet address. Try /connectwallet again.")
    except Exception as e:
        logger.error(f"Error in handle_wallet_address: {str(e)}")
        await context.bot.send_message(user_id, f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def handle_tx_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    start_time = time.time()
    user_id = str(update.effective_user.id)
    logger.info(f"Received transaction hash from user {user_id}: {update.message.text}")
    pending = await get_pending_wallet(user_id)
    if not pending or not pending.get("awaiting_tx"):
        await update.message.reply_text("No pending transaction. Use /createprofile or /buyTours again! 😅")
        return
    tx_hash = update.message.text.strip()
    if not tx_hash.startswith("0x") or len(tx_hash) != 66:
        await update.message.reply_text("Invalid transaction hash. Send a valid hash (e.g., 0x123...).")
        return
    try:
        receipt = await w3.eth.get_transaction_receipt(tx_hash)
        if receipt and receipt.status:
            action = "Action completed"
            tx_data_hex = pending["tx_data"]["data"][2:10]
            if tx_data_hex == banall_contract.functions.createProfile("", 0).selector[2:]:
                action = "Profile created with 1 $TOURS funded to your wallet"
            elif tx_data_hex == tours_contract.functions.depositTours(0).selector[2:]:
                amount = int.from_bytes(bytes.fromhex(pending["tx_data"]["data"][10:]), byteorder='big') / 10**18
                action = f"Successfully purchased {amount} $TOURS"
            elif tx_data_hex == tours_contract.functions.transfer('0x0', 0).selector[2:]:
                action = "Successfully sent $TOURS to the recipient"
            await update.message.reply_text(f"Transaction confirmed! [Tx: {tx_hash}]({EXPLORER_URL}/tx/{tx_hash}) 🪙 {action}.", parse_mode="Markdown")
            if CHAT_HANDLE:
                await send_notification(CHAT_HANDLE, f"New activity by {escape_html(update.effective_user.username or update.effective_user.first_name)}! <a href=\"{EXPLORER_URL}/tx/{tx_hash}\">Tx: {tx_hash}</a>")
            await delete_pending_wallet(user_id)
        else:
            await update.message.reply_text("Transaction failed or pending. Check and try again! 😅")
    except Exception as e:
        logger.error(f"Error in handle_tx_hash: {str(e)}")
        await update.message.reply_text(f"Error: {html.escape(str(e))}. Try again or contact <a href=\"https://t.me/empowertourschat\">EmpowerTours Chat</a>. 😅", parse_mode="HTML")

async def monitor_events(context: ContextTypes.DEFAULT_TYPE):
    start_time = time.time()
    global last_processed_block
    if not w3 or not banall_contract:
        logger.error("Web3 or contract not initialized, cannot monitor events")
        return
    try:
        latest_block = await w3.eth.get_block_number()
        if last_processed_block == 0:
            last_processed_block = max(0, latest_block - 100)
        batch_size = 100
        end_block = min(last_processed_block + batch_size, latest_block + 1)
        num_blocks = end_block - last_processed_block - 1
        if num_blocks <= 0:
            return
        logger.info(f"Processing {num_blocks} blocks (from {last_processed_block + 1} to {end_block - 1})")
        logs = await w3.eth.get_logs({
            'fromBlock': last_processed_block + 1,
            'toBlock': end_block - 1,
            'address': w3.to_checksum_address(BANALL_CONTRACT_ADDRESS)
        })
        event_map = {
            "aa3a75c48d1cad3bf60136ab33bc8fd62f31c2b25812d8604da0b7e7fc6d7271": (
                banall_contract.events.ProfileCreated,
                lambda e: f"New BAN@LL player joined! 🧗 Address: <a href=\"{EXPLORER_URL}/address/{e.args.user}\">{e.args.user[:6]}...</a> Username: {e.args.username}"
            ),
            "0c1a0c90c4d37e5e3a2e5e0d7a0fddd6e0f0a0e5e0d7a0fddd6e0f0a0e5e0d7": (
                banall_contract.events.GameStarted,
                lambda e: f"BAN@LL game started! 🏆 Start time: {datetime.fromtimestamp(e.args.startTime).strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            "f0f0525a5ef10132058aa9a3feb1a1f6d503037788ea59f454076e216da1a741": (
                banall_contract.events.GameEnded,
                lambda e: f"BAN@LL game ended! Winner: <a href=\"{EXPLORER_URL}/address/{e.args.winner}\">{e.args.winner[:6]}...</a> Prize: {e.args.monPot / 10**18} $MON, {e.args.toursReward / 10**18} $TOURS 🏆"
            ),
            "9b71079da01b6505f63bcd5edd4a7a9dbc55173971019151c9654ae29def6bac": (
                banall_contract.events.PlayerBanned,
                lambda e: f"Player <a href=\"{EXPLORER_URL}/address/{e.args.banned}\">{e.args.banned[:6]}...</a> banned by <a href=\"{EXPLORER_URL}/address/{e.args.by}\">{e.args.by[:6]}...</a> in BAN@LL! 🚫"
            ),
            "b9f217daf6aa350a9b78812562d0d1afba9439b7b595919c7d9dfc40d2230f35": (
                banall_contract.events.RewardDistributed,
                lambda e: f"Reward of {e.args.amount / 10**18} $TOURS distributed to <a href=\"{EXPLORER_URL}/address/{e.args.user}\">{e.args.user[:6]}...</a> in BAN@LL! 🪙"
            ),
        }
        for log in logs:
            try:
                topic0 = log['topics'][0].hex()
                if topic0 in event_map:
                    event_class, message_fn = event_map[topic0]
                    event = event_class().process_log(log)
                    message = message_fn(event)
                    if CHAT_HANDLE:
                        await send_notification(CHAT_HANDLE, message)
                    user_address = event.args.get('user') or event.args.get('winner') or event.args.get('banned') or event.args.get('by')
                    if user_address and user_address.lower() in reverse_sessions and application:
                        user_id = reverse_sessions[user_address.lower()]
                        await application.bot.send_message(user_id, f"Your action succeeded! {message.replace('<a href=', '[Tx: ').replace('</a>', ']')} 🪙 Check details on {EXPLORER_URL}/tx/{log['transactionHash'].hex()}", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error processing log: {str(e)}")
        last_processed_block = end_block - 1
        logger.info(f"Processed events up to block {last_processed_block}, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in monitor_events: {str(e)}")

async def startup_event():
    start_time = time.time()
    global application, webhook_failed, pool, sessions, reverse_sessions, pending_wallets
    try:
        # Initialize Postgres pool if DATABASE_URL is set
        if DATABASE_URL != "none":
            pool = await asyncpg.create_pool(DATABASE_URL)
            async with pool.acquire() as conn:
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    user_id TEXT PRIMARY KEY,
                    wallet_address TEXT
                )
                """)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS pending_wallets (
                    user_id TEXT PRIMARY KEY,
                    data JSONB,
                    timestamp FLOAT
                )
                """)
                rows = await conn.fetch("SELECT * FROM sessions")
                sessions = {}
                reverse_sessions = {}
                for row in rows:
                    sessions[row['user_id']] = {"wallet_address": row['wallet_address']}
                    if row['wallet_address']:
                        reverse_sessions[row['wallet_address'].lower()] = row['user_id']
                rows = await conn.fetch("SELECT * FROM pending_wallets")
                pending_wallets = {}
                current_time = time.time()
                for row in rows:
                    if current_time - row['timestamp'] < 3600:
                        pending_wallets[row['user_id']] = json.loads(row['data'])
                        pending_wallets[row['user_id']]['timestamp'] = row['timestamp']
                logger.info(f"Loaded from DB: {len(sessions)} sessions, {len(pending_wallets)} pending_wallets")

        # Check and free port
        port = int(os.getenv("PORT", 8080))
        ports = [port, 8081]
        selected_port = None
        for p in ports:
            logger.info(f"Checking for port {p} availability")
            for attempt in range(1, 4):
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(('0.0.0.0', p))
                    sock.close()
                    logger.info(f"Port {p} is available")
                    selected_port = p
                    break
                except socket.error as e:
                    logger.error(f"Port {p} in use on attempt {attempt}/3: {str(e)}. Attempting to free port...")
                    try:
                        result = subprocess.run(
                            f"lsof -i :{p} | grep LISTEN | awk '{{print $2}}' | xargs kill -9",
                            shell=True, capture_output=True, text=True
                        )
                        logger.info(f"Port {p} cleanup result: {result.stdout}, {result.stderr}")
                    except subprocess.SubprocessError as se:
                        logger.error(f"Failed to run cleanup command for port {p}: {str(se)}")
                    time.sleep(2)
                    if attempt == 3 and p == ports[-1]:
                        logger.error("No available ports. Falling back to polling.")
                        webhook_failed = True
                else:
                    break
            if selected_port:
                break

        await initialize_web3()
        
        # Initialize Telegram bot only if token is provided
        if TELEGRAM_TOKEN and TELEGRAM_TOKEN != "":
            application = Application.builder().token(TELEGRAM_TOKEN).build()
            application.add_handler(CommandHandler("start", start))
            application.add_handler(CommandHandler("help", help))
            application.add_handler(CommandHandler("connectwallet", connect_wallet))
            application.add_handler(CommandHandler("createprofile", create_profile))
            application.add_handler(CommandHandler("banall", banall))
            application.add_handler(CommandHandler("addbots", addbots))
            application.add_handler(CommandHandler("buyTours", buy_tours))
            application.add_handler(CommandHandler("sendTours", send_tours))
            application.add_handler(CommandHandler("balance", balance))
            application.add_handler(CommandHandler("ping", ping))
            application.add_handler(CommandHandler("clearcache", clearcache))
            application.add_handler(CommandHandler("forcewebhook", forcewebhook))
            application.add_handler(CommandHandler("debug", debug_command))
            application.add_handler(MessageHandler(filters.Regex(r'^0x[a-fA-F0-9]{64}$'), handle_tx_hash))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("Use a valid command like /banall or /help. 😅")))
            application.job_queue.run_repeating(monitor_events, interval=10, first=1)

            await application.initialize()
            if not webhook_failed:
                webhook_success = await reset_webhook()
                if webhook_success:
                    logger.info(f"Webhook set successfully to {API_BASE_URL.rstrip('/')}/webhook")
                    await application.start()
                else:
                    logger.warning("Webhook setup failed, falling back to polling")
                    webhook_failed = True
            if webhook_failed:
                logger.info("Starting polling mode")
                await application.start()
                await application.updater.start_polling()
            logger.info("Telegram bot initialized successfully")
        else:
            logger.warning("Telegram token not provided - running in web-only mode")
        logger.info(f"Startup completed, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}, took {time.time() - start_time:.2f} seconds")
        raise

async def shutdown_event():
    start_time = time.time()
    try:
        if application:
            if application.updater and application.updater.running:
                await application.updater.stop()
            await application.stop()
            await application.shutdown()
        if DATABASE_URL != "none" and pool:
            await pool.close()
        logger.info(f"Shutdown completed, took {time.time() - start_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error during shutdown: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_event()
    yield
    await shutdown_event()

app = FastAPI(lifespan=lifespan)

# Initialize game manager
game_manager = GameManager()

# Serve static files
app.mount("/public", StaticFiles(directory="/app/public"), name="public")

@app.websocket("/ws/{player_id}")
async def websocket_endpoint(websocket: WebSocket, player_id: str):
    await websocket.accept()
    
    try:
        await game_manager.add_player(player_id, websocket)
        
        # Send initial room state
        room_id = game_manager.player_to_room.get(player_id, "main")
        await websocket.send_text(json.dumps({
            "type": "room_joined",
            "player_id": player_id,
            "room_state": game_manager.get_room_state(room_id)
        }))
        
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "position_update":
                # Handle position updates
                pass
            elif message["type"] == "chat_message":
                await game_manager.handle_chat_message(player_id, message["message"])
            elif message["type"] == "start_game":
                # Start game logic
                room_id = game_manager.player_to_room.get(player_id, "main")
                room = game_manager.rooms.get(room_id)
                if room and len(room.players) >= 2:
                    room.is_active = True
                    room.game_start_time = time.time()
                    import random
                    bastral = random.choice(list(room.players.values()))
                    room.bastral_id = bastral.id
                    bastral.is_bastral = True
                    
                    await game_manager.broadcast_to_room(room_id, {
                        "type": "game_started",
                        "bastral_id": bastral.id,
                        "bastral_username": bastral.username,
                        "game_start_time": room.game_start_time
                    })
                    
    except WebSocketDisconnect:
        await game_manager.remove_player(player_id)
    except Exception as e:
        logger.error(f"WebSocket error for player {player_id}: {str(e)}")
        await game_manager.remove_player(player_id)

@app.get("/api/game_state/{room_id}")
async def get_game_state_endpoint(room_id: str = "main"):
    """Get current game state for a room"""
    return game_manager.get_room_state(room_id)

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "game_rooms": len(game_manager.rooms), "active_connections": len(game_manager.connections)}

@app.get("/health")
async def railway_health_check():
    """Railway health check endpoint"""
    return {"status": "healthy", "timestamp": time.time()}

@app.get("/public/env.js")
async def serve_env():
    content = f"""
window.env = {{
  TOURS_TOKEN_ADDRESS: "{TOURS_TOKEN_ADDRESS}",
  BANALL_CONTRACT_ADDRESS: "{BANALL_CONTRACT_ADDRESS}",
  API_BASE_URL: "{API_BASE_URL}",
  MONAD_RPC_URL: "{MONAD_RPC_URL}"
}};
    """
    return Response(content=content, media_type="application/javascript")

app.mount("/public", StaticFiles(directory="public"), name="public")

@app.get("/")
async def root():
    return RedirectResponse(url="/public/banall.html")

@app.get("/public/{path:path}")
async def serve_public(path: str):
    file_path = f"public/{path}"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/get_session")
async def get_session(userId: str):
    if DATABASE_URL == "none":
        return {"wallet_address": sessions.get(userId, {}).get("wallet_address")}
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT wallet_address FROM sessions WHERE user_id = $1", userId)
        return {"wallet_address": row['wallet_address'] if row else None}

@app.get("/check_profile")
async def check_profile(wallet: str):
    checksum = w3.to_checksum_address(wallet)
    has_profile = await banall_contract.functions.hasProfile(checksum).call()
    return {"hasProfile": has_profile}

@app.get("/game_state")
async def game_state():
    state = await banall_contract.functions.getGameState().call()
    return {
        "timeLeft": state[0],
        "bastral": state[1],
        "playersList": state[2],
        "usernames": state[3],
        "banned": state[4],
        "toursBalances": state[5],
        "spectators": state[6],
        "farcasterFids": state[7],
        "isGameActive": state[0] > 0
    }

@app.get("/get_transaction")
async def get_transaction(userId: str):
    start_time = time.time()
    logger.info(f"Received get_transaction request for userId: {userId}")
    try:
        pending = await get_pending_wallet(userId)
        if not pending or not pending.get("awaiting_tx"):
            return {"status": "error", "message": "No pending transaction"}
        return {
            "status": "success",
            "transaction": pending.get("tx_data"),
            "wallet_address": pending.get("wallet_address")
        }
    except Exception as e:
        logger.error(f"Error in get_transaction for userId {userId}: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.post("/submit_wallet")
async def submit_wallet(request: Request):
    start_time = time.time()
    try:
        data = await request.json()
        user_id = data.get("userId")
        wallet_address = data.get("walletAddress")
        logger.info(f"Received submit_wallet for userId: {user_id}, walletAddress: {wallet_address}")
        if not user_id or not wallet_address:
            return {"status": "error", "message": "Missing userId or walletAddress"}
        await handle_wallet_address(user_id, wallet_address, application)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in submit_wallet: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.post("/submit_tx")
async def submit_tx(request: Request):
    start_time = time.time()
    try:
        data = await request.json()
        user_id = data.get("userId")
        tx_hash = data.get("txHash")
        logger.info(f"Received submit_tx for userId: {user_id}, txHash: {tx_hash}")
        if not user_id or not tx_hash:
            return {"status": "error", "message": "Missing userId or txHash"}
        await application.bot.send_message(user_id, f"Received transaction hash: {tx_hash}")
        await handle_tx_hash(Update.de_json({
            "update_id": 0,
            "message": {
                "message_id": 0,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": user_id},
                "text": tx_hash
            }
        }, application.bot), application)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in submit_tx: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.post("/webhook")
async def webhook(request: Request):
    start_time = time.time()
    try:
        update = Update.de_json(await request.json(), application.bot)
        if not update:
            logger.error("Invalid webhook update received")
            return {"status": "error", "message": "Invalid update"}
        update_id = update.update_id
        if update_id in processed_updates:
            logger.warning(f"Duplicate update_id {update_id} received, ignoring")
            return {"status": "success", "message": "Duplicate update ignored"}
        processed_updates.add(update_id)
        if len(processed_updates) > 1000:
            processed_updates.clear()
        await application.process_update(update)
        logger.info(f"Webhook processed update_id {update_id}, took {time.time() - start_time:.2f} seconds")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in webhook: {str(e)}, took {time.time() - start_time:.2f} seconds")
        return {"status": "error", "message": str(e)}

@app.get("/frame")
@app.post("/frame")
async def farcaster_frame(request: Request):
    start_time = time.time()
    logger.info(f"Received /frame request")
    try:
        game_active = await banall_contract.functions.isGameActive().call() if banall_contract else False
        game_state = await banall_contract.functions.getGameState().call() if banall_contract else (0, "0x0", [], [], [], [], [], [])
        time_left = game_state[0]
        players = len([p for p, b, s in zip(game_state[2], game_state[4], game_state[6]) if not b and not s])
        status = "Active" if game_active else "Not Active"
        image_url = f"{API_BASE_URL.rstrip('/')}/public/empowertours_logo.svg"
        buttons = [
            {"type": 1, "label": "Play BAN@LL", "url": f"{API_BASE_URL.rstrip('/')}/public/banall.html"},
            {"type": 1, "label": "Join Community", "url": "https://t.me/empowertourschat"}
        ]
        if not game_active:
            buttons.append({"type": 3, "label": "Add Bots (1-10)", "value": "addbots"})
        frame_response = {
            "version": "vNext",
            "image": image_url,
            "buttons": buttons,
            "post_url": f"{API_BASE_URL.rstrip('/')}/frame",
            "og_title": "EmpowerTours BAN@LL Game",
            "text": f"BAN@LL Game Status: {status}\nPlayers: {players}\nTime Left: {time_left // 60} minutes"
        }
        if request.method == "POST":
            data = await request.json()
            message = data.get("untrustedData", {})
            if message.get("buttonIndex") == 3:
                user_id = str(message.get("fid", "unknown"))
                await application.bot.send_message(
                    user_id,
                    "Please specify the number of bots (1-10) using /addbots [number] in the Telegram bot."
                )
        return frame_response
    except Exception as e:
        logger.error(f"Error in /frame: {str(e)}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
