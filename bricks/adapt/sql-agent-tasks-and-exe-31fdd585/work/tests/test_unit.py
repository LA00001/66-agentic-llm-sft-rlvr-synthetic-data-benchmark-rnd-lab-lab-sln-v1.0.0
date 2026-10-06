import importlib.util
from pathlib import Path

BRICK_ID = 'sql-agent-tasks-and-exe-31fdd585'
CORE = Path('src') / 'bricks' / BRICK_ID / 'core.py'
spec = importlib.util.spec_from_file_location('brick_core', CORE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_default_agent_sql_matches_independent_oracle():
    result = module.execute({})
    assert result['status'] == 'MATCH'
    assert result['failure_classification'] is None
    assert result['evidence']['database_engine'] == 'sqlite3'
    assert result['evidence']['canonical_query_executed'] is True
    assert result['evidence']['agent_query_executed'] is True
    assert result['evidence']['oracle_independently_computed'] is True
    assert result['expected_rows'] == [
        {'customer_id': 'c3', 'segment': 'business', 'account_id': 'a3', 'net_amount': 200.0, 'tx_count': 2, 'segment_rank': 1},
        {'customer_id': 'c1', 'segment': 'retail', 'account_id': 'a1', 'net_amount': 100.0, 'tx_count': 2, 'segment_rank': 1},
        {'customer_id': 'c2', 'segment': 'retail', 'account_id': 'a2', 'net_amount': 85.0, 'tx_count': 2, 'segment_rank': 2}
    ]
    assert result['actual_rows'] == result['expected_rows']


def test_textually_different_agent_sql_can_match_by_result():
    sql = '''
    SELECT c.customer_id, c.segment, a.account_id,
           ROUND(SUM(t.amount), 2) AS net_amount,
           COUNT(t.tx_id) AS tx_count,
           ROW_NUMBER() OVER (
               PARTITION BY c.segment
               ORDER BY SUM(t.amount) DESC, a.account_id
           ) AS segment_rank
    FROM transactions t
    INNER JOIN accounts a ON t.account_id = a.account_id
    INNER JOIN customers c ON a.customer_id = c.customer_id
    WHERE t.posted_at BETWEEN :start_date AND :end_date
    GROUP BY c.customer_id, c.segment, a.account_id
    HAVING SUM(t.amount) >= :min_net_amount
    ORDER BY c.segment, segment_rank, a.account_id
    '''
    result = module.execute({'agent_sql': sql})
    assert sql.strip() != result['artifact']['canonical_query'].strip()
    assert result['status'] == 'MATCH'
    assert result['actual_rows'] == result['expected_rows']


def test_wrong_result_is_distinct_from_sql_execution_failure():
    sql = '''
    SELECT c.customer_id, c.segment, a.account_id,
           ROUND(SUM(t.amount), 2) AS net_amount,
           COUNT(t.tx_id) AS tx_count,
           1 AS segment_rank
    FROM customers c
    JOIN accounts a ON a.customer_id = c.customer_id
    JOIN transactions t ON t.account_id = a.account_id
    WHERE t.posted_at BETWEEN :start_date AND :end_date
    GROUP BY c.customer_id, c.segment, a.account_id
    HAVING SUM(t.amount) >= :min_net_amount
    ORDER BY c.segment, a.account_id
    '''
    result = module.execute({'agent_sql': sql})
    assert result['status'] == 'MISMATCH'
    assert result['failure_classification'] == 'WRONG_RESULT'
    assert result['actual_rows'] is not None
    assert result['actual_rows'] != result['expected_rows']


def test_parameter_changes_oracle_and_execution():
    result = module.execute({'parameters': {'start_date': '2026-01-01', 'end_date': '2026-12-31', 'min_net_amount': 90}})
    assert result['status'] == 'MATCH'
    assert [row['account_id'] for row in result['expected_rows']] == ['a3', 'a1']
    assert result['artifact']['parameters']['min_net_amount'] == 90.0


def test_input_validation_rejects_malformed_fixture():
    try:
        module.execute({'fixture': {'customers': [], 'accounts': [], 'transactions': []}})
    except ValueError as exc:
        assert 'non-empty list' in str(exc)
    else:
        raise AssertionError('expected ValueError')


if __name__ == '__main__':
    test_default_agent_sql_matches_independent_oracle()
    test_textually_different_agent_sql_can_match_by_result()
    test_wrong_result_is_distinct_from_sql_execution_failure()
    test_parameter_changes_oracle_and_execution()
    test_input_validation_rejects_malformed_fixture()
