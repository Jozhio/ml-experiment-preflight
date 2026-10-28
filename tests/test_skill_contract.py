"""Static contract checks for the project-level Agent Skill files."""

import re
from pathlib import Path
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SKILL_DIRS = (
    PROJECT / ".claude" / "skills" / "ml-experiment-preflight",
    PROJECT / ".agents" / "skills" / "ml-experiment-preflight",
)


class SkillContractTests(unittest.TestCase):
    def read_skill(self, directory):
        path = directory / "SKILL.md"
        self.assertTrue(path.is_file(), path)
        return path.read_text(encoding="utf-8")

    @staticmethod
    def frontmatter(text):
        assert text.startswith("---\n")
        end = text.find("\n---\n", 4)
        assert end > 0
        return text[4:end], text[end + 5:]

    def test_skill_layouts_exist_and_copies_are_identical(self):
        for directory in SKILL_DIRS:
            self.assertTrue((directory / "SKILL.md").is_file())
        self.assertEqual(
            (SKILL_DIRS[0] / "SKILL.md").read_bytes(),
            (SKILL_DIRS[1] / "SKILL.md").read_bytes(),
            "Claude Code and Codex skill copies must stay identical",
        )

    def test_frontmatter_name_and_description_follow_spec(self):
        for directory in SKILL_DIRS:
            front, _ = self.frontmatter(self.read_skill(directory))
            name = re.search(r"^name:\s*(.+)$", front, re.M).group(1).strip()
            description = re.search(
                r"^description:\s*(.+)$", front, re.M
            ).group(1).strip()
            self.assertRegex(name, r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
            self.assertEqual(name, directory.name)
            self.assertLessEqual(len(name), 64)
            self.assertTrue(1 <= len(description) <= 1024)
            self.assertIn("preflight", description.lower())
            self.assertIn('version: "0.1.0"', front)

    def test_body_documents_cli_and_six_result_interpretation(self):
        for directory in SKILL_DIRS:
            _, body = self.frontmatter(self.read_skill(directory))
            self.assertIn("--format json", body)
            self.assertIn("python -m ml_experiment_preflight", body)
            self.assertIn("GIT-001", body)
            self.assertIn("OUT-002", body)
            self.assertIn("coverage_complete", body)
            self.assertIn("blocked", body)
            self.assertIn("incomplete", body)
            self.assertIn("unknown", body)

    def test_unknown_is_never_pass_and_blocked_is_not_hidden(self):
        for directory in SKILL_DIRS:
            _, body = self.frontmatter(self.read_skill(directory))
            self.assertIn("Never describe unknown as pass", body)
            self.assertIn("Always state `blocked` explicitly", body)
            self.assertIn("coverage_complete=false", body)
            self.assertIn("Do not infer", body)

    def test_hard_boundaries_are_explicit(self):
        for directory in SKILL_DIRS:
            _, body = self.frontmatter(self.read_skill(directory))
            for required in (
                "Never run training",
                "Never read the contents of training data",
                "Never create, edit, move, or delete user experiment files",
                "Never upload",
                "Never run `git add`",
                "Do not reimplement",
                "do not execute",
            ):
                self.assertIn(required, body)

    def test_skill_has_no_absolute_paths_or_host_specific_commands(self):
        for directory in SKILL_DIRS:
            text = self.read_skill(directory)
            self.assertNotIn("F:\\", text)
            self.assertNotIn("C:\\Users\\", text)
            self.assertNotIn("/home/", text)
            self.assertNotIn("--dangerously", text)
            self.assertNotIn("allow_implicit_invocation", text)

    def test_skill_does_not_contain_a_second_rule_engine(self):
        for directory in SKILL_DIRS:
            _, body = self.frontmatter(self.read_skill(directory))
            self.assertNotIn("def evaluate_", body)
            self.assertNotIn("import subprocess", body)
            self.assertNotIn("class ", body)
            self.assertIn("CLI", body)


if __name__ == "__main__":
    unittest.main()
