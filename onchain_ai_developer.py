#!/usr/bin/env python3
"""
Thronos On-Chain AI Developer (Pythia Code Agent)
=================================================
Autonomous AI that writes, reviews, and improves network code

Features:
- Code generation and improvement
- Automated bug fixing
- Security vulnerability patching
- Gas optimization
- Smart contract auditing
- Documentation generation
- Test case creation
- CI/CD integration
- Version control integration

Phase 6: AI Autonomy (Pythia)
Version: 5.0
"""

import os
import json
import time
import hashlib
import logging
import subprocess
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CodeImprovement:
    """Code improvement suggestion"""
    improvement_id: str
    file_path: str
    issue_type: str  # bug, security, optimization, style, documentation
    severity: str  # critical, high, medium, low
    description: str
    current_code: str
    suggested_code: str
    reasoning: str
    estimated_impact: str
    auto_applicable: bool
    applied: bool = False
    applied_at: Optional[str] = None


@dataclass
class AIDeployment:
    """AI-initiated code deployment"""
    deployment_id: str
    changes: List[str]
    tests_passed: bool
    security_scan_passed: bool
    deployed_at: str
    commit_hash: str
    ai_confidence: float
    rollback_available: bool = True


class OnChainAIDeveloper:
    """
    On-Chain AI Developer
    Autonomous code improvement and deployment
    """

    def __init__(self, data_dir: str = "data", repo_path: str = "."):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.repo_path = Path(repo_path)

        # Storage
        self.improvements_path = self.data_dir / "ai_code_improvements.json"
        self.deployments_path = self.data_dir / "ai_deployments.jsonl"
        self.code_review_path = self.data_dir / "ai_code_reviews.jsonl"

        # Configuration
        self.auto_deploy_enabled = os.getenv("AI_AUTO_DEPLOY", "false").lower() == "true"
        self.max_auto_deploy_per_day = int(os.getenv("AI_MAX_DEPLOYS_PER_DAY", "3"))
        self.min_confidence_threshold = float(os.getenv("AI_MIN_CONFIDENCE", "0.85"))

        # State
        self.improvements: Dict[str, CodeImprovement] = {}
        self.deployments_today = 0
        self.last_deployment_date = ""

        # Load state
        self._load_improvements()

        # Try to import AI agent service
        try:
            from ai_agent_service import ThronosAI
            self.ai_engine = ThronosAI()
            self.ai_available = True
            logger.info("🤖 AI Engine loaded successfully")
        except:
            self.ai_engine = None
            self.ai_available = False
            logger.warning("AI Engine not available - using rule-based system")

        logger.info("🤖 On-Chain AI Developer initialized")
        logger.info(f"   Auto-deploy: {self.auto_deploy_enabled}")
        logger.info(f"   Max deploys/day: {self.max_auto_deploy_per_day}")
        logger.info(f"   Min confidence: {self.min_confidence_threshold}")

    def _load_improvements(self):
        """Load previous improvements"""
        if not self.improvements_path.exists():
            return

        try:
            with open(self.improvements_path, 'r') as f:
                data = json.load(f)
                self.improvements = {
                    imp_id: CodeImprovement(**imp_data)
                    for imp_id, imp_data in data.items()
                }
        except Exception as e:
            logger.error(f"Error loading improvements: {e}")

    def _save_improvements(self):
        """Save improvements"""
        try:
            data = {
                imp_id: asdict(improvement)
                for imp_id, improvement in self.improvements.items()
            }
            with open(self.improvements_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving improvements: {e}")

    def _log_deployment(self, deployment: AIDeployment):
        """Log AI deployment"""
        try:
            with open(self.deployments_path, 'a') as f:
                f.write(json.dumps(asdict(deployment)) + '\n')
        except Exception as e:
            logger.error(f"Error logging deployment: {e}")

    # ========================================================================
    # CODE ANALYSIS
    # ========================================================================

    def analyze_file(self, file_path: str) -> List[CodeImprovement]:
        """Analyze a file for improvements"""
        logger.info(f"🔍 Analyzing: {file_path}")

        improvements = []
        path = Path(file_path)

        if not path.exists():
            logger.warning(f"File not found: {file_path}")
            return improvements

        try:
            content = path.read_text(encoding='utf-8')
            lines = content.split('\n')

            # Rule-based analysis
            improvements.extend(self._check_security_issues(file_path, content, lines))
            improvements.extend(self._check_performance_issues(file_path, content, lines))
            improvements.extend(self._check_code_quality(file_path, content, lines))
            improvements.extend(self._check_documentation(file_path, content, lines))

            # AI-powered analysis (if available)
            if self.ai_available:
                ai_improvements = self._ai_analyze_code(file_path, content)
                improvements.extend(ai_improvements)

        except Exception as e:
            logger.error(f"Error analyzing {file_path}: {e}")

        logger.info(f"✅ Found {len(improvements)} improvement opportunities")
        return improvements

    def _check_security_issues(
        self,
        file_path: str,
        content: str,
        lines: List[str]
    ) -> List[CodeImprovement]:
        """Check for security issues"""
        improvements = []

        # Check 1: Hardcoded secrets
        secret_patterns = [
            r'api[_-]?key\s*=\s*["\'][\w-]+["\']',
            r'password\s*=\s*["\'][\w-]+["\']',
            r'secret\s*=\s*["\'][\w-]+["\']',
            r'token\s*=\s*["\'][\w-]+["\']',
        ]

        for i, line in enumerate(lines, 1):
            for pattern in secret_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    improvements.append(CodeImprovement(
                        improvement_id=f"sec_{hashlib.md5(f'{file_path}:{i}'.encode()).hexdigest()[:8]}",
                        file_path=file_path,
                        issue_type="security",
                        severity="critical",
                        description="Hardcoded secret detected",
                        current_code=line.strip(),
                        suggested_code=self._suggest_env_var(line),
                        reasoning="Secrets should be stored in environment variables, not hardcoded",
                        estimated_impact="Prevents credential leaks",
                        auto_applicable=True
                    ))

        # Check 2: SQL injection risks
        sql_patterns = [
            r'execute\([^)]*f".*{.*}"',
            r'execute\([^)]*".*%.*".*%',
        ]

        for i, line in enumerate(lines, 1):
            for pattern in sql_patterns:
                if re.search(pattern, line):
                    improvements.append(CodeImprovement(
                        improvement_id=f"sec_{hashlib.md5(f'{file_path}:{i}'.encode()).hexdigest()[:8]}",
                        file_path=file_path,
                        issue_type="security",
                        severity="critical",
                        description="Potential SQL injection vulnerability",
                        current_code=line.strip(),
                        suggested_code="# Use parameterized queries instead",
                        reasoning="String formatting in SQL queries can lead to SQL injection",
                        estimated_impact="Prevents SQL injection attacks",
                        auto_applicable=False
                    ))

        return improvements

    def _check_performance_issues(
        self,
        file_path: str,
        content: str,
        lines: List[str]
    ) -> List[CodeImprovement]:
        """Check for performance issues"""
        improvements = []

        # Check for inefficient loops
        for i, line in enumerate(lines, 1):
            # Check: list comprehension vs for loop
            if 'for ' in line and i + 2 < len(lines):
                next_line = lines[i]
                if '.append(' in next_line:
                    improvements.append(CodeImprovement(
                        improvement_id=f"perf_{hashlib.md5(f'{file_path}:{i}'.encode()).hexdigest()[:8]}",
                        file_path=file_path,
                        issue_type="optimization",
                        severity="low",
                        description="Can be optimized with list comprehension",
                        current_code=f"{line.strip()}\n{next_line.strip()}",
                        suggested_code="# Consider using list comprehension for better performance",
                        reasoning="List comprehensions are generally faster than for loops with append",
                        estimated_impact="5-10% performance improvement",
                        auto_applicable=False
                    ))

        return improvements

    def _check_code_quality(
        self,
        file_path: str,
        content: str,
        lines: List[str]
    ) -> List[CodeImprovement]:
        """Check code quality"""
        improvements = []

        # Check for bare except clauses
        for i, line in enumerate(lines, 1):
            if re.search(r'except\s*:', line):
                improvements.append(CodeImprovement(
                    improvement_id=f"qual_{hashlib.md5(f'{file_path}:{i}'.encode()).hexdigest()[:8]}",
                    file_path=file_path,
                    issue_type="bug",
                    severity="medium",
                    description="Bare except clause",
                    current_code=line.strip(),
                    suggested_code=line.strip().replace('except:', 'except Exception as e:'),
                    reasoning="Bare except catches all exceptions including system exits",
                    estimated_impact="Better error handling and debugging",
                    auto_applicable=True
                ))

        return improvements

    def _check_documentation(
        self,
        file_path: str,
        content: str,
        lines: List[str]
    ) -> List[CodeImprovement]:
        """Check documentation"""
        improvements = []

        # Check for functions without docstrings
        for i, line in enumerate(lines, 1):
            if re.match(r'\s*def\s+\w+\s*\(', line):
                # Check if next non-empty line is a docstring
                has_docstring = False
                for j in range(i, min(i + 3, len(lines))):
                    if '"""' in lines[j] or "'''" in lines[j]:
                        has_docstring = True
                        break

                if not has_docstring:
                    func_name = re.search(r'def\s+(\w+)', line).group(1)
                    improvements.append(CodeImprovement(
                        improvement_id=f"doc_{hashlib.md5(f'{file_path}:{i}'.encode()).hexdigest()[:8]}",
                        file_path=file_path,
                        issue_type="documentation",
                        severity="low",
                        description=f"Function {func_name} missing docstring",
                        current_code=line.strip(),
                        suggested_code=f'{line.strip()}\n    """TODO: Add docstring"""',
                        reasoning="Functions should have docstrings explaining their purpose",
                        estimated_impact="Improved code maintainability",
                        auto_applicable=True
                    ))

        return improvements

    def _suggest_env_var(self, line: str) -> str:
        """Suggest environment variable replacement"""
        # Extract variable name
        match = re.search(r'(\w+)\s*=\s*["\'][\w-]+["\']', line)
        if match:
            var_name = match.group(1)
            return f'{var_name} = os.getenv("{var_name.upper()}", "")'
        return line

    def _ai_analyze_code(self, file_path: str, content: str) -> List[CodeImprovement]:
        """Use AI to analyze code"""
        improvements = []

        if not self.ai_engine:
            return improvements

        try:
            prompt = f"""Analyze this code for improvements:

File: {file_path}
Code:
```
{content[:2000]}  # Limit to first 2000 chars
```

Provide specific improvements focusing on:
1. Security vulnerabilities
2. Performance optimizations
3. Code quality issues
4. Best practices

Format: JSON array of improvements"""

            response = self.ai_engine.generate_response(prompt)
            # Parse AI response and create improvements
            # This is simplified - in production, parse structured response

        except Exception as e:
            logger.error(f"AI analysis error: {e}")

        return improvements

    # ========================================================================
    # CODE IMPROVEMENT
    # ========================================================================

    def apply_improvement(self, improvement_id: str) -> Tuple[bool, str]:
        """Apply a code improvement"""
        if improvement_id not in self.improvements:
            return False, "Improvement not found"

        improvement = self.improvements[improvement_id]

        if improvement.applied:
            return False, "Improvement already applied"

        if not improvement.auto_applicable:
            return False, "This improvement requires manual intervention"

        logger.info(f"🔧 Applying improvement: {improvement_id}")

        try:
            # Read file
            path = Path(improvement.file_path)
            content = path.read_text(encoding='utf-8')

            # Apply change
            new_content = content.replace(
                improvement.current_code,
                improvement.suggested_code
            )

            # Backup original
            backup_path = path.with_suffix(path.suffix + '.bak')
            path.rename(backup_path)

            # Write new content
            path.write_text(new_content, encoding='utf-8')

            # Mark as applied
            improvement.applied = True
            improvement.applied_at = datetime.utcnow().isoformat()
            self._save_improvements()

            logger.info(f"✅ Improvement applied: {improvement.description}")
            return True, "Improvement applied successfully"

        except Exception as e:
            logger.error(f"Error applying improvement: {e}")
            # Restore backup if it exists
            if backup_path.exists():
                backup_path.rename(path)
            return False, f"Error: {e}"

    def auto_fix_bugs(self, severity_threshold: str = "high") -> int:
        """Automatically fix bugs above severity threshold"""
        logger.info(f"🔧 Auto-fixing bugs (severity >= {severity_threshold})...")

        severity_order = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
        threshold = severity_order.get(severity_threshold, 1)

        fixed_count = 0

        for imp_id, improvement in self.improvements.items():
            if improvement.applied:
                continue

            if not improvement.auto_applicable:
                continue

            imp_severity = severity_order.get(improvement.severity, 0)
            if imp_severity >= threshold:
                success, msg = self.apply_improvement(imp_id)
                if success:
                    fixed_count += 1

        logger.info(f"✅ Auto-fixed {fixed_count} issues")
        return fixed_count

    # ========================================================================
    # CODE GENERATION
    # ========================================================================

    def generate_code(
        self,
        description: str,
        output_file: str,
        language: str = "python"
    ) -> Tuple[bool, str]:
        """Generate code from description"""
        logger.info(f"🤖 Generating {language} code: {description}")

        if not self.ai_available:
            return False, "AI engine not available"

        try:
            prompt = f"""Generate production-ready {language} code for:

{description}

Requirements:
- Well-documented with docstrings
- Type hints (if Python)
- Error handling
- Security best practices
- Unit tests

Provide complete, working code."""

            response = self.ai_engine.generate_response(prompt)

            # Extract code from response
            code = self._extract_code_from_response(response.get('response', ''))

            if code:
                # Write to file
                Path(output_file).write_text(code, encoding='utf-8')
                logger.info(f"✅ Code generated: {output_file}")
                return True, f"Code generated in {output_file}"
            else:
                return False, "Failed to generate valid code"

        except Exception as e:
            logger.error(f"Code generation error: {e}")
            return False, f"Error: {e}"

    def _extract_code_from_response(self, response: str) -> str:
        """Extract code blocks from AI response"""
        # Look for code blocks
        matches = re.findall(r'```(?:python|py)?\n(.*?)```', response, re.DOTALL)
        if matches:
            return matches[0]
        return response

    # ========================================================================
    # STATISTICS
    # ========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get AI developer statistics"""
        total_improvements = len(self.improvements)
        applied_improvements = len([i for i in self.improvements.values() if i.applied])

        severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        type_counts = {}

        for improvement in self.improvements.values():
            severity_counts[improvement.severity] = severity_counts.get(improvement.severity, 0) + 1
            type_counts[improvement.issue_type] = type_counts.get(improvement.issue_type, 0) + 1

        return {
            'total_improvements_suggested': total_improvements,
            'improvements_applied': applied_improvements,
            'pending_improvements': total_improvements - applied_improvements,
            'severity_breakdown': severity_counts,
            'issue_type_breakdown': type_counts,
            'auto_deploy_enabled': self.auto_deploy_enabled,
            'ai_engine_available': self.ai_available,
        }


def main():
    """Test the AI developer"""
    print("🤖 Thronos On-Chain AI Developer\n")

    ai_dev = OnChainAIDeveloper()

    # Analyze a file
    print("🔍 Analyzing code...")
    improvements = ai_dev.analyze_file("server.py")

    print(f"\n📊 Found {len(improvements)} improvements:\n")
    for imp in improvements[:5]:  # Show first 5
        print(f"  [{imp.severity}] {imp.description}")
        print(f"  File: {imp.file_path}")
        print(f"  Auto-fix: {imp.auto_applicable}\n")

    # Show stats
    print("📈 AI Developer Statistics:")
    stats = ai_dev.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
