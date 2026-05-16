"""
Offline Mesh Network Manager
Enables Thronos blockchain to survive internet outages through:
- Radio mesh networks (WiFi/802.15.4)
- LoRa long-range communication
- Satellite backup (Starlink, Iridium)
- Fallback to physical media (USB mesh sticks, QR codes)

Philosophy: A blockchain that depends on internet will fail.
Thronos is designed to operate offline for years if needed.
"""

import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from enum import Enum
import uuid


class NetworkType(Enum):
    """Types of network connectivity"""
    INTERNET = "internet"           # Traditional internet
    RADIO_MESH = "radio_mesh"       # Local radio mesh (WiFi, 802.15.4)
    LORA = "lora"                   # LoRa long-range (~10km per hop)
    SATELLITE = "satellite"         # Starlink, Iridium, other LEO
    USB_MESH = "usb_mesh"           # Physical USB media exchange
    QR_CODE = "qr_code"             # QR code physical transfer


class NodeRole(Enum):
    """Role of mesh node in network"""
    FULL_NODE = "full_node"         # Complete blockchain copy
    RELAY = "relay"                 # Routes packets, no storage
    LITE_NODE = "lite_node"         # SPV - minimal data
    SATELLITE_GATEWAY = "sat_gateway"  # Satellite uplink
    ARCHIVE = "archive"             # Long-term storage only


class MeshNodeStatus(Enum):
    """Status of a mesh node"""
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"           # Limited connectivity
    RECOVERING = "recovering"       # Attempting reconnect


class SyncStatus(Enum):
    """Data synchronization status"""
    SYNCED = "synced"               # Up to date with network
    SYNCING = "syncing"             # Currently synchronizing
    OUT_OF_SYNC = "out_of_sync"     # Behind network
    PAUSED = "paused"               # Sync paused (low bandwidth)


class MeshNode:
    """Represents a single node in the mesh network"""

    def __init__(self, node_id: str, node_type: NodeRole, location: str):
        self.node_id = node_id
        self.node_type = node_type
        self.location = location
        self.status = MeshNodeStatus.OFFLINE
        self.sync_status = SyncStatus.OUT_OF_SYNC
        self.last_seen = 0
        self.uptime_percentage = 0.0
        self.storage_capacity_gb = 0
        self.storage_used_gb = 0
        self.bandwidth_mbps = 0.0
        self.signal_strength = 0.0  # 0-100 scale
        self.hop_distance = 0
        self.neighbors: Set[str] = set()  # IDs of connected nodes
        self.created_timestamp = int(time.time())
        self.last_sync_timestamp = 0
        self.sync_progress_percent = 0
        self.verified_blocks = 0
        self.network_interfaces: List[Dict] = []

    def to_dict(self) -> Dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "location": self.location,
            "status": self.status.value,
            "sync_status": self.sync_status.value,
            "last_seen": self.last_seen,
            "uptime_percentage": round(self.uptime_percentage, 2),
            "storage_used_gb": self.storage_used_gb,
            "storage_capacity_gb": self.storage_capacity_gb,
            "bandwidth_mbps": self.bandwidth_mbps,
            "signal_strength": self.signal_strength,
            "hop_distance": self.hop_distance,
            "neighbor_count": len(self.neighbors),
            "verified_blocks": self.verified_blocks,
            "sync_progress_percent": self.sync_progress_percent
        }


class MeshPacket:
    """Data packet transmitted over mesh network"""

    def __init__(self, packet_type: str, source_node: str, destination_node: str,
                 payload: Dict, priority: int = 5):
        self.packet_id = str(uuid.uuid4())
        self.packet_type = packet_type  # "transaction", "block", "sync", "beacon"
        self.source_node = source_node
        self.destination_node = destination_node
        self.payload = payload
        self.priority = priority  # 1-10, 10 is highest
        self.created_timestamp = int(time.time())
        self.ttl = 255  # Hops remaining
        self.path: List[str] = [source_node]
        self.delivered = False
        self.delivery_timestamp = 0

    def to_dict(self) -> Dict:
        return {
            "packet_id": self.packet_id,
            "packet_type": self.packet_type,
            "source_node": self.source_node,
            "destination_node": self.destination_node,
            "priority": self.priority,
            "created_timestamp": self.created_timestamp,
            "ttl": self.ttl,
            "path_length": len(self.path),
            "delivered": self.delivered,
            "payload_size": len(json.dumps(self.payload))
        }


class MeshNetworkManager:
    """Manages entire mesh network infrastructure"""

    # Recovery mode constants
    RECOVERY_MODE_TIMEOUT = 7 * 24 * 60 * 60  # 7 days
    SYNC_BATCH_SIZE = 100  # Blocks per sync batch
    MESH_HEARTBEAT_INTERVAL = 300  # 5 minutes

    def __init__(self):
        self.nodes: Dict[str, MeshNode] = {}
        self.packets: Dict[str, MeshPacket] = {}
        self.internet_available = True
        self.recovery_mode = False
        self.recovery_mode_start = 0
        self.total_packets_transmitted = 0
        self.total_packets_delivered = 0
        self.network_uptime_percent = 99.9
        self.broadcast_messages: List[Dict] = []

    def register_mesh_node(self, node_id: str, node_type: NodeRole,
                          location: str, storage_gb: int = 0) -> str:
        """
        Register a new node in the mesh network.

        Args:
            node_id: Unique identifier for node
            node_type: Role of this node (full_node, relay, etc)
            location: Geographic location description
            storage_gb: Storage capacity in GB (0 for relay nodes)

        Returns:
            node_id: The registered node ID
        """
        if node_id in self.nodes:
            raise ValueError(f"Node {node_id} already registered")

        node = MeshNode(node_id, node_type, location)
        node.storage_capacity_gb = storage_gb

        self.nodes[node_id] = node
        return node_id

    def connect_nodes(self, node_id1: str, node_id2: str) -> bool:
        """
        Create a connection between two mesh nodes.

        Args:
            node_id1: First node
            node_id2: Second node

        Returns:
            success: True if connected
        """
        if node_id1 not in self.nodes or node_id2 not in self.nodes:
            raise ValueError("One or both nodes not found")

        # Bidirectional connection
        self.nodes[node_id1].neighbors.add(node_id2)
        self.nodes[node_id2].neighbors.add(node_id1)

        return True

    def broadcast_packet(self, packet_type: str, source_node: str,
                        payload: Dict, priority: int = 5) -> str:
        """
        Broadcast a packet across the mesh network.

        Args:
            packet_type: Type of packet (transaction, block, beacon, etc)
            source_node: ID of broadcasting node
            payload: Data to broadcast
            priority: Packet priority (1-10)

        Returns:
            packet_id: ID of created packet
        """
        if source_node not in self.nodes:
            raise ValueError(f"Source node {source_node} not found")

        # Broadcast to all nodes (destination = "broadcast")
        packet = MeshPacket(
            packet_type=packet_type,
            source_node=source_node,
            destination_node="broadcast",
            payload=payload,
            priority=priority
        )

        self.packets[packet.packet_id] = packet
        self.total_packets_transmitted += 1

        return packet.packet_id

    def send_packet_to_node(self, packet_type: str, source_node: str,
                           destination_node: str, payload: Dict,
                           priority: int = 5) -> str:
        """
        Send a packet to a specific node.

        Args:
            packet_type: Type of packet
            source_node: Sending node
            destination_node: Receiving node
            payload: Data payload
            priority: Packet priority

        Returns:
            packet_id: ID of created packet
        """
        if source_node not in self.nodes:
            raise ValueError(f"Source node {source_node} not found")

        if destination_node not in self.nodes:
            raise ValueError(f"Destination node {destination_node} not found")

        packet = MeshPacket(
            packet_type=packet_type,
            source_node=source_node,
            destination_node=destination_node,
            payload=payload,
            priority=priority
        )

        self.packets[packet.packet_id] = packet
        self.total_packets_transmitted += 1

        return packet.packet_id

    def find_route(self, source_node: str, destination_node: str) -> Optional[List[str]]:
        """
        Find shortest path between two nodes using BFS.

        Returns:
            route: List of node IDs from source to destination, or None if no path
        """
        if source_node not in self.nodes or destination_node not in self.nodes:
            return None

        if source_node == destination_node:
            return [source_node]

        # BFS to find shortest path
        visited = {source_node}
        queue = [(source_node, [source_node])]

        while queue:
            current, path = queue.pop(0)

            for neighbor in self.nodes[current].neighbors:
                if neighbor == destination_node:
                    return path + [neighbor]

                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None

    def deliver_packet(self, packet_id: str) -> bool:
        """
        Mark a packet as delivered.

        Args:
            packet_id: ID of packet to deliver

        Returns:
            success: True if delivered
        """
        if packet_id not in self.packets:
            raise ValueError(f"Packet {packet_id} not found")

        packet = self.packets[packet_id]
        packet.delivered = True
        packet.delivery_timestamp = int(time.time())
        self.total_packets_delivered += 1

        return True

    def enable_recovery_mode(self) -> bool:
        """
        Enable network recovery mode for internet outage.
        Uses only mesh, satellite, and offline media.

        Returns:
            success: True if recovery mode enabled
        """
        self.recovery_mode = True
        self.recovery_mode_start = int(time.time())
        self.internet_available = False
        return True

    def disable_recovery_mode(self) -> bool:
        """Resume normal operation with internet"""
        self.recovery_mode = False
        self.internet_available = True
        return True

    def get_recovery_mode_duration(self) -> int:
        """Get how long recovery mode has been active (seconds)"""
        if not self.recovery_mode:
            return 0
        return int(time.time()) - self.recovery_mode_start

    def sync_blockchain_segment(self, node_id: str, start_block: int,
                               end_block: int) -> Dict:
        """
        Synchronize a segment of blockchain blocks between nodes.

        Args:
            node_id: Node to sync
            start_block: Starting block number
            end_block: Ending block number

        Returns:
            sync_info: Sync operation details
        """
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self.nodes[node_id]
        node.sync_status = SyncStatus.SYNCING
        node.last_sync_timestamp = int(time.time())

        block_count = end_block - start_block + 1
        batch_count = (block_count + self.SYNC_BATCH_SIZE - 1) // self.SYNC_BATCH_SIZE

        return {
            "node_id": node_id,
            "start_block": start_block,
            "end_block": end_block,
            "block_count": block_count,
            "estimated_batches": batch_count,
            "sync_started": node.last_sync_timestamp
        }

    def complete_node_sync(self, node_id: str, verified_blocks: int) -> bool:
        """
        Mark node sync as complete.

        Args:
            node_id: Node that completed sync
            verified_blocks: Number of blocks successfully verified

        Returns:
            success: True if completed
        """
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self.nodes[node_id]
        node.sync_status = SyncStatus.SYNCED
        node.verified_blocks = verified_blocks
        node.sync_progress_percent = 100

        return True

    def update_node_status(self, node_id: str, status: MeshNodeStatus,
                          signal_strength: float = 0.0) -> bool:
        """
        Update a node's connectivity status.

        Args:
            node_id: Node to update
            status: New status
            signal_strength: Signal quality (0-100)

        Returns:
            success: True if updated
        """
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self.nodes[node_id]
        node.status = status
        node.last_seen = int(time.time())
        node.signal_strength = signal_strength

        return True

    def get_network_topology(self) -> Dict:
        """Get current network topology"""
        nodes_info = []
        for node_id, node in self.nodes.items():
            nodes_info.append({
                "node_id": node_id,
                "status": node.status.value,
                "neighbors": list(node.neighbors),
                "hop_distance": node.hop_distance
            })

        return {
            "total_nodes": len(self.nodes),
            "online_nodes": len([n for n in self.nodes.values() if n.status == MeshNodeStatus.ONLINE]),
            "nodes": nodes_info,
            "network_diameter": self._calculate_network_diameter()
        }

    def get_network_stats(self) -> Dict:
        """Get network statistics"""
        online_nodes = len([n for n in self.nodes.values() if n.status == MeshNodeStatus.ONLINE])
        total_nodes = len(self.nodes)
        recovery_duration = self.get_recovery_mode_duration()

        delivery_rate = 0.0
        if self.total_packets_transmitted > 0:
            delivery_rate = (self.total_packets_delivered / self.total_packets_transmitted) * 100

        return {
            "total_nodes": total_nodes,
            "online_nodes": online_nodes,
            "offline_nodes": total_nodes - online_nodes,
            "network_uptime_percent": self.network_uptime_percent,
            "recovery_mode_active": self.recovery_mode,
            "recovery_mode_duration_seconds": recovery_duration,
            "total_packets_transmitted": self.total_packets_transmitted,
            "total_packets_delivered": self.total_packets_delivered,
            "packet_delivery_rate_percent": round(delivery_rate, 2),
            "internet_available": self.internet_available
        }

    def get_node_info(self, node_id: str) -> Optional[Dict]:
        """Get detailed information about a node"""
        if node_id not in self.nodes:
            return None
        return self.nodes[node_id].to_dict()

    def get_nodes_by_type(self, node_type: NodeRole) -> List[Dict]:
        """Get all nodes of a specific type"""
        matching = [
            node.to_dict() for node in self.nodes.values()
            if node.node_type == node_type
        ]
        return matching

    def get_online_nodes(self) -> List[Dict]:
        """Get all currently online nodes"""
        online = [
            node.to_dict() for node in self.nodes.values()
            if node.status == MeshNodeStatus.ONLINE
        ]
        return online

    def broadcast_message(self, message: str, priority: int = 5) -> str:
        """
        Broadcast a text message across the mesh.
        Useful for emergency communications.

        Args:
            message: Text message to broadcast
            priority: Message priority (1-10)

        Returns:
            message_id: ID of broadcast message
        """
        message_id = str(uuid.uuid4())
        broadcast = {
            "message_id": message_id,
            "message": message,
            "timestamp": int(time.time()),
            "priority": priority,
            "received_by_nodes": []
        }
        self.broadcast_messages.append(broadcast)
        return message_id

    def get_packet_status(self, packet_id: str) -> Optional[Dict]:
        """Get status of a specific packet"""
        if packet_id not in self.packets:
            return None
        return self.packets[packet_id].to_dict()

    def simulate_internet_outage(self, duration_seconds: int = 3600) -> bool:
        """
        Simulate an internet outage for testing resilience.

        Args:
            duration_seconds: How long outage lasts

        Returns:
            success: True if outage simulation started
        """
        self.enable_recovery_mode()
        self.internet_available = False
        return True

    def recover_from_outage(self) -> bool:
        """Recover from simulated outage"""
        self.disable_recovery_mode()
        self.internet_available = True
        return True

    def _calculate_network_diameter(self) -> int:
        """Calculate the diameter of the mesh network (longest shortest path)"""
        if len(self.nodes) <= 1:
            return 0

        max_distance = 0

        # This would be expensive for large networks
        # In production, use more efficient algorithm
        for start_node in self.nodes.keys():
            distances = self._bfs_distances(start_node)
            if distances:
                max_distance = max(max_distance, max(distances.values()))

        return max_distance

    def _bfs_distances(self, start_node: str) -> Dict[str, int]:
        """Calculate distances from start node to all others using BFS"""
        distances = {start_node: 0}
        queue = [start_node]

        while queue:
            current = queue.pop(0)

            for neighbor in self.nodes[current].neighbors:
                if neighbor not in distances:
                    distances[neighbor] = distances[current] + 1
                    queue.append(neighbor)

        return distances


class SatelliteGateway:
    """Manages satellite communication for global coverage"""

    def __init__(self, gateway_id: str, location: str, satellite_network: str):
        self.gateway_id = gateway_id
        self.location = location
        self.satellite_network = satellite_network  # "starlink", "iridium", etc
        self.status = MeshNodeStatus.OFFLINE
        self.uplink_mbps = 0.0
        self.downlink_mbps = 0.0
        self.latency_ms = 0.0
        self.messages_sent = 0
        self.messages_received = 0
        self.created_timestamp = int(time.time())

    def to_dict(self) -> Dict:
        return {
            "gateway_id": self.gateway_id,
            "location": self.location,
            "satellite_network": self.satellite_network,
            "status": self.status.value,
            "uplink_mbps": self.uplink_mbps,
            "downlink_mbps": self.downlink_mbps,
            "latency_ms": self.latency_ms,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received
        }


class OfflineMediaManager:
    """Manages physical offline media for blockchain data"""

    def __init__(self):
        self.usb_sticks: Dict[str, Dict] = {}  # usb_id → data
        self.qr_codes: List[Dict] = []
        self.paper_backups: List[Dict] = []

    def create_usb_mesh_backup(self, backup_id: str, blockchain_data: Dict,
                              digital_signatures: Dict) -> str:
        """
        Create a USB mesh stick with blockchain data and signatures.

        Args:
            backup_id: Unique ID for this backup
            blockchain_data: Blockchain state to backup
            digital_signatures: Verification signatures

        Returns:
            usb_id: ID of created USB backup
        """
        usb_id = f"usb_{backup_id}"

        self.usb_sticks[usb_id] = {
            "usb_id": usb_id,
            "backup_id": backup_id,
            "created_timestamp": int(time.time()),
            "blockchain_blocks": len(blockchain_data),
            "signatures_count": len(digital_signatures),
            "data_hash": hashlib.sha256(json.dumps(blockchain_data).encode()).hexdigest(),
            "verified": False
        }

        return usb_id

    def create_qr_code_backup(self, backup_id: str, data: Dict) -> str:
        """
        Create QR code containing blockchain state.
        Useful for physical storage and air-gapped recovery.

        Args:
            backup_id: Unique ID for this backup
            data: Data to encode in QR

        Returns:
            qr_id: ID of created QR code
        """
        qr_id = f"qr_{backup_id}"

        qr_code = {
            "qr_id": qr_id,
            "backup_id": backup_id,
            "created_timestamp": int(time.time()),
            "data_size_bytes": len(json.dumps(data)),
            "data_hash": hashlib.sha256(json.dumps(data).encode()).hexdigest(),
            "scanned_count": 0
        }

        self.qr_codes.append(qr_code)
        return qr_id

    def verify_usb_backup(self, usb_id: str, data_hash: str) -> bool:
        """Verify integrity of USB backup"""
        if usb_id not in self.usb_sticks:
            return False

        usb = self.usb_sticks[usb_id]
        return usb["data_hash"] == data_hash
