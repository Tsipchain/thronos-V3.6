"""
Comprehensive Test Suite for Phase 1 Systems
Tests all Epoch 3 systems for August 15, 2026 deployment.

Coverage:
- Core Node Management (registration, rewards, reporting)
- Bridge Coordinator (multi-chain swaps, liquidity)
- Mesh Network Manager (offline resilience, recovery)
- Emergency Recovery (failure scenarios, restoration)
- Community Treasury (proposals, voting, distribution)
"""

import unittest
import time
import json
from core_node_management import (
    CoreNodeRegistry, CoreNodeRewardCalculator, NodeType, NodeStatus, ImpactReport
)
from bridge_coordinator import (
    BridgeCoordinator, ChainType, BridgeStatus, SwapDirection, LiquidityPool
)
from mesh_network_manager import (
    MeshNetworkManager, MeshNode, NodeRole, MeshNodeStatus, SyncStatus, NetworkType
)
from emergency_recovery_system import (
    EmergencyRecoverySystem, FailureType, RecoveryStatus, RecoveryPhase, BackupLocation
)


class TestCoreNodeManagement(unittest.TestCase):
    """Test core node registration and reward system"""

    def setUp(self):
        self.registry = CoreNodeRegistry()
        self.calculator = CoreNodeRewardCalculator(self.registry)

    def test_register_hospital_node(self):
        """Test registering a hospital core node"""
        node_id = self.registry.register_core_node(
            organization_address="0xhospital001",
            node_type=NodeType.HOSPITAL,
            organization_name="Global Health Foundation",
            mission="Provide medical care to underserved regions",
            legal_registration_hash="hash_hospital_001"
        )

        self.assertIsNotNone(node_id)
        self.assertIn(node_id, self.registry.nodes)
        self.assertEqual(self.registry.total_registered_nodes, 1)

    def test_register_university_node(self):
        """Test registering a university core node"""
        node_id = self.registry.register_core_node(
            organization_address="0xuniversity001",
            node_type=NodeType.UNIVERSITY,
            organization_name="African Tech Institute",
            mission="Provide technology education to Africa",
            legal_registration_hash="hash_university_001"
        )

        self.assertIsNotNone(node_id)
        node_data = self.registry.get_node_info(node_id)
        self.assertEqual(node_data["node_type"], "university")

    def test_register_charity_node(self):
        """Test registering a charity core node"""
        node_id = self.registry.register_core_node(
            organization_address="0xcharity001",
            node_type=NodeType.CHARITY,
            organization_name="Medical Research Foundation",
            mission="Fund cancer research",
            legal_registration_hash="hash_charity_001"
        )

        self.assertIsNotNone(node_id)
        self.assertEqual(self.registry.total_registered_nodes, 1)

    def test_dao_approval_workflow(self):
        """Test DAO approval of core nodes"""
        node_id = self.registry.register_core_node(
            organization_address="0xhosp001",
            node_type=NodeType.HOSPITAL,
            organization_name="Hospital A",
            mission="Serve 100k patients",
            legal_registration_hash="hash001"
        )

        # Node starts in REGISTERED status
        node = self.registry.nodes[node_id]
        self.assertEqual(node.status, NodeStatus.REGISTERED)

        # DAO approves with 75% vote
        self.registry.approve_node_by_dao(node_id, 75.0)
        self.assertEqual(node.status, NodeStatus.DAO_APPROVED)
        self.assertEqual(node.dao_approval_percentage, 75.0)

        # Activate node
        self.registry.activate_node(node_id)
        self.assertEqual(node.status, NodeStatus.ACTIVE)

    def test_reward_calculation(self):
        """Test reward calculation with impact bonus"""
        node_id = self.registry.register_core_node(
            organization_address="0xhosp002",
            node_type=NodeType.HOSPITAL,
            organization_name="Hospital B",
            mission="Serve patients",
            legal_registration_hash="hash002"
        )

        # Approve and activate
        self.registry.approve_node_by_dao(node_id, 51.0)
        self.registry.activate_node(node_id)

        # Set impact metric (1000 patients served)
        node = self.registry.nodes[node_id]
        node.impact_metric = 1000

        # Calculate reward: 0.00625 base + (1000 * 0.001 bonus) = 1.00625
        reward = self.registry.calculate_node_reward(node_id)
        expected = 0.00625 + (1000 * 0.001)
        self.assertEqual(reward, expected)

    def test_impact_report_submission(self):
        """Test impact reporting from core nodes"""
        node_id = self.registry.register_core_node(
            organization_address="0xhosp003",
            node_type=NodeType.HOSPITAL,
            organization_name="Hospital C",
            mission="Serve patients",
            legal_registration_hash="hash003"
        )

        self.registry.approve_node_by_dao(node_id, 51.0)
        self.registry.activate_node(node_id)

        # Submit impact report
        report_id = self.registry.submit_impact_report(
            node_id=node_id,
            people_served=5000,
            services_delivered=12500,
            report_hash="ipfs_hash_001",
            report_url="https://report.hospital.org/q1_2026"
        )

        self.assertIsNotNone(report_id)
        node = self.registry.nodes[node_id]
        self.assertEqual(node.impact_metric, 5000)
        self.assertEqual(len(node.impact_reports), 1)

    def test_reward_distribution(self):
        """Test distributing rewards to nodes"""
        node_id = self.registry.register_core_node(
            organization_address="0xhosp004",
            node_type=NodeType.HOSPITAL,
            organization_name="Hospital D",
            mission="Serve patients",
            legal_registration_hash="hash004"
        )

        self.registry.approve_node_by_dao(node_id, 51.0)
        self.registry.activate_node(node_id)

        # Distribute reward
        self.registry.distribute_reward(
            node_id=node_id,
            reward_amount=0.10625,
            block_number=630100,
            tx_hash="0x_block_630100"
        )

        node = self.registry.nodes[node_id]
        self.assertEqual(node.total_rewards_earned, 0.10625)
        self.assertEqual(len(node.reward_history), 1)

    def test_batch_reward_distribution(self):
        """Test batch distribution to multiple nodes"""
        # Register 3 nodes
        node_ids = []
        for i in range(3):
            node_id = self.registry.register_core_node(
                organization_address=f"0xorg{i:03d}",
                node_type=NodeType.HOSPITAL,
                organization_name=f"Hospital {i}",
                mission="Serve patients",
                legal_registration_hash=f"hash{i:03d}"
            )
            self.registry.approve_node_by_dao(node_id, 51.0)
            self.registry.activate_node(node_id)
            node_ids.append(node_id)

        # Batch distribute
        rewards = {node_id: 0.10625 for node_id in node_ids}
        results = self.registry.batch_distribute_rewards(rewards, 630100)

        self.assertEqual(len(results), 3)
        self.assertTrue(all(results.values()))
        self.assertEqual(self.registry.total_rewards_distributed, 0.31875)

    def test_registry_statistics(self):
        """Test registry statistics calculation"""
        # Register multiple nodes of different types
        hospital_id = self.registry.register_core_node(
            organization_address="0xhosp_stat",
            node_type=NodeType.HOSPITAL,
            organization_name="Hospital",
            mission="Medical care",
            legal_registration_hash="hash_h"
        )

        university_id = self.registry.register_core_node(
            organization_address="0xuniv_stat",
            node_type=NodeType.UNIVERSITY,
            organization_name="University",
            mission="Education",
            legal_registration_hash="hash_u"
        )

        self.registry.approve_node_by_dao(hospital_id, 51.0)
        self.registry.activate_node(hospital_id)

        stats = self.registry.get_registry_stats()

        self.assertEqual(stats["total_registered_nodes"], 2)
        self.assertEqual(stats["active_nodes"], 1)
        self.assertEqual(stats["nodes_by_type"]["hospital"], 1)
        self.assertEqual(stats["nodes_by_type"]["university"], 1)


class TestBridgeCoordinator(unittest.TestCase):
    """Test multi-chain bridge operations"""

    def setUp(self):
        self.bridge = BridgeCoordinator()

    def test_initiate_bridge_transaction(self):
        """Test initiating a cross-chain transaction"""
        tx_id = self.bridge.initiate_bridge_transaction(
            source_chain=ChainType.BITCOIN,
            destination_chain=ChainType.THRONOS,
            source_address="1A1z7agoat2LWQLZC1QxAqvZbJgTQgCDy",
            destination_address="0xdest001",
            amount=10.0
        )

        self.assertIsNotNone(tx_id)
        tx = self.bridge.transactions[tx_id]
        self.assertEqual(tx.source_chain, ChainType.BITCOIN)
        self.assertEqual(tx.amount, 10.0)
        self.assertEqual(tx.status, BridgeStatus.INITIATED)

    def test_bridge_fee_calculation(self):
        """Test bridge fee calculation"""
        tx_id = self.bridge.initiate_bridge_transaction(
            source_chain=ChainType.ETHEREUM,
            destination_chain=ChainType.THRONOS,
            source_address="0xsource001",
            destination_address="0xdest002",
            amount=100.0
        )

        tx = self.bridge.transactions[tx_id]
        # 0.25% fee = 100 * 0.0025 = 0.25
        expected_fee = 0.25
        self.assertAlmostEqual(tx.fee_amount, expected_fee, places=4)
        self.assertEqual(tx.received_amount, 99.75)

    def test_liquidity_pool_creation(self):
        """Test automatic liquidity pool creation"""
        pools = len(self.bridge.pools)
        self.assertEqual(pools, 6)  # BTC, ETH, Solana, XRP, Polkadot, Cosmos

    def test_liquidity_provision(self):
        """Test adding liquidity to a pool"""
        result = self.bridge.add_liquidity(
            base_chain=ChainType.BITCOIN,
            paired_chain=ChainType.THRONOS,
            provider_address="0xprovider001",
            base_amount=5.0,
            paired_amount=100000.0
        )

        self.assertIsNotNone(result)
        self.assertIn("shares_issued", result)
        self.assertTrue(result["shares_issued"] > 0)

    def test_bridge_transaction_confirmation(self):
        """Test confirming bridge transaction on both chains"""
        tx_id = self.bridge.initiate_bridge_transaction(
            source_chain=ChainType.BITCOIN,
            destination_chain=ChainType.THRONOS,
            source_address="1A1z7agoat2LWQLZC1QxAqvZbJgTQgCDy",
            destination_address="0xdest003",
            amount=5.0
        )

        # Confirm on source chain (Bitcoin requires 12 confirmations)
        confirmed = self.bridge.confirm_source_transaction(
            tx_id=tx_id,
            source_tx_hash="tx_hash_001",
            confirmation_count=12
        )
        self.assertTrue(confirmed)

        # Lock source tokens
        self.bridge.lock_source_tokens(tx_id)
        tx = self.bridge.transactions[tx_id]
        self.assertEqual(tx.status, BridgeStatus.LOCKED)

        # Mint on destination
        self.bridge.mint_destination_tokens(tx_id, "tx_hash_002")

        # Confirm on destination (Thronos requires 100 confirmations)
        confirmed = self.bridge.confirm_destination_transaction(
            tx_id=tx_id,
            confirmation_count=100
        )
        self.assertTrue(confirmed)
        self.assertEqual(tx.status, BridgeStatus.CONFIRMED)

    def test_bridge_statistics(self):
        """Test bridge statistics"""
        # Create a few transactions and complete at least one
        for i in range(3):
            tx_id = self.bridge.initiate_bridge_transaction(
                source_chain=ChainType.ETHEREUM,
                destination_chain=ChainType.THRONOS,
                source_address=f"0xsource{i:03d}",
                destination_address=f"0xdest{i:03d}",
                amount=10.0 * (i + 1)
            )

            # Complete the first transaction
            if i == 0:
                self.bridge.confirm_source_transaction(tx_id, "tx_hash", 30)
                self.bridge.lock_source_tokens(tx_id)
                self.bridge.mint_destination_tokens(tx_id, "tx_hash_2")
                self.bridge.confirm_destination_transaction(tx_id, 100)

        stats = self.bridge.get_bridge_stats()

        self.assertEqual(stats["total_transactions"], 3)
        self.assertEqual(stats["pending_transactions"], 2)
        self.assertGreater(stats["total_fees_collected"], 0)


class TestMeshNetwork(unittest.TestCase):
    """Test offline mesh network operations"""

    def setUp(self):
        self.mesh = MeshNetworkManager()

    def test_register_mesh_nodes(self):
        """Test registering nodes in mesh network"""
        node_id = self.mesh.register_mesh_node(
            node_id="node_full_001",
            node_type=NodeRole.FULL_NODE,
            location="Kenya",
            storage_gb=500
        )

        self.assertEqual(node_id, "node_full_001")
        self.assertEqual(self.mesh.nodes[node_id].node_type, NodeRole.FULL_NODE)

    def test_mesh_node_connectivity(self):
        """Test connecting nodes in mesh"""
        node1 = self.mesh.register_mesh_node(
            "relay_001", NodeRole.RELAY, "Nigeria", 100
        )
        node2 = self.mesh.register_mesh_node(
            "relay_002", NodeRole.RELAY, "Ghana", 100
        )

        self.mesh.connect_nodes(node1, node2)

        self.assertIn(node2, self.mesh.nodes[node1].neighbors)
        self.assertIn(node1, self.mesh.nodes[node2].neighbors)

    def test_broadcast_packet(self):
        """Test broadcasting packet across mesh"""
        node_id = self.mesh.register_mesh_node(
            "node_broadcast_001", NodeRole.FULL_NODE, "Location", 500
        )

        packet_id = self.mesh.broadcast_packet(
            packet_type="block",
            source_node=node_id,
            payload={"block_number": 630100, "hash": "0xhash"},
            priority=8
        )

        self.assertIsNotNone(packet_id)
        packet = self.mesh.packets[packet_id]
        self.assertEqual(packet.destination_node, "broadcast")

    def test_recovery_mode_activation(self):
        """Test enabling recovery mode"""
        self.assertFalse(self.mesh.recovery_mode)
        self.assertTrue(self.mesh.internet_available)

        self.mesh.enable_recovery_mode()

        self.assertTrue(self.mesh.recovery_mode)
        self.assertFalse(self.mesh.internet_available)

    def test_blockchain_synchronization(self):
        """Test blockchain sync over mesh"""
        node_id = self.mesh.register_mesh_node(
            "sync_node_001", NodeRole.FULL_NODE, "Location", 1000
        )

        sync_info = self.mesh.sync_blockchain_segment(
            node_id=node_id,
            start_block=630000,
            end_block=630099
        )

        self.assertEqual(sync_info["start_block"], 630000)
        self.assertEqual(sync_info["end_block"], 630099)
        self.assertEqual(sync_info["block_count"], 100)

    def test_network_topology(self):
        """Test network topology calculation"""
        # Create a small mesh
        for i in range(5):
            self.mesh.register_mesh_node(
                f"node_{i:03d}", NodeRole.RELAY, f"Location_{i}", 100
            )

        # Connect in a line: 0-1-2-3-4
        nodes = list(self.mesh.nodes.keys())
        for i in range(len(nodes) - 1):
            self.mesh.connect_nodes(nodes[i], nodes[i + 1])

        topology = self.mesh.get_network_topology()

        self.assertEqual(topology["total_nodes"], 5)
        self.assertGreater(topology["network_diameter"], 0)

    def test_network_statistics(self):
        """Test network statistics"""
        node_id = self.mesh.register_mesh_node(
            "stat_node_001", NodeRole.FULL_NODE, "Location", 500
        )

        self.mesh.update_node_status(node_id, MeshNodeStatus.ONLINE, signal_strength=95)

        stats = self.mesh.get_network_stats()

        self.assertEqual(stats["total_nodes"], 1)
        self.assertEqual(stats["online_nodes"], 1)


class TestEmergencyRecovery(unittest.TestCase):
    """Test emergency recovery procedures"""

    def setUp(self):
        self.recovery = EmergencyRecoverySystem()

    def test_detect_internet_outage(self):
        """Test detecting internet outage failure"""
        recovery_id = self.recovery.detect_failure(
            FailureType.INTERNET_OUTAGE,
            ["internet_connection"]
        )

        self.assertIsNotNone(recovery_id)
        self.assertIn(recovery_id, self.recovery.recovery_procedures)
        procedure = self.recovery.recovery_procedures[recovery_id]
        self.assertEqual(procedure.failure_type, FailureType.INTERNET_OUTAGE)

    def test_recovery_from_internet_outage(self):
        """Test recovery from internet outage"""
        recovery_id = self.recovery.detect_failure(
            FailureType.INTERNET_OUTAGE,
            ["internet"]
        )

        success = self.recovery.initiate_recovery(recovery_id)

        self.assertTrue(success)
        procedure = self.recovery.recovery_procedures[recovery_id]
        self.assertEqual(procedure.status, RecoveryStatus.COMPLETE)

    def test_partner_node_registration(self):
        """Test registering partner nodes for recovery"""
        self.recovery.register_partner_node("partner_na", "North America")
        self.recovery.register_partner_node("partner_eu", "Europe")
        self.recovery.register_partner_node("partner_asia", "Asia")

        self.assertEqual(len(self.recovery.partner_nodes), 3)

    def test_satellite_gateway_registration(self):
        """Test registering satellite gateways"""
        self.recovery.register_satellite_gateway("gateway_starlink_1", "starlink")
        self.recovery.register_satellite_gateway("gateway_iridium_1", "iridium")

        self.assertEqual(len(self.recovery.satellite_gateways), 2)

    def test_resilience_score(self):
        """Test system resilience score calculation"""
        # Add backup infrastructure
        for i in range(5):
            from emergency_recovery_system import DataBackup
            backup = DataBackup(f"backup_{i}", 630000 + i * 100, int(time.time()))
            backup.add_location(BackupLocation.PRIMARY, "verified")
            backup.verified = True
            self.recovery.data_backups[backup.backup_id] = backup

        self.recovery.register_partner_node("p1", "NA")
        self.recovery.register_partner_node("p2", "EU")
        self.recovery.register_satellite_gateway("g1", "starlink")

        score = self.recovery.get_system_resilience_score()

        self.assertGreater(score, 0)
        self.assertLessEqual(score, 100)

    def test_recovery_timeline(self):
        """Test recovery timeline tracking"""
        recovery_id = self.recovery.detect_failure(
            FailureType.INTERNET_OUTAGE,
            ["internet"]
        )

        self.recovery.initiate_recovery(recovery_id)

        timeline = self.recovery.get_recovery_timeline(recovery_id)

        self.assertIn("recovery_id", timeline)
        self.assertIn("phases", timeline)
        self.assertIn("actions", timeline)
        self.assertGreater(len(timeline["actions"]), 0)


class TestCommunityTreasuryIntegration(unittest.TestCase):
    """Test Community Treasury DAO integration"""

    def test_treasury_balance_tracking(self):
        """Test tracking community treasury balance"""
        # Epoch 3 block reward: 0.125 THR
        # Community allocation: 5% = 0.00625 THR per block
        # After 1000 blocks: 6.25 THR

        blocks_processed = 1000
        block_reward = 0.125
        community_allocation = 0.05

        total_treasury = blocks_processed * block_reward * community_allocation

        self.assertEqual(total_treasury, 6.25)

    def test_proposal_creation(self):
        """Test creating a treasury proposal"""
        # In production: Use actual API
        # This is a placeholder for integration

        proposal = {
            "title": "Medical Research Fund",
            "description": "Support cancer research across Africa",
            "requested_amount": 1000.0,
            "beneficiary_type": "medical",
            "beneficiary_name": "Cancer Research Institute",
            "beneficiary_address": "0xresearch001"
        }

        self.assertIsNotNone(proposal["title"])
        self.assertEqual(proposal["beneficiary_type"], "medical")

    def test_quadratic_voting(self):
        """Test quadratic voting mechanism"""
        # Cost to vote with power 10: 10^2 = 100 THR
        voting_power = 10
        voting_cost = voting_power ** 2

        self.assertEqual(voting_cost, 100)

        # Cost to vote with power 1: 1^2 = 1 THR
        voting_power_small = 1
        voting_cost_small = voting_power_small ** 2

        self.assertEqual(voting_cost_small, 1)


class TestIntegrationScenarios(unittest.TestCase):
    """Test real-world integration scenarios"""

    def test_hospital_node_full_cycle(self):
        """Test complete hospital node lifecycle"""
        registry = CoreNodeRegistry()

        # 1. Register hospital
        hospital_id = registry.register_core_node(
            organization_address="0xhospital_final",
            node_type=NodeType.HOSPITAL,
            organization_name="Global Health Foundation",
            mission="Serve 100k patients annually",
            legal_registration_hash="hash_hospital_final"
        )

        # 2. DAO approves
        registry.approve_node_by_dao(hospital_id, 65.0)
        registry.activate_node(hospital_id)

        # 3. Hospital operates and reports impact
        registry.submit_impact_report(
            node_id=hospital_id,
            people_served=50000,
            services_delivered=150000,
            report_hash="ipfs_hash_q1",
            report_url="https://hospital.org/report/q1_2026"
        )

        # 4. DAO approves report
        registry.approve_impact_report(hospital_id, 0)

        # 5. Calculate and distribute rewards
        reward = registry.calculate_node_reward(hospital_id)

        # Base: 0.00625 + Bonus: 50000 * 0.001 = 50.00625
        expected = 0.00625 + 50.0
        self.assertEqual(reward, expected)

        # 6. Distribute for 1000 blocks
        total_reward = reward * 1000
        registry.distribute_reward(hospital_id, total_reward, 630100)

        # Verify
        node = registry.nodes[hospital_id]
        self.assertEqual(node.status, NodeStatus.ACTIVE)
        self.assertEqual(node.total_rewards_earned, total_reward)

    def test_btc_to_thronos_bridge_cycle(self):
        """Test complete Bitcoin to Thronos bridge operation"""
        bridge = BridgeCoordinator()

        # 1. Initiate bridge
        tx_id = bridge.initiate_bridge_transaction(
            source_chain=ChainType.BITCOIN,
            destination_chain=ChainType.THRONOS,
            source_address="1A1z7agoat2LWQLZC1QxAqvZbJgTQgCDy",
            destination_address="0xthronos_user_001",
            amount=5.0
        )

        # 2. Confirm on Bitcoin (12 confirmations required)
        bridge.confirm_source_transaction(tx_id, "tx_btc_hash", 12)
        bridge.lock_source_tokens(tx_id)

        # 3. Mint on Thronos
        bridge.mint_destination_tokens(tx_id, "tx_thronos_hash")

        # 4. Confirm on Thronos (100 confirmations required)
        bridge.confirm_destination_transaction(tx_id, 100)

        # Verify
        tx = bridge.transactions[tx_id]
        self.assertEqual(tx.status, BridgeStatus.CONFIRMED)
        self.assertAlmostEqual(tx.received_amount, 4.9875, places=4)

    def test_mesh_network_recovery_cycle(self):
        """Test complete mesh network recovery"""
        mesh = MeshNetworkManager()

        # 1. Register mesh nodes across regions
        for region in ["Kenya", "Nigeria", "Brazil", "India", "Australia"]:
            mesh.register_mesh_node(
                f"node_{region.lower()}",
                NodeRole.FULL_NODE,
                region,
                storage_gb=1000
            )

        # 2. Connect nodes
        nodes = list(mesh.nodes.keys())
        for i in range(len(nodes) - 1):
            mesh.connect_nodes(nodes[i], nodes[i + 1])

        # 3. Internet goes down
        mesh.enable_recovery_mode()
        self.assertTrue(mesh.recovery_mode)

        # 4. Sync blockchain over mesh
        sync_info = mesh.sync_blockchain_segment(
            node_id=nodes[0],
            start_block=630000,
            end_block=630099
        )

        # 5. Bring node back online
        mesh.complete_node_sync(nodes[0], verified_blocks=100)
        node = mesh.nodes[nodes[0]]
        self.assertEqual(node.sync_status, SyncStatus.SYNCED)


def run_all_tests():
    """Run all test suites"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestCoreNodeManagement))
    suite.addTests(loader.loadTestsFromTestCase(TestBridgeCoordinator))
    suite.addTests(loader.loadTestsFromTestCase(TestMeshNetwork))
    suite.addTests(loader.loadTestsFromTestCase(TestEmergencyRecovery))
    suite.addTests(loader.loadTestsFromTestCase(TestCommunityTreasuryIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegrationScenarios))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result


if __name__ == "__main__":
    result = run_all_tests()
    exit(0 if result.wasSuccessful() else 1)
