"""
Core Node Management System
Manages blockchain infrastructure nodes (hospitals, universities, charities, mesh networks, archives)
that receive 5% of Epoch 3+ block rewards for providing services to humanity.

Philosophy: Stop burning value. Start building infrastructure.
Every core node funds real services: medical care, education, research, connectivity, knowledge.
"""

import json
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
import uuid


class NodeType(Enum):
    """Core node types and their characteristics"""
    HOSPITAL = "hospital"           # Medical facilities
    UNIVERSITY = "university"       # Educational institutions
    CHARITY = "charity"             # Non-profit organizations
    MESH = "mesh"                   # Offline network operators
    ARCHIVE = "archive"             # Data archival nodes


class NodeStatus(Enum):
    """Node registration status"""
    REGISTERED = "registered"       # Initial registration (pending DAO approval)
    DAO_APPROVED = "dao_approved"   # Approved by community vote
    ACTIVE = "active"               # Receiving rewards
    SUSPENDED = "suspended"         # Temporarily paused
    DEACTIVATED = "deactivated"     # Permanently removed


class CoreNode:
    """Represents a single core node in the network"""

    def __init__(self, node_id: str, organization_address: str, node_type: NodeType,
                 organization_name: str, mission: str, legal_registration_hash: str):
        self.node_id = node_id
        self.organization_address = organization_address
        self.node_type = node_type
        self.organization_name = organization_name
        self.mission = mission
        self.legal_registration_hash = legal_registration_hash
        self.registered_block = 0
        self.registered_timestamp = int(time.time())
        self.dao_approval_percentage = 0
        self.status = NodeStatus.REGISTERED
        self.reward_tier = 1
        self.impact_metric = 0  # How many people served/students/patients
        self.total_rewards_earned = 0.0
        self.reporting_url = ""
        self.last_report_timestamp = 0
        self.impact_reports: List[Dict] = []
        self.reward_history: List[Dict] = []

    def to_dict(self) -> Dict:
        """Convert to dictionary representation"""
        return {
            "node_id": self.node_id,
            "organization_address": self.organization_address,
            "node_type": self.node_type.value,
            "organization_name": self.organization_name,
            "mission": self.mission,
            "legal_registration_hash": self.legal_registration_hash,
            "registered_block": self.registered_block,
            "registered_timestamp": self.registered_timestamp,
            "dao_approval_percentage": self.dao_approval_percentage,
            "status": self.status.value,
            "reward_tier": self.reward_tier,
            "impact_metric": self.impact_metric,
            "total_rewards_earned": self.total_rewards_earned,
            "reporting_url": self.reporting_url,
            "last_report_timestamp": self.last_report_timestamp,
            "impact_reports_count": len(self.impact_reports),
            "rewards_distributed": len(self.reward_history)
        }


class ImpactReport:
    """Quarterly or annual impact report from a core node"""

    def __init__(self, node_id: str, people_served: int, services_delivered: int,
                 report_hash: str, report_url: str = ""):
        self.node_id = node_id
        self.report_id = str(uuid.uuid4())
        self.people_served = people_served
        self.services_delivered = services_delivered
        self.report_hash = report_hash
        self.report_url = report_url
        self.report_timestamp = int(time.time())
        self.dao_approved = False

    def to_dict(self) -> Dict:
        return {
            "report_id": self.report_id,
            "node_id": self.node_id,
            "people_served": self.people_served,
            "services_delivered": self.services_delivered,
            "report_hash": self.report_hash,
            "report_url": self.report_url,
            "report_timestamp": self.report_timestamp,
            "dao_approved": self.dao_approved
        }


class CoreNodeRegistry:
    """Central registry managing all core nodes in the Thronos network"""

    # Epoch 3 constants
    EPOCH3_BLOCK_REWARD = 0.125
    CORE_NODE_ALLOCATION = 0.05  # 5% of rewards
    BASE_REWARD_PER_BLOCK = 0.00625  # 0.00625 THR base

    # Impact bonus per unit by node type (THR per unit)
    IMPACT_BONUSES = {
        NodeType.HOSPITAL: 0.001,    # 0.001 THR per patient served
        NodeType.UNIVERSITY: 0.001,  # 0.001 THR per student
        NodeType.CHARITY: 0.0005,    # 0.0005 THR per person helped
        NodeType.MESH: 0.0001,       # 0.0001 THR per km² coverage
        NodeType.ARCHIVE: 0.0001     # 0.0001 THR per TB stored
    }

    def __init__(self):
        self.nodes: Dict[str, CoreNode] = {}
        self.address_to_node_id: Dict[str, str] = {}
        self.total_registered_nodes = 0
        self.total_rewards_distributed = 0.0
        self.epoch3_start_block = 630000
        self.current_block = 0

    def register_core_node(self, organization_address: str, node_type: NodeType,
                          organization_name: str, mission: str,
                          legal_registration_hash: str) -> str:
        """
        Register a new core node. Node enters REGISTERED status pending DAO approval.

        Args:
            organization_address: Blockchain address of the organization
            node_type: Type of node (hospital, university, charity, mesh, archive)
            organization_name: Name of the organization
            mission: Mission statement/description
            legal_registration_hash: Hash of legal registration documents

        Returns:
            node_id: Unique identifier for the registered node
        """
        # Validate inputs
        if organization_address in self.address_to_node_id:
            raise ValueError(f"Organization {organization_address} already registered")

        if not organization_name or len(organization_name.strip()) == 0:
            raise ValueError("Organization name required")

        if not mission or len(mission.strip()) == 0:
            raise ValueError("Mission statement required")

        # Generate unique node ID
        node_id = self._generate_node_id(organization_address, node_type)

        # Create and register node
        node = CoreNode(
            node_id=node_id,
            organization_address=organization_address,
            node_type=node_type,
            organization_name=organization_name,
            mission=mission,
            legal_registration_hash=legal_registration_hash
        )

        self.nodes[node_id] = node
        self.address_to_node_id[organization_address] = node_id
        self.total_registered_nodes += 1

        return node_id

    def approve_node_by_dao(self, node_id: str, approval_percentage: float) -> bool:
        """
        Approve a node following DAO governance vote.

        Args:
            node_id: ID of the node to approve
            approval_percentage: DAO approval percentage (must be >= 51)

        Returns:
            success: True if approved, False if vote failed
        """
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        if approval_percentage < 51:
            raise ValueError("Approval requires 51% threshold")

        node = self.nodes[node_id]
        node.dao_approval_percentage = approval_percentage
        node.status = NodeStatus.DAO_APPROVED
        node.registered_block = self.current_block

        return True

    def activate_node(self, node_id: str) -> bool:
        """Activate a DAO-approved node to start receiving rewards"""
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self.nodes[node_id]
        if node.status != NodeStatus.DAO_APPROVED:
            raise ValueError(f"Node {node_id} not DAO approved")

        node.status = NodeStatus.ACTIVE
        return True

    def calculate_node_reward(self, node_id: str) -> float:
        """
        Calculate reward for a node based on base reward + impact bonus.

        Formula:
            reward = BASE_REWARD + (impact_metric * impact_bonus_per_unit)

        Args:
            node_id: ID of the node

        Returns:
            reward: Calculated reward in THR
        """
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self.nodes[node_id]

        if node.status != NodeStatus.ACTIVE:
            return 0.0

        # Base reward
        base_reward = self.BASE_REWARD_PER_BLOCK

        # Impact bonus
        impact_bonus_per_unit = self.IMPACT_BONUSES.get(node.node_type, 0)
        impact_bonus = node.impact_metric * impact_bonus_per_unit

        total_reward = base_reward + impact_bonus
        return round(total_reward, 8)

    def distribute_reward(self, node_id: str, reward_amount: float,
                         block_number: int, tx_hash: str = "") -> bool:
        """
        Distribute block reward to a core node.

        Args:
            node_id: ID of the node receiving reward
            reward_amount: Amount of THR to distribute
            block_number: Block number this reward is for
            tx_hash: Transaction hash on blockchain

        Returns:
            success: True if distributed successfully
        """
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self.nodes[node_id]

        if node.status != NodeStatus.ACTIVE:
            raise ValueError(f"Node {node_id} not active")

        # Record distribution
        distribution = {
            "distribution_id": str(uuid.uuid4()),
            "block_number": block_number,
            "amount": reward_amount,
            "timestamp": int(time.time()),
            "tx_hash": tx_hash
        }

        node.reward_history.append(distribution)
        node.total_rewards_earned += reward_amount
        self.total_rewards_distributed += reward_amount

        return True

    def batch_distribute_rewards(self, node_rewards: Dict[str, float],
                                block_number: int) -> Dict[str, bool]:
        """
        Distribute rewards to multiple nodes in a single epoch block.

        Args:
            node_rewards: Dict mapping node_id to reward amount
            block_number: Block number this distribution is for

        Returns:
            results: Dict mapping node_id to success status
        """
        results = {}
        for node_id, reward in node_rewards.items():
            try:
                success = self.distribute_reward(node_id, reward, block_number)
                results[node_id] = success
            except Exception as e:
                results[node_id] = False

        return results

    def submit_impact_report(self, node_id: str, people_served: int,
                            services_delivered: int, report_hash: str,
                            report_url: str = "") -> str:
        """
        Submit quarterly or annual impact report from a core node.

        Args:
            node_id: ID of the node submitting report
            people_served: Number of people served in reporting period
            services_delivered: Number of services/transactions delivered
            report_hash: IPFS hash of full report
            report_url: URL where full report is available

        Returns:
            report_id: Unique identifier for the report
        """
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self.nodes[node_id]

        if node.status != NodeStatus.ACTIVE:
            raise ValueError(f"Node {node_id} not active")

        # Create impact report
        report = ImpactReport(
            node_id=node_id,
            people_served=people_served,
            services_delivered=services_delivered,
            report_hash=report_hash,
            report_url=report_url
        )

        # Update node's impact metric and last report time
        node.impact_metric = people_served
        node.last_report_timestamp = report.report_timestamp
        node.impact_reports.append(report.to_dict())

        return report.report_id

    def approve_impact_report(self, node_id: str, report_index: int) -> bool:
        """
        Approve an impact report following DAO review.

        Args:
            node_id: ID of the node
            report_index: Index of the report in the node's reports list

        Returns:
            success: True if approved
        """
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self.nodes[node_id]

        if report_index >= len(node.impact_reports):
            raise ValueError("Report index out of range")

        node.impact_reports[report_index]["dao_approved"] = True
        return True

    def suspend_node(self, node_id: str, reason: str = "") -> bool:
        """
        Temporarily suspend a node (stops receiving rewards).

        Args:
            node_id: ID of the node to suspend
            reason: Reason for suspension

        Returns:
            success: True if suspended
        """
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self.nodes[node_id]
        node.status = NodeStatus.SUSPENDED
        return True

    def deactivate_node(self, node_id: str, reason: str = "") -> bool:
        """
        Permanently deactivate a node.

        Args:
            node_id: ID of the node to deactivate
            reason: Reason for deactivation

        Returns:
            success: True if deactivated
        """
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self.nodes[node_id]
        node.status = NodeStatus.DEACTIVATED
        return True

    def get_node_info(self, node_id: str) -> Optional[Dict]:
        """Get detailed information about a node"""
        if node_id not in self.nodes:
            return None
        return self.nodes[node_id].to_dict()

    def get_nodes_by_type(self, node_type: NodeType) -> List[Dict]:
        """Get all nodes of a specific type"""
        matching_nodes = [
            node.to_dict() for node in self.nodes.values()
            if node.node_type == node_type
        ]
        return matching_nodes

    def get_active_nodes(self) -> List[Dict]:
        """Get all currently active nodes"""
        active_nodes = [
            node.to_dict() for node in self.nodes.values()
            if node.status == NodeStatus.ACTIVE
        ]
        return active_nodes

    def get_nodes_by_status(self, status: NodeStatus) -> List[Dict]:
        """Get all nodes with a specific status"""
        matching_nodes = [
            node.to_dict() for node in self.nodes.values()
            if node.status == status
        ]
        return matching_nodes

    def get_registry_stats(self) -> Dict:
        """Get overall registry statistics"""
        active_nodes = [n for n in self.nodes.values() if n.status == NodeStatus.ACTIVE]

        stats = {
            "total_registered_nodes": self.total_registered_nodes,
            "active_nodes": len(active_nodes),
            "dao_approved_nodes": len([n for n in self.nodes.values() if n.status != NodeStatus.REGISTERED]),
            "total_rewards_distributed": round(self.total_rewards_distributed, 8),
            "nodes_by_type": {}
        }

        # Count by type
        for node_type in NodeType:
            count = len([n for n in self.nodes.values() if n.node_type == node_type])
            if count > 0:
                stats["nodes_by_type"][node_type.value] = count

        return stats

    def get_epoch3_allocation(self, block_reward: float = 0.125) -> float:
        """
        Calculate total 5% allocation for core nodes from block reward.

        Args:
            block_reward: Block reward amount

        Returns:
            allocation: 5% of block reward
        """
        return block_reward * 0.05

    def calculate_type_rewards(self, block_reward: float = 0.125) -> Dict[str, float]:
        """
        Calculate annual projected rewards per node type.

        Args:
            block_reward: Block reward amount (default 0.125 for Epoch 3)

        Returns:
            projections: Dict with annual reward projections per type
        """
        blocks_per_year = 52560  # Approximate blocks per year
        allocation_per_block = self.get_epoch3_allocation(block_reward)

        # Distribute equally among active nodes by type
        projections = {}
        for node_type in NodeType:
            nodes_of_type = len(self.get_nodes_by_type(node_type))
            if nodes_of_type > 0:
                reward_per_node = (allocation_per_block * blocks_per_year) / nodes_of_type
                projections[node_type.value] = round(reward_per_node, 8)
            else:
                projections[node_type.value] = 0.0

        return projections

    def _generate_node_id(self, organization_address: str, node_type: NodeType) -> str:
        """Generate unique node ID"""
        content = f"{organization_address}_{node_type.value}_{int(time.time())}".encode()
        hash_obj = hashlib.sha256(content)
        return f"node_{node_type.value}_{hash_obj.hexdigest()[:16]}"

    def export_nodes_json(self) -> str:
        """Export all nodes to JSON"""
        nodes_list = [node.to_dict() for node in self.nodes.values()]
        return json.dumps(nodes_list, indent=2)

    def import_nodes_json(self, json_data: str) -> int:
        """Import nodes from JSON. Returns count imported."""
        # Not implemented for security (no blind imports)
        raise NotImplementedError("Import disabled for security")


class CoreNodeRewardCalculator:
    """Calculates rewards for core nodes based on impact metrics"""

    def __init__(self, registry: CoreNodeRegistry):
        self.registry = registry

    def calculate_epoch_rewards(self, block_reward: float = 0.125) -> Dict[str, float]:
        """
        Calculate rewards for all active nodes for a block.

        Args:
            block_reward: The current block reward amount

        Returns:
            rewards: Dict mapping node_id to reward amount
        """
        active_nodes = self.registry.get_active_nodes()
        node_rewards = {}

        allocation_per_block = self.registry.get_epoch3_allocation(block_reward)

        # Calculate total reward for all active nodes
        total_calculated_reward = 0.0
        individual_rewards = {}

        for node_data in active_nodes:
            node_id = node_data["node_id"]
            node = self.registry.nodes[node_id]
            reward = self.registry.calculate_node_reward(node_id)
            individual_rewards[node_id] = reward
            total_calculated_reward += reward

        # Normalize to fit within allocation
        if total_calculated_reward > allocation_per_block:
            scaling_factor = allocation_per_block / total_calculated_reward
            for node_id, reward in individual_rewards.items():
                node_rewards[node_id] = round(reward * scaling_factor, 8)
        else:
            node_rewards = individual_rewards

        return node_rewards

    def get_annual_projection(self, node_id: str, block_reward: float = 0.125) -> float:
        """
        Project annual rewards for a specific node.

        Args:
            node_id: ID of the node
            block_reward: Block reward amount

        Returns:
            annual_reward: Projected annual THR reward
        """
        node_reward_per_block = self.registry.calculate_node_reward(node_id)
        blocks_per_year = 52560
        return round(node_reward_per_block * blocks_per_year, 8)

    def get_impact_bonus_potential(self, node_id: str, new_impact_metric: int) -> float:
        """
        Calculate how much additional reward a node could earn with new impact.

        Args:
            node_id: ID of the node
            new_impact_metric: Target impact metric (people served, students, etc)

        Returns:
            additional_reward: Additional THR per block if impact is achieved
        """
        if node_id not in self.registry.nodes:
            raise ValueError(f"Node {node_id} not found")

        node = self.registry.nodes[node_id]
        bonus_per_unit = self.registry.IMPACT_BONUSES.get(node.node_type, 0)
        current_bonus = node.impact_metric * bonus_per_unit
        new_bonus = new_impact_metric * bonus_per_unit
        additional = new_bonus - current_bonus

        return round(additional, 8)
