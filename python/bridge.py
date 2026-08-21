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
from datetime import datetime
from typing import Set, Dict, Any

# Configuration
SERIAL_BAUD = 115200
WEBSOCKET_PORT = 8080
SERIAL_TIMEOUT = 1.0
RECONNECT_DELAY = 5.0

# Connected WebSocket clients
connected_clients: Set[websockets.WebSocketServerProtocol] = set()

# Latest node data cache
node_data: Dict[int, Dict[str, Any]] = {}

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
                print("[BRIDGE] ERROR: No ESP32 device found. Available ports:")
                for port in serial.tools.list_ports.comports():
                    print(f"  - {port.device}: {port.description}")
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
            return True
            
        except serial.SerialException as e:
            print(f"[BRIDGE] ERROR: Failed to connect: {e}")
            return False
    
    def disconnect(self):
        """Close serial connection"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print("[BRIDGE] Serial connection closed")
    
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
        print(f"[WS] Client disconnected: {client_addr}")


async def main():
    """Main application entry point"""
    print("=" * 60)
    print("ESP32-S3 Federated Learning Bridge")
    print("=" * 60)
    
    # Start serial reader
    serial_reader = SerialReader()
    serial_task = asyncio.create_task(serial_reader.read_loop())
    
    # Start WebSocket server
    print(f"[WS] Starting WebSocket server on port {WEBSOCKET_PORT}...")
    
    async with websockets.serve(websocket_handler, "localhost", WEBSOCKET_PORT):
        print(f"[WS] WebSocket server running on ws://localhost:{WEBSOCKET_PORT}")
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
