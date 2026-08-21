#ifndef TINY_CNN_H
#define TINY_CNN_H

#include <Arduino.h>
#include <math.h>

// Lightweight 1-Layer Perceptron for anomaly detection
// Architecture: 10 inputs -> 8 hidden -> 1 output
// Total trainable parameters: (10*8) + 8 + (8*1) + 1 = 80 + 8 + 8 + 1 = 97
// But we'll use 12 key parameters for mesh sync (first layer subset + biases)

class TinyAnomalyNet {
private:
    // Network architecture
    static const int INPUT_SIZE = 10;
    static const int HIDDEN_SIZE = 8;
    static const int OUTPUT_SIZE = 1;
    
    // Weights and biases (12 key trainable parameters)
    float weights_input_hidden[12];  // First 12 connections (subset of 80)
    float bias_hidden[8];
    float weights_hidden_output[8];
    float bias_output;
    
    // Hidden layer activations
    float hidden[HIDDEN_SIZE];
    float output;
    
    float learning_rate;
    
    // ReLU activation
    inline float relu(float x) {
        return x > 0 ? x : 0;
    }
    
    // ReLU derivative
    inline float relu_derivative(float x) {
        return x > 0 ? 1.0f : 0.0f;
    }
    
    // Random initialization with Xavier/He scaling
    float random_weight() {
        return (random(0, 10000) / 10000.0f - 0.5f) * 0.5f;
    }

public:
    TinyAnomalyNet(float lr = 0.01f) : learning_rate(lr), output(0.0f) {
        // Initialize weights randomly
        for (int i = 0; i < 12; i++) {
            weights_input_hidden[i] = random_weight();
        }
        for (int i = 0; i < HIDDEN_SIZE; i++) {
            bias_hidden[i] = 0.0f;
            weights_hidden_output[i] = random_weight();
        }
        bias_output = 0.0f;
    }
    
    // Forward pass - returns anomaly score [0.0 - 1.0]
    float predict(float* input) {
        // Hidden layer computation
        for (int h = 0; h < HIDDEN_SIZE; h++) {
            float sum = bias_hidden[h];
            
            // Use first 12 weights for demonstration
            for (int i = 0; i < min(INPUT_SIZE, 12); i++) {
                int weight_idx = h + i;
                if (weight_idx < 12) {
                    sum += input[i] * weights_input_hidden[weight_idx];
                }
            }
            
            // Add remaining inputs with fixed small weights
            for (int i = 12 / HIDDEN_SIZE; i < INPUT_SIZE; i++) {
                sum += input[i] * 0.1f;
            }
            
            hidden[h] = relu(sum);
        }
        
        // Output layer computation
        float out_sum = bias_output;
        for (int h = 0; h < HIDDEN_SIZE; h++) {
            out_sum += hidden[h] * weights_hidden_output[h];
        }
        
        // Sigmoid to get 0-1 range (anomaly probability)
        output = 1.0f / (1.0f + exp(-out_sum));
        return output;
    }
    
    // Training step with SGD
    void train_step(float* input, float target) {
        // Forward pass
        float prediction = predict(input);
        
        // Compute loss (MAE - Mean Absolute Error)
        float loss = abs(target - prediction);
        
        // Backpropagation - simplified SGD update
        float output_error = (target - prediction) * prediction * (1.0f - prediction); // Sigmoid derivative
        
        // Update output layer weights
        for (int h = 0; h < HIDDEN_SIZE; h++) {
            float gradient = output_error * hidden[h];
            weights_hidden_output[h] += learning_rate * gradient;
        }
        bias_output += learning_rate * output_error;
        
        // Update hidden layer weights (backprop through ReLU)
        for (int h = 0; h < HIDDEN_SIZE; h++) {
            float hidden_error = output_error * weights_hidden_output[h] * relu_derivative(hidden[h]);
            
            // Update first 12 weights
            for (int i = 0; i < min(INPUT_SIZE, 12); i++) {
                int weight_idx = h + i;
                if (weight_idx < 12) {
                    weights_input_hidden[weight_idx] += learning_rate * hidden_error * input[i];
                }
            }
            
            bias_hidden[h] += learning_rate * hidden_error;
        }
    }
    
    // Extract 12 key weights for mesh synchronization
    void get_weights(float* buffer_12) {
        memcpy(buffer_12, weights_input_hidden, sizeof(float) * 12);
    }
    
    // Set 12 key weights from mesh synchronization
    void set_weights(float* buffer_12) {
        memcpy(weights_input_hidden, buffer_12, sizeof(float) * 12);
    }
    
    // Get current learning rate
    float get_learning_rate() {
        return learning_rate;
    }
    
    // Set learning rate
    void set_learning_rate(float lr) {
        learning_rate = lr;
    }
    
    // Get memory usage estimate
    size_t get_memory_usage() {
        return sizeof(TinyAnomalyNet);
    }
};

#endif // TINY_CNN_H
