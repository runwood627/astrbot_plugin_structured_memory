"""Offline regression tests using synthetic data and temporary databases."""
import importlib.util
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

spec = importlib.util.spec_from_file_location('structured_memory_store', Path(__file__).resolve().parents[1] / 'store.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
FactStore = module.FactStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'facts.db'
        self.store = FactStore(self.path)

    def test_user_and_session_isolation(self):
        self.store.save('group-a', 'alice', '偏好', '饮品', '桂花乌龙', '1', '我喜欢桂花乌龙')
        self.assertEqual(self.store.search('group-a', 'alice', '偏好')[0][3], '桂花乌龙')
        self.assertEqual(self.store.search('group-a', 'bob'), [])
        self.assertEqual(self.store.search('group-b', 'alice'), [])

    def test_shared_profiles_require_scope_bound_consent(self):
        self.store.save('p:GroupMessage:1', 'alice', '偏好', '茶', '乌龙', '1', '我喜欢乌龙')
        self.store.save('p:GroupMessage:1', 'alice', '个人信息', '住址', '秘密', '2', '住址')
        self.store.save('p:GroupMessage:1', 'alice', '性格', '气质', '可能安静', '3', '也许', certainty='unconfirmed')
        self.assertEqual(self.store.shared_profile('p:GroupMessage:1', 'alice'), [])
        self.store.set_profile_sharing('p:GroupMessage:1', 'alice', True)
        self.assertEqual(self.store.shared_profile('p:GroupMessage:1', 'alice'), [('偏好', '茶', '乌龙')])
        self.assertEqual(self.store.shared_profile('p:GroupMessage:2', 'alice'), [])
        self.store.set_profile_sharing('p:GroupMessage:1', 'alice', False)
        self.assertEqual(self.store.shared_profile('p:GroupMessage:1', 'alice'), [])

    def test_cross_session_is_own_opt_in_and_platform_bound(self):
        self.store.save('p_x:GroupMessage:1', 'alice', '偏好', '茶', '乌龙', '1', '我喜欢乌龙')
        self.store.save('pAx:GroupMessage:1', 'alice', '偏好', '茶', '错误', '2', '其他平台')
        self.store.save('p_x:GroupMessage:1', 'bob', '偏好', '茶', '奶茶', '3', '其他人')
        self.assertEqual(self.store.own_cross_session('p_x', 'alice', 'p_x:FriendMessage:alice'), [])
        self.store.set_cross_session('p_x', 'alice', True)
        self.assertEqual(self.store.own_cross_session('p_x', 'alice', 'p_x:FriendMessage:alice'), [('偏好', '茶', '乌龙')])
        self.store.set_cross_session('p_x', 'alice', False)
        self.assertEqual(self.store.own_cross_session('p_x', 'alice', 'p_x:FriendMessage:alice'), [])

    def test_dedup_uses_normalized_stored_values(self):
        args = ('group', 'alice', '偏好', 'a' * 90, 'b' * 310, '1', 'source')
        first = self.store.save(*args)
        self.assertEqual(first, self.store.save(*args))
        self.assertEqual(len(self.store.list_facts('group', 'alice')), 1)
        with self.assertRaises(ValueError):
            self.store.save('group', 'alice', '偏好', ' ', ' ', '1', 'source')

    def test_correction_and_deletion_scope(self):
        first = self.store.save('group', 'alice', '称呼', '名字', '小明', '1', '叫我小明')
        self.assertIsNone(self.store.correct('group', 'bob', first, '阿明', '2', '改名'))
        changed = self.store.correct('group', 'alice', first, '阿明', '2', '改名')
        self.assertEqual(self.store.search('group', 'alice')[0][3], '阿明')
        self.assertEqual(self.store.forget('group', 'bob', changed), 0)
        self.assertEqual(self.store.forget('group', 'alice', changed), 1)
        self.assertEqual(self.store.list_facts('group', 'alice'), [])

    def test_expiration_and_uncertainty(self):
        self.store.save('g', 'u', '其他', '过去', '过期', '1', '来源', expires_on='2000-01-01')
        self.store.save('g', 'u', '其他', '可能', '可能旅行', '2', '来源', certainty='unconfirmed')
        results = self.store.search('g', 'u')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][6], 'unconfirmed')
        self.assertEqual(len(self.store.list_facts('g', 'u')), 2)

    def test_event_scope_dates_and_literal_wildcards(self):
        self.store.save_event('g', 'alice', '生日聚会', '大家见面', '2026-10-01', '1', '请记住')
        self.assertEqual(len(self.store.search_events('g', '生日', '2026-10-01', '2026-10-31')), 1)
        self.assertEqual(self.store.search_events('other', '生日'), [])
        self.assertEqual(self.store.search_events('g', '%'), [])
        with self.assertRaises(ValueError):
            self.store.save_event('g', 'alice', '标题', '内容', '明天', '1', '来源')

    def test_previous_schema_is_upgraded_without_losing_records(self):
        other = Path(self.temp.name) / 'old.db'
        with closing(sqlite3.connect(other)) as db, db:
            db.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY, scope TEXT NOT NULL, user_id TEXT NOT NULL, category TEXT NOT NULL, attribute TEXT NOT NULL, value TEXT NOT NULL, source_message_id TEXT NOT NULL, source_text TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL DEFAULT 'active')")
            db.execute("INSERT INTO facts(scope,user_id,category,attribute,value,source_message_id,source_text) VALUES('g','u','偏好','食物','米饭','1','喜欢米饭')")
        migrated = FactStore(other)
        self.assertEqual(migrated.search('g', 'u')[0][3], '米饭')
        self.assertEqual(FactStore(other).search('g', 'u')[0][3], '米饭')


if __name__ == '__main__':
    unittest.main()
