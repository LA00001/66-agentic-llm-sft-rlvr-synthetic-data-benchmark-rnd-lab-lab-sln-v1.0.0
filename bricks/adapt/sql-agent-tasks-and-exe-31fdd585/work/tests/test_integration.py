import importlib.util
from pathlib import Path

BRICK_ID = 'sql-agent-tasks-and-exe-31fdd585'
CORE = Path('src') / 'bricks' / BRICK_ID / 'core.py'
spec = importlib.util.spec_from_file_location('brick_core_integration', CORE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_agent_benchmark_end_to_end_with_custom_fixture():
    fixture = {
        'customers': [
            {'customer_id': 'u1', 'segment': 'alpha'},
            {'customer_id': 'u2', 'segment': 'alpha'},
            {'customer_id': 'u3', 'segment': 'beta'}
        ],
        'accounts': [
            {'account_id': 'x1', 'customer_id': 'u1'},
            {'account_id': 'x2', 'customer_id': 'u2'},
            {'account_id': 'x3', 'customer_id': 'u3'}
        ],
        'transactions': [
            {'tx_id': 'q1', 'account_id': 'x1', 'posted_at': '2026-03-01', 'amount': 40.0},
            {'tx_id': 'q2', 'account_id': 'x1', 'posted_at': '2026-03-02', 'amount': 30.0},
            {'tx_id': 'q3', 'account_id': 'x2', 'posted_at': '2026-03-01', 'amount': 100.0},
            {'tx_id': 'q4', 'account_id': 'x2', 'posted_at': '2026-03-03', 'amount': -10.0},
            {'tx_id': 'q5', 'account_id': 'x3', 'posted_at': '2026-03-04', 'amount': 55.0},
            {'tx_id': 'q6', 'account_id': 'x3', 'posted_at': '2026-03-05', 'amount': -5.0},
            {'tx_id': 'q7', 'account_id': 'x3', 'posted_at': '2026-04-01', 'amount': 500.0}
        ]
    }
    agent_sql = '''
    WITH sums AS (
        SELECT a.account_id, a.customer_id, c.segment,
               SUM(t.amount) AS total, COUNT(*) AS n
        FROM accounts a
        JOIN customers c ON c.customer_id = a.customer_id
        JOIN transactions t ON t.account_id = a.account_id
        WHERE t.posted_at >= :start_date AND t.posted_at <= :end_date
        GROUP BY a.account_id, a.customer_id, c.segment
    )
    SELECT customer_id, segment, account_id,
           ROUND(total, 2) AS net_amount,
           n AS tx_count,
           ROW_NUMBER() OVER (PARTITION BY segment ORDER BY total DESC, account_id) AS segment_rank
    FROM sums
    WHERE total >= :min_net_amount
    ORDER BY segment, segment_rank, account_id
    '''
    payload = {
        'fixture': fixture,
        'parameters': {
            'start_date': '2026-03-01',
            'end_date': '2026-03-31',
            'min_net_amount': 50
        },
        'agent_sql': agent_sql
    }
    result = module.execute(payload)
    assert result['status'] == 'MATCH'
    assert result['expected_rows'] == [
        {'customer_id': 'u2', 'segment': 'alpha', 'account_id': 'x2', 'net_amount': 90.0, 'tx_count': 2, 'segment_rank': 1},
        {'customer_id': 'u1', 'segment': 'alpha', 'account_id': 'x1', 'net_amount': 70.0, 'tx_count': 2, 'segment_rank': 2},
        {'customer_id': 'u3', 'segment': 'beta', 'account_id': 'x3', 'net_amount': 50.0, 'tx_count': 2, 'segment_rank': 1}
    ]
    assert result['actual_rows'] == result['expected_rows']
    assert result['artifact']['query'] == agent_sql
    assert result['artifact']['parameters']['end_date'] == '2026-03-31'
    assert result['artifact']['expected_result'] == result['artifact']['actual_result']
    assert result['evidence']['fixture_tables_created'] == ['customers', 'accounts', 'transactions']
    assert result['evidence']['fixture_insert_count'] == 13


def test_end_to_end_failure_modes_remain_distinct_on_same_fixture_engine():
    syntax = module.execute({'agent_sql': 'SELECT account_id, FROM accounts'})
    runtime = module.execute({'agent_sql': 'SELECT missing_value FROM accounts'})
    wrong = module.execute({'agent_sql': 'SELECT customer_id, segment, account_id, 0 AS net_amount, 0 AS tx_count, 0 AS segment_rank FROM accounts JOIN customers USING(customer_id) ORDER BY segment, account_id'})
    assert syntax['failure_classification'] == 'SYNTAX_ERROR'
    assert runtime['failure_classification'] == 'RUNTIME_ERROR'
    assert wrong['failure_classification'] == 'WRONG_RESULT'
    assert syntax['actual_rows'] is None
    assert runtime['actual_rows'] is None
    assert wrong['actual_rows'] is not None


if __name__ == '__main__':
    test_agent_benchmark_end_to_end_with_custom_fixture()
    test_end_to_end_failure_modes_remain_distinct_on_same_fixture_engine()
