#!/usr/bin/env python3
"""check_rule_divergence.py carries its own copy of install.py's rule splitting, because a bundle
script can't import the installer. This test keeps the two in step on the shipped rules file."""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSameRuleSplitting(unittest.TestCase):
    def test_both_split_the_shipped_claude_md_the_same_way(self):
        installer = _load("install_mod", "install.py")
        script = _load("divergence_mod", "payload/skills/finalise/scripts/check_rule_divergence.py")
        with open(os.path.join(ROOT, "payload/user-CLAUDE.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(installer.split_rules(text), script.split_rules(text))
        self.assertGreater(len(script.split_rules(text)), 10)


if __name__ == "__main__":
    unittest.main()
