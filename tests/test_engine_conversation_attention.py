"""The indicator observes only successful, bounded tool return values."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tinyassets.engine_conversation_attention import ConversationAttention


def context(name="bash", arguments=None, session="background-session"):
    return SimpleNamespace(
        message=SimpleNamespace(name=name, arguments=arguments or {}),
        fastmcp_context=SimpleNamespace(session_id=session),
    )


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = []
        for target, value in [
            ("tinyassets.engine_mcp_server._ACTOR_ID", "founder"),
            ("tinyassets.engine_mcp_server._GRAPH_ID", "u-one"),
            ("tinyassets.engine_mcp_server._binding_error", lambda: None),
            ("tinyassets.api.branches._base_path", lambda: "/unused"),
            ("tinyassets.shared_self.require_founder_home", lambda *args: "/owner-only"),
        ]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        self.middleware = ConversationAttention()

    async def test_refreshes_after_call_preserves_payload_and_durable_reader(self):
        calls = []
        async def next_call(ctx):
            calls.append("tool")
            return SimpleNamespace(content=[SimpleNamespace(text="original")],
                                   structured_content={"result": "original"}, is_error=False)
        def observe(root, session, reader, *, page):
            calls.append((root, session, reader))
            return {"available": True, "unread_count": 3}
        with patch("tinyassets.engine_conversation_attention.observe", observe):
            first = await self.middleware.on_call_tool(context(
                "read_graph", {"target": "conversation", "query": "reader:background"},
            ), next_call)
            second = await self.middleware.on_call_tool(context(), next_call)
            await self.middleware.on_call_tool(context(session="foreground-session"), next_call)
        self.assertEqual(first.content[0].text, "original")
        self.assertEqual(first.structured_content, {"result": "original"})
        self.assertEqual(json.loads(second.content[-1].text)
                         ["conversation_indicator"]["unread_count"], 3)
        self.assertEqual(calls[0], "tool")
        self.assertEqual(calls[1], ("/owner-only", "principal:founder", "named:background"))
        self.assertEqual(calls[3][2], "named:background")
        self.assertEqual(calls[5][2], "session:foreground-session")

    async def test_no_count_after_revocation(self):
        result = SimpleNamespace(content=[], structured_content={}, is_error=False)
        async def next_call(ctx):
            return result
        with patch("tinyassets.engine_mcp_server._binding_error", side_effect=[None, "revoked"]):
            with patch("tinyassets.engine_conversation_attention.observe") as observe:
                got = await self.middleware.on_call_tool(context(), next_call)
        self.assertIs(got, result)
        observe.assert_not_called()
        self.assertEqual(got.content, [])

    async def test_metadata_failure_preserves_completed_effect(self):
        result = SimpleNamespace(content=[SimpleNamespace(text="write completed")],
                                 structured_content={"result": "write completed"}, is_error=False)
        async def next_call(ctx):
            return result
        with patch("tinyassets.engine_conversation_attention.observe",
                   side_effect=OSError("db busy")):
            got = await self.middleware.on_call_tool(context(), next_call)
        self.assertFalse(got.is_error)
        self.assertEqual(got.content[0].text, "write completed")
        self.assertIsNone(json.loads(got.content[-1].text)
                          ["conversation_indicator"]["unread_count"])

    async def test_failed_tool_read_never_acknowledges(self):
        async def next_call(ctx):
            return SimpleNamespace(content=[SimpleNamespace(text='{"available": true}')],
                                   is_error=True)
        with patch("tinyassets.engine_conversation_attention.observe",
                   return_value={"available": True, "unread_count": 1}) as observe:
            await self.middleware.on_call_tool(context(
                "read_graph", {"target": "conversation", "field_name": "1"},
            ), next_call)
        self.assertIsNone(observe.call_args.kwargs["page"])

    async def test_no_session_does_not_share_anonymous_cursor(self):
        async def next_call(ctx):
            return SimpleNamespace(content=[], is_error=False)
        with patch("tinyassets.engine_conversation_attention.observe") as observe:
            result = await self.middleware.on_call_tool(context(session=None), next_call)
        observe.assert_not_called()
        self.assertIsNone(json.loads(result.content[-1].text)
                          ["conversation_indicator"]["unread_count"])
