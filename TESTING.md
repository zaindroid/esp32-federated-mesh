# Test Suite for ESP32-S3 Federated Learning Mesh

This document describes how to validate the system works correctly.

## Pre-Flight Checks

### Hardware Test
```bash
# Check if PlatformIO can detect your board
pio device list

# Expected output should show your COM port:
# COM3
#   Hardware ID: USB VID:PID=1A86:7523
#   Description: USB-SERIAL CH340
```

### Firmware Compilation Test
```bash
cd C:/Users/zain_/esp32_federated_mesh

# Build without flashing
pio run

# Should complete with:
# SUCCESS
# RAM:   [===       ]  XX.X% (used XXXXX bytes)
# Flash: [===       ]  XX.X% (used XXXXX bytes)
```

## Unit Tests

### 1. ESP-NOW Mesh Packet Test

**Test**: Verify packet structure fits in 250 bytes
```cpp
// In src/main.cpp, add to setup():
Serial.printf("MeshPacket size: %d bytes\n", sizeof(MeshPacket));
// Expected: 68 bytes (well under 250 byte limit)
```

### 2. Neural Network Memory Test

**Test**: Verify model fits in RAM
```cpp
// Already in main.cpp setup():
Serial.printf("Model Memory: %d bytes\n", model.get_memory_usage());
// Expected: < 1000 bytes
```

### 3. Training Loop Test

**Test**: Single node training converges
1. Flash ONE board with NODE_ID=1
2. Monitor serial for 60 seconds
3. Verify LOSS decreases from ~0.5 to <0.1

**Expected Log Pattern**:
```
[NODE 1] STEP 0 | LOSS: 0.4523 | ANOMALY: 0.23 | TARGET: 0.0
[NODE 1] STEP 10 | LOSS: 0.3821 | ANOMALY: 0.18 | TARGET: 0.0
[NODE 1] STEP 100 | LOSS: 0.1234 | ANOMALY: 0.09 | TARGET: 0.0
```

✅ **PASS**: Loss < 0.2 after 100 steps
❌ **FAIL**: Loss stays > 0.4 (check learning rate)

### 4. Anomaly Detection Test

**Test**: Model detects injected anomalies
1. Wait for 30 seconds (anomaly injection phase)
2. Watch for "ANOMALY DETECTED" messages

**Expected**:
```
[NODE 1] *** ANOMALY DETECTED: 0.95 ***
```

✅ **PASS**: Anomaly score > 0.7 during injection phase
❌ **FAIL**: Never detects anomalies (check threshold)

### 5. ESP-NOW Broadcast Test

**Test**: Node successfully broadcasts
1. Monitor serial
2. Wait 15 seconds

**Expected**:
```
[NODE 1] MESH BROADCAST: Sent weights
```

✅ **PASS**: Broadcast message appears every 15 seconds
❌ **FAIL**: "MESH BROADCAST FAILED" (check WiFi init)

### 6. Mesh Reception Test (2+ Boards)

**Test**: Nodes communicate via ESP-NOW
1. Flash 2 boards with NODE_ID=1 and NODE_ID=2
2. Power both simultaneously
3. Monitor both serial ports
4. Wait 15 seconds

**Expected on Node 1**:
```
[NODE 1] MESH SYNC: Received weights from Node 2
[NODE 1] MESH SYNC: Applied federated averaging
```

**Expected on Node 2**:
```
[NODE 2] MESH SYNC: Received weights from Node 1
[NODE 2] MESH SYNC: Applied federated averaging
```

✅ **PASS**: Both nodes receive from each other
❌ **FAIL**: No reception (check proximity, power, MAC addresses)

### 7. Federated Averaging Test

**Test**: Weights converge across nodes
1. Flash 2 boards with different random seeds
2. Let them train independently for 30 seconds
3. Enable mesh sync
4. Watch loss values converge

**Method**: Extract weights manually and compare
```cpp
// Add to main.cpp after mesh sync:
float weights[12];
model.get_weights(weights);
Serial.printf("[DEBUG] Weights: [%.3f, %.3f, %.3f, ...]\n", 
              weights[0], weights[1], weights[2]);
```

✅ **PASS**: Weights become similar across nodes (±10%)
❌ **FAIL**: Weights diverge (check averaging logic)

## Integration Tests

### 8. Python Bridge Test

**Test**: Bridge parses serial and serves WebSocket

**Step 1**: Test serial connection
```bash
cd python
python bridge.py
```

**Expected**:
```
[BRIDGE] Found ESP32 device: COM3
[BRIDGE] Connected to COM3
[WS] WebSocket server running on ws://localhost:8080
```

**Step 2**: Verify parsing
- Should print timestamped ESP32 logs
- Look for parsed telemetry in console

✅ **PASS**: Logs stream with timestamps, WebSocket server running
❌ **FAIL**: "No ESP32 device found" (check port, drivers)

### 9. WebSocket Communication Test

**Test**: Web dashboard receives data

**Method 1**: Browser console
1. Open `web/index.html`
2. Press F12 (open DevTools)
3. Go to Console tab
4. Look for WebSocket messages

**Expected**:
```javascript
WebSocket connected
{type: "telemetry", node_id: 1, loss: 0.0345, anomaly: 0.12, ...}
```

**Method 2**: Python WebSocket client
```python
import asyncio
import websockets
import json

async def test():
    async with websockets.connect('ws://localhost:8080') as ws:
        for _ in range(10):
            msg = await ws.recv()
            print(json.loads(msg))

asyncio.run(test())
```

✅ **PASS**: Telemetry messages received
❌ **FAIL**: Connection refused (verify bridge is running)

### 10. Visualization Test

**Test**: Dashboard displays live data

**Checklist**:
- [ ] 3 cubes visible and rotating
- [ ] Cubes change color (green/yellow/red)
- [ ] Loss values update on labels
- [ ] Info panel shows node statistics
- [ ] Connection status shows "Connected"
- [ ] Glowing arcs appear during mesh sync
- [ ] Mesh event notifications appear at bottom

✅ **PASS**: All elements working
❌ **FAIL**: Static display (check WebSocket, browser console)

## System Tests

### 11. End-to-End Test (Full Stack)

**Test**: Complete system working together

**Setup**:
1. 3x ESP32-S3 boards flashed (NODE_ID 1, 2, 3)
2. Python bridge running
3. Web dashboard open

**Test Sequence**:

**T+0s**: Power all boards
- [ ] All nodes initialize
- [ ] Serial logs start streaming
- [ ] Bridge connects to one hub node
- [ ] Dashboard shows 3 green cubes

**T+15s**: First mesh sync
- [ ] Serial: "MESH BROADCAST" on all nodes
- [ ] Serial: "MESH SYNC: Received weights" on all nodes
- [ ] Dashboard: Glowing arcs between cubes
- [ ] Dashboard: Notification "FEDERATED SYNC"

**T+30s**: First anomaly injection
- [ ] Serial: "ANOMALY DETECTED" on all nodes
- [ ] Dashboard: Cubes turn RED
- [ ] Info panel: Status changes to "ANOMALY"
- [ ] Cubes pulse/vibrate

**T+35s**: Anomaly ends
- [ ] Serial: "System returned to normal"
- [ ] Dashboard: Cubes turn GREEN
- [ ] Loss decreases back to <0.1

**T+5min**: Convergence check
- [ ] All nodes: Loss < 0.05 on normal data
- [ ] Consistent anomaly detection across nodes
- [ ] Regular mesh syncs every 15s

✅ **PASS**: All checkpoints passed
❌ **FAIL**: Document which step failed

### 12. Resilience Test

**Test**: System handles node failure

**Procedure**:
1. Start with 3 nodes running
2. Unplug Node 2 (simulate failure)
3. Verify Nodes 1 and 3 continue operating
4. Replug Node 2
5. Verify it rejoins mesh

**Expected**:
- Remaining nodes continue training
- Mesh syncs continue between active nodes
- Rejoined node receives weights and catches up

✅ **PASS**: Graceful degradation and recovery
❌ **FAIL**: Crash or deadlock

### 13. Performance Test

**Test**: System meets performance targets

**Metrics**:
```bash
# Monitor for 5 minutes and record:
```

| Metric | Target | Actual | Pass? |
|--------|--------|--------|-------|
| Training speed | >50 steps/s | ___ | ☐ |
| Inference latency | <10ms | ___ | ☐ |
| Mesh sync time | <100ms | ___ | ☐ |
| Dashboard FPS | >30 | ___ | ☐ |
| RAM usage | <100KB | ___ | ☐ |
| Power per node | <200mA | ___ | ☐ |

**How to measure**:
- **Training speed**: Count steps in serial log over 10 seconds
- **Mesh sync time**: Time between "BROADCAST" and "SYNC" messages
- **Dashboard FPS**: Chrome DevTools → Rendering → Frame Rendering Stats
- **RAM usage**: Check PlatformIO build output
- **Power**: Multimeter in series with USB power line

## Automated Test Script

Save as `test_system.py`:

```python
#!/usr/bin/env python3
"""Automated system validation"""

import serial
import time
import re

def test_node(port, node_id, duration=60):
    """Test a single node for convergence"""
    print(f"\n=== Testing Node {node_id} on {port} ===")
    
    ser = serial.Serial(port, 115200, timeout=1)
    time.sleep(2)  # Wait for init
    
    start_time = time.time()
    losses = []
    anomalies_detected = 0
    mesh_syncs = 0
    
    while time.time() - start_time < duration:
        line = ser.readline().decode('utf-8', errors='ignore').strip()
        
        # Parse loss
        loss_match = re.search(r'LOSS:\s*([\d.]+)', line)
        if loss_match:
            losses.append(float(loss_match.group(1)))
        
        # Count anomalies
        if 'ANOMALY DETECTED' in line:
            anomalies_detected += 1
        
        # Count mesh syncs
        if 'MESH SYNC' in line:
            mesh_syncs += 1
    
    ser.close()
    
    # Validate
    print(f"Losses collected: {len(losses)}")
    print(f"Initial loss: {losses[0]:.4f}")
    print(f"Final loss: {losses[-1]:.4f}")
    print(f"Anomalies detected: {anomalies_detected}")
    print(f"Mesh syncs: {mesh_syncs}")
    
    # Pass criteria
    convergence = losses[-1] < 0.2
    anomaly_detection = anomalies_detected > 0
    mesh_active = mesh_syncs > 0
    
    print(f"\n✅ Convergence: {convergence}")
    print(f"✅ Anomaly detection: {anomaly_detection}")
    print(f"✅ Mesh active: {mesh_active}")
    
    return convergence and anomaly_detection and mesh_active

if __name__ == "__main__":
    # Test Node 1
    result = test_node("COM3", 1, duration=60)
    
    if result:
        print("\n🎉 ALL TESTS PASSED")
    else:
        print("\n❌ TESTS FAILED")
```

Run with:
```bash
python test_system.py
```

## Troubleshooting Failed Tests

### Test 3 Fails (Training doesn't converge)
- Check learning rate (try 0.01)
- Verify forward/backward pass logic
- Ensure random seed is set

### Test 5 Fails (Broadcast fails)
- Verify WiFi.mode(WIFI_STA) called
- Check esp_now_init() return code
- Ensure broadcast peer added

### Test 6 Fails (No mesh reception)
- Check boards are within range (<10m)
- Verify different NODE_IDs
- Check callback registration
- Review MAC addresses (print in setup)

### Test 8 Fails (Bridge connection issues)
- Install USB drivers
- Check port permissions (Linux: add to dialout group)
- Verify pyserial installed
- Try manual port specification

### Test 11 Fails (End-to-end issues)
- Test each component individually first
- Check all processes are running
- Verify network ports not blocked by firewall
- Review browser console for errors

---

**Testing Checklist Complete**: Run all tests before deploying to production!
