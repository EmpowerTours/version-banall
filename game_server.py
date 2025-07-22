import asyncio
import json
import logging
import math
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import aiohttp
from web3 import AsyncWeb3
from web3.providers.async_rpc import AsyncHTTPProvider
from dotenv import load_dotenv
import os
from dataclasses import dataclass, asdict

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
MONAD_RPC_URL = os.getenv("MONAD_RPC_URL")
BANALL_CONTRACT_ADDRESS = os.getenv("BANALL_CONTRACT_ADDRESS")
TOURS_TOKEN_ADDRESS = os.getenv("TOURS_TOKEN_ADDRESS")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")

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
    animation_state: str = "idle"  # idle, walking, climbing, kicking

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
        """Add a player to a game room"""
        self.connections[player_id] = websocket
        self.player_to_room[player_id] = room_id
        
        if room_id not in self.rooms:
            self.rooms[room_id] = GameRoom(id=room_id, players={})
            
        # Initialize player at spawn point on climbing wall
        spawn_position = PlayerPosition(
            x=float(len(self.rooms[room_id].players) * 2 - 10),  # Spread players along wall
            y=0.0,  # Ground level
            z=-2.0,  # Close to climbing wall
            rotation_y=0.0
        )
        
        player = Player(
            id=player_id,
            username=f"Player_{player_id}",
            wallet_address="",  # Will be set when wallet connects
            position=spawn_position,
            last_updated=time.time()
        )
        
        self.rooms[room_id].players[player_id] = player
        
        # Broadcast new player joined
        await self.broadcast_to_room(room_id, {
            "type": "player_joined",
            "player": asdict(player),
            "room_state": self.get_room_state(room_id)
        })
        
    async def remove_player(self, player_id: str):
        """Remove a player from the game"""
        if player_id in self.connections:
            del self.connections[player_id]
            
        if player_id in self.player_to_room:
            room_id = self.player_to_room[player_id]
            del self.player_to_room[player_id]
            
            if room_id in self.rooms and player_id in self.rooms[room_id].players:
                del self.rooms[room_id].players[player_id]
                
                # Broadcast player left
                await self.broadcast_to_room(room_id, {
                    "type": "player_left",
                    "player_id": player_id,
                    "room_state": self.get_room_state(room_id)
                })
                
    async def update_player_position(self, player_id: str, position_data: dict):
        """Update player position and animation state"""
        if player_id not in self.player_to_room:
            return
            
        room_id = self.player_to_room[player_id]
        if room_id not in self.rooms or player_id not in self.rooms[room_id].players:
            return
            
        player = self.rooms[room_id].players[player_id]
        player.position.x = position_data.get("x", player.position.x)
        player.position.y = position_data.get("y", player.position.y)
        player.position.z = position_data.get("z", player.position.z)
        player.position.rotation_y = position_data.get("rotation_y", player.position.rotation_y)
        player.animation_state = position_data.get("animation_state", "idle")
        player.last_updated = time.time()
        
        # Broadcast position update to all players in room
        await self.broadcast_to_room(room_id, {
            "type": "player_moved",
            "player_id": player_id,
            "position": asdict(player.position),
            "animation_state": player.animation_state
        }, exclude_player=player_id)
        
    async def handle_chat_message(self, player_id: str, message: str):
        """Handle chat messages and game commands"""
        if player_id not in self.player_to_room:
            return
            
        room_id = self.player_to_room[player_id]
        room = self.rooms.get(room_id)
        if not room:
            return
            
        player = room.players.get(player_id)
        if not player:
            return
            
        # Check for ban command
        if message.strip().lower() == "/ban @bastral":
            await self.handle_ban_attempt(player_id, room_id)
        else:
            # Regular chat message
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
        """Handle ban/kick attempt"""
        room = self.rooms.get(room_id)
        if not room or not room.is_active:
            return
            
        player = room.players.get(player_id)
        bastral = room.players.get(room.bastral_id) if room.bastral_id else None
        
        if not player or not bastral or player.is_banned or bastral.is_banned:
            return
            
        if player_id == room.bastral_id:
            # Can't ban yourself
            await self.send_to_player(player_id, {
                "type": "ban_failed",
                "reason": "Cannot ban yourself!"
            })
            return
            
        # Check proximity (players must be within 3 units of each other)
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
            
        # Successful ban!
        bastral.is_banned = True
        
        # Trigger kick animation
        player.animation_state = "kicking"
        bastral.animation_state = "falling"
        
        # Broadcast ban event
        ban_event = {
            "type": "player_banned",
            "banner_id": player_id,
            "banned_id": room.bastral_id,
            "banner_username": player.username,
            "banned_username": bastral.username,
            "position": asdict(bastral.position)
        }
        
        await self.broadcast_to_room(room_id, ban_event)
        
        # Select new bastral
        await self.select_new_bastral(room_id)
        
        # Check for game end
        await self.check_game_end(room_id)
        
    async def select_new_bastral(self, room_id: str):
        """Select a new bastral from unbanned players"""
        room = self.rooms.get(room_id)
        if not room:
            return
            
        unbanned_players = [p for p in room.players.values() 
                          if not p.is_banned and not p.is_spectator]
        
        if unbanned_players:
            import random
            new_bastral = random.choice(unbanned_players)
            room.bastral_id = new_bastral.id
            new_bastral.is_bastral = True
            
            await self.broadcast_to_room(room_id, {
                "type": "new_bastral",
                "bastral_id": new_bastral.id,
                "bastral_username": new_bastral.username
            })
            
    async def check_game_end(self, room_id: str):
        """Check if game should end"""
        room = self.rooms.get(room_id)
        if not room:
            return
            
        unbanned_players = [p for p in room.players.values() 
                          if not p.is_banned and not p.is_spectator]
        
        if len(unbanned_players) <= 1:
            # Game over
            room.is_active = False
            winner = unbanned_players[0] if unbanned_players else None
            
            await self.broadcast_to_room(room_id, {
                "type": "game_ended",
                "winner_id": winner.id if winner else None,
                "winner_username": winner.username if winner else None
            })
            
            # Reset room for next game
            for player in room.players.values():
                player.is_banned = False
                player.is_bastral = False
                player.animation_state = "idle"
                
    def get_room_state(self, room_id: str) -> dict:
        """Get current state of a room"""
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
        """Send message to specific player"""
        if player_id in self.connections:
            try:
                await self.connections[player_id].send_text(json.dumps(message))
            except:
                pass
                
    async def broadcast_to_room(self, room_id: str, message: dict, exclude_player: str = None):
        """Broadcast message to all players in room"""
        room = self.rooms.get(room_id)
        if not room:
            return
            
        for player_id in room.players.keys():
            if player_id != exclude_player:
                await self.send_to_player(player_id, message)

# Global game manager
game_manager = GameManager()

# FastAPI app
app = FastAPI(title="BAN@LL Game Server")

# Serve static files
app.mount("/public", StaticFiles(directory="/app/public"), name="public")

@app.get("/")
async def root():
    return FileResponse("/app/public/banall.html")

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
                await game_manager.update_player_position(player_id, message["data"])
            elif message["type"] == "chat_message":
                await game_manager.handle_chat_message(player_id, message["message"])
            elif message["type"] == "start_game":
                # Start game logic (can be triggered by game owner)
                room_id = game_manager.player_to_room.get(player_id, "main")
                room = game_manager.rooms.get(room_id)
                if room and len(room.players) >= 2:
                    room.is_active = True
                    room.game_start_time = time.time()
                    # Select random bastral
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
async def get_game_state(room_id: str = "main"):
    """Get current game state for a room"""
    return game_manager.get_room_state(room_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)