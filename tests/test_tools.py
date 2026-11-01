"""Tool-level checks; requires an AstrBot runtime in the Python environment."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from astrbot_plugin_structured_memory.main import StructuredMemory
from astrbot_plugin_structured_memory.store import FactStore


class ToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_search_arguments_and_user_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin = StructuredMemory.__new__(StructuredMemory)
            plugin.store = FactStore(Path(directory) / 'facts.sqlite3')
            alice = SimpleNamespace(unified_msg_origin='group-a', get_sender_id=lambda: 'alice',
                                    get_message_str=lambda: '我喜欢桂花乌龙', message_obj=SimpleNamespace(message_id='1'))
            bob = SimpleNamespace(unified_msg_origin='group-a', get_sender_id=lambda: 'bob',
                                  get_message_str=lambda: '我喜欢什么', message_obj=SimpleNamespace(message_id='2'))
            await plugin.remember_user_fact(alice, '偏好', '饮品', '桂花乌龙')
            self.assertIn('桂花乌龙', await plugin.find_user_facts(alice))
            self.assertIn('No matching', await plugin.find_user_facts(bob))
            self.assertIn('No matching', await plugin.find_session_events(alice))


if __name__ == '__main__':
    unittest.main()
