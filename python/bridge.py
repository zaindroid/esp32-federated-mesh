#!/usr/bin/env python3
"""
ESP32-S3 Federated Learning Bridge
Reads serial data from ESP32-S3 nodes and broadcasts via WebSocket
"""

import serial
import serial.tools.list_ports
import json
import asyncio
import websockets
import re
import time
import os
from datetime import datetime
from typing import Set, Dict, Any
from aiohttp import web

# Configuration
SERIAL_BAUD = 115200
WEBSOCKET_PORT = int(os.getenv('PORT', 8080))
SERIAL_PORT = os.getenv('SERIAL_PORT', None)
SERIAL_TIMEOUT = 1.0
RECONNECT_DELAY = 5.0
APP_VERSION = os.getenv('APP_VERSION', 'dev')
BUILD_SHA = os.getenv('BUILD_SHA', 'unknown')

# Connected WebSocket clients
connected_clients: Set[websockets.WebSocketServerProtocol] = set()

# Latest node data cache
node_data: Dict[int, Dict[str, Any]] = {}

# Health status
health_status = {
    'serial_connected': False,
    'last_data_time': None,
    'clients_connected': 0
}

class SerialReader:
    def __init__(self, port: str = None, baud: int = SERIAL_BAUD):
        self.port = port
        self.baud = baud
        self.serial_conn = None
        self.running = False
        
    def find_esp32_port(self) -> str:
        """Auto-detect ESP32-S3 serial port"""
        ports = serial.tools.list_ports.comports()
        for port in ports:
            # Look for common ESP32 USB identifiers
            if any(x in port.description.lower() for x in ['cp210', 'ch340', 'usb-serial', 'uart', 'esp32']):
                print(f"[BRIDGE] Found ESP32 device: {port.device} - {port.description}")
                return port.device
        return None
    
    def connect(self) -> bool:
        """Establish serial connection"""
        try:
            if not self.port:
                self.port = self.find_esp32_port()
                
            if not self.port:
                print("[BRIDGE] WARNING: No ESP32 device found. Available ports:")
                for port in serial.tools.list_ports.comports():
                    print(f"  - {port.device}: {port.description}")
                print("[BRIDGE] Running in mock mode - health checks will work, but no real data")
                health_status['serial_connected'] = False
                return False
            
            print(f"[BRIDGE] Connecting to {self.port} at {self.baud} baud...")
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=SERIAL_TIMEOUT
            )
            
            # Flush buffers
            self.serial_conn.reset_input_buffer()
            self.serial_conn.reset_output_buffer()
            
            print(f"[BRIDGE] Connected to {self.port}")
            health_status['serial_connected'] = True
            return True
            
        except serial.SerialException as e:
            print(f"[BRIDGE] ERROR: Failed to connect: {e}")
            health_status['serial_connected'] = False
            return False
    
    def disconnect(self):
        """Close serial connection"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print("[BRIDGE] Serial connection closed")
        health_status['serial_connected'] = False
    
    def parse_log_line(self, line: str) -> Dict[str, Any]:
        """Parse ESP32 serial log line and extract telemetry"""
        data = {}
        
        # Extract node ID
        node_match = re.search(r'\[NODE (\d+)\]', line)
        if node_match:
            data['node_id'] = int(node_match.group(1))
        else:
            return None
        
        # Extract loss
        loss_match = re.search(r'LOSS:\s*([\d.]+)', line)
        if loss_match:
            data['loss'] = float(loss_match.group(1))
        
        # Extract anomaly score
        anomaly_match = re.search(r'ANOMALY:\s*([\d.]+)', line)
        if anomaly_match:
            data['anomaly'] = float(anomaly_match.group(1))
        
        # Detect mesh sync events
        if 'MESH SYNC' in line or 'MESH BROADCAST' in line:
            data['mesh_event'] = True
            
            # Try to extract peer node ID
            peer_match = re.search(r'from Node (\d+)', line)
            if peer_match:
                data['peer_node_id'] = int(peer_match.group(1))
        
        # Detect anomaly alerts
        if 'ANOMALY DETECTED' in line:
            data['alert'] = 'anomaly_detected'
            anomaly_value = re.search(r'DETECTED:\s*([\d.]+)', line)
            if anomaly_value:
                data['anomaly'] = float(anomaly_value.group(1))
        
        return data if data else None
    
    async def read_loop(self):
        """Main serial reading loop"""
        self.running = True
        
        while self.running:
            try:
                if not self.serial_conn or not self.serial_conn.is_open:
                    print("[BRIDGE] Attempting to reconnect...")
                    if self.connect():
                        await asyncio.sleep(2)  # Wait for ESP32 to stabilize
                    else:
                        await asyncio.sleep(RECONNECT_DELAY)
                        continue
                
                # Read line from serial
                if self.serial_conn.in_waiting > 0:
                    line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    
                    if line:
                        # Print to console
                        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
                        print(f"[{timestamp}] {line}")
                        
                        # Parse and broadcast
                        parsed_data = self.parse_log_line(line)
                        if parsed_data:
                            health_status['last_data_time'] = time.time()
                            await self.broadcast_telemetry(parsed_data)
                
                await asyncio.sleep(0.01)  # Small delay to prevent CPU thrashing
                
            except serial.SerialException as e:
                print(f"[BRIDGE] Serial error: {e}")
                self.disconnect()
                await asyncio.sleep(RECONNECT_DELAY)
                
            except Exception as e:
                print(f"[BRIDGE] Unexpected error: {e}")
                await asyncio.sleep(1)
    
    async def broadcast_telemetry(self, data: Dict[str, Any]):
        """Broadcast telemetry to all connected WebSocket clients"""
        if not data or 'node_id' not in data:
            return
        
        node_id = data['node_id']
        
        # Update cache
        if node_id not in node_data:
            node_data[node_id] = {}
        node_data[node_id].update(data)
        node_data[node_id]['timestamp'] = time.time()
        
        # Prepare message
        message = {
            'type': 'telemetry',
            'timestamp': time.time(),
            **data
        }
        
        # Send to all connected clients
        if connected_clients:
            message_json = json.dumps(message)
            disconnected = set()
            
            for client in connected_clients:
                try:
                    await client.send(message_json)
                except websockets.exceptions.ConnectionClosed:
                    disconnected.add(client)
                except Exception as e:
                    print(f"[BRIDGE] Error sending to client: {e}")
                    disconnected.add(client)
            
            # Remove disconnected clients
            for client in disconnected:
                connected_clients.discard(client)
    
    def stop(self):
        """Stop the serial reader"""
        self.running = False
        self.disconnect()


async def websocket_handler(websocket, path):
    """Handle WebSocket connections"""
    client_addr = websocket.remote_address
    print(f"[WS] Client connected: {client_addr}")
    
    connected_clients.add(websocket)
    health_status['clients_connected'] = len(connected_clients)
    
    try:
        # Send current state to new client
        for node_id, data in node_data.items():
            welcome_msg = {
                'type': 'telemetry',
                'timestamp': time.time(),
                **data
            }
            await websocket.send(json.dumps(welcome_msg))
        
        # Keep connection alive
        async for message in websocket:
            # Echo back for ping/pong
            if message == "ping":
                await websocket.send("pong")
    
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
    # For this app, we're ready even without serial connection
    # (it can run in mock mode)
    return web.json_response({
        'status': 'ready',
        'serial_connected': health_status['serial_connected'],
        'clients_connected': health_status['clients_connected']
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
            'description': 'WebSocket bridge for ESP32-S3 federated learning telemetry'
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
    print("ESP32-S3 Federated Learning Bridge")
    print(f"Version: {APP_VERSION}")
    print("=" * 60)
    
    # Validate required env vars
    if not SERIAL_PORT:
        print("[BRIDGE] WARNING: SERIAL_PORT env var not set, will auto-detect")
    
    # Start HTTP server for health checks
    await start_http_server()
    
    # Start serial reader
    serial_reader = SerialReader(port=SERIAL_PORT)
    serial_task = asyncio.create_task(serial_reader.read_loop())
    
    # Start WebSocket server on same port (will handle upgrade)
    print(f"[WS] Starting WebSocket server on port {WEBSOCKET_PORT}...")
    
    async with websockets.serve(websocket_handler, "0.0.0.0", WEBSOCKET_PORT + 1):
        print(f"[WS] WebSocket server running on ws://0.0.0.0:{WEBSOCKET_PORT + 1}")
        print(f"[BRIDGE] Ready to bridge ESP32-S3 telemetry to web clients")
        print()
        
        # Run forever
        try:
            await serial_task
        except KeyboardInterrupt:
            print("\n[BRIDGE] Shutting down...")
            serial_reader.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[BRIDGE] Stopped by user")
