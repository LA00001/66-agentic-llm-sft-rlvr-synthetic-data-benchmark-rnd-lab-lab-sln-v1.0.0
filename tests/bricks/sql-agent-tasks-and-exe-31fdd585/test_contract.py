import importlib.util
from pathlib import Path

BRICK_ID = 'sql-agent-tasks-and-exe-31fdd585'
CORE = Path('src') / 'bricks' / BRICK_ID / 'core.py'
spec = importlib.util.spec_from_file_location('brick_core_contract', CORE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_reproducible_benchmark_artifact_contract():
    result = module.execute({})
    artifact = result['artifact']
    assert artifact['engine'] == 'sqlite3'
    assert artifact['scope'] == 'LOCAL'
    assert isinstance(artifact['query'], str) and artifact['query'].strip()
    assert isinstance(artifact['canonical_query'], str) and 'JOIN' in artifact['canonical_query'].upper()
    assert 'GROUP BY' in artifact['canonical_query'].upper()
    assert 'ROW_NUMBER() OVER' in artifact['canonical_query'].upper()
    assert artifact['parameters'] == {
        'start_date': '2026-01-01',
        'end_date': '2026-12-31',
        'min_net_amount': 0.0
    }
    assert artifact['expected_result'] == artifact['canonical_sql_result']
    assert artifact['actual_result'] == artifact['expected_result']
    assert artifact['comparison'] == 'MATCH'
    assert artifact['failure'] is None
    assert set(artifact['fixture']) == {'customers', 'accounts', 'transactions'}
    assert result['evidence']['fixture_insert_count'] == 13


def test_syntax_error_classification():
    result = module.execute({'agent_sql': 'SELECT FROM accounts'})
    assert result['status'] == 'MISMATCH'
    assert result['failure_classification'] == 'SYNTAX_ERROR'
    assert result['actual_rows'] is None
    assert result['artifact']['failure']['classification'] == 'SYNTAX_ERROR'


def test_runtime_error_classification():
    result = module.execute({'agent_sql': 'SELECT definitely_missing_column FROM accounts'})
    assert result['status'] == 'MISMATCH'
    assert result['failure_classification'] == 'RUNTIME_ERROR'
    assert result['actual_rows'] is None
    assert 'column' in result['artifact']['failure']['message'].lower()


def test_wrong_result_classification():
    result = module.execute({'agent_sql': 'SELECT customer_id, segment, NULL AS account_id, 0.0 AS net_amount, 0 AS tx_count, 0 AS segment_rank FROM customers ORDER BY segment, customer_id'})
    assert result['status'] == 'MISMATCH'
    assert result['failure_classification'] == 'WRONG_RESULT'
    assert result['actual_rows'] is not None
    assert result['artifact']['expected_result'] != result['artifact']['actual_result']


def test_read_only_contract_rejects_mutating_agent_sql():
    result = module.execute({'agent_sql': "DELETE FROM transactions WHERE tx_id = 't1'"})
    assert result['status'] == 'MISMATCH'
    assert result['failure_classification'] == 'VALIDATION_ERROR'
    assert result['actual_rows'] is None


if __name__ == '__main__':
    test_reproducible_benchmark_artifact_contract()
    test_syntax_error_classification()
    test_runtime_error_classification()
    test_wrong_result_classification()
    test_read_only_contract_rejects_mutating_agent_sql()
