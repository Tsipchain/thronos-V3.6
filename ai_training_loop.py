#!/usr/bin/env python3
"""
AI Training Loop for Thronos Network
Trains the AI Agent using conversation history and creates programming blueprints
"""

import os
import json
import time
import hashlib
from datetime import datetime
from typing import List, Dict, Any

# Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CORPUS_FILE = os.path.join(DATA_DIR, "ai_offline_corpus.json")
BLUEPRINTS_DIR = os.path.join(DATA_DIR, "ai_blueprints")
TRAINING_BLOCKS_FILE = os.path.join(DATA_DIR, "training_blocks.json")

os.makedirs(BLUEPRINTS_DIR, exist_ok=True)


def load_json(path: str, default=None):
    """Load JSON file safely"""
    if default is None:
        default = []
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}")
    return default


def save_json(path: str, data: Any):
    """Save JSON file safely"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving {path}: {e}")
        return False


class AITrainingLoop:
    """Main AI Training Loop"""

    def __init__(self):
        self.corpus = load_json(CORPUS_FILE, [])
        self.training_blocks = load_json(TRAINING_BLOCKS_FILE, [])
        self.blueprints = {}
        self.load_blueprints()

    def load_blueprints(self):
        """Load all existing blueprints"""
        if not os.path.exists(BLUEPRINTS_DIR):
            return

        for filename in os.listdir(BLUEPRINTS_DIR):
            if filename.endswith(".json"):
                path = os.path.join(BLUEPRINTS_DIR, filename)
                blueprint_id = filename.replace(".json", "")
                self.blueprints[blueprint_id] = load_json(path, {})

    def process_corpus(self):
        """Process corpus into training blocks"""
        print(f"📚 Processing {len(self.corpus)} corpus entries...")

        new_blocks = 0
        for entry in self.corpus:
            if self._should_create_block(entry):
                block = self._create_training_block(entry)
                if block:
                    self.training_blocks.append(block)
                    new_blocks += 1

        print(f"✅ Created {new_blocks} new training blocks")
        save_json(TRAINING_BLOCKS_FILE, self.training_blocks)

    def _should_create_block(self, entry: Dict) -> bool:
        """Determine if corpus entry should become a training block"""
        user_msg = entry.get("user_message", "")
        ai_msg = entry.get("ai_response", "")

        # Create blocks for programming-related conversations
        keywords = [
            "code", "function", "class", "program", "script", "app",
            "apk", "ios", "assembly", "python", "javascript", "solidity",
            "smart contract", "api", "database", "algorithm", "blueprint"
        ]

        text = (user_msg + " " + ai_msg).lower()
        return any(keyword in text for keyword in keywords)

    def _create_training_block(self, entry: Dict) -> Dict:
        """Create a training block from corpus entry"""
        user_msg = entry.get("user_message", "")
        ai_msg = entry.get("ai_response", "")
        timestamp = entry.get("timestamp", "")

        block_id = hashlib.sha256(
            f"{user_msg}{ai_msg}{timestamp}".encode()
        ).hexdigest()[:16]

        return {
            "block_id": block_id,
            "timestamp": timestamp,
            "user_input": user_msg,
            "ai_output": ai_msg,
            "category": self._categorize_interaction(user_msg, ai_msg),
            "extracted_patterns": self._extract_patterns(user_msg, ai_msg),
            "quality_score": self._calculate_quality(user_msg, ai_msg),
        }

    def _categorize_interaction(self, user_msg: str, ai_msg: str) -> str:
        """Categorize the type of interaction"""
        text = (user_msg + " " + ai_msg).lower()

        categories = {
            "code_generation": ["create", "generate", "write", "build", "code"],
            "debugging": ["fix", "error", "bug", "debug", "issue"],
            "explanation": ["explain", "what is", "how does", "why"],
            "architecture": ["design", "structure", "architecture", "blueprint"],
            "optimization": ["optimize", "improve", "faster", "better"],
        }

        for category, keywords in categories.items():
            if any(kw in text for kw in keywords):
                return category

        return "general"

    def _extract_patterns(self, user_msg: str, ai_msg: str) -> List[str]:
        """Extract programming patterns from interaction"""
        patterns = []

        # Extract code blocks
        if "```" in ai_msg:
            patterns.append("code_block_provided")

        # Extract specific language mentions
        languages = [
            "python", "javascript", "solidity", "rust", "go",
            "assembly", "c++", "java", "swift", "kotlin"
        ]
        for lang in languages:
            if lang in (user_msg + ai_msg).lower():
                patterns.append(f"language:{lang}")

        return patterns

    def _calculate_quality(self, user_msg: str, ai_msg: str) -> float:
        """Calculate quality score for training block (0-1)"""
        score = 0.5  # Base score

        # Higher score for longer, detailed responses
        if len(ai_msg) > 500:
            score += 0.2

        # Higher score for code examples
        if "```" in ai_msg:
            score += 0.2

        # Higher score for structured responses
        if any(marker in ai_msg for marker in ["1.", "2.", "-", "*"]):
            score += 0.1

        return min(score, 1.0)

    def create_blueprint(self, task_description: str, language: str) -> Dict:
        """Create a programming blueprint"""
        print(f"🎨 Creating blueprint for {language} task...")

        blueprint_id = hashlib.sha256(
            f"{task_description}{language}{time.time()}".encode()
        ).hexdigest()[:16]

        # Analyze training blocks for similar tasks
        similar_blocks = self._find_similar_blocks(task_description, language)

        blueprint = {
            "id": blueprint_id,
            "task": task_description,
            "language": language,
            "created_at": datetime.now().isoformat(),
            "template": self._generate_template(task_description, language),
            "similar_examples": [b["block_id"] for b in similar_blocks[:5]],
            "estimated_complexity": self._estimate_complexity(task_description),
            "suggested_approach": self._suggest_approach(
                task_description, language, similar_blocks
            ),
        }

        # Save blueprint
        blueprint_path = os.path.join(BLUEPRINTS_DIR, f"{blueprint_id}.json")
        save_json(blueprint_path, blueprint)
        self.blueprints[blueprint_id] = blueprint

        print(f"✅ Blueprint {blueprint_id} created!")
        return blueprint

    def _find_similar_blocks(
        self, task: str, language: str
    ) -> List[Dict]:
        """Find training blocks similar to the task"""
        similar = []
        task_lower = task.lower()
        lang_lower = language.lower()

        for block in self.training_blocks:
            score = 0

            # Check language match
            if f"language:{lang_lower}" in block.get("extracted_patterns", []):
                score += 2

            # Check task similarity
            block_text = (
                block.get("user_input", "") + " " + block.get("ai_output", "")
            ).lower()

            # Simple keyword matching
            task_words = set(task_lower.split())
            if task_words.intersection(set(block_text.split())):
                score += 1

            if score > 0:
                similar.append({**block, "similarity_score": score})

        return sorted(similar, key=lambda x: x["similarity_score"], reverse=True)

    def _generate_template(self, task: str, language: str) -> str:
        """Generate code template based on language"""
        templates = {
            "python": '''# {task}

def main():
    """Main function"""
    pass

if __name__ == "__main__":
    main()
''',
            "javascript": '''// {task}

function main() {{
    // Implementation here
}}

main();
''',
            "solidity": '''// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

// {task}
contract Solution {{
    // Implementation here
}}
''',
            "assembly": '''; {task}
section .text
    global _start

_start:
    ; Implementation here
    mov eax, 1
    xor ebx, ebx
    int 0x80
''',
        }

        template = templates.get(language.lower(), f"# {task}\n# TODO: Implement")
        return template.format(task=task)

    def _estimate_complexity(self, task: str) -> str:
        """Estimate task complexity"""
        task_lower = task.lower()

        high_complexity_keywords = [
            "system", "blockchain", "database", "api", "full stack",
            "machine learning", "neural network", "compiler"
        ]

        medium_complexity_keywords = [
            "app", "application", "game", "website", "algorithm", "data structure"
        ]

        if any(kw in task_lower for kw in high_complexity_keywords):
            return "high"
        elif any(kw in task_lower for kw in medium_complexity_keywords):
            return "medium"
        else:
            return "low"

    def _suggest_approach(
        self, task: str, language: str, similar_blocks: List[Dict]
    ) -> List[str]:
        """Suggest implementation approach"""
        suggestions = []

        # Base suggestions per language
        lang_suggestions = {
            "python": [
                "Use type hints for better code clarity",
                "Follow PEP 8 style guidelines",
                "Add docstrings to functions",
            ],
            "javascript": [
                "Use async/await for asynchronous operations",
                "Follow ES6+ standards",
                "Add JSDoc comments",
            ],
            "solidity": [
                "Follow Checks-Effects-Interactions pattern",
                "Add NatSpec comments",
                "Optimize for gas efficiency",
            ],
        }

        suggestions.extend(lang_suggestions.get(language.lower(), []))

        # Add suggestions from similar blocks
        if similar_blocks:
            suggestions.append(
                f"Review {len(similar_blocks)} similar examples in training blocks"
            )

        return suggestions

    def run_training_cycle(self):
        """Run one complete training cycle"""
        print("🚀 Starting AI Training Cycle...")
        print("=" * 60)

        # Step 1: Process corpus
        self.process_corpus()

        # Step 2: Analyze patterns
        print(f"\n📊 Total training blocks: {len(self.training_blocks)}")
        print(f"📋 Total blueprints: {len(self.blueprints)}")

        # Step 3: Generate stats
        categories = {}
        for block in self.training_blocks:
            cat = block.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1

        print("\n📈 Training Block Categories:")
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            print(f"   {cat}: {count}")

        print("\n✅ Training cycle complete!")
        print("=" * 60)


def main():
    """Main entry point"""
    trainer = AITrainingLoop()

    # Run training cycle
    trainer.run_training_cycle()

    # Example: Create a blueprint
    print("\n🎨 Example Blueprint Creation:")
    blueprint = trainer.create_blueprint(
        "Create a voting smart contract with rewards",
        "solidity"
    )
    print(f"\nBlueprint ID: {blueprint['id']}")
    print(f"Complexity: {blueprint['estimated_complexity']}")
    print(f"Suggested Approach:")
    for i, suggestion in enumerate(blueprint['suggested_approach'], 1):
        print(f"   {i}. {suggestion}")


if __name__ == "__main__":
    main()
