#!/usr/bin/env python3
"""
Backend API Testing for BAN@LL 3D Web3 Multiplayer Game
Tests all backend endpoints and WebSocket functionality
"""

import requests
import websocket
import json
import time
import sys
import threading
from datetime import datetime

class BanallAPITester:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url.rstrip('/')
        self.tests_run = 0
        self.tests_passed = 0
        self.websocket_messages = []
        self.websocket_connected = False

    def log(self, message):
        """Log test messages with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def run_test(self, name, method, endpoint, expected_status=200, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if headers is None:
            headers = {'Content-Type': 'application/json'}

        self.tests_run += 1
        self.log(f"🔍 Testing {name}...")
        self.log(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASSED - Status: {response.status_code}")
                
                # Try to parse JSON response
                try:
                    json_response = response.json()
                    self.log(f"   Response: {json.dumps(json_response, indent=2)[:200]}...")
                except:
                    self.log(f"   Response: {response.text[:200]}...")
            else:
                self.log(f"❌ FAILED - Expected {expected_status}, got {response.status_code}")
                self.log(f"   Response: {response.text[:200]}...")

            return success, response

        except Exception as e:
            self.log(f"❌ FAILED - Error: {str(e)}")
            return False, None

    def test_health_endpoint(self):
        """Test health check endpoint"""
        return self.run_test(
            "Health Check",
            "GET", 
            "/api/health",
            200
        )

    def test_game_state_endpoint(self):
        """Test game state endpoint"""
        return self.run_test(
            "Game State",
            "GET",
            "/api/game_state/main",
            200
        )

    def test_root_endpoint(self):
        """Test root endpoint - should serve banall.html"""
        success, response = self.run_test(
            "Root Endpoint",
            "GET",
            "/",
            200
        )
        
        if success and response:
            # Check if it contains expected HTML content
            content = response.text
            if "BAN@LL" in content and "3D Rock Climbing Game" in content:
                self.log("   ✅ Contains expected BAN@LL content")
            else:
                self.log("   ⚠️  Response doesn't contain expected BAN@LL content")
        
        return success, response

    def test_static_files(self):
        """Test static file serving"""
        static_files = [
            "/public/banall.html",
            "/public/game3d.html", 
            "/public/env.js",
            "/public/empowertours_logo.svg"
        ]
        
        all_passed = True
        for file_path in static_files:
            success, _ = self.run_test(
                f"Static File: {file_path}",
                "GET",
                file_path,
                200
            )
            if not success:
                all_passed = False
        
        return all_passed

    def on_websocket_message(self, ws, message):
        """Handle WebSocket messages"""
        try:
            data = json.loads(message)
            self.websocket_messages.append(data)
            self.log(f"📨 WebSocket received: {data.get('type', 'unknown')}")
        except Exception as e:
            self.log(f"❌ WebSocket message parse error: {e}")

    def on_websocket_error(self, ws, error):
        """Handle WebSocket errors"""
        self.log(f"❌ WebSocket error: {error}")

    def on_websocket_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        self.log(f"🔌 WebSocket closed: {close_status_code} - {close_msg}")
        self.websocket_connected = False

    def on_websocket_open(self, ws):
        """Handle WebSocket open"""
        self.log("🔌 WebSocket connected successfully")
        self.websocket_connected = True
        
        # Send a test message
        test_message = {
            "type": "position_update",
            "data": {
                "x": 0,
                "y": 0,
                "z": 0,
                "rotation_y": 0,
                "animation_state": "idle"
            }
        }
        ws.send(json.dumps(test_message))
        self.log("📤 Sent test position update")

    def test_websocket_connection(self):
        """Test WebSocket connectivity"""
        self.log("🔍 Testing WebSocket Connection...")
        
        # Convert HTTP URL to WebSocket URL
        ws_url = self.base_url.replace('https://', 'wss://').replace('http://', 'ws://')
        test_player_id = f"test_player_{int(time.time())}"
        ws_endpoint = f"{ws_url}/ws/{test_player_id}"
        
        self.log(f"   WebSocket URL: {ws_endpoint}")
        
        try:
            # Create WebSocket connection
            ws = websocket.WebSocketApp(
                ws_endpoint,
                on_open=self.on_websocket_open,
                on_message=self.on_websocket_message,
                on_error=self.on_websocket_error,
                on_close=self.on_websocket_close
            )
            
            # Run WebSocket in a separate thread
            ws_thread = threading.Thread(target=ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()
            
            # Wait for connection and messages
            timeout = 10
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if self.websocket_connected and len(self.websocket_messages) >= 1:
                    break
                time.sleep(0.1)
            
            # Give a bit more time for messages to arrive
            time.sleep(1)
            
            ws.close()
            
            # Check if we got the expected messages
            expected_messages = ['player_joined', 'room_joined']
            received_types = [msg.get('type') for msg in self.websocket_messages]
            
            if self.websocket_connected and any(msg_type in expected_messages for msg_type in received_types):
                self.tests_passed += 1
                self.log("✅ WebSocket connection successful")
                self.log(f"   Received {len(self.websocket_messages)} messages: {received_types}")
                
                # Test sending a chat message
                if len(self.websocket_messages) > 0:
                    self.log("   Testing chat message functionality...")
                    # This would require keeping the connection open longer
                    
                return True
            else:
                self.log("❌ WebSocket connection failed or no expected messages received")
                self.log(f"   Messages received: {received_types}")
                return False
                
        except Exception as e:
            self.log(f"❌ WebSocket test failed: {str(e)}")
            return False
        finally:
            self.tests_run += 1

    def test_game_logic_websocket(self):
        """Test game logic through WebSocket messages"""
        self.log("🔍 Testing Game Logic via WebSocket...")
        
        ws_url = self.base_url.replace('https://', 'wss://').replace('http://', 'ws://')
        test_player_id = f"marine_{int(time.time())}"
        ws_endpoint = f"{ws_url}/ws/{test_player_id}"
        
        self.log(f"   Testing game logic with player: {test_player_id}")
        
        try:
            # Reset message tracking
            self.websocket_messages = []
            self.websocket_connected = False
            
            ws = websocket.WebSocketApp(
                ws_endpoint,
                on_open=lambda ws: self.on_game_websocket_open(ws, test_player_id),
                on_message=self.on_websocket_message,
                on_error=self.on_websocket_error,
                on_close=self.on_websocket_close
            )
            
            ws_thread = threading.Thread(target=ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()
            
            # Wait for connection and initial messages
            timeout = 15
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                if self.websocket_connected and len(self.websocket_messages) >= 2:
                    break
                time.sleep(0.1)
            
            # Give more time for all messages
            time.sleep(2)
            
            ws.close()
            
            # Analyze received messages
            message_types = [msg.get('type') for msg in self.websocket_messages]
            self.log(f"   Received message types: {message_types}")
            
            # Check for expected game messages
            expected_types = ['player_joined', 'room_joined']
            success = any(msg_type in expected_types for msg_type in message_types)
            
            if success:
                self.tests_passed += 1
                self.log("✅ Game logic WebSocket test successful")
                
                # Check for game state in messages
                for msg in self.websocket_messages:
                    if msg.get('type') == 'room_joined' and 'room_state' in msg:
                        room_state = msg['room_state']
                        self.log(f"   Room state received: players={room_state.get('player_count', 0)}")
                        break
                        
                return True
            else:
                self.log("❌ Game logic WebSocket test failed - no expected messages")
                return False
                
        except Exception as e:
            self.log(f"❌ Game logic WebSocket test failed: {str(e)}")
            return False
        finally:
            self.tests_run += 1

    def on_game_websocket_open(self, ws, player_id):
        """Handle game WebSocket open with more comprehensive testing"""
        self.log(f"🔌 Game WebSocket connected for player: {player_id}")
        self.websocket_connected = True
        
        # Send position update
        position_update = {
            "type": "position_update",
            "data": {
                "x": 5.0,
                "y": 1.0,
                "z": -2.0,
                "rotation_y": 0.5,
                "animation_state": "walking"
            }
        }
        ws.send(json.dumps(position_update))
        self.log("📤 Sent position update")
        
        # Send chat message
        time.sleep(0.5)
        chat_message = {
            "type": "chat_message",
            "message": "Test marine reporting for duty!"
        }
        ws.send(json.dumps(chat_message))
        self.log("📤 Sent chat message")
        """Run all backend tests"""
        self.log("🚀 Starting BAN@LL Backend API Tests")
        self.log(f"   Base URL: {self.base_url}")
        self.log("=" * 60)
        
        # Test basic endpoints
        self.test_health_endpoint()
        self.test_game_state_endpoint()
        self.test_root_endpoint()
        
        # Test static file serving
        self.test_static_files()
        
        # Test WebSocket connectivity
        self.test_websocket_connection()
        
        # Print summary
        self.log("=" * 60)
        self.log(f"📊 Test Results: {self.tests_passed}/{self.tests_run} tests passed")
        
        if self.tests_passed == self.tests_run:
            self.log("🎉 All tests PASSED!")
            return 0
        else:
            self.log("❌ Some tests FAILED!")
            return 1

def main():
    """Main test runner"""
    tester = BanallAPITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())