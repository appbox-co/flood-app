#!/usr/bin/env python3
"""Unit tests for scripts/bootstrap.py (python3 only; no Docker or argon2 needed).

Cases: a missing database is created; a database with only index lines, or
only deleted users, gets the default user and keeps a backup; a database with
any user is never changed; an unreadable one is left alone; a second start
after seeding changes nothing; special characters reach the hash unchanged.
"""
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile

spec = importlib.util.spec_from_file_location(
    'bootstrap', Path(__file__).resolve().parents[1] / 'scripts' / 'bootstrap.py')
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)

hashed = []


def fake_hash(password):
    hashed.append(password)
    return '$argon2id$fake$' + str(len(hashed))


bootstrap.hash_password = fake_hash
INDEX_LINE = json.dumps(bootstrap.INDEX) + '\n'
USERNAME = 'gate"user\\\'$x'
PASSWORD = 'p"a\\s\'s$HOME`x` w'
uid, gid = os.getuid(), os.getgid()


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run(initial):
    folder = Path(tempfile.mkdtemp(prefix='flood-bootstrap-test-'))
    database = folder / 'db' / 'users.db'
    if initial is not None:
        database.parent.mkdir()
        database.write_text(initial)
    result = bootstrap.ensure_user(database, USERNAME, PASSWORD, uid, gid)
    return result, database


def assert_seeded(database):
    rows = records(database)
    assert rows[0] == bootstrap.INDEX, rows
    users = bootstrap.live_users(database.read_text())
    assert len(users) == 1 and users[0]['username'] == USERNAME, users
    assert users[0]['level'] == 10 and users[0]['client']['type'] == 'socket'
    assert hashed[-1] == PASSWORD
    assert stat.S_IMODE(database.stat().st_mode) == 0o600
    assert not list(database.parent.glob('users.db.seed-*'))
    return users[0]['_id']


result, database = run(None)
assert result == 'created', result
assert_seeded(database)
assert not (database.parent / 'users.db.pre-seed').exists()
print('PASS missing database: default user created')

result, database = run(INDEX_LINE)
assert result == 'seeded', result
user_id = assert_seeded(database)
assert (database.parent / 'users.db.pre-seed').read_text() == INDEX_LINE
print('PASS index-only database: default user created, original kept as users.db.pre-seed')

before = database.read_bytes()
calls = len(hashed)
assert bootstrap.ensure_user(database, USERNAME, PASSWORD, uid, gid) == 'kept'
assert database.read_bytes() == before and len(hashed) == calls
assert bootstrap.live_users(database.read_text())[0]['_id'] == user_id
print('PASS second start: seeded user kept unchanged')

deleted = INDEX_LINE + json.dumps({'username': 'old', 'password': 'x', '_id': 'a1'}) + '\n' \
    + json.dumps({'$$deleted': True, '_id': 'a1'}) + '\n'
result, database = run(deleted)
assert result == 'seeded', result
assert_seeded(database)
print('PASS deleted-users database: default user created')

result, database = run('')
assert result == 'seeded', result
assert_seeded(database)
print('PASS empty database file: default user created')

existing = INDEX_LINE + json.dumps({'username': 'someone-else', 'password': 'x', '_id': 'b2'}) + '\n'
result, database = run(existing)
assert result == 'kept', result
assert database.read_text() == existing
assert not (database.parent / 'users.db.pre-seed').exists()
print('PASS existing user: database unchanged, even under another username')

updated = existing + json.dumps({'username': 'someone-else', 'password': 'y', '_id': 'b2'}) + '\n'
result, database = run(updated)
assert result == 'kept' and database.read_text() == updated
print('PASS updated user: database unchanged')

damaged = INDEX_LINE + '{not json\n'
result, database = run(damaged)
assert result == 'unreadable', result
assert database.read_text() == damaged
print('PASS unreadable database: left unchanged')
print('PASS bootstrap unit tests')
