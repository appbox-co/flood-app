#!/usr/bin/env python3
"""Create the default Flood user when the database has none; never replace persisted users.

Installs that once ran Flood with authentication disabled can leave a users.db
that holds only NeDB index lines. Flood then shows its first-run "Create an
account" page instead of a login, so a database without users is treated like
a missing one. A database that still has any user is left exactly as it is.
"""
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

DATABASE = Path('/home/flood/.local/db/users.db')
INDEX = {'$$indexCreated': {'fieldName': 'username', 'unique': True, 'sparse': False}}
FLOOD_UID = FLOOD_GID = 1000


def hash_password(password):
    return subprocess.run(['argon2', secrets.token_hex(16), '-id', '-t', '256', '-m', '9', '-p', '1', '-e'],
                          input=password.encode(), capture_output=True, check=True).stdout.decode().strip()


def live_users(text):
    """Return the users an NeDB datafile still holds after its updates and deletes."""
    records = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError('Unexpected record')
        if record.get('$$deleted') is True:
            records.pop(record.get('_id'), None)
        elif '_id' in record:
            # Index lines carry no _id; a later line with the same _id is an update.
            records[record['_id']] = record
    return [record for record in records.values() if record.get('username')]


def user_record(username, password):
    return {'username': username, 'password': hash_password(password),
            'client': {'client': 'rTorrent', 'type': 'socket', 'version': 1,
                       'socket': '/torrents/config/rtorrent/rtorrent.sock'},
            'level': 10, 'timestamp': int(time.time()), '_id': secrets.token_hex(8)}


def write_database(database, username, password, uid, gid):
    database.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(INDEX) + '\n' + json.dumps(user_record(username, password)) + '\n'
    temporary = database.with_name(database.name + '.seed-' + secrets.token_hex(4))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chown(temporary, uid, gid)
        os.replace(temporary, database)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    directory = os.open(database.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    os.chown(database.parent, uid, gid)


def ensure_user(database, username, password, uid=FLOOD_UID, gid=FLOOD_GID):
    """Return 'created', 'seeded', 'kept' or 'unreadable'."""
    if not database.exists():
        write_database(database, username, password, uid, gid)
        return 'created'
    try:
        users = live_users(database.read_text(encoding='utf-8'))
    except (ValueError, UnicodeDecodeError) as error:
        # Leave a damaged database for Flood and support to judge; do not stop the app.
        print('Flood user database is unreadable; leaving it unchanged (' + type(error).__name__ + ')',
              file=sys.stderr, flush=True)
        return 'unreadable'
    if users:
        return 'kept'
    backup = database.with_name(database.name + '.pre-seed')
    if not backup.exists():
        shutil.copy2(database, backup)
        os.chown(backup, uid, gid)
    write_database(database, username, password, uid, gid)
    print('Flood user database had no users; created the default user', flush=True)
    return 'seeded'


if __name__ == '__main__':
    ensure_user(DATABASE, os.environ['USERNAME'], os.environ['PASSWORD'])
