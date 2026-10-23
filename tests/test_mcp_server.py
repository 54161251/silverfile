"""The tax tools must be reachable through a real MCP server, not just as importable functions."""
import asyncio
import unittest

from src.agents.computation import ToolCallError, ToolClient
from src.tools.mcp_server import SERVER_NAME, build_server
from src.tools.tax_math import TOOLS


class McpServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = build_server()
        cls.client = ToolClient(cls.server)

    def call(self, name, **arguments):
        return asyncio.run(self.client.call(name, **arguments))

    def test_server_name(self):
        self.assertEqual(SERVER_NAME, "silverfile-tax-math")

    def test_lists_every_tool(self):
        listed = asyncio.run(self.server.list_tools())
        self.assertEqual({tool.name for tool in listed}, set(TOOLS))

    def test_every_tool_has_a_description_and_schema(self):
        for tool in asyncio.run(self.server.list_tools()):
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.description)
                schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
                self.assertEqual(schema["type"], "object")

    def test_call_returns_structured_provenance_fields(self):
        result = self.call("income_tax", filing_status="single", taxable_income=26775)
        self.assertEqual(result["value"], 2975)
        for key in ("formula", "inputs", "tool", "unrounded"):
            self.assertIn(key, result)

    def test_tool_errors_surface_with_their_message(self):
        with self.assertRaises(ToolCallError) as caught:
            self.call("standard_deduction", filing_status="zzz", box_count=0)
        self.assertIn("Unknown filing status", str(caught.exception))

    def test_unknown_tool_is_an_error(self):
        with self.assertRaises(ToolCallError):
            self.call("does_not_exist")


if __name__ == "__main__":
    unittest.main()
