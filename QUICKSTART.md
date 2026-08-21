# Quick Start Guide - ESP32-S3 Federated Mesh

Get your federated learning mesh running in 10 minutes!

## ⚡ Prerequisites Check

- [ ] ESP32-S3-DevKitC-1 board(s) (1-3 units)
- [ ] USB cables
- [ ] VS Code with PlatformIO extension OR PlatformIO CLI
- [ ] Python 3.7+
- [ ] Modern web browser

---

## 📋 Step-by-Step Setup

### 1. Install PlatformIO (5 minutes)

**Option A: VS Code Extension (Recommended)**
1. Open VS Code
2. Go to Extensions (Ctrl+Shift+X)
3. Search "PlatformIO IDE"
4. Click Install
5. Restart VS Code

**Option B: CLI Only**
```bash
pip install platformio
```

### 2. Install Python Dependencies (1 minute)

```bash
cd C:/Users/zain_/esp32_federated_mesh/python
pip install pyserial websockets
```

### 3. Configure Your Board (1 minute)

**Find your COM port:**

Windows - Device Manager:
- Open Device Manager
- Expand "Ports (COM & LPT)"
- Look for "USB-SERIAL" or "CP210x" → Note the COM number (e.g., COM3)

Or use PowerShell:
```powershell
Get-WmiObject Win32_SerialPort | Select-Object DeviceID,Description
```

**Edit platformio.ini:**
```ini
upload_port = COM3  ; Change to your port!
```

**Set Node ID (repeat for each board):**

Edit `src/main.cpp` line 6:
```cpp
#define NODE_ID 1  ; Change to 1, 2, or 3
```

### 4. Compile & Flash (2 minutes per board)

**VS Code:**
1. Open project folder
2. Click PlatformIO icon (alien head) in left sidebar
3. Under "esp32-s3-devkitc-1" → Click "Upload"
4. Wait for "SUCCESS"

**CLI:**
```bash
cd C:/Users/zain_/esp32_federated_mesh
pio run --target upload
```

**For multiple boards:**
- Flash board 1 with NODE_ID=1
- Disconnect board 1
- Change NODE_ID to 2, flash board 2
- Repeat for board 3

### 5. Verify Firmware (30 seconds)

**Monitor serial output:**

VS Code: Click "Monitor" in PlatformIO sidebar

OR

```bash
pio device monitor --baud 115200
```

**Expected output:**
```
=== ESP32-S3 Federated Learning Mesh ===
Node ID: 1
[MESH] Node 1 initialized
[MESH] MAC: XX:XX:XX:XX:XX:XX
[READY] System initialized successfully
[NODE 1] STEP 0 | LOSS: 0.4523 | ANOMALY: 0.23 | TARGET: 0.0
```

**Press Ctrl+C to exit monitor (don't forget this!)**

### 6. Start Python Bridge (1 minute)

Open a NEW terminal:
```bash
cd C:/Users/zain_/esp32_federated_mesh/python
python bridge.py
```

**Expected output:**
```
[BRIDGE] Found ESP32 device: COM3
[BRIDGE] Connected to COM3
[WS] WebSocket server running on ws://localhost:8080
```

**Leave this running!**

### 7. Open Web Dashboard (30 seconds)

1. Navigate to `C:/Users/zain_/esp32_federated_mesh/web/`
2. Double-click `index.html`
3. Browser opens automatically

OR

```bash
start web/index.html  # Windows
```

**What you'll see:**
- 3 rotating cubes (green = normal, red = anomaly)
- Live loss values above each cube
- Info panel on the left with node stats
- Connection status "⚡ Connected" in top-right

---

## 🎉 Success Indicators

✅ **Firmware Running**: LED blinks on ESP32-S3, serial shows training steps

✅ **Mesh Active**: Serial shows "MESH SYNC: Received weights from Node X"

✅ **Bridge Connected**: Python terminal shows timestamped log entries

✅ **Dashboard Live**: Cubes rotate, status shows "Connected", loss values update

---

## 🐛 Quick Troubleshooting

### Problem: "Port COM3 not found"
**Fix**: 
1. Check Device Manager for correct port
2. Install USB drivers: [CP210x](https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers) or [CH340](http://www.wch-ic.com/downloads/CH341SER_EXE.html)
3. Try different USB cable (some are power-only)

### Problem: "Upload failed"
**Fix**:
1. Unplug and replug USB cable
2. Hold BOOT button while clicking Upload
3. Check another USB port

### Problem: "Bridge can't find ESP32"
**Fix**:
1. Close PlatformIO monitor (Ctrl+C) - only one program can use serial at a time
2. Verify port in Device Manager
3. Run: `python -m serial.tools.list_ports`

### Problem: "Dashboard shows Disconnected"
**Fix**:
1. Verify bridge is running (check Python terminal)
2. Check browser console (F12) for errors
3. Try `http://localhost:8080` directly to test WebSocket
4. Disable antivirus/firewall temporarily

### Problem: "No mesh activity"
**Fix**:
1. Power all boards simultaneously
2. Wait 15 seconds (first sync interval)
3. Check serial logs for "MESH BROADCAST"
4. Boards must be within ~10m of each other

---

## 📊 What to Expect

### First 30 Seconds
- Nodes training independently
- Loss decreasing from ~0.5 to ~0.2
- Anomaly scores low (<0.2)
- Dashboard cubes GREEN

### At 15 Seconds (First Sync)
- Serial shows "MESH BROADCAST: Sent weights"
- Serial shows "MESH SYNC: Received weights from Node X"
- Dashboard shows glowing arc between cubes
- Loss may spike briefly, then stabilize

### At 30 Seconds (First Anomaly)
- Anomaly injected automatically
- Serial shows "*** ANOMALY DETECTED: 0.95 ***"
- Dashboard cubes turn RED
- Loss increases temporarily
- Info panel shows "ANOMALY" status

### After 5 Minutes
- All nodes converged (~0.05 loss on normal data)
- Consistent anomaly detection (>90% accuracy)
- Regular mesh syncs every 15 seconds

---

## 🎓 Next Steps

### Experiment 1: Adjust Sync Frequency
Edit `src/main.cpp`:
```cpp
#define MESH_SYNC_INTERVAL 10000  // 10 seconds instead of 15
```
Rebuild and reflash. Watch how faster syncing affects convergence.

### Experiment 2: Change Learning Rate
Edit `src/main.cpp`:
```cpp
TinyAnomalyNet model(0.005f);  // Slower learning
```
Try 0.001, 0.01, 0.1 and observe training speed vs stability.

### Experiment 3: Modify Anomaly Threshold
Edit `src/main.cpp`:
```cpp
#define ANOMALY_THRESHOLD 0.5  // More sensitive (was 0.7)
```
Lower = more sensitive (more false positives), Higher = less sensitive.

### Experiment 4: Add Real Sensors
Replace simulated data with actual readings:
```cpp
void generate_sensor_data(float* features, bool inject_anomaly) {
    features[0] = analogRead(A0) / 4096.0f;
    features[1] = readTemperature();
    // ...
}
```

---

## 📖 Full Documentation

- **README.md** - Complete system documentation
- **MATH_EXPLAINED.md** - Mathematical foundations
- **include/*.h** - Code documentation in headers

---

## 🆘 Still Stuck?

1. Check serial output for specific error messages
2. Verify all cables and connections
3. Try with just 1 board first
4. Review the full README.md troubleshooting section
5. Check PlatformIO device monitor for ESP32 crash dumps

---

**Total Setup Time: ~10 minutes**
**Difficulty: Intermediate**
**Support: See README.md for detailed troubleshooting**
