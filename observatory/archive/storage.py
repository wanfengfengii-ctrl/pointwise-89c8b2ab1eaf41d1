from contextlib import contextmanager
import sqlite3


class ArchiveDatabase:
    STORAGE_VERSION = 1

    def __init__(self, connection):
        self.connection = connection

    @classmethod
    def open(cls, path):
        connection = sqlite3.connect(path, isolation_level=None)
        try:
            connection.execute('PRAGMA foreign_keys = ON')
            version = connection.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, cls.STORAGE_VERSION):
                raise ValueError('unsupported storage version')
            if version == 0:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                if tables:
                    raise ValueError('unversioned nonempty database')
                connection.execute('PRAGMA user_version = 1')
            return cls(connection)
        except BaseException:
            connection.close()
            raise

    @contextmanager
    def transaction(self):
        if self.connection.in_transaction:
            raise RuntimeError('nested transaction is not supported')
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            yield self.connection
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
