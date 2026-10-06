import hashlib
import random


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _stable_id(prefix, *parts):
    raw = '|'.join(str(p) for p in parts).encode('utf-8')
    return prefix + '-' + hashlib.sha256(raw).hexdigest()[:16]


def _normalize_seed_items(seed_items):
    _require(isinstance(seed_items, list) and len(seed_items) >= 2, 'seed_items must be a list with at least two items')
    normalized = []
    for index, item in enumerate(seed_items):
        _require(isinstance(item, dict), 'each seed item must be an object')
        domain = item.get('domain')
        prompt = item.get('prompt')
        expected = item.get('expected')
        _require(isinstance(domain, str) and domain.strip(), 'seed item domain must be non-empty string')
        _require(isinstance(prompt, str) and prompt.strip(), 'seed item prompt must be non-empty string')
        _require(isinstance(expected, str) and expected.strip(), 'seed item expected must be non-empty string')
        normalized.append({
            'source_index': index,
            'domain': domain.strip(),
            'prompt': prompt.strip(),
            'expected': expected.strip()
        })
    return normalized


def _generate_tasks(seed_items, seed):
    rng = random.Random(seed)
    order = list(range(len(seed_items)))
    rng.shuffle(order)
    tasks = []
    for generation_rank, source_index in enumerate(order):
        item = seed_items[source_index]
        task_id = _stable_id('task', seed, source_index, item['domain'], item['prompt'], item['expected'])
        tasks.append({
            'task_id': task_id,
            'generation_rank': generation_rank,
            'source_index': source_index,
            'domain': item['domain'],
            'instruction': item['prompt'],
            'oracle_expected': item['expected']
        })
    return tasks


def _agent_rollout(task):
    instruction = task['instruction'].strip()
    expected = task['oracle_expected'].strip()
    lower = instruction.lower()
    trajectory = [
        {'step': 1, 'role': 'agent', 'action': 'inspect_task', 'content': instruction},
        {'step': 2, 'role': 'agent', 'action': 'derive_candidate', 'content': expected}
    ]
    if '[fail]' in lower:
        answer = 'incorrect:' + expected
        trajectory.append({'step': 3, 'role': 'agent', 'action': 'final_answer', 'content': answer})
    elif '[invalid]' in lower:
        answer = ''
        trajectory.append({'step': 3, 'role': 'agent', 'action': 'final_answer', 'content': answer})
    elif '[low-quality]' in lower:
        answer = expected
        trajectory.append({'step': 3, 'role': 'agent', 'action': 'final_answer', 'content': answer})
    else:
        answer = expected
        trajectory.append({'step': 3, 'role': 'agent', 'action': 'verify_candidate', 'content': 'candidate compared against deterministic task oracle'})
        trajectory.append({'step': 4, 'role': 'agent', 'action': 'final_answer', 'content': answer})
    return {
        'task_id': task['task_id'],
        'answer': answer,
        'trajectory': trajectory
    }


def _verify(task, rollout):
    answer = rollout['answer']
    expected = task['oracle_expected']
    valid = isinstance(answer, str) and bool(answer.strip())
    exact_match = valid and answer.strip() == expected.strip()
    if not valid:
        verdict = 'invalid'
        reason = 'empty_or_non_string_answer'
    elif exact_match:
        verdict = 'passed'
        reason = 'exact_oracle_match'
    else:
        verdict = 'failed'
        reason = 'oracle_mismatch'
    return {
        'task_id': task['task_id'],
        'verdict': verdict,
        'reason': reason,
        'valid': valid,
        'oracle_match': exact_match
    }


def _quality_score(task, rollout, verification):
    if verification['verdict'] != 'passed':
        return 0.0
    actions = [step['action'] for step in rollout['trajectory']]
    has_inspection = 'inspect_task' in actions
    has_verification = 'verify_candidate' in actions
    has_final = 'final_answer' in actions
    score = 0.55
    score += 0.15 if has_inspection else 0.0
    score += 0.20 if has_verification else 0.0
    score += 0.10 if has_final else 0.0
    if '[low-quality]' in task['instruction'].lower():
        score = min(score, 0.60)
    return round(min(score, 1.0), 3)


def _validate_dataset(records):
    ids = []
    required = {'record_id', 'task_id', 'split', 'domain', 'instruction', 'answer', 'trajectory', 'verification', 'quality_score'}
    for record in records:
        _require(isinstance(record, dict), 'dataset record must be object')
        _require(required.issubset(record.keys()), 'dataset record schema is incomplete')
        _require(record['split'] in ('train', 'eval'), 'dataset split must be train or eval')
        _require(record['verification']['verdict'] == 'passed', 'dataset may contain only verified records')
        _require(record['quality_score'] >= 0.75, 'dataset may contain only records passing quality threshold')
        _require(isinstance(record['trajectory'], list) and len(record['trajectory']) >= 3, 'trajectory must contain agent steps')
        ids.append(record['record_id'])
    _require(len(ids) == len(set(ids)), 'dataset record IDs must be unique')
    return True


def execute(payload):
    _require(isinstance(payload, dict), 'payload must be an object')
    seed = payload.get('seed', 0)
    _require(isinstance(seed, int) and not isinstance(seed, bool), 'seed must be an integer')
    quality_threshold = payload.get('quality_threshold', 0.75)
    _require(isinstance(quality_threshold, (int, float)) and not isinstance(quality_threshold, bool), 'quality_threshold must be numeric')
    _require(0.0 <= float(quality_threshold) <= 1.0, 'quality_threshold must be between 0 and 1')
    seed_items = _normalize_seed_items(payload.get('seed_items'))
    tasks = _generate_tasks(seed_items, seed)
    processed = []
    rejection_counts = {'failed': 0, 'invalid': 0, 'low_quality': 0}
    dataset = []
    for task in tasks:
        rollout = _agent_rollout(task)
        verification = _verify(task, rollout)
        quality_score = _quality_score(task, rollout, verification)
        accepted = verification['verdict'] == 'passed' and quality_score >= float(quality_threshold)
        filter_reason = 'accepted'
        if verification['verdict'] == 'failed':
            rejection_counts['failed'] += 1
            filter_reason = 'verifier_failed'
        elif verification['verdict'] == 'invalid':
            rejection_counts['invalid'] += 1
            filter_reason = 'invalid_trajectory'
        elif quality_score < float(quality_threshold):
            rejection_counts['low_quality'] += 1
            filter_reason = 'quality_below_threshold'
        entry = {
            'task': task,
            'rollout': rollout,
            'verification': verification,
            'quality_score': quality_score,
            'accepted': accepted,
            'filter_reason': filter_reason
        }
        processed.append(entry)
        if accepted:
            bucket = int(hashlib.sha256((task['task_id'] + '|' + str(seed)).encode('utf-8')).hexdigest()[:8], 16) % 5
            split = 'eval' if bucket == 0 else 'train'
            dataset.append({
                'record_id': _stable_id('record', seed, task['task_id'], rollout['answer']),
                'task_id': task['task_id'],
                'split': split,
                'domain': task['domain'],
                'instruction': task['instruction'],
                'answer': rollout['answer'],
                'trajectory': rollout['trajectory'],
                'verification': verification,
                'quality_score': quality_score
            })
    _validate_dataset(dataset)
    train_count = sum(1 for row in dataset if row['split'] == 'train')
    eval_count = sum(1 for row in dataset if row['split'] == 'eval')
    statistics = {
        'seed': seed,
        'generated_tasks': len(tasks),
        'rollouts_completed': len(processed),
        'verified_passed': sum(1 for row in processed if row['verification']['verdict'] == 'passed'),
        'verified_failed': sum(1 for row in processed if row['verification']['verdict'] == 'failed'),
        'verified_invalid': sum(1 for row in processed if row['verification']['verdict'] == 'invalid'),
        'accepted_records': len(dataset),
        'rejected_records': len(processed) - len(dataset),
        'train_records': train_count,
        'eval_records': eval_count,
        'quality_threshold': float(quality_threshold),
        'rejection_counts': rejection_counts,
        'dataset_fingerprint': hashlib.sha256(repr([(r['record_id'], r['split'], r['quality_score']) for r in dataset]).encode('utf-8')).hexdigest()
    }
    return {
        'tasks': tasks,
        'processed': processed,
        'dataset': dataset,
        'statistics': statistics,
        'schema_valid': True
    }
