import unittest

from support import exports, snapshot


class ParseForms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = snapshot("v1", "9.9.9")
        cls.fx = exports(cls.snap, "effect/Effect")

    def names(self):
        return {n for n, _ in self.fx}

    def test_const_one_line(self):
        e = self.fx[("succeed", "value")]
        self.assertEqual((e["kind"], e["since"], e["stability"]), ("const", "2.0.0", "stable"))

    def test_dual_api_inner_comments_are_not_exports_or_tags(self):
        e = self.fx[("map", "value")]
        self.assertEqual(e["stability"], "stable")  # the inner @stability unstable belongs to a signature
        self.assertEqual([k for k in self.fx if k[0] == "map"], [("map", "value")])

    def test_overloads_are_one_export(self):
        self.assertEqual([k for k in self.fx if k[0] == "gen"], [("gen", "value")])
        self.assertEqual(self.fx[("gen", "value")]["kind"], "function")

    def test_type_and_value_sharing_a_name_stay_distinct(self):
        self.assertEqual(self.fx[("Effect", "type")]["kind"], "interface")
        self.assertEqual(self.fx[("Effect", "value")]["kind"], "const")
        self.assertEqual(self.fx[("Effect", "namespace")]["kind"], "namespace")

    def test_namespace_members_are_recorded_dotted_with_own_tier(self):
        self.assertEqual(self.fx[("Effect.Success", "type")]["stability"], "stable")
        self.assertEqual(self.fx[("Effect.Services", "type")]["stability"], "unstable")

    def test_class_helper_is_not_an_export(self):
        self.assertIn(("Service", "value"), self.fx)
        self.assertNotIn("Service_base", self.names())

    def test_reserved_word_alias_exports_the_alias(self):
        e = self.fx[("void", "value")]
        self.assertEqual((e["kind"], e["since"]), ("const", "2.0.0"))
        self.assertNotIn("void_", self.names())

    def test_empty_export_adds_nothing_and_example_code_is_not_declarations(self):
        self.assertNotIn("fake", self.names())
        self.assertNotIn("Fake", self.names())
        self.assertIn("real", self.names())

    def test_stability_is_per_export_not_per_module(self):
        self.assertEqual(self.fx[("Tagged", "type")]["stability"], "unstable")
        self.assertEqual(self.fx[("succeed", "value")]["stability"], "stable")
        router = exports(self.snap, "effect/http/Router")
        self.assertEqual({e["stability"] for e in router.values()}, {"unstable"})

    def test_root_reexport_lists_and_star_as_barrel_entries(self):
        root = exports(self.snap, "effect")
        self.assertEqual(root[("identity", "value")]["kind"], "reexport")
        self.assertEqual(root[("identity", "value")]["stability"], "stable")
        self.assertEqual(root[("pipe", "value")]["stability"], "unstable")
        self.assertEqual(root[("Effect", "value")]["kind"], "module")
        self.assertEqual(root[("Effect", "value")]["stability"], "unstable")
        self.assertTrue(self.snap["modules"]["effect"]["barrel"])
        self.assertTrue(self.snap["modules"]["effect/http"]["barrel"])

    def test_internal_paths_are_excluded(self):
        self.assertEqual(self.snap["internal_files_excluded"], 2)
        self.assertFalse([m for m in self.snap["modules"] if "internal" in m])

    def test_hash_tracks_the_declaration_not_whitespace_or_comments(self):
        from support import tool
        a = tool.build_snapshot({"M.d.ts": "/** @since 1.0.0 */\nexport declare const x: number;\n"}, "1.0.0")
        b = tool.build_snapshot({"M.d.ts": "// c\n/** other doc @since 1.0.0 */\nexport   declare const x:\n number;"}, "1.0.0")
        c = tool.build_snapshot({"M.d.ts": "/** @since 1.0.0 */\nexport declare const x: string;\n"}, "1.0.0")
        h = lambda s: s["modules"]["effect/M"]["exports"][0]["hash"]
        self.assertEqual(h(a), h(b))
        self.assertNotEqual(h(a), h(c))

    def test_unrecognised_export_is_an_error_not_silence(self):
        from support import tool
        with self.assertRaises(ValueError):
            tool.build_snapshot({"M.d.ts": "export default foo;\n"}, "1.0.0")


if __name__ == "__main__":
    unittest.main()
