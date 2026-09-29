#!/usr/bin/env python3
"""
VANGUARD Backend Concurrent Load Test
Tests multiple concurrent rooms with multiple clients to verify:
1. Room isolation (snapshots/scores don't leak across rooms)
2. Stability under concurrent load
3. Proper handling of multiple simultaneous connections
"""

import asyncio
import websockets
import json
import time
from typing import List, Dict, Any

WS_URL = "ws://localhost:8001/api/ws"

class TestClient:
    def __init__(self, name: str, room: str):
        self.name = name
        self.room = room
        self.ws = None
        self.client_id = None
        self.messages = []
        self.connected = False
        
    async def connect(self):
        """Connect to WebSocket and perform handshake"""
        try:
            self.ws = await websockets.connect(WS_URL)
            self.connected = True
            
            # Wait for hello
            hello_msg = await asyncio.wait_for(self.ws.recv(), timeout=5)
            hello = json.loads(hello_msg)
            if hello.get('t') != 'hello':
                raise Exception(f"Expected hello, got {hello}")
            self.client_id = hello.get('id')
            
            # Join room
            await self.ws.send(json.dumps({
                't': 'join',
                'room': self.room,
                'name': self.name,
                'map': 'testmap'
            }))
            
            # Wait for welcome
            welcome_msg = await asyncio.wait_for(self.ws.recv(), timeout=5)
            welcome = json.loads(welcome_msg)
            if welcome.get('t') != 'welcome':
                raise Exception(f"Expected welcome, got {welcome}")
                
            return True
        except Exception as e:
            self.connected = False
            raise Exception(f"Connection failed for {self.name}: {e}")
    
    async def listen(self, duration: float = 5.0):
        """Listen for messages for a specified duration"""
        end_time = time.time() + duration
        try:
            while time.time() < end_time and self.connected:
                try:
                    msg = await asyncio.wait_for(self.ws.recv(), timeout=0.5)
                    data = json.loads(msg)
                    self.messages.append(data)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    break
        except Exception as e:
            pass
    
    async def send_snapshot(self, position: List[float]):
        """Send a snapshot with position"""
        if self.ws and self.connected:
            await self.ws.send(json.dumps({
                't': 'snapshot',
                's': {
                    'p': position,
                    'y': 0.0,
                    'hp': 100
                }
            }))
    
    async def send_fire(self):
        """Send a fire event"""
        if self.ws and self.connected:
            await self.ws.send(json.dumps({
                't': 'fire',
                'o': [0, 0, 0],
                'd': [1, 0, 0],
                'w': 'rifle'
            }))
    
    async def close(self):
        """Close the connection"""
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
        self.connected = False


async def test_concurrent_rooms():
    """Test multiple concurrent rooms with multiple clients each"""
    print("\n=== Testing Concurrent Rooms ===")
    
    # Create 3 rooms with 3 clients each
    rooms = {
        'ROOM_A': ['Alice_A', 'Bob_A', 'Charlie_A'],
        'ROOM_B': ['Alice_B', 'Bob_B', 'Charlie_B'],
        'ROOM_C': ['Alice_C', 'Bob_C', 'Charlie_C']
    }
    
    all_clients = []
    
    # Connect all clients concurrently
    print("Connecting 9 clients across 3 rooms...")
    connect_tasks = []
    for room_code, names in rooms.items():
        for name in names:
            client = TestClient(name, room_code)
            all_clients.append(client)
            connect_tasks.append(client.connect())
    
    try:
        results = await asyncio.gather(*connect_tasks, return_exceptions=True)
        
        # Check connection results
        failed_connections = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_connections.append(f"{all_clients[i].name}: {result}")
        
        if failed_connections:
            print(f"❌ FAIL: {len(failed_connections)} clients failed to connect:")
            for fail in failed_connections:
                print(f"  - {fail}")
            return False
        
        print(f"✅ PASS: All 9 clients connected successfully")
        
        # Group clients by room
        room_clients = {}
        for client in all_clients:
            if client.room not in room_clients:
                room_clients[client.room] = []
            room_clients[client.room].append(client)
        
        # Each client sends a unique snapshot
        print("\nSending unique snapshots from each client...")
        snapshot_tasks = []
        for i, client in enumerate(all_clients):
            # Each client gets a unique position based on their index
            position = [float(i * 10), float(i * 10), float(i * 10)]
            snapshot_tasks.append(client.send_snapshot(position))
        
        await asyncio.gather(*snapshot_tasks)
        
        # Listen for messages
        print("Listening for broadcast messages...")
        listen_tasks = [client.listen(3.0) for client in all_clients]
        await asyncio.gather(*listen_tasks)
        
        # Verify room isolation
        print("\nVerifying room isolation...")
        isolation_pass = True
        
        for room_code, clients in room_clients.items():
            print(f"\n  Room {room_code}:")
            
            # Get all client IDs in this room
            room_client_ids = {c.client_id for c in clients}
            
            for client in clients:
                # Check snapshots received
                snapshots = [m for m in client.messages if m.get('t') == 'snapshot']
                
                if not snapshots:
                    print(f"    ⚠️  {client.name}: No snapshots received")
                    continue
                
                # Check if any snapshot contains IDs from other rooms
                leaked_ids = set()
                for snap in snapshots:
                    states = snap.get('states', [])
                    for state in states:
                        state_id = state.get('id')
                        if state_id and state_id not in room_client_ids:
                            leaked_ids.add(state_id)
                
                if leaked_ids:
                    print(f"    ❌ {client.name}: Received snapshots from other rooms! IDs: {leaked_ids}")
                    isolation_pass = False
                else:
                    print(f"    ✅ {client.name}: Only received snapshots from same room ({len(snapshots)} snapshots)")
        
        if isolation_pass:
            print("\n✅ PASS: Room isolation verified - no cross-room leakage")
        else:
            print("\n❌ FAIL: Room isolation broken - snapshots leaked across rooms")
        
        # Test concurrent fire events
        print("\nTesting concurrent fire events...")
        fire_tasks = [client.send_fire() for client in all_clients]
        await asyncio.gather(*fire_tasks)
        
        # Listen for fire events
        listen_tasks = [client.listen(2.0) for client in all_clients]
        await asyncio.gather(*listen_tasks)
        
        # Verify fire events are isolated
        fire_isolation_pass = True
        for room_code, clients in room_clients.items():
            room_client_ids = {c.client_id for c in clients}
            
            for client in clients:
                fire_events = [m for m in client.messages if m.get('t') == 'fire']
                
                for fire_event in fire_events:
                    fire_from = fire_event.get('from')
                    if fire_from and fire_from not in room_client_ids:
                        print(f"    ❌ {client.name} in {room_code}: Received fire from other room (ID: {fire_from})")
                        fire_isolation_pass = False
        
        if fire_isolation_pass:
            print("✅ PASS: Fire events isolated per room")
        else:
            print("❌ FAIL: Fire events leaked across rooms")
        
        # Close all connections
        print("\nClosing all connections...")
        close_tasks = [client.close() for client in all_clients]
        await asyncio.gather(*close_tasks)
        
        return isolation_pass and fire_isolation_pass
        
    except Exception as e:
        print(f"❌ FAIL: Concurrent room test error: {e}")
        # Clean up
        for client in all_clients:
            await client.close()
        return False


async def test_room_capacity():
    """Test that rooms enforce MAX_ROOM capacity"""
    print("\n=== Testing Room Capacity Enforcement ===")
    
    room_code = "CAPACITY_TEST"
    clients = []
    
    try:
        # Try to connect 13 clients (max is 12)
        print("Attempting to connect 13 clients to a single room (max=12)...")
        
        for i in range(13):
            client = TestClient(f"Player_{i+1}", room_code)
            try:
                await client.connect()
                clients.append(client)
                print(f"  Client {i+1}: Connected (ID: {client.client_id})")
            except Exception as e:
                if i >= 12:
                    print(f"  Client {i+1}: Rejected (expected) - {e}")
                else:
                    print(f"  Client {i+1}: Failed unexpectedly - {e}")
                    return False
        
        if len(clients) == 12:
            print(f"✅ PASS: Room capacity enforced - 12 clients connected, 13th rejected")
            result = True
        elif len(clients) > 12:
            print(f"❌ FAIL: Room capacity NOT enforced - {len(clients)} clients connected (max should be 12)")
            result = False
        else:
            print(f"❌ FAIL: Only {len(clients)} clients connected (expected 12)")
            result = False
        
        # Clean up
        for client in clients:
            await client.close()
        
        return result
        
    except Exception as e:
        print(f"❌ FAIL: Capacity test error: {e}")
        for client in clients:
            await client.close()
        return False


async def test_cors_and_origin():
    """Test CORS and origin handling"""
    print("\n=== Testing CORS and Origin Handling ===")
    
    # Test WebSocket with custom origin header
    custom_origins = [
        "https://vanguardfps.xyz",
        "https://custom-domain.com",
        "http://localhost:3000"
    ]
    
    all_pass = True
    
    for origin in custom_origins:
        try:
            # WebSocket connection with custom origin
            ws = await websockets.connect(
                WS_URL,
                extra_headers={"Origin": origin}
            )
            
            # Wait for hello
            hello_msg = await asyncio.wait_for(ws.recv(), timeout=5)
            hello = json.loads(hello_msg)
            
            if hello.get('t') == 'hello':
                print(f"  ✅ Origin '{origin}': Accepted")
            else:
                print(f"  ❌ Origin '{origin}': Unexpected response")
                all_pass = False
            
            await ws.close()
            
        except Exception as e:
            print(f"  ❌ Origin '{origin}': Rejected - {e}")
            all_pass = False
    
    if all_pass:
        print("✅ PASS: All origins accepted (CORS configured correctly)")
    else:
        print("❌ FAIL: Some origins rejected")
    
    return all_pass


async def main():
    """Run all backend tests"""
    print("=" * 60)
    print("VANGUARD Backend Concurrent Load Test")
    print("=" * 60)
    
    results = {}
    
    # Test 1: Concurrent rooms
    results['concurrent_rooms'] = await test_concurrent_rooms()
    
    # Test 2: Room capacity
    results['room_capacity'] = await test_room_capacity()
    
    # Test 3: CORS and origin
    results['cors_origin'] = await test_cors_and_origin()
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(results.values())
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ ALL TESTS PASSED - Backend is production-ready")
    else:
        print("❌ SOME TESTS FAILED - Review failures above")
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)
