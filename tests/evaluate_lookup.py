"""Small deterministic lookup demonstration, not an end-to-end model benchmark."""
import importlib.util
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

spec = importlib.util.spec_from_file_location('structured_store', Path(__file__).resolve().parents[1] / 'store.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

FACTS = [
    ('g1', 'alice', '偏好', '饮品', '桂花乌龙', '我喜欢桂花乌龙'),
    ('g1', 'alice', '偏好', '食物', '米饭', '我最喜欢米饭'),
    ('g1', 'alice', '称呼', '名字', '小明', '请叫我小明'),
    ('g1', 'bob', '偏好', '饮品', '柠檬茶', '我喜欢柠檬茶'),
    ('g2', 'alice', '偏好', '饮品', '咖啡', '我喜欢咖啡'),
]
# Scope, user, category, exact attribute, literal baseline keyword, expected value.
# Category/attribute are manually supplied: this deliberately excludes model parsing.
QUERIES = [
    ('g1', 'alice', '偏好', '饮品', '饮品', '桂花乌龙'),
    ('g1', 'alice', '偏好', '食物', '米饭', '米饭'),
    ('g1', 'alice', '称呼', '名字', '名字', '小明'),
    ('g1', 'bob', '偏好', '饮品', '柠檬茶', '柠檬茶'),
    ('g2', 'alice', '偏好', '饮品', '饮品', '咖啡'),
    ('g1', 'alice', '偏好', '爱喝的茶', '爱喝的茶', '桂花乌龙'),
    ('g1', 'carol', '偏好', '饮品', '饮品', None),
    ('g3', 'alice', '偏好', '饮品', '饮品', None),
]


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'synthetic.sqlite3'
        store = module.FactStore(path)
        for scope, user, category, attribute, value, source in FACTS:
            store.save(scope, user, category, attribute, value, 'synthetic', source)
        metrics = {'structured_exact': {'hit': 0, 'miss': 0, 'empty_correct': 0, 'empty_wrong': 0},
                   'literal_source': {'hit': 0, 'miss': 0, 'empty_correct': 0, 'empty_wrong': 0}}
        for scope, user, category, attribute, keyword, expected in QUERIES:
            rows = store.search(scope, user, category, attribute)
            structured = [row[3] for row in rows]
            with closing(sqlite3.connect(path)) as db:
                baseline = [r[0] for r in db.execute('SELECT value FROM facts WHERE scope=? AND user_id=? AND status=? AND instr(source_text,?)>0', (scope, user, 'active', keyword))]
            for name, values in [('structured_exact', structured), ('literal_source', baseline)]:
                outcome = ('hit' if expected in values else 'miss') if expected is not None else ('empty_wrong' if values else 'empty_correct')
                metrics[name][outcome] += 1
        print('Synthetic deterministic lookup; categories and attributes supplied by the experiment, not an LLM.')
        print('Six answerable queries (one intentionally uses an alias); two empty/isolation queries.')
        for name, result in metrics.items():
            print(name, result)
        assert metrics['structured_exact']['empty_wrong'] == 0


if __name__ == '__main__':
    main()
