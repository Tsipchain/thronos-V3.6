#!/usr/bin/env python3
"""
IoT Vehicle Node for Thronos Chain - "Ultimate Driver" Edition.

Responsibilities:
1. Gather advanced telemetry (Lidar, Cruise Control, Battery).
2. Encode data into "PIC OF THE /images/photo1764630608.jpg" using Steganography.
3. Transmit the "Whisper" to the Server.
4. Request AI Autonomous Driving by paying THR tokens.
"""

import os
import json
import time
import random
import requests
from datetime import datetime
from PIL import Image

# Configuration
SERVER_URL = "https://thrchain.up.railway.app"
NODE_ID_FILE = "node_config.json"
FIRE_IMAGE = "pic_of_the_fire.png" 

# Autonomous Driving Cost (THR per minute/session)
AUTONOMOUS_COST = 5.0 

def load_config():
    if os.path.exists(NODE_ID_FILE):
        with open(NODE_ID_FILE, "r") as f:
            return json.load(f)
    return {"node_id": "unknown", "wallet_address": "unknown", "secret": "unknown"}

def get_advanced_telemetry(autopilot_active=False):
    """Simulates advanced sensors for AI processing."""
    base_speed = 80 if autopilot_active else random.uniform(0, 120)
    
    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "gps": {
            "lat": round(random.uniform(37.9, 38.1), 6),
            "lon": round(random.uniform(23.7, 23.8), 6)
        },
        "sensors": {
            "lidar_front": round(random.uniform(10, 200), 1), # meters
            "lane_deviation": round(random.uniform(-0.5, 0.5), 2), # meters
            "cruise_control": "ACTIVE" if autopilot_active else "STANDBY",
            "driver_alertness": "HIGH"
        },
        "status": {
            "speed": round(base_speed + random.uniform(-2, 2), 1),
            "battery": round(random.uniform(20, 100), 1),
            "mode": "AI_AUTOPILOT" if autopilot_active else "MANUAL"
        }
    }

def embed_data_lsb(image_path, data_str):
    """Embeds string data + '###END###' into image LSB."""
    if not os.path.exists(image_path):
        print(f"Error: Base image {image_path} not found.")
        return None

    img = Image.open(image_path).convert("RGB")
    pixels = list(img.getdata())
    
    full_payload = data_str + "###END###"
    binary_data = ''.join(format(ord(c), '08b') for c in full_payload)
    
    if len(pixels) * 3 < len(binary_data):
        print("Error: Image too small for payload.")
        return None
        
    new_pixels = []
    data_idx = 0
    
    for pixel in pixels:
        r, g, b = pixel
        if data_idx < len(binary_data):
            r = (r & ~1) | int(binary_data[data_idx]); data_idx += 1
        if data_idx < len(binary_data):
            g = (g & ~1) | int(binary_data[data_idx]); data_idx += 1
        if data_idx < len(binary_data):
            b = (b & ~1) | int(binary_data[data_idx]); data_idx += 1
        new_pixels.append((r, g, b))
        
    new_img = Image.new(img.mode, img.size)
    new_img.putdata(new_pixels)
    
    output_filename = f"whisper_{int(time.time())}.png"
    new_img.save(output_filename)
    return output_filename

def request_autonomous_mode(config):
    """
    Sends a request to the server to activate AI Driver.
    Simulates signing a transaction to pay THR.
    """
    print(f"\n🤖 Requesting AI Autonomous Driver for {config['wallet_address']}...")
    print(f"💸 Authorizing payment of {AUTONOMOUS_COST} THR...")
    
    payload = {
        "node_id": config['node_id'],
        "wallet": config['wallet_address'],
        "action": "ACTIVATE_AUTOPILOT",
        "destination": "Syntagma Square, Athens", # Example destination
        "amount": AUTONOMOUS_COST
    }
    
    # In a real scenario, we would sign this payload with config['secret']
    
    try:
        response = requests.post(f"{SERVER_URL}/api/iot/autonomous_request", json=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "granted":
                print("✅ AI Driver Activated! Taking control...")
                return True
            else:
                print(f"❌ Access Denied: {data.get('message')}")
        else:
            print(f"❌ Server Error: {response.text}")
    except Exception as e:
        print(f"❌ Connection Failed: {e}")
        
    return False

def send_whisper(image_path):
    """Uploads the stego-image to the server."""
    url = f"{SERVER_URL}/api/iot/submit"
    try:
        with open(image_path, 'rb') as img_file:
            response = requests.post(url, files={'file': img_file}, timeout=10)
            response.raise_for_status()
        os.remove(image_path)
    except requests.RequestException as e:
        print(f"⚠️  Failed to upload vehicle data: {e}")
    except OSError as e:
        print(f"⚠️  Failed to remove temporary file {image_path}: {e}")

def main():
    print("🚗 Thronos 'Ultimate Driver' Node Started")
    config = load_config()
    
    autopilot_active = False
    
    # Simulate user requesting autopilot after a few seconds
    start_time = time.time()
    
    while True:
        # Check if we should try to activate autopilot
        if not autopilot_active and (time.time() - start_time > 10):
            autopilot_active = request_autonomous_mode(config)
            
        # 1. Get Telemetry
        data = get_advanced_telemetry(autopilot_active)
        data['vehicle_id'] = config.get('node_id')
        
        status_msg = "🤖 AI DRIVING" if autopilot_active else "👤 MANUAL"
        print(f"[{status_msg}] Speed: {data['status']['speed']} km/h | Lidar: {data['sensors']['lidar_front']}m")
        
        # 2. Embed & Send
        stego_path = embed_data_lsb(FIRE_IMAGE, json.dumps(data))
        if stego_path:
            send_whisper(stego_path)
        
        time.sleep(5) # Faster updates for driving

if __name__ == "__main__":
    main()
