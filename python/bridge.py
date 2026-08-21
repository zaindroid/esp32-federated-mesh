#!/usr/bin/env python3
"""
ESP32-S3 Federated Learning Bridge
WebSocket relay server - receives telemetry from web clients and broadcasts to all
"""

import json
import asyncio
import websockets
import time
import os
from datetime import datetime
from typing import Set, Dict, Any
from aiohttp import web

# Configuration
WEBSOCKET_PORT = int(os.getenv('PORT', 8080))
APP_VERSION = os.getenv('APP_VERSION', 'dev')
BUILD_SHA = os.getenv('BUILD_SHA', 'unknown')

# Connected WebSocket clients
connected_clients: Set[websockets.WebSocketServerProtocol] = set()

# Latest node data cache
node_data: Dict[int, Dict[str, Any]] = {}

# Health status
health_status = {
    'clients_connected': 0,
    'nodes_seen': 0,
    'last_data_time': None
}


async def websocket_handler(websocket, path):
    """Handle WebSocket connections"""
    client_addr = websocket.remote_address
    print(f"[WS] Client connected: {client_addr}")
    
    connected_clients.add(websocket)
    health_status['clients_connected'] = len(connected_clients)
    
    try:
        # Send current state to new client
        if node_data:
            for node_id, data in node_data.items():
                welcome_msg = {
                    'type': 'telemetry',
                    'timestamp': time.time(),
                    **data
                }
                await websocket.send(json.dumps(welcome_msg))
            print(f"[WS] Sent {len(node_data)} cached nodes to new client")
        
        # Listen for messages from client
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Handle ping/pong
                if data.get('type') == 'ping':
                    await websocket.send(json.dumps({'type': 'pong'}))
                    continue
                
                # Handle telemetry from client
                if data.get('type') == 'telemetry' and 'node_id' in data:
                    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                    print(f"[{timestamp}] Telemetry from Node {data['node_id']}: {data}")
                    
                    # Update cache
                    node_id = data['node_id']
                    if node_id not in node_data:
                        node_data[node_id] = {}
                    node_data[node_id].update(data)
                    node_data[node_id]['timestamp'] = time.time()
                    
                    health_status['nodes_seen'] = len(node_data)
                    health_status['last_data_time'] = time.time()
                    
                    # Broadcast to all other clients
                    message_json = json.dumps(data)
                    disconnected = set()
                    
                    for client in connected_clients:
                        if client != websocket:  # Don't echo back to sender
                            try:
                                await client.send(message_json)
                            except websockets.exceptions.ConnectionClosed:
                                disconnected.add(client)
                            except Exception as e:
                                print(f"[WS] Error broadcasting: {e}")
                                disconnected.add(client)
                    
                    # Remove disconnected clients
                    for client in disconnected:
                        connected_clients.discard(client)
                        health_status['clients_connected'] = len(connected_clients)
                        
            except json.JSONDecodeError:
                print(f"[WS] Invalid JSON from {client_addr}: {message[:100]}")
            except Exception as e:
                print(f"[WS] Error processing message: {e}")
    
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"[WS] Error: {e}")
    finally:
        connected_clients.discard(websocket)
        health_status['clients_connected'] = len(connected_clients)
        print(f"[WS] Client disconnected: {client_addr}")


# HTTP endpoints for health checks
async def health_handler(request):
    """Health check endpoint - must be fast and not touch database"""
    return web.json_response({'status': 'ok'})

async def ready_handler(request):
    """Readiness check - verifies dependencies"""
    return web.json_response({
        'status': 'ready',
        'clients_connected': health_status['clients_connected'],
        'nodes_seen': health_status['nodes_seen']
    })

async def version_handler(request):
    """Version endpoint"""
    return web.json_response({
        'version': APP_VERSION,
        'sha': BUILD_SHA,
        'built': datetime.now().isoformat()
    })

async def openapi_handler(request):
    """OpenAPI spec endpoint"""
    spec = {
        'openapi': '3.0.0',
        'info': {
            'title': 'ESP32 Federated Learning Bridge',
            'version': APP_VERSION,
            'description': 'WebSocket relay for ESP32-S3 federated learning telemetry'
        },
        'paths': {
            '/health': {
                'get': {
                    'summary': 'Health check',
                    'responses': {'200': {'description': 'Service is healthy'}}
                }
            },
            '/ready': {
                'get': {
                    'summary': 'Readiness check',
                    'responses': {'200': {'description': 'Service is ready'}}
                }
            },
            '/version': {
                'get': {
                    'summary': 'Version information',
                    'responses': {'200': {'description': 'Version and build info'}}
                }
            }
        }
    }
    return web.json_response(spec)

async def index_handler(request):
    """Serve the web dashboard"""
    try:
        with open('web/index.html', 'r') as f:
            return web.Response(text=f.read(), content_type='text/html')
    except FileNotFoundError:
        return web.Response(text='Dashboard not found', status=404)


async def start_http_server():
    """Start HTTP server for health checks and static files"""
    app = web.Application()
    app.router.add_get('/health', health_handler)
    app.router.add_get('/ready', ready_handler)
    app.router.add_get('/version', version_handler)
    app.router.add_get('/openapi.json', openapi_handler)
    app.router.add_get('/', index_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', WEBSOCKET_PORT)
    await site.start()
    print(f"[HTTP] Server running on http://0.0.0.0:{WEBSOCKET_PORT}")


async def main():
    """Main application entry point"""
    print("=" * 60)
    print("ESP32-S3 Federated Learning Bridge (WebSocket Relay)")
    print(f"Version: {APP_VERSION}")
    print("=" * 60)
    
    # Start HTTP server for health checks
    await start_http_server()
    
    # Start WebSocket server
    print(f"[WS] Starting WebSocket server on port {WEBSOCKET_PORT + 1}...")
    
    async with websockets.serve(websocket_handler, "0.0.0.0", WEBSOCKET_PORT + 1):
        print(f"[WS] WebSocket server running on ws://0.0.0.0:{WEBSOCKET_PORT + 1}")
        print(f"[BRIDGE] Ready to relay ESP32-S3 telemetry between clients")
        print()
        
        # Run forever
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[BRIDGE] Stopped by user")
