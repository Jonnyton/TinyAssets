"""Keep the explicit served catalog aligned with registered universe tools."""
import ast
from pathlib import Path
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ServedEngineCatalogTests(unittest.TestCase):
    def test_all_registered_engine_tools_are_exposed(self):
        tree = ast.parse((ROOT / "tinyassets/engine_mcp_server.py").read_text())
        registered = {
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(dec, ast.Attribute)
                and isinstance(dec.value, ast.Name)
                and dec.value.id == "mcp" and dec.attr == "tool"
                for dec in node.decorator_list
            )
        }
        served = runpy.run_path(str(ROOT / "tinyassets/served_tools.py"))[
            "SERVED_ENGINE_MCP_TOOLS"
        ]
        self.assertTrue(registered)
        self.assertEqual(registered, set(served))
        self.assertEqual(len(served), len(set(served)))


if __name__ == "__main__":
    unittest.main()
