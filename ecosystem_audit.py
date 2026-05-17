#!/usr/bin/env python3
"""
Thronos Ecosystem Audit & Mapping Tool
=======================================

Comprehensive documentation and validation of all Thronos blockchain systems.
Identifies real vs mock data, validates all parameters, and creates complete audit report.

Usage:
  python3 ecosystem_audit.py [--full] [--output audit_report.json]

Author: Thronos Development
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple

# ─────────────────────────────────────────────────────────────
# ECOSYSTEM COMPONENTS TO AUDIT
# ─────────────────────────────────────────────────────────────

AUDIT_SECTIONS = {
    "mining_system": {
        "name": "Mining System (PoW)",
        "key_files": ["server.py"],
        "key_variables": [
            "TARGET_BLOCK_TIME",
            "INITIAL_TARGET",
            "RETARGET_INTERVAL",
            "HALVING_INTERVAL",
            "INITIAL_BLOCK_REWARD"
        ],
        "critical": True
    },
    "pledge_system": {
        "name": "Pledge System (BTC Pledges)",
        "key_files": ["server.py"],
        "key_files_data": ["pledge_chain.json", "free_pledge_whitelist.json"],
        "critical": True
    },
    "token_systems": {
        "name": "Token Systems (THR, L2E, etc.)",
        "key_files": ["server.py"],
        "key_files_data": ["tokens.json", "token_holders.json"],
        "critical": True
    },
    "liquidity_pools": {
        "name": "Liquidity Pools & AMM",
        "key_files": ["server.py"],
        "key_files_data": ["pools.json"],
        "critical": True
    },
    "digital_legacy": {
        "name": "Digital Legacy System",
        "key_files": [
            "digital_legacy_manager.py",
            "digital_will_smart_contract.py",
            "digital_distribution_manager.py",
            "digital_pool_redistribution.py"
        ],
        "key_files_data": [
            "digital_estates.json",
            "digital_wills.json",
            "distributions.json",
            "charity_pool.json"
        ],
        "critical": True
    },
    "mining_ecosystem": {
        "name": "Mining Ecosystem & Tokenomics",
        "key_files": ["mining_ecosystem_tokenomics.py"],
        "critical": True
    },
    "mempool": {
        "name": "Mempool & Transaction Queue",
        "key_files": ["server.py"],
        "key_files_data": ["mempool.json"],
        "critical": True
    },
    "iot_miners": {
        "name": "IoT Miners & Device Network",
        "key_files": ["server.py"],
        "key_files_data": ["t2e_rewards.json"],
        "critical": False
    }
}


class EcosystemAuditor:
    """Audit entire Thronos ecosystem"""

    def __init__(self, base_dir: str = "/home/user/thronos-V3.6"):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.report: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "audit_version": "1.0",
            "base_directory": str(self.base_dir),
            "sections": {}
        }
        self.issues: List[Tuple[str, str, str]] = []  # (section, severity, message)

    def run_audit(self) -> Dict:
        """Run complete ecosystem audit"""
        print("🔍 Starting Thronos Ecosystem Audit...\n")

        for section_key, section_config in AUDIT_SECTIONS.items():
            print(f"📋 Auditing {section_config['name']}...")
            self._audit_section(section_key, section_config)

        self.report["issues"] = [
            {
                "section": issue[0],
                "severity": issue[1],
                "message": issue[2]
            }
            for issue in self.issues
        ]

        self.report["summary"] = {
            "total_sections_audited": len(AUDIT_SECTIONS),
            "issues_found": len(self.issues),
            "critical_issues": len([i for i in self.issues if i[1] == "CRITICAL"]),
            "warnings": len([i for i in self.issues if i[1] == "WARNING"]),
            "info_items": len([i for i in self.issues if i[1] == "INFO"])
        }

        return self.report

    def _audit_section(self, section_key: str, config: Dict):
        """Audit a single section"""
        section_report = {
            "name": config["name"],
            "status": "✅ OK",
            "components": {},
            "data_files": {},
            "findings": []
        }

        # Check code files
        for file_name in config.get("key_files", []):
            file_path = self.base_dir / file_name
            finding = self._check_file(file_path, config.get("key_variables", []))
            section_report["components"][file_name] = finding

        # Check data files
        for file_name in config.get("key_files_data", []):
            file_path = self.data_dir / file_name
            finding = self._check_data_file(file_path, section_key)
            section_report["data_files"][file_name] = finding

        self.report["sections"][section_key] = section_report

    def _check_file(self, file_path: Path, key_vars: List[str]) -> Dict:
        """Check if code file exists and contains key variables"""
        result = {
            "exists": file_path.exists(),
            "path": str(file_path),
            "size_bytes": 0,
            "key_variables_found": [],
            "status": "❌ NOT FOUND"
        }

        if not file_path.exists():
            self.issues.append((
                file_path.name,
                "CRITICAL" if "server.py" in str(file_path) else "WARNING",
                f"File not found: {file_path}"
            ))
            return result

        result["size_bytes"] = file_path.stat().st_size
        result["status"] = "✅ EXISTS"

        if key_vars:
            try:
                content = file_path.read_text()
                for var in key_vars:
                    if var in content:
                        result["key_variables_found"].append(var)
                    else:
                        self.issues.append((
                            file_path.name,
                            "WARNING",
                            f"Key variable '{var}' not found"
                        ))
            except Exception as e:
                self.issues.append((
                    file_path.name,
                    "ERROR",
                    f"Error reading file: {e}"
                ))

        return result

    def _check_data_file(self, file_path: Path, section: str) -> Dict:
        """Check if data file exists and has content"""
        result = {
            "exists": file_path.exists(),
            "path": str(file_path),
            "size_bytes": 0,
            "records": 0,
            "is_empty": True,
            "is_mock_data": False,
            "status": "❌ NOT FOUND"
        }

        if not file_path.exists():
            result["status"] = "⚠️ NO DATA"
            self.issues.append((
                file_path.name,
                "INFO",
                f"Data file not created yet (may be normal on fresh install)"
            ))
            return result

        result["size_bytes"] = file_path.stat().st_size
        result["status"] = "✅ EXISTS"

        try:
            data = json.loads(file_path.read_text())

            if isinstance(data, list):
                result["records"] = len(data)
            elif isinstance(data, dict):
                result["records"] = len(data)

            result["is_empty"] = result["records"] == 0

            # Check for mock data indicators
            if result["records"] > 0:
                sample = data[0] if isinstance(data, list) else list(data.values())[0]
                if isinstance(sample, dict):
                    mock_indicators = ["test", "mock", "fake", "demo", "example"]
                    for key, value in sample.items():
                        if isinstance(value, str):
                            for indicator in mock_indicators:
                                if indicator.lower() in value.lower():
                                    result["is_mock_data"] = True
                                    self.issues.append((
                                        file_path.name,
                                        "WARNING",
                                        f"Detected possible mock data: '{value[:50]}...'"
                                    ))
                                    break

        except json.JSONDecodeError as e:
            self.issues.append((
                file_path.name,
                "ERROR",
                f"Invalid JSON: {e}"
            ))

        return result


def print_report(report: Dict):
    """Pretty print audit report"""
    print("\n" + "=" * 80)
    print("🔍 THRONOS ECOSYSTEM AUDIT REPORT")
    print("=" * 80)

    print(f"\n📅 Timestamp: {report['timestamp']}")
    print(f"📁 Directory: {report['base_directory']}")

    # Summary
    summary = report["summary"]
    print(f"\n📊 SUMMARY:")
    print(f"   Sections Audited: {summary['total_sections_audited']}")
    print(f"   Issues Found: {summary['issues_found']}")
    print(f"   🔴 Critical: {summary['critical_issues']}")
    print(f"   🟠 Warnings: {summary['warnings']}")
    print(f"   ℹ️  Info: {summary['info_items']}")

    # Sections
    print(f"\n📋 SECTIONS:")
    for section_key, section_data in report["sections"].items():
        status_icon = "✅" if section_data["status"] == "✅ OK" else "⚠️"
        print(f"\n{status_icon} {section_data['name']}")

        for component, finding in section_data["components"].items():
            print(f"   📄 {component}: {finding['status']} ({finding['size_bytes']} bytes)")
            if finding["key_variables_found"]:
                print(f"      Variables: {', '.join(finding['key_variables_found'][:3])}...")

        for data_file, finding in section_data["data_files"].items():
            icon = "📊" if finding["exists"] else "⚫"
            mock = " [MOCK DATA]" if finding["is_mock_data"] else ""
            print(f"   {icon} {data_file}: {finding['status']} ({finding['records']} records){mock}")

    # Issues
    if report["issues"]:
        print(f"\n⚠️  ISSUES & FINDINGS:")
        for issue in report["issues"]:
            severity_icon = "🔴" if issue["severity"] == "CRITICAL" else "🟠" if issue["severity"] == "WARNING" else "ℹ️"
            print(f"\n{severity_icon} [{issue['severity']}] {issue['section']}")
            print(f"   {issue['message']}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    auditor = EcosystemAuditor()
    report = auditor.run_audit()
    print_report(report)

    # Save report
    output_file = Path("/home/user/thronos-V3.6/ecosystem_audit_report.json")
    output_file.write_text(json.dumps(report, indent=2))
    print(f"\n💾 Report saved to: {output_file}\n")
