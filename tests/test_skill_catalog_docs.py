#!/usr/bin/env python3

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestSkillCatalogDocs(unittest.TestCase):
    def test_readme_lists_four_skills_and_new_install_commands(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Four skills cover the core surface", readme)
        self.assertIn("modeio-skill-audit", readme)
        self.assertIn("--skill modeio-skill-audit --agent claude-code", readme)
        self.assertIn("--skill modeio-skill-audit --agent codex", readme)
        self.assertIn("--skill modeio-skill-audit --agent opencode", readme)
        self.assertIn("Cursor is not currently supported in this repo", readme)
        self.assertNotIn(
            "modeio-guardrail/scripts/skill_safety_assessment.py evaluate", readme
        )

    def test_skill_audit_skill_surface_has_expected_frontmatter_and_links(self):
        skill_doc = (REPO_ROOT / "modeio-skill-audit" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("name: modeio-skill-audit", skill_doc)
        self.assertIn("scan this skill repo", skill_doc)
        self.assertIn("is this repo safe to install", skill_doc)
        self.assertIn("references/prompt-contract.md", skill_doc)
        self.assertIn("scripts/skill_safety_assessment.py evaluate", skill_doc)

    def test_middleware_skill_surface_mentions_monitoring(self):
        skill_doc = (REPO_ROOT / "modeio-middleware" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("name: modeio-middleware", skill_doc)
        self.assertIn("monitor", skill_doc)
        self.assertIn("/modeio/dashboard", skill_doc)
        self.assertIn("/modeio/api/events", skill_doc)


if __name__ == "__main__":
    unittest.main()
