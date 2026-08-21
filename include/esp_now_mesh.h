#ifndef ESP_NOW_MESH_H
#define ESP_NOW_MESH_H

#include <Arduino.h>
#include <esp_now.h>
#include <WiFi.h>

// ESP-NOW mesh packet structure (under 250 bytes)
typedef struct __attribute__((packed)) {
    uint8_t version;           // Protocol version
    uint8_t node_id;          // Source node ID
    uint32_t timestamp;       // Milliseconds since boot
    float weights[12];        // 12 trainable parameters (48 bytes)
    float learning_rate;      // Current learning rate
    uint8_t checksum;         // Simple checksum for validation
} MeshPacket;

class ESPNowMesh {
private:
    uint8_t node_id;
    uint8_t broadcast_addr[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
    float accumulated_weights[12];
    int accumulation_count;
    bool new_weights_available;
    
    // Callback function pointer
    static ESPNowMesh* instance;
    
    // Calculate simple checksum
    uint8_t calculate_checksum(MeshPacket* packet) {
        uint8_t sum = 0;
        uint8_t* data = (uint8_t*)packet;
        for (int i = 0; i < sizeof(MeshPacket) - 1; i++) {
            sum ^= data[i];
        }
        return sum;
    }
    
    // Static callback wrapper
    static void on_data_recv_wrapper(const uint8_t *mac_addr, const uint8_t *data, int len) {
        if (instance) {
            instance->on_data_recv(mac_addr, data, len);
        }
    }

public:
    ESPNowMesh(uint8_t id) : node_id(id), accumulation_count(0), new_weights_available(false) {
        instance = this;
        for (int i = 0; i < 12; i++) {
            accumulated_weights[i] = 0.0f;
        }
    }
    
    bool init() {
        // Set WiFi to station mode (required for ESP-NOW)
        WiFi.mode(WIFI_STA);
        WiFi.disconnect();
        
        // Initialize ESP-NOW
        if (esp_now_init() != ESP_OK) {
            Serial.println("[MESH] ESP-NOW initialization failed");
            return false;
        }
        
        // Register broadcast peer
        esp_now_peer_info_t peerInfo = {};
        memcpy(peerInfo.peer_addr, broadcast_addr, 6);
        peerInfo.channel = 0;
        peerInfo.encrypt = false;
        
        if (esp_now_add_peer(&peerInfo) != ESP_OK) {
            Serial.println("[MESH] Failed to add broadcast peer");
            return false;
        }
        
        // Register receive callback
        esp_now_register_recv_cb(on_data_recv_wrapper);
        
        Serial.printf("[MESH] Node %d initialized\n", node_id);
        Serial.printf("[MESH] MAC: %s\n", WiFi.macAddress().c_str());
        return true;
    }
    
    // Broadcast weights to mesh network
    bool broadcast_weights(float* weights, float learning_rate) {
        MeshPacket packet;
        packet.version = 1;
        packet.node_id = node_id;
        packet.timestamp = millis();
        packet.learning_rate = learning_rate;
        
        // Copy weights
        memcpy(packet.weights, weights, sizeof(float) * 12);
        
        // Calculate checksum
        packet.checksum = calculate_checksum(&packet);
        
        // Send via ESP-NOW
        esp_err_t result = esp_now_send(broadcast_addr, (uint8_t*)&packet, sizeof(MeshPacket));
        
        if (result == ESP_OK) {
            Serial.printf("[NODE %d] MESH BROADCAST: Sent weights\n", node_id);
            return true;
        } else {
            Serial.printf("[NODE %d] MESH BROADCAST FAILED: %d\n", node_id, result);
            return false;
        }
    }
    
    // Handle incoming mesh data
    void on_data_recv(const uint8_t *mac_addr, const uint8_t *data, int len) {
        if (len != sizeof(MeshPacket)) {
            Serial.printf("[NODE %d] MESH ERROR: Invalid packet size %d\n", node_id, len);
            return;
        }
        
        MeshPacket* packet = (MeshPacket*)data;
        
        // Validate checksum
        uint8_t received_checksum = packet->checksum;
        uint8_t calculated_checksum = calculate_checksum(packet);
        
        if (received_checksum != calculated_checksum) {
            Serial.printf("[NODE %d] MESH ERROR: Checksum mismatch\n", node_id);
            return;
        }
        
        // Ignore own broadcasts
        if (packet->node_id == node_id) {
            return;
        }
        
        // Accumulate weights for federated averaging
        for (int i = 0; i < 12; i++) {
            accumulated_weights[i] += packet->weights[i];
        }
        accumulation_count++;
        new_weights_available = true;
        
        Serial.printf("[NODE %d] MESH SYNC: Received weights from Node %d\n", 
                     node_id, packet->node_id);
        
        // Blink LED to indicate packet received
        digitalWrite(LED_BUILTIN, HIGH);
        delay(50);
        digitalWrite(LED_BUILTIN, LOW);
    }
    
    // Check if new federated weights are available
    bool has_new_weights() {
        return new_weights_available;
    }
    
    // Get federated averaged weights: new_weight = (local + incoming) / 2
    void get_averaged_weights(float* local_weights, float* output_weights) {
        if (!new_weights_available || accumulation_count == 0) {
            // No new data, return local weights unchanged
            memcpy(output_weights, local_weights, sizeof(float) * 12);
            return;
        }
        
        // Compute average of accumulated weights
        for (int i = 0; i < 12; i++) {
            float avg_incoming = accumulated_weights[i] / accumulation_count;
            // Federated averaging: (local + incoming) / 2
            output_weights[i] = (local_weights[i] + avg_incoming) / 2.0f;
        }
        
        Serial.printf("[NODE %d] MESH SYNC: Averaged weights with %d peers\n", 
                     node_id, accumulation_count);
        
        // Reset accumulation
        for (int i = 0; i < 12; i++) {
            accumulated_weights[i] = 0.0f;
        }
        accumulation_count = 0;
        new_weights_available = false;
    }
    
    uint8_t get_node_id() { return node_id; }
};

// Static instance pointer
ESPNowMesh* ESPNowMesh::instance = nullptr;

#endif // ESP_NOW_MESH_H
