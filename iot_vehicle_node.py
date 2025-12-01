import os
import time
import json
import random
import hashlib
import secrets
import requests
import glob
from datetime import datetime
from PIL import Image, ImageDraw

# Configuration
SERVER_URL = "http://localhost:3333"  # Update this if deploying to a remote server
VEHICLE_ID_FILE = "vehicle_id.json"
SOURCE_IMAGE = "PIC OF THE /images/photo1764609981.jpg"
OFFLINE_DIR = "offline_storage"
UPLOAD_ENDPOINT = "/api/iot/submit"
INTERVAL_SECONDS = 60

def load_or_create_identity():
    if os.path.exists(VEHICLE_ID_FILE):
        with open(VEHICLE_ID_FILE, 'r') as f:
            return json.load(f)
    else:
        identity = {
            "vehicle_id": "THR-CAR-" + secrets.token_hex(4).upper(),
            "private_key": secrets.token_hex(32),
            "public_key": secrets.token_hex(32)
        }
        with open(VEHICLE_ID_FILE, 'w') as f:
            json.dump(identity, f, indent=2)
        return identity

def get_vehicle_telemetry(identity):
    # Simulate reading from OBD-II / GPS sensors
    return {
        "vehicle_id": identity['vehicle_id'],
        "timestamp": time.time(),
        "gps_lat": 37.9838 + random.uniform(-0.01, 0.01),
        "gps_lon": 23.7275 + random.uniform(-0.01, 0.01),
        "speed_kmh": random.randint(0, 120),
        "odometer": 12000 + random.randint(0, 100),
        "battery_level": random.randint(20, 100),
        "status": "active"
    }

def create_dummy_image_if_needed(path):
    if not os.path.exists(path):
        print(f"⚠️ Source image {path} not found. Creating a placeholder.")
        img = Image.new('RGB', (800, 600), color = (200, 100, 50))
        d = ImageDraw.Draw(img)
        d.text((50, 250), "PIC OF THE FIRE (Placeholder)", fill=(255, 255, 255))
        img.save(path)

def encode_steganography(image_path, data_dict, output_path):
    """Encodes JSON data into the LSB of the image."""
    create_dummy_image_if_needed(image_path)
    
    img = Image.open(image_path)
    encoded = img.copy()
    width, height = img.size
    pixels = encoded.load()
    
    # Prepare data: Length header (32-bit) + JSON string
    data_str = json.dumps(data_dict)
    binary_data = ''.join(format(ord(i), '08b') for i in data_str)
    
    # Add a delimiter or length header could be better, but for this MVP 
    # we will just embed the raw binary. A real implementation needs a robust header.
    # We'll prepend the length as a 32-bit binary string for the decoder to know when to stop.
    length_bin = format(len(binary_data), '032b')
    full_payload = length_bin + binary_data
    
    data_len = len(full_payload)
    if data_len > width * height * 3:
        raise ValueError("Data too large for image capacity")
        
    idx = 0
    for y in range(height):
        for x in range(width):
            if idx < data_len:
                r, g, b = pixels[x, y]
                
                if idx < data_len:
                    r = (r & ~1) | int(full_payload[idx])
                    idx += 1
                if idx < data_len:
                    g = (g & ~1) | int(full_payload[idx])
                    idx += 1
                if idx < data_len:
                    b = (b & ~1) | int(full_payload[idx])
                    idx += 1
                    
                pixels[x, y] = (r, g, b)
            else:
                break
        if idx >= data_len:
            break
            
    encoded.save(output_path)
    return True

def save_offline(telemetry, identity):
    if not os.path.exists(OFFLINE_DIR):
        os.makedirs(OFFLINE_DIR)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{OFFLINE_DIR}/images/Telemetry.jpg"
    
    # Sign the data
    payload_str = json.dumps(telemetry)
    signature = hashlib.sha256((payload_str + identity['private_key']).encode()).hexdigest()
    final_payload = {"data": telemetry, "sig": signature}
    
    try:
        encode_steganography(SOURCE_IMAGE, final_payload, filename)
        print(f"💾 [Offline] Saved telemetry to {filename}")
        return True
    except Exception as e:
        print(f"❌ [Offline] Error saving: {e}")
        return False

def upload_image(filepath):
    try:
        with open(filepath, 'rb') as f:
            files = {'file': f}
            # In a real scenario, we might send the wallet address as a form field too
            response = requests.post(f"{SERVER_URL}{UPLOAD_ENDPOINT}", files=files, timeout=5)
            
        if response.status_code == 200:
            print(f"✅ [Upload] Successfully uploaded {filepath}")
            return True
        else:
            print(f"⚠️ [Upload] Server returned {response.status_code}: {response.text}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ [Upload] Connection failed. Server unreachable.")
        return False
    except Exception as e:
        print(f"❌ [Upload] Error: {e}")
        return False

def process_offline_queue():
    if not os.path.exists(OFFLINE_DIR):
        return

    files = glob.glob(f"{OFFLINE_DIR}/*.png")
    if not files:
        return

    print(f"🔄 [Queue] Found {len(files)} offline records. Attempting upload...")
    
    for filepath in files:
        if upload_image(filepath):
            # Delete after successful upload
            os.remove(filepath)
            print(f"🗑️ [Queue] Deleted local copy: {filepath}")
        else:
            print("⏹️ [Queue] Upload failed, stopping queue processing.")
            break

def main():
    print("🚗 Thronos IoT Vehicle Node Started")
    print("-----------------------------------")
    identity = load_or_create_identity()
    print(f"Vehicle ID: {identity['vehicle_id']}")
    
    # Ensure source image exists
    create_dummy_image_if_needed(SOURCE_IMAGE)
    
    while True:
        print("\n⏱️  Collecting Telemetry...")
        telemetry = get_vehicle_telemetry(identity)
        
        # 1. Always create a temporary current state image
        current_image = "/images/photo1764609981.jpg"
        
        # Sign data
        payload_str = json.dumps(telemetry)
        signature = hashlib.sha256((payload_str + identity['private_key']).encode()).hexdigest()
        final_payload = {"data": telemetry, "sig": signature}
        
        encode_steganography(SOURCE_IMAGE, final_payload, current_image)
        
        # 2. Try to upload immediately
        print("📡 Attempting connection to server...")
        if upload_image(current_image):
            # If successful, also check if we have offline data to sync
            process_offline_queue()
        else:
            # If failed, save to offline storage
            print("🔌 Server unreachable. Switching to Offline Mode.")
            save_offline(telemetry, identity)
            
        # Cleanup temp file
        if os.path.exists(current_image):
            os.remove(current_image)
            
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    main()