#!/usr/bin/env python3
"""
WebSocket Server for Lightning Network Simulation

This script creates a WebSocket server that allows real-time
communication between the simulation and ML model.
"""

import asyncio
import websockets
import json
import time
from datetime import datetime

# Store connected clients
connected = set()
# Store network state
network_state = {
    "channels": {},
    "transactions": [],
    "last_update": None
}

async def register(websocket):
    """Register a new client"""
    connected.add(websocket)
    # Send current state to new client
    await websocket.send(json.dumps({
        "type": "state_update",
        "data": network_state
    }))

async def unregister(websocket):
    """Unregister a client"""
    connected.remove(websocket)

async def broadcast_update(update):
    """Broadcast an update to all connected clients"""
    if connected:
        await asyncio.gather(
            *[client.send(json.dumps(update)) for client in connected]
        )

async def handle_message(websocket, message):
    """Handle incoming messages"""
    data = json.loads(message)
    
    if data["type"] == "channel_update":
        network_state["channels"] = data["channels"]
        network_state["last_update"] = datetime.now().isoformat()
        # Broadcast to all clients
        await broadcast_update({
            "type": "channel_update",
            "data": data["channels"]
        })
    
    elif data["type"] == "transaction":
        network_state["transactions"].append(data["transaction"])
        # Keep only the last 100 transactions
        if len(network_state["transactions"]) > 100:
            network_state["transactions"] = network_state["transactions"][-100:]
        # Broadcast to all clients
        await broadcast_update({
            "type": "transaction",
            "data": data["transaction"]
        })
    
    elif data["type"] == "rebalance_suggestion":
        # Broadcast suggestion to all clients
        await broadcast_update({
            "type": "rebalance_suggestion",
            "data": data["suggestion"]
        })

async def server(websocket, path):
    """Handle WebSocket connections"""
    await register(websocket)
    try:
        async for message in websocket:
            await handle_message(websocket, message)
    finally:
        await unregister(websocket)

def start_websocket_server():
    """Start the WebSocket server"""
    return websockets.serve(server, "0.0.0.0", 6789)

if __name__ == "__main__":
    # Modern way to handle asyncio event loops
    async def main():
        server = await start_websocket_server()
        print("WebSocket server started at ws://localhost:6789")
        # Keep the server running
        await asyncio.Future()  # Run forever
    
    # Run the async main function with cleaner exit
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nWebSocket server stopped") 