import importlib.util
import pathlib

TARGET = 'synthetic-agent-data-ge-5456d7a2'
path = pathlib.Path('src') / 'bricks' / TARGET / 'core.py'
spec = importlib.util.spec_from_file_location('brick_core', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

payload = {
    'seed': 42,
    'seed_items': [
        {'domain': 'code', 'prompt': 'Produce A', 'expected': 'A'},
        {'domain': 'sql', 'prompt': 'Produce B', 'expected': 'B'},
        {'domain': 'office', 'prompt': 'Produce C [fail]', 'expected': 'C'},
        {'domain': 'cyber', 'prompt': 'Produce D', 'expected': 'D'}
    ]
}
first = module.execute(payload)
second = module.execute(payload)
required_top = {'tasks', 'processed', 'dataset', 'statistics', 'schema_valid'}
assert set(first.keys()) == required_top
assert first == second
assert first['statistics'] == second['statistics']
assert first['statistics']['dataset_fingerprint'] == second['statistics']['dataset_fingerprint']
assert first['schema_valid'] is True
assert len(first['processed']) == len(first['tasks']) == 4
for item in first['processed']:
    assert set(item.keys()) == {'task', 'rollout', 'verification', 'quality_score', 'accepted', 'filter_reason'}
    assert item['rollout']['task_id'] == item['task']['task_id']
    assert item['verification']['task_id'] == item['task']['task_id']
    assert item['verification']['verdict'] in {'passed', 'failed', 'invalid'}
for row in first['dataset']:
    assert {'record_id', 'task_id', 'split', 'domain', 'instruction', 'answer', 'trajectory', 'verification', 'quality_score'} <= set(row.keys())
    assert row['split'] in {'train', 'eval'}
    assert row['verification']['verdict'] == 'passed'
    assert row['quality_score'] >= 0.75
accepted_task_ids = {item['task']['task_id'] for item in first['processed'] if item['accepted']}
dataset_task_ids = {row['task_id'] for row in first['dataset']}
assert dataset_task_ids == accepted_task_ids
