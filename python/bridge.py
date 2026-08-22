#!/usr/bin/env python3
"""
ESP32-S3 Federated Learning Bridge
Relay server for broadcasting telemetry between browser clients
"""

import asyncio
import json
import os
from datetime import datetime
from aiohttp import web
import aiohttp

# Configuration
HTTP_PORT = int(os.getenv('PORT', 8080))
APP_VERSION = os.getenv('APP_VERSION', 'dev')
BUILD_SHA = os.getenv('BUILD_SHA', 'unknown')

# Connected WebSocket clients
clients = set()

# Startup time for health checks
startup_time = datetime.utcnow()


def find_web_dir():
    """Find the web directory in different deployment scenarios"""
    # Get the directory containing this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Scenario 1: Docker container (/app/bridge.py, web at /app/web/)
    web_dir = os.path.join(script_dir, 'web')
    if os.path.exists(web_dir):
        return web_dir
    
    # Scenario 2: Development (python/bridge.py, web at ../web/)
    web_dir = os.path.join(os.path.dirname(script_dir), 'web')
    if os.path.exists(web_dir):
        return web_dir
    
    # Not found
    raise FileNotFoundError(f"Could not find web directory. Searched: {script_dir}/web and {os.path.dirname(script_dir)}/web")


async def health_handler(request):
    """Health check endpoint for load balancer"""
    uptime_seconds = (datetime.utcnow() - startup_time).total_seconds()
    
    health_data = {
        "status": "healthy",
        "service": "esp32-federated-bridge",
        "version": APP_VERSION,
        "build": BUILD_SHA,
        "uptime_seconds": uptime_seconds,
        "connected_clients": len(clients),
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return web.json_response(health_data)


async def websocket_handler(request):
    """Handle WebSocket connections from browser clients"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    clients.add(ws)
    print(f"[WS] Client connected. Total clients: {len(clients)}")
    
    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    
                    # Broadcast telemetry to all other clients
                    if data.get('type') == 'telemetry':
                        print(f"[RELAY] Broadcasting telemetry from node {data.get('node_id', 'unknown')}")
                        
                        # Send to all clients except sender
                        for client in clients:
                            if client != ws and not client.closed:
                                try:
                                    await client.send_str(msg.data)
                                except Exception as e:
                                    print(f"[ERROR] Failed to send to client: {e}")
                
                except json.JSONDecodeError:
                    print(f"[ERROR] Invalid JSON received")
                except Exception as e:
                    print(f"[ERROR] Error processing message: {e}")
            
            elif msg.type == aiohttp.WSMsgType.ERROR:
                print(f"[WS] Connection error: {ws.exception()}")
    
    finally:
        clients.discard(ws)
        print(f"[WS] Client disconnected. Total clients: {len(clients)}")
    
    return ws


async def index_handler(request):
    """Serve the dashboard HTML"""
    web_dir = find_web_dir()
    index_path = os.path.join(web_dir, 'index.html')
    return web.FileResponse(index_path)


async def flasher_handler(request):
    """Serve the firmware flasher HTML"""
    web_dir = find_web_dir()
    flasher_path = os.path.join(web_dir, 'flasher.html')
    return web.FileResponse(flasher_path)


async def on_startup(app):
    """Print startup banner"""
    print()
    print("=" * 70)
    print("ESP32-S3 Federated Learning Bridge")
    print("=" * 70)
    print(f"Version: {APP_VERSION}")
    print(f"Build: {BUILD_SHA}")
    print(f"HTTP/WebSocket Port: {HTTP_PORT}")
    print()
    print("Endpoints:")
    print(f"  Dashboard:   http://0.0.0.0:{HTTP_PORT}/")
    print(f"  Health:      http://0.0.0.0:{HTTP_PORT}/health")
    print(f"  WebSocket:   ws://0.0.0.0:{HTTP_PORT}/ws")
    print()
    print(f"Web directory: {find_web_dir()}")
    print()
    print("Ready to relay telemetry between browser clients")
    print("=" * 70)
    print()


async def on_cleanup(app):
    """Cleanup on shutdown"""
    print("\n[SHUTDOWN] Closing all WebSocket connections...")
    for ws in clients:
        await ws.close()
    clients.clear()


def create_app():
    """Create and configure the aiohttp application"""
    app = web.Application()
    
    # Routes
    app.router.add_get('/', index_handler)
    app.router.add_get('/flasher.html', flasher_handler)
    app.router.add_get('/health', health_handler)
    app.router.add_get('/ws', websocket_handler)
    
    # Static files
    web_dir = find_web_dir()
    app.router.add_static('/static', web_dir, name='static')
    
    # Lifecycle hooks
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    return app


if __name__ == '__main__':
    app = create_app()
    web.run_app(app, host='0.0.0.0', port=HTTP_PORT)
