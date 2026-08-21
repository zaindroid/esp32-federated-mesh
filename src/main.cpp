#include <Arduino.h>
#include "esp_now_mesh.h"
#include "tiny_cnn.h"

// Node configuration - CHANGE THIS FOR EACH ESP32-S3
#define NODE_ID 1  // Set to 1, 2, or 3 for different boards

// Timing configuration
#define TRAINING_INTERVAL 100      // Train every 100ms
#define MESH_SYNC_INTERVAL 15000   // Broadcast weights every 15 seconds
#define ANOMALY_THRESHOLD 0.7      // Anomaly detection threshold

// Global objects
ESPNowMesh mesh(NODE_ID);
TinyAnomalyNet model(0.01f);  // Learning rate = 0.01

// Timing variables
unsigned long last_training_time = 0;
unsigned long last_mesh_sync_time = 0;

// Training state
int training_step = 0;
bool anomaly_mode = false;
unsigned long anomaly_mode_start = 0;

// Generate simulated 10-dimensional sensor data
void generate_sensor_data(float* features, bool inject_anomaly) {
    float time_factor = millis() / 1000.0f;
    
    if (!inject_anomaly) {
        // Normal state: smooth sine waves with Gaussian noise
        for (int i = 0; i < 10; i++) {
            float phase = (i + 1) * 0.5f;
            float frequency = 0.1f + i * 0.05f;
            
            // Sine wave base
            float base = sin(time_factor * frequency + phase);
            
            // Add Gaussian-like noise (approximated with uniform random)
            float noise = (random(-1000, 1000) / 10000.0f) * 0.1f;
            
            features[i] = base + noise;
        }
    } else {
        // Anomaly state: random high-amplitude spikes
        for (int i = 0; i < 10; i++) {
            // Large random spikes
            float spike = (random(-10000, 10000) / 1000.0f);
            float noise = (random(-1000, 1000) / 1000.0f) * 0.5f;
            
            features[i] = spike + noise;
        }
    }
}

// Check if we should inject anomaly (every 60 seconds for 5 seconds)
bool should_inject_anomaly() {
    unsigned long current_time = millis();
    unsigned long cycle_time = current_time % 60000;  // 60-second cycle
    
    // Anomaly during seconds 30-35 of each minute
    return (cycle_time >= 30000 && cycle_time < 35000);
}

void setup() {
    // Initialize serial
    Serial.begin(115200);
    delay(1000);
    
    Serial.println("\n=== ESP32-S3 Federated Learning Mesh ===");
    Serial.printf("Node ID: %d\n", NODE_ID);
    Serial.printf("Model Memory: %d bytes\n", model.get_memory_usage());
    
    // Initialize built-in LED
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, LOW);
    
    // Initialize random seed
    randomSeed(analogRead(0) + NODE_ID * 1000);
    
    // Initialize mesh network
    if (!mesh.init()) {
        Serial.println("[ERROR] Mesh initialization failed!");
        while (1) {
            digitalWrite(LED_BUILTIN, HIGH);
            delay(100);
            digitalWrite(LED_BUILTIN, LOW);
            delay(100);
        }
    }
    
    Serial.println("[READY] System initialized successfully");
    Serial.println("Legend: LOSS=training error, ANOMALY=detection score (0-1)");
    Serial.println();
    
    // LED startup sequence
    for (int i = 0; i < 3; i++) {
        digitalWrite(LED_BUILTIN, HIGH);
        delay(200);
        digitalWrite(LED_BUILTIN, LOW);
        delay(200);
    }
}

void loop() {
    unsigned long current_time = millis();
    
    // === LOCAL TRAINING ===
    if (current_time - last_training_time >= TRAINING_INTERVAL) {
        last_training_time = current_time;
        
        // Generate sensor features
        float features[10];
        bool inject_anomaly = should_inject_anomaly();
        generate_sensor_data(features, inject_anomaly);
        
        // Target: 0.0 for normal, 1.0 for anomaly
        float target = inject_anomaly ? 1.0f : 0.0f;
        
        // Train the model
        model.train_step(features, target);
        
        // Predict anomaly score
        float anomaly_score = model.predict(features);
        
        // Calculate loss (MAE)
        float loss = abs(target - anomaly_score);
        
        // Log every 10 training steps
        if (training_step % 10 == 0) {
            Serial.printf("[NODE %d] STEP %d | LOSS: %.4f | ANOMALY: %.4f | TARGET: %.1f\n",
                         NODE_ID, training_step, loss, anomaly_score, target);
        }
        
        // Detect anomalies
        if (anomaly_score > ANOMALY_THRESHOLD) {
            if (!anomaly_mode) {
                Serial.printf("[NODE %d] *** ANOMALY DETECTED: %.2f ***\n", NODE_ID, anomaly_score);
                anomaly_mode = true;
                anomaly_mode_start = current_time;
            }
        } else {
            if (anomaly_mode && (current_time - anomaly_mode_start > 2000)) {
                Serial.printf("[NODE %d] System returned to normal\n", NODE_ID);
                anomaly_mode = false;
            }
        }
        
        training_step++;
    }
    
    // === FEDERATED MESH SYNCHRONIZATION ===
    if (current_time - last_mesh_sync_time >= MESH_SYNC_INTERVAL) {
        last_mesh_sync_time = current_time;
        
        // Get current local weights
        float local_weights[12];
        model.get_weights(local_weights);
        
        // Check if new weights received from peers
        if (mesh.has_new_weights()) {
            float averaged_weights[12];
            mesh.get_averaged_weights(local_weights, averaged_weights);
            
            // Update model with federated averaged weights
            model.set_weights(averaged_weights);
            
            Serial.printf("[NODE %d] MESH SYNC: Applied federated averaging\n", NODE_ID);
        }
        
        // Broadcast current weights to mesh
        mesh.broadcast_weights(local_weights, model.get_learning_rate());
    }
    
    // Small delay to prevent watchdog issues
    delay(10);
}
