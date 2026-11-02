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
    async def test_group_profile_consent_and_current_speaker_injection(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin = StructuredMemory.__new__(StructuredMemory)
            plugin.store = FactStore(Path(directory) / 'facts.sqlite3')
            plugin.config = {'inject_speaker_profile': True}
            def event(user, group='42'):
                return SimpleNamespace(unified_msg_origin='qq:GroupMessage:42', get_sender_id=lambda: user,
                                       get_group_id=lambda: group, get_platform_id=lambda: 'qq',
                                       get_message_str=lambda: '测试', message_obj=SimpleNamespace(message_id='1'),
                                       plain_result=lambda text: text)
            alice, bob = event('101'), event('202')
            plugin.store.save(alice.unified_msg_origin, '101', '偏好', '茶', '乌龙', '1', '我喜欢乌龙')
            self.assertIn('No shared', await plugin.find_shared_group_profile(bob, '101'))
            [item async for item in plugin.share_my_profile(alice)]
            self.assertIn('乌龙', await plugin.find_shared_group_profile(bob, '101'))
            self.assertIn('unavailable', await plugin.find_shared_group_profile(event('202', ''), '101'))
            request = SimpleNamespace(extra_user_content_parts=[])
            await plugin.add_memory_policy(bob, request)
            self.assertNotIn('乌龙', '\n'.join(item.text for item in request.extra_user_content_parts))
            [item async for item in plugin.unshare_my_profile(alice)]
            self.assertIn('No shared', await plugin.find_shared_group_profile(bob, '101'))

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

    async def test_configured_limits_and_save_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin = StructuredMemory.__new__(StructuredMemory)
            plugin.store = FactStore(Path(directory) / 'facts.sqlite3')
            plugin.config = {'fact_search_limit': 1, 'list_limit': 1, 'event_search_limit': 1,
                             'suggest_automatic_memory': False}
            user = SimpleNamespace(unified_msg_origin='group-a', get_sender_id=lambda: 'alice',
                                   get_message_str=lambda: '测试', message_obj=SimpleNamespace(message_id='1'),
                                   plain_result=lambda text: text, get_platform_id=lambda: 'platform')
            plugin.store.save('group-a', 'alice', '偏好', '茶', '乌龙', '1', '我喜欢乌龙')
            plugin.store.save('group-a', 'alice', '偏好', '饭', '米饭', '2', '我喜欢米饭')
            self.assertEqual((await plugin.find_user_facts(user)).count('id='), 1)
            listing = [item async for item in plugin.list_my_memories(user)]
            self.assertIn('最多 1 条', listing[0])
            request = SimpleNamespace(extra_user_content_parts=[])
            await plugin.add_memory_policy(user, request)
            self.assertIn('只在当前说话者明确要求记住', request.extra_user_content_parts[0].text)
            plugin.config['list_limit'] = -10
            self.assertEqual(plugin._limit('list_limit', 50, 200), 1)
            plugin.config['list_limit'] = 'invalid'
            self.assertEqual(plugin._limit('list_limit', 50, 200), 50)


if __name__ == '__main__':
    unittest.main()
