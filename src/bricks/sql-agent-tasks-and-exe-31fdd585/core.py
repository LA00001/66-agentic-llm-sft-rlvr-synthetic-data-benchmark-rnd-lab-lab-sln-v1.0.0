import sqlite3

_CANONICAL_SQL = '''
WITH account_totals AS (
    SELECT
        c.customer_id,
        c.segment,
        a.account_id,
        SUM(t.amount) AS net_amount,
        COUNT(t.tx_id) AS tx_count
    FROM customers AS c
    JOIN accounts AS a ON a.customer_id = c.customer_id
    JOIN transactions AS t ON t.account_id = a.account_id
    WHERE t.posted_at >= :start_date
      AND t.posted_at <= :end_date
    GROUP BY c.customer_id, c.segment, a.account_id
), ranked AS (
    SELECT
        customer_id,
        segment,
        account_id,
        ROUND(net_amount, 2) AS net_amount,
        tx_count,
        ROW_NUMBER() OVER (
            PARTITION BY segment
            ORDER BY net_amount DESC, account_id ASC
        ) AS segment_rank
    FROM account_totals
)
SELECT customer_id, segment, account_id, net_amount, tx_count, segment_rank
FROM ranked
WHERE net_amount >= :min_net_amount
ORDER BY segment, segment_rank, account_id
'''

_DEFAULT_FIXTURE = {
    'customers': [
        {'customer_id': 'c1', 'segment': 'retail'},
        {'customer_id': 'c2', 'segment': 'retail'},
        {'customer_id': 'c3', 'segment': 'business'}
    ],
    'accounts': [
        {'account_id': 'a1', 'customer_id': 'c1'},
        {'account_id': 'a2', 'customer_id': 'c2'},
        {'account_id': 'a3', 'customer_id': 'c3'}
    ],
    'transactions': [
        {'tx_id': 't1', 'account_id': 'a1', 'posted_at': '2026-01-02', 'amount': 120.0},
        {'tx_id': 't2', 'account_id': 'a1', 'posted_at': '2026-01-03', 'amount': -20.0},
        {'tx_id': 't3', 'account_id': 'a2', 'posted_at': '2026-01-04', 'amount': 75.0},
        {'tx_id': 't4', 'account_id': 'a2', 'posted_at': '2026-01-05', 'amount': 10.0},
        {'tx_id': 't5', 'account_id': 'a3', 'posted_at': '2026-01-06', 'amount': 250.0},
        {'tx_id': 't6', 'account_id': 'a3', 'posted_at': '2026-01-07', 'amount': -50.0},
        {'tx_id': 't7', 'account_id': 'a1', 'posted_at': '2025-12-01', 'amount': 999.0}
    ]
}

_REQUIRED_COLUMNS = {
    'customers': {'customer_id', 'segment'},
    'accounts': {'account_id', 'customer_id'},
    'transactions': {'tx_id', 'account_id', 'posted_at', 'amount'}
}


def _validate_fixture(fixture):
    if not isinstance(fixture, dict):
        raise ValueError('fixture must be an object')
    for table, columns in _REQUIRED_COLUMNS.items():
        rows = fixture.get(table)
        if not isinstance(rows, list) or not rows:
            raise ValueError('fixture.%s must be a non-empty list' % table)
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError('fixture.%s[%d] must be an object' % (table, index))
            missing = columns - set(row)
            if missing:
                raise ValueError('fixture.%s[%d] missing columns: %s' % (table, index, ', '.join(sorted(missing))))


def _parameters(payload):
    params = payload.get('parameters', {})
    if not isinstance(params, dict):
        raise ValueError('parameters must be an object')
    result = {
        'start_date': params.get('start_date', '2026-01-01'),
        'end_date': params.get('end_date', '2026-12-31'),
        'min_net_amount': params.get('min_net_amount', 0.0)
    }
    if not isinstance(result['start_date'], str) or not result['start_date']:
        raise ValueError('parameters.start_date must be a non-empty string')
    if not isinstance(result['end_date'], str) or not result['end_date']:
        raise ValueError('parameters.end_date must be a non-empty string')
    if not isinstance(result['min_net_amount'], (int, float)) or isinstance(result['min_net_amount'], bool):
        raise ValueError('parameters.min_net_amount must be numeric')
    result['min_net_amount'] = float(result['min_net_amount'])
    return result


def _create_database(fixture):
    connection = sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE customers (customer_id TEXT PRIMARY KEY, segment TEXT NOT NULL)')
    connection.execute('CREATE TABLE accounts (account_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, FOREIGN KEY(customer_id) REFERENCES customers(customer_id))')
    connection.execute('CREATE TABLE transactions (tx_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, posted_at TEXT NOT NULL, amount REAL NOT NULL, FOREIGN KEY(account_id) REFERENCES accounts(account_id))')
    connection.executemany(
        'INSERT INTO customers(customer_id, segment) VALUES (:customer_id, :segment)',
        fixture['customers']
    )
    connection.executemany(
        'INSERT INTO accounts(account_id, customer_id) VALUES (:account_id, :customer_id)',
        fixture['accounts']
    )
    connection.executemany(
        'INSERT INTO transactions(tx_id, account_id, posted_at, amount) VALUES (:tx_id, :account_id, :posted_at, :amount)',
        fixture['transactions']
    )
    return connection


def _rows(cursor):
    columns = [description[0] for description in cursor.description]
    return [{columns[i]: row[i] for i in range(len(columns))} for row in cursor.fetchall()]


def _execute_select(connection, sql, parameters):
    if not isinstance(sql, str) or not sql.strip():
        raise ValueError('agent_sql must be a non-empty string')
    stripped = sql.strip()
    if ';' in stripped.rstrip(';'):
        raise ValueError('agent_sql must contain exactly one SQL statement')
    first = stripped.lstrip().split(None, 1)[0].upper()
    if first not in {'SELECT', 'WITH'}:
        raise ValueError('agent_sql must be a read-only SELECT or WITH query')
    cursor = connection.execute(sql, parameters)
    if cursor.description is None:
        raise ValueError('agent_sql must return a result set')
    return _rows(cursor)


def _independent_oracle(fixture, params):
    customer_segment = {row['customer_id']: row['segment'] for row in fixture['customers']}
    account_customer = {row['account_id']: row['customer_id'] for row in fixture['accounts']}
    aggregates = {}
    for tx in fixture['transactions']:
        if params['start_date'] <= tx['posted_at'] <= params['end_date']:
            account_id = tx['account_id']
            if account_id not in account_customer:
                continue
            item = aggregates.setdefault(account_id, {'net_amount': 0.0, 'tx_count': 0})
            item['net_amount'] += float(tx['amount'])
            item['tx_count'] += 1
    candidates = []
    for account_id, values in aggregates.items():
        customer_id = account_customer[account_id]
        segment = customer_segment[customer_id]
        net_amount = round(values['net_amount'], 2)
        if net_amount >= params['min_net_amount']:
            candidates.append({
                'customer_id': customer_id,
                'segment': segment,
                'account_id': account_id,
                'net_amount': net_amount,
                'tx_count': values['tx_count']
            })
    ranks = {}
    for segment in sorted({row['segment'] for row in candidates}):
        segment_rows = [row for row in candidates if row['segment'] == segment]
        segment_rows.sort(key=lambda row: (-row['net_amount'], row['account_id']))
        for index, row in enumerate(segment_rows, 1):
            ranks[(segment, row['account_id'])] = index
    for row in candidates:
        row['segment_rank'] = ranks[(row['segment'], row['account_id'])]
    candidates.sort(key=lambda row: (row['segment'], row['segment_rank'], row['account_id']))
    return candidates


def _classify_sql_error(error):
    message = str(error).lower()
    syntax_tokens = ('syntax error', 'incomplete input', 'unrecognized token', 'near ')
    if any(token in message for token in syntax_tokens):
        return 'SYNTAX_ERROR'
    return 'RUNTIME_ERROR'


def execute(payload):
    if not isinstance(payload, dict):
        raise ValueError('payload must be an object')
    fixture = payload.get('fixture', _DEFAULT_FIXTURE)
    _validate_fixture(fixture)
    params = _parameters(payload)
    agent_sql = payload.get('agent_sql', _CANONICAL_SQL)

    expected_rows = _independent_oracle(fixture, params)
    connection = _create_database(fixture)
    try:
        canonical_rows = _execute_select(connection, _CANONICAL_SQL, params)
        if canonical_rows != expected_rows:
            raise RuntimeError('canonical SQL disagrees with independently computed oracle')

        actual_rows = None
        failure = None
        try:
            actual_rows = _execute_select(connection, agent_sql, params)
        except sqlite3.Error as exc:
            failure = {
                'classification': _classify_sql_error(exc),
                'message': str(exc)
            }
        except ValueError as exc:
            failure = {
                'classification': 'VALIDATION_ERROR',
                'message': str(exc)
            }

        if failure is None and actual_rows != expected_rows:
            failure = {
                'classification': 'WRONG_RESULT',
                'message': 'agent SQL executed successfully but result set differs from canonical oracle'
            }

        status = 'MATCH' if failure is None else 'MISMATCH'
        artifact = {
            'engine': 'sqlite3',
            'scope': 'LOCAL',
            'fixture': {
                'customers': [dict(row) for row in fixture['customers']],
                'accounts': [dict(row) for row in fixture['accounts']],
                'transactions': [dict(row) for row in fixture['transactions']]
            },
            'query': agent_sql,
            'canonical_query': _CANONICAL_SQL,
            'parameters': dict(params),
            'expected_result': expected_rows,
            'canonical_sql_result': canonical_rows,
            'actual_result': actual_rows,
            'comparison': status,
            'failure': failure
        }
        return {
            'status': status,
            'failure_classification': None if failure is None else failure['classification'],
            'expected_rows': expected_rows,
            'actual_rows': actual_rows,
            'artifact': artifact,
            'evidence': {
                'database_engine': 'sqlite3',
                'fixture_tables_created': ['customers', 'accounts', 'transactions'],
                'fixture_insert_count': sum(len(fixture[name]) for name in ('customers', 'accounts', 'transactions')),
                'canonical_query_executed': True,
                'agent_query_executed': actual_rows is not None,
                'oracle_independently_computed': True,
                'result_sets_equal': actual_rows == expected_rows if actual_rows is not None else False
            }
        }
    finally:
        connection.close()
