# evm_core.py
# Thronos Autonomous EVM Implementation
# Based on the design document: "Σχεδιασμός Αυτόνομης EVM για το Δίκτυο Thronos"

import os
import json
import time
import hashlib
import secrets
from typing import Dict, Any, List, Optional, Tuple

# ─── EVM CONFIGURATION ──────────────────────────────────────────────────

# Gas costs for opcodes (simplified, based on Ethereum)
GAS_COSTS = {
    # Arithmetic
    "ADD": 3, "SUB": 3, "MUL": 5, "DIV": 5, "MOD": 5,
    "ADDMOD": 8, "MULMOD": 8, "EXP": 10,
    
    # Comparison & Bitwise
    "LT": 3, "GT": 3, "EQ": 3, "ISZERO": 3,
    "AND": 3, "OR": 3, "XOR": 3, "NOT": 3,
    "BYTE": 3, "SHL": 3, "SHR": 3, "SAR": 3,
    
    # Stack operations
    "POP": 2, "PUSH": 3, "DUP": 3, "SWAP": 3,
    
    # Memory operations
    "MLOAD": 3, "MSTORE": 3, "MSTORE8": 3,
    
    # Storage operations (expensive)
    "SLOAD": 200, "SSTORE": 5000,
    
    # Control flow
    "JUMP": 8, "JUMPI": 10, "PC": 2, "JUMPDEST": 1,
    
    # Environment
    "ADDRESS": 2, "BALANCE": 400, "ORIGIN": 2, "CALLER": 2,
    "CALLVALUE": 2, "CALLDATALOAD": 3, "CALLDATASIZE": 2,
    "CALLDATACOPY": 3, "CODESIZE": 2, "CODECOPY": 3,
    "GASPRICE": 2, "EXTCODESIZE": 700, "EXTCODECOPY": 700,
    "RETURNDATASIZE": 2, "RETURNDATACOPY": 3,
    
    # Block information
    "BLOCKHASH": 20, "COINBASE": 2, "TIMESTAMP": 2,
    "NUMBER": 2, "DIFFICULTY": 2, "GASLIMIT": 2,
    
    # Contract operations
    "CREATE": 32000, "CALL": 700, "CALLCODE": 700,
    "RETURN": 0, "DELEGATECALL": 700, "STATICCALL": 700,
    "REVERT": 0, "SELFDESTRUCT": 5000,
    
    # Logging
    "LOG0": 375, "LOG1": 750, "LOG2": 1125, "LOG3": 1500, "LOG4": 1875,
    
    # System
    "STOP": 0,
}

# Maximum stack depth
MAX_STACK_DEPTH = 1024

# Maximum memory size (in bytes)
MAX_MEMORY_SIZE = 2 ** 20  # 1 MB


# ─── EVM STATE ──────────────────────────────────────────────────────────

class EVMState:
    """
    Represents the execution state of the EVM.
    Includes stack, memory, storage, and gas tracking.
    """
    
    def __init__(self, gas_limit: int = 1000000):
        self.stack: List[int] = []
        self.memory: bytearray = bytearray()
        self.storage: Dict[int, int] = {}  # key-value store (256-bit to 256-bit)
        self.gas_remaining: int = gas_limit
        self.gas_used: int = 0
        self.pc: int = 0  # Program counter
        self.stopped: bool = False
        self.reverted: bool = False
        self.return_data: bytes = b""
        self.logs: List[Dict] = []
        
    def consume_gas(self, amount: int) -> bool:
        """Consume gas. Returns False if out of gas."""
        if self.gas_remaining < amount:
            return False
        self.gas_remaining -= amount
        self.gas_used += amount
        return True
    
    def push(self, value: int):
        """Push value onto stack."""
        if len(self.stack) >= MAX_STACK_DEPTH:
            raise Exception("Stack overflow")
        # Ensure 256-bit value
        self.stack.append(value & ((1 << 256) - 1))
    
    def pop(self) -> int:
        """Pop value from stack."""
        if not self.stack:
            raise Exception("Stack underflow")
        return self.stack.pop()
    
    def peek(self, depth: int = 0) -> int:
        """Peek at stack value at depth."""
        if depth >= len(self.stack):
            raise Exception("Stack underflow")
        return self.stack[-(depth + 1)]
    
    def swap(self, depth: int):
        """Swap top of stack with value at depth."""
        if depth >= len(self.stack):
            raise Exception("Stack underflow")
        self.stack[-1], self.stack[-(depth + 1)] = self.stack[-(depth + 1)], self.stack[-1]
    
    def dup(self, depth: int):
        """Duplicate stack value at depth."""
        if depth > len(self.stack):
            raise Exception("Stack underflow")
        self.push(self.stack[-(depth)])
    
    def memory_write(self, offset: int, data: bytes):
        """Write data to memory at offset."""
        end = offset + len(data)
        if end > MAX_MEMORY_SIZE:
            raise Exception("Memory limit exceeded")
        if end > len(self.memory):
            self.memory.extend(b'\x00' * (end - len(self.memory)))
        self.memory[offset:end] = data
    
    def memory_read(self, offset: int, size: int) -> bytes:
        """Read data from memory."""
        if offset + size > len(self.memory):
            # Expand memory with zeros
            self.memory.extend(b'\x00' * (offset + size - len(self.memory)))
        return bytes(self.memory[offset:offset + size])


# ─── EVM EXECUTOR ───────────────────────────────────────────────────────

class ThronosEVM:
    """
    Thronos Ethereum Virtual Machine implementation.
    Executes smart contract bytecode in a sandboxed environment.
    """
    
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.contracts_file = os.path.join(data_dir, "evm_contracts.json")
        self.contracts: Dict[str, Dict] = self._load_contracts()
    
    def _load_contracts(self) -> Dict[str, Dict]:
        """Load deployed contracts from storage."""
        try:
            if os.path.exists(self.contracts_file):
                with open(self.contracts_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"[EVM] Error loading contracts: {e}")
        return {}
    
    def _save_contracts(self):
        """Save contracts to storage."""
        try:
            with open(self.contracts_file, 'w') as f:
                json.dump(self.contracts, f, indent=2)
        except Exception as e:
            print(f"[EVM] Error saving contracts: {e}")
    
    def deploy_contract(
        self,
        bytecode: str,
        deployer: str,
        value: float = 0.0,
        gas_limit: int = 1000000
    ) -> Tuple[bool, Optional[str], str]:
        """
        Deploy a new smart contract.
        
        Args:
            bytecode: Contract bytecode (hex string)
            deployer: THR address of deployer
            value: THR amount sent with deployment
            gas_limit: Maximum gas for deployment
        
        Returns:
            (success, contract_address, message)
        """
        try:
            # Generate contract address (simplified)
            nonce = len(self.contracts)
            contract_addr = f"CONTRACT_{hashlib.sha256(f'{deployer}{nonce}'.encode()).hexdigest()[:40]}"
            
            # Create execution context
            state = EVMState(gas_limit)
            context = {
                "contract_address": contract_addr,
                "sender": deployer,
                "value": value,
                "data": b"",
                "block_number": 0,
                "timestamp": int(time.time()),
            }
            
            # Execute constructor (bytecode is constructor + runtime code)
            success, result = self._execute_bytecode(bytecode, state, context)
            
            if not success:
                return False, None, f"Deployment failed: {result}"
            
            # Store deployed contract
            self.contracts[contract_addr] = {
                "address": contract_addr,
                "bytecode": bytecode,
                "deployer": deployer,
                "storage": {},
                "balance": value,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            }
            self._save_contracts()
            
            return True, contract_addr, f"Contract deployed at {contract_addr}"
            
        except Exception as e:
            return False, None, f"Deployment error: {str(e)}"
    
    def call_contract(
        self,
        contract_address: str,
        caller: str,
        data: bytes,
        value: float = 0.0,
        gas_limit: int = 1000000
    ) -> Tuple[bool, Any, int]:
        """
        Call a deployed contract.
        
        Args:
            contract_address: Address of contract to call
            caller: THR address of caller
            data: Call data (function selector + arguments)
            value: THR amount sent with call
            gas_limit: Maximum gas for execution
        
        Returns:
            (success, return_data, gas_used)
        """
        try:
            # Check if contract exists
            if contract_address not in self.contracts:
                return False, "Contract not found", 0
            
            contract = self.contracts[contract_address]
            
            # Create execution context
            state = EVMState(gas_limit)
            # Load contract storage
            state.storage = contract.get("storage", {})
            
            context = {
                "contract_address": contract_address,
                "sender": caller,
                "value": value,
                "data": data,
                "block_number": 0,
                "timestamp": int(time.time()),
            }
            
            # Execute contract bytecode
            success, result = self._execute_bytecode(
                contract["bytecode"],
                state,
                context
            )
            
            # Save updated storage
            contract["storage"] = state.storage
            self._save_contracts()
            
            return success, result, state.gas_used
            
        except Exception as e:
            return False, f"Execution error: {str(e)}", 0
    
    def _execute_bytecode(
        self,
        bytecode: str,
        state: EVMState,
        context: Dict
    ) -> Tuple[bool, Any]:
        """
        Execute EVM bytecode.
        
        This is a simplified interpreter that executes basic opcodes.
        For production, this would need full EVM opcode support.
        
        Args:
            bytecode: Hex string of bytecode
            state: EVM execution state
            context: Execution context (sender, value, etc.)
        
        Returns:
            (success, result_or_error)
        """
        try:
            # Convert hex bytecode to bytes
            if bytecode.startswith("0x"):
                bytecode = bytecode[2:]
            code = bytes.fromhex(bytecode)
            
            # Execution loop
            while state.pc < len(code) and not state.stopped:
                # Check gas
                if state.gas_remaining <= 0:
                    state.reverted = True
                    return False, "Out of gas"
                
                # Fetch opcode
                opcode = code[state.pc]
                state.pc += 1
                
                # Execute opcode
                try:
                    self._execute_opcode(opcode, code, state, context)
                except Exception as e:
                    state.reverted = True
                    return False, f"Execution error: {str(e)}"
            
            # Check if reverted
            if state.reverted:
                return False, state.return_data
            
            return True, state.return_data
            
        except Exception as e:
            return False, f"Bytecode execution error: {str(e)}"
    
    def _execute_opcode(
        self,
        opcode: int,
        code: bytes,
        state: EVMState,
        context: Dict
    ):
        """
        Execute a single opcode.
        
        This is a simplified implementation with core opcodes.
        A full implementation would include all ~140 EVM opcodes.
        """
        
        # STOP
        if opcode == 0x00:
            if not state.consume_gas(GAS_COSTS.get("STOP", 0)):
                raise Exception("Out of gas")
            state.stopped = True
        
        # ADD
        elif opcode == 0x01:
            if not state.consume_gas(GAS_COSTS.get("ADD", 3)):
                raise Exception("Out of gas")
            a = state.pop()
            b = state.pop()
            state.push((a + b) & ((1 << 256) - 1))
        
        # MUL
        elif opcode == 0x02:
            if not state.consume_gas(GAS_COSTS.get("MUL", 5)):
                raise Exception("Out of gas")
            a = state.pop()
            b = state.pop()
            state.push((a * b) & ((1 << 256) - 1))
        
        # SUB
        elif opcode == 0x03:
            if not state.consume_gas(GAS_COSTS.get("SUB", 3)):
                raise Exception("Out of gas")
            a = state.pop()
            b = state.pop()
            state.push((a - b) & ((1 << 256) - 1))
        
        # DIV
        elif opcode == 0x04:
            if not state.consume_gas(GAS_COSTS.get("DIV", 5)):
                raise Exception("Out of gas")
            a = state.pop()
            b = state.pop()
            if b == 0:
                state.push(0)
            else:
                state.push(a // b)
        
        # LT (Less Than)
        elif opcode == 0x10:
            if not state.consume_gas(GAS_COSTS.get("LT", 3)):
                raise Exception("Out of gas")
            a = state.pop()
            b = state.pop()
            state.push(1 if a < b else 0)
        
        # GT (Greater Than)
        elif opcode == 0x11:
            if not state.consume_gas(GAS_COSTS.get("GT", 3)):
                raise Exception("Out of gas")
            a = state.pop()
            b = state.pop()
            state.push(1 if a > b else 0)
        
        # EQ (Equal)
        elif opcode == 0x14:
            if not state.consume_gas(GAS_COSTS.get("EQ", 3)):
                raise Exception("Out of gas")
            a = state.pop()
            b = state.pop()
            state.push(1 if a == b else 0)
        
        # ISZERO
        elif opcode == 0x15:
            if not state.consume_gas(GAS_COSTS.get("ISZERO", 3)):
                raise Exception("Out of gas")
            a = state.pop()
            state.push(1 if a == 0 else 0)
        
        # POP
        elif opcode == 0x50:
            if not state.consume_gas(GAS_COSTS.get("POP", 2)):
                raise Exception("Out of gas")
            state.pop()
        
        # MLOAD
        elif opcode == 0x51:
            if not state.consume_gas(GAS_COSTS.get("MLOAD", 3)):
                raise Exception("Out of gas")
            offset = state.pop()
            data = state.memory_read(offset, 32)
            state.push(int.from_bytes(data, 'big'))
        
        # MSTORE
        elif opcode == 0x52:
            if not state.consume_gas(GAS_COSTS.get("MSTORE", 3)):
                raise Exception("Out of gas")
            offset = state.pop()
            value = state.pop()
            state.memory_write(offset, value.to_bytes(32, 'big'))
        
        # SLOAD (Storage Load)
        elif opcode == 0x54:
            if not state.consume_gas(GAS_COSTS.get("SLOAD", 200)):
                raise Exception("Out of gas")
            key = state.pop()
            value = state.storage.get(key, 0)
            state.push(value)
        
        # SSTORE (Storage Store)
        elif opcode == 0x55:
            if not state.consume_gas(GAS_COSTS.get("SSTORE", 5000)):
                raise Exception("Out of gas")
            key = state.pop()
            value = state.pop()
            state.storage[key] = value
        
        # JUMP
        elif opcode == 0x56:
            if not state.consume_gas(GAS_COSTS.get("JUMP", 8)):
                raise Exception("Out of gas")
            dest = state.pop()
            state.pc = dest
        
        # JUMPI (Conditional Jump)
        elif opcode == 0x57:
            if not state.consume_gas(GAS_COSTS.get("JUMPI", 10)):
                raise Exception("Out of gas")
            dest = state.pop()
            cond = state.pop()
            if cond != 0:
                state.pc = dest
        
        # PC (Program Counter)
        elif opcode == 0x58:
            if not state.consume_gas(GAS_COSTS.get("PC", 2)):
                raise Exception("Out of gas")
            state.push(state.pc - 1)
        
        # JUMPDEST
        elif opcode == 0x5b:
            if not state.consume_gas(GAS_COSTS.get("JUMPDEST", 1)):
                raise Exception("Out of gas")
            # Valid jump destination marker
            pass
        
        # PUSH1-PUSH32 (0x60-0x7f)
        elif 0x60 <= opcode <= 0x7f:
            if not state.consume_gas(GAS_COSTS.get("PUSH", 3)):
                raise Exception("Out of gas")
            size = opcode - 0x5f
            if state.pc + size > len(code):
                raise Exception("Invalid PUSH: not enough bytes")
            value = int.from_bytes(code[state.pc:state.pc + size], 'big')
            state.pc += size
            state.push(value)
        
        # DUP1-DUP16 (0x80-0x8f)
        elif 0x80 <= opcode <= 0x8f:
            if not state.consume_gas(GAS_COSTS.get("DUP", 3)):
                raise Exception("Out of gas")
            depth = opcode - 0x7f
            state.dup(depth)
        
        # SWAP1-SWAP16 (0x90-0x9f)
        elif 0x90 <= opcode <= 0x9f:
            if not state.consume_gas(GAS_COSTS.get("SWAP", 3)):
                raise Exception("Out of gas")
            depth = opcode - 0x8f
            state.swap(depth)
        
        # RETURN
        elif opcode == 0xf3:
            if not state.consume_gas(GAS_COSTS.get("RETURN", 0)):
                raise Exception("Out of gas")
            offset = state.pop()
            size = state.pop()
            state.return_data = state.memory_read(offset, size)
            state.stopped = True
        
        # REVERT
        elif opcode == 0xfd:
            if not state.consume_gas(GAS_COSTS.get("REVERT", 0)):
                raise Exception("Out of gas")
            offset = state.pop()
            size = state.pop()
            state.return_data = state.memory_read(offset, size)
            state.reverted = True
            state.stopped = True
        
        else:
            # Unsupported opcode
            raise Exception(f"Unsupported opcode: 0x{opcode:02x}")
    
    def get_contract(self, address: str) -> Optional[Dict]:
        """Get contract details by address."""
        return self.contracts.get(address)
    
    def get_storage(self, address: str, key: int) -> int:
        """Get storage value for a contract."""
        contract = self.contracts.get(address)
        if not contract:
            return 0
        return contract.get("storage", {}).get(key, 0)
    
    def list_contracts(self) -> List[Dict]:
        """List all deployed contracts."""
        return list(self.contracts.values())


# ─── HELPER FUNCTIONS ───────────────────────────────────────────────────

def compile_solidity_stub(source_code: str) -> str:
    """
    Stub function for Solidity compilation.
    In production, this would call solc compiler.
    
    For now, returns a simple bytecode placeholder.
    """
    # This is a placeholder. Real implementation would use:
    # - py-solc-x library
    # - solc binary
    # - Or integrate with Remix API
    
    return "0x6080604052348015600f57600080fd5b50603f80601d6000396000f3fe6080604052600080fdfea2646970667358221220"


def estimate_gas(bytecode: str, data: bytes = b"") -> int:
    """
    Estimate gas cost for contract deployment or call.
    
    This is a simplified estimation.
    """
    base_cost = 21000  # Base transaction cost
    code_cost = len(bytecode) // 2 * 200  # Per byte of code
    data_cost = len(data) * 16  # Per byte of data
    
    return base_cost + code_cost + data_cost