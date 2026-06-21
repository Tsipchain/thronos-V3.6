#!/usr/bin/env bash
# Thronos CPU Miner launcher (Linux / macOS)

THR_ADDRESS="${1:-${THR_ADDRESS:-}}"
API_URL="${THRONOS_API_URL:-https://api.thronoschain.org}"

if [ -z "$THR_ADDRESS" ]; then
    read -rp "Enter your THR wallet address: " THR_ADDRESS
fi

if [ -z "$THR_ADDRESS" ]; then
    echo "ERROR: THR address is required."
    exit 1
fi

echo "==========================================="
echo " Thronos CPU Miner"
echo " Address: $THR_ADDRESS"
echo " Server : $API_URL"
echo "==========================================="
echo

python3 pow_miner_cpu.py --address "$THR_ADDRESS" --api "$API_URL"
