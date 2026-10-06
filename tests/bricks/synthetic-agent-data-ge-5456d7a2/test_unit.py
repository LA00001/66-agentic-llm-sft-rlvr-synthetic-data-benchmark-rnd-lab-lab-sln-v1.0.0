import importlib.util
import pathlib

TARGET = 'synthetic-agent-data-ge-5456d7a2'
path = pathlib.Path('src') / 'bricks' / TARGET / 'core.py'
spec = importlib.util.spec_from_file_location('brick_core', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

payload = {
    'seed': 17,
    'quality_threshold': 0.75,
    'seed_items': [
        {'domain': 'code', 'prompt': 'Return token ALPHA', 'expected': 'ALPHA'},
        {'domain': 'sql', 'prompt': 'Return token BETA [fail]', 'expected': 'BETA'},
        {'domain': 'office', 'prompt': 'Return token GAMMA [invalid]', 'expected': 'GAMMA'},
        {'domain': 'cyber', 'prompt': 'Return token DELTA [low-quality]', 'expected': 'DELTA'},
        {'domain': 'code', 'prompt': 'Return token EPSILON', 'expected': 'EPSILON'}
    ]
}
result = module.execute(payload)
assert result['statistics']['generated_tasks'] == 5
assert result['statistics']['rollouts_completed'] == 5
assert result['statistics']['accepted_records'] == 2
assert result['statistics']['rejected_records'] == 3
assert result['statistics']['rejection_counts'] == {'failed': 1, 'invalid': 1, 'low_quality': 1}
assert all(len(item['rollout']['trajectory']) >= 3 for item in result['processed'])
verdicts = {item['task']['instruction']: item['verification']['verdict'] for item in result['processed']}
assert verdicts['Return token BETA [fail]'] == 'failed'
assert verdicts['Return token GAMMA [invalid]'] == 'invalid'
assert all(row['verification']['verdict'] == 'passed' for row in result['dataset'])
assert all(row['quality_score'] >= 0.75 for row in result['dataset'])
assert len({row['record_id'] for row in result['dataset']}) == len(result['dataset'])
try:
    module.execute({'seed': 1, 'seed_items': [{'domain': 'x', 'prompt': 'x', 'expected': 'x'}]})
    raise AssertionError('expected validation failure')
except ValueError as exc:
    assert 'at least two' in str(exc)
