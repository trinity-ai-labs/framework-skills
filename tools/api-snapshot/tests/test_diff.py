import unittest

from support import snapshot, tool


class DiffReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = tool.diff_snapshots(snapshot("v1", "9.9.9"), snapshot("v2", "9.9.10"))

    def section(self, tier, heading):
        body = self.report.split("## %s\n" % tier, 1)[1]
        body = body.split("\n## ", 1)[0]
        return body.split("### %s\n" % heading, 1)[1].split("\n### ", 1)[0]

    def test_added_export_under_its_tier(self):
        self.assertIn("`brandNew`", self.section("stable", "Exports added"))

    def test_removed_export_under_its_tier(self):
        self.assertIn("`map`", self.section("stable", "Exports removed"))

    def test_changed_export_reports_the_declaration(self):
        changed = self.section("stable", "Exports changed")
        self.assertIn("`succeed`", changed)
        self.assertIn("declaration changed", changed)

    def test_tier_change_is_reported_under_the_new_tier(self):
        self.assertIn("tier unstable -> stable", self.section("stable", "Exports changed"))
        self.assertIn("`Tagged` (type)", self.section("stable", "Exports changed"))

    def test_modules_added_and_removed_by_tier(self):
        self.assertIn("`effect/Fresh`", self.section("unstable", "Modules added"))
        self.assertIn("`effect/http/Router`", self.section("unstable", "Modules removed"))
        self.assertIn("`effect/Function`", self.section("stable", "Modules removed"))

    def test_stable_tier_comes_first_and_output_is_stable(self):
        self.assertLess(self.report.index("## stable"), self.report.index("## unstable"))
        again = tool.diff_snapshots(snapshot("v1", "9.9.9"), snapshot("v2", "9.9.10"))
        self.assertEqual(self.report, again)

    def test_identical_snapshots_report_no_changes(self):
        s = snapshot("v1", "9.9.9")
        self.assertIn("No changes.", tool.diff_snapshots(s, s))


if __name__ == "__main__":
    unittest.main()
