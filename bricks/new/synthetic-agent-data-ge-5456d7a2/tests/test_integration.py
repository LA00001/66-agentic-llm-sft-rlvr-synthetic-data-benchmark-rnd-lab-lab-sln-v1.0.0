import importlib.util
import pathlib

TARGET = 'synthetic-agent-data-ge-5456d7a2'
path = pathlib.Path('src') / 'bricks' / TARGET / 'core.py'
spec = importlib.util.spec_from_file_location('brick_core', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

corpus = [
    {'domain': 'code', 'prompt': 'Solve deterministic code task one', 'expected': 'CODE-1'},
    {'domain': 'sql', 'prompt': 'Solve deterministic SQL task two', 'expected': 'SQL-2'},
    {'domain': 'office', 'prompt': 'Solve office task three [low-quality]', 'expected': 'OFFICE-3'},
    {'domain': 'cybersecurity', 'prompt': 'Solve cyber task four [fail]', 'expected': 'CYBER-4'},
    {'domain': 'code', 'prompt': 'Solve code task five [invalid]', 'expected': 'CODE-5'},
    {'domain': 'sql', 'prompt': 'Solve SQL task six', 'expected': 'SQL-6'}
]
payload = {'seed': 2026, 'quality_threshold': 0.75, 'seed_items': corpus}
run1 = module.execute(payload)
run2 = module.execute(payload)
assert run1['statistics']['generated_tasks'] == 6
assert run1['statistics']['rollouts_completed'] == 6
assert run1['statistics']['verified_passed'] == 4
assert run1['statistics']['verified_failed'] == 1
assert run1['statistics']['verified_invalid'] == 1
assert run1['statistics']['accepted_records'] == 3
assert run1['statistics']['rejected_records'] == 3
assert run1['statistics']['rejection_counts'] == {'failed': 1, 'invalid': 1, 'low_quality': 1}
assert run1['statistics'] == run2['statistics']
assert run1['dataset'] == run2['dataset']
assert run1['tasks'] == run2['tasks']
assert all(item['rollout']['trajectory'] for item in run1['processed'])
assert all(item['verification']['reason'] for item in run1['processed'])
accepted = [item for item in run1['processed'] if item['accepted']]
rejected = [item for item in run1['processed'] if not item['accepted']]
assert len(accepted) == 3
assert len(rejected) == 3
accepted_ids = {item['task']['task_id'] for item in accepted}
assert {row['task_id'] for row in run1['dataset']} == accepted_ids
assert not any(row['task_id'] in {item['task']['task_id'] for item in rejected} for row in run1['dataset'])
assert len({row['record_id'] for row in run1['dataset']}) == len(run1['dataset'])
assert run1['statistics']['train_records'] + run1['statistics']['eval_records'] == len(run1['dataset'])
changed = module.execute({'seed': 2027, 'quality_threshold': 0.75, 'seed_items': corpus})
assert changed['statistics']['seed'] == 2027
assert changed['statistics']['dataset_fingerprint'] != run1['statistics']['dataset_fingerprint']
