"""Keep automatic IDs ahead of the explicit IDs used by the demo catalogue."""
from django.db import DEFAULT_DB_ALIAS, DatabaseError, connections, transaction

from .models import Product, Restaurant


SEEDED_ID_MODELS = (Product, Restaurant)


def lock_seeded_tables(using=DEFAULT_DB_ALIAS):
    """Serialize seeding/repair with ordinary inserts; the caller owns the transaction."""
    connection = connections[using]
    if connection.vendor != 'postgresql':
        return
    if not connection.in_atomic_block:
        raise transaction.TransactionManagementError('Le verrou des séquences exige une transaction.')
    tables = ', '.join(connection.ops.quote_name(model._meta.db_table) for model in SEEDED_ID_MODELS)
    with connection.cursor() as cursor:
        cursor.execute(f'LOCK TABLE {tables} IN SHARE ROW EXCLUSIVE MODE')


def repair_crm_sequences(using=DEFAULT_DB_ALIAS):
    """Advance PostgreSQL counters only, preserving data and already allocated IDs.

    SQLite tracks explicit AUTOINCREMENT IDs itself. PostgreSQL's setval is not
    rolled back: only advancing it makes a failed transaction harmless (a gap).
    Table locks protect normal INSERTs, which acquire ROW EXCLUSIVE before nextval.
    """
    connection = connections[using]
    if connection.vendor != 'postgresql':
        return 0
    changed = 0
    with transaction.atomic(using=using):
        lock_seeded_tables(using)
        with connection.cursor() as cursor:
            for model in SEEDED_ID_MODELS:
                table = model._meta.db_table
                column = model._meta.pk.column
                cursor.execute(
                    'SELECT n.nspname, c.relname FROM pg_class c '
                    'JOIN pg_namespace n ON n.oid = c.relnamespace '
                    'WHERE c.oid = pg_get_serial_sequence(%s, %s)::regclass',
                    [table, column],
                )
                sequence = cursor.fetchone()
                if sequence is None:
                    raise DatabaseError(f'Séquence automatique introuvable pour {table}.')
                sequence_name = '.'.join(connection.ops.quote_name(part) for part in sequence)
                cursor.execute(f'SELECT last_value, is_called FROM {sequence_name}')
                last_value, is_called = cursor.fetchone()
                cursor.execute(
                    f'SELECT MAX({connection.ops.quote_name(column)}) '
                    f'FROM {connection.ops.quote_name(table)}'
                )
                maximum = cursor.fetchone()[0]
                # max == last_value still needs is_called=true when that ID exists.
                # A higher reserved value or an empty table must remain untouched.
                if maximum is not None and (maximum > last_value or (maximum == last_value and not is_called)):
                    cursor.execute('SELECT setval(%s::regclass, %s, true)', [sequence_name, maximum])
                    changed += 1
    return changed
