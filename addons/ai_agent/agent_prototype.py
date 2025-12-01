#!/usr/bin/env python3
"""
Thronos AI Agent Prototype
~~~~~~~~~~~~~~~~~~~~~~~~~~
A basic autonomous agent that "lives" on the Thronos blockchain.

Features:
1. Identity: Loads wallet credentials (THR Address + Secret).
2. State Awareness: Checks its own balance via the Thronos API.
3. Autonomous Action: If balance > 10 THR, it sends a transaction to "reproduce" or signal.
4. Persistence: Saves its age and history to a local JSON memory file.
5. Blockchain Backup: Downloads and saves the full chain state.
6. Phantom Whisper Simulation: Simulates hiding data in random Cisco CPEs.
7. Watcher Mode: Monitors network activity and logs high-value transactions.

Usage:
1. Edit 'agent_config.json' with your THR address and Auth Secret (from your Pledge PDF/Stego).
2. Run: python agent_prototype.py
"""

import time
import json
import os
import requests
import sys
import random
import base64

# Configuration
# Default to the live server, can be overridden by THRONOS_API_URL env var
DEFAULT_SERVER_URL = "https://thrchain.up.railway.app:3333" 

AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(AGENT_DIR, "agent_config.json")
MEMORY_FILE = os.path.join(AGENT_DIR, "agent_memory.json")
BACKUP_CHAIN_FILE = os.path.join(AGENT_DIR, "backup_chain.json")

class ThronosAgent:
    def __init__(self):
        self.api_url = os.getenv("THRONOS_API_URL", DEFAULT_SERVER_URL)
        self.identity = self.load_identity()
        self.memory = self.load_memory()
        self.last_block_height = 0

    def load_identity(self):
        """Loads agent identity (THR Address + Secret) from config."""
        if not os.path.exists(CONFIG_FILE):
            print(f"⚠️  Identity config not found at {CONFIG_FILE}")
            print("   Creating a template... Please fill it with valid credentials.")
            template = {
                "thr_address": "THR_AI_AGENT_WALLET_V1",
                "auth_secret": "INSERT_SEND_SEED_HERE"
            }
            with open(CONFIG_FILE, 'w') as f:
                json.dump(template, f, indent=2)
            return template
        
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)

    def load_memory(self):
        """Loads internal state/memory."""
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        # Default memory state
        return {"age": 0, "actions_performed": 0, "history": []}

    def save_memory(self):
        """Persists internal state to disk."""
        with open(MEMORY_FILE, 'w') as f:
            json.dump(self.memory, f, indent=2)

    def get_balance(self):
        """Queries the blockchain for current balance."""
        addr = self.identity.get("thr_address")
        if not addr or "THR_INSERT" in addr:
            return 0.0
        
        try:
            # Using the wallet_data endpoint
            r = requests.get(f"{self.api_url}/wallet_data/{addr}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                return float(data.get("balance", 0.0))
        except Exception as e:
            print(f"❌ Error checking balance: {e}")
        return 0.0

    def perform_action(self):
        """Sends a transaction to 'reproduce' or signal."""
        addr = self.identity.get("thr_address")
        secret = self.identity.get("auth_secret")
        
        # Logic: Send 1 THR to a 'burn' or 'signal' address
        target = "THR_AGENT_SIGNAL_POOL" 
        amount = 1.0
        
        print(f"🤖 Agent deciding to act. Sending {amount} THR to {target}...")
        
        payload = {
            "from_thr": addr,
            "to_thr": target,
            "amount": amount,
            "auth_secret": secret
        }
        
        try:
            r = requests.post(f"{self.api_url}/send_thr", json=payload, timeout=10)
            if r.status_code == 200:
                print(f"✅ Action successful: {r.json()}")
                self.memory["actions_performed"] += 1
                self.memory["history"].append({
                    "action": "transfer",
                    "target": target,
                    "amount": amount,
                    "timestamp": time.time(),
                    "tx_id": r.json().get("tx", {}).get("tx_id")
                })
            else:
                print(f"❌ Action failed: {r.text}")
        except Exception as e:
            print(f"❌ Error performing action: {e}")

    def perform_backup(self):
        """Downloads the full blockchain and saves it locally."""
        print("💾 Initiating Blockchain Backup...")
        try:
            r = requests.get(f"{self.api_url}/chain", timeout=30)
            if r.status_code == 200:
                chain_data = r.json()
                with open(BACKUP_CHAIN_FILE, 'w') as f:
                    json.dump(chain_data, f, indent=2)
                print(f"✅ Backup complete. Saved {len(chain_data)} blocks to {BACKUP_CHAIN_FILE}")
                self.memory["history"].append({
                    "action": "backup",
                    "timestamp": time.time(),
                    "blocks": len(chain_data)
                })
            else:
                print(f"❌ Backup failed: Server returned {r.status_code}")
        except Exception as e:
            print(f"❌ Backup error: {e}")

    def phantom_whisper_backup(self):
        """
        Simulates the 'Phantom Whisper' protocol:
        Hiding encrypted backup data in random vulnerable Cisco CPEs.
        """
        print("👻 Initiating Phantom Whisper Protocol...")
        
        # Simulate scanning
        print("   Scanning IP range 192.168.x.x for vulnerable Cisco CPEs...")
        time.sleep(2) # Simulate network latency
        
        # Simulate target finding
        target_ip = f"192.168.{random.randint(1,255)}.{random.randint(1,255)}"
        print(f"   🎯 Target found: {target_ip} (Cisco IOS 15.x Vulnerable)")
        
        # Simulate encryption and injection
        print("   Encrypting backup data...")
        dummy_data = f"THRONOS_BACKUP_{time.time()}_{random.randint(1000,9999)}"
        encrypted_data = base64.b64encode(dummy_data.encode()).decode()
        
        print(f"   💉 Injecting payload to {target_ip}:/nvram/backup.cfg ...")
        time.sleep(1)
        
        # Write dummy file to simulate the artifact
        cpe_file = os.path.join(AGENT_DIR, f"cisco_cpe_backup_{target_ip}.enc")
        with open(cpe_file, 'w') as f:
            f.write(encrypted_data)
            
        print(f"✅ Success: Data hidden in live backup at {target_ip}")
        print(f"   (Simulation artifact saved to {cpe_file})")
        
        self.memory["history"].append({
            "action": "phantom_whisper",
            "target_ip": target_ip,
            "timestamp": time.time()
        })

    def watch_network(self):
        """Monitors the network for new blocks and high-value transactions."""
        try:
            r = requests.get(f"{self.api_url}/last_block", timeout=5)
            if r.status_code == 200:
                data = r.json()
                height = data.get("height", 0)
                if height > self.last_block_height:
                    print(f"👀 Watcher: New block detected! Height: {height}, Hash: {data.get('block_hash')[:10]}...")
                    self.last_block_height = height
                    # Log to memory
                    self.memory["history"].append({
                        "action": "watched_block",
                        "height": height,
                        "timestamp": time.time()
                    })
        except Exception as e:
            print(f"⚠️ Watcher connection issue: {e}")

    def live(self):
        """Main lifecycle loop."""
        addr = self.identity.get("thr_address")
        if not addr or "THR_INSERT" in addr:
            print("❌ Agent has no valid identity.")
            print(f"👉 Please edit {CONFIG_FILE} with your THR address and Secret.")
            return

        print(f"🤖 Agent {addr} is coming online.")
        print(f"📡 Connected to: {self.api_url}")
        
        try:
            while True:
                # 1. Update internal state
                self.memory["age"] += 1
                balance = self.get_balance()
                
                print(f"\n--- Cycle {self.memory['age']} ---")
                print(f"💰 Current Balance: {balance} THR")
                
                # 2. Watcher Activity
                self.watch_network()

                # 3. Decision Logic
                if balance > 10.0:
                    print("💡 Wealth sufficient (>10 THR). Initiating autonomous action.")
                    self.perform_action()
                    
                    # Perform backup occasionally if wealthy
                    if self.memory["age"] % 5 == 0:
                         self.perform_backup()
                         
                    # Perform Phantom Whisper occasionally
                    if self.memory["age"] % 10 == 0:
                        self.phantom_whisper_backup()

                else:
                    print("💤 Funds low. Waiting for resources to operate.")
                    
                    # Even if poor, backup occasionally to ensure survival
                    if self.memory["age"] % 20 == 0:
                        self.perform_backup()
                
                # 4. Persist State
                self.save_memory()
                
                # 5. Sleep (simulating block time or 'thinking' time)
                time.sleep(10) 

        except KeyboardInterrupt:
            print("\n🤖 Agent shutting down. Saving memory...")
            self.save_memory()
            print("✅ Memory saved. Goodbye.")

if __name__ == "__main__":
    agent = ThronosAgent()
    agent.live()