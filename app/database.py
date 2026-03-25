import sqlite3
import os
import uuid
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'cases.db')


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS cases (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            patient_id TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            nifti_filename TEXT DEFAULT '',
            glb_filename TEXT DEFAULT '',
            ct_filename TEXT DEFAULT '',
            video_filename TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_cases_user_id ON cases(user_id);
        CREATE INDEX IF NOT EXISTS idx_cases_created_at ON cases(created_at);
    ''')
    # Add ct_filename column if upgrading from old schema
    try:
        conn.execute('ALTER TABLE cases ADD COLUMN ct_filename TEXT DEFAULT ""')
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.close()


def create_case(user_id, title, patient_id='', notes=''):
    conn = get_db()
    case_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()
    conn.execute(
        'INSERT INTO cases (id, user_id, title, patient_id, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (case_id, user_id, title, patient_id, notes, now, now)
    )
    conn.commit()
    conn.close()
    return case_id


def get_cases_for_user(user_id):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM cases WHERE user_id = ? ORDER BY created_at DESC', (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_case(case_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM cases WHERE id = ?', (case_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_case(case_id, **kwargs):
    conn = get_db()
    kwargs['updated_at'] = datetime.utcnow().isoformat()
    set_clause = ', '.join(f'{k} = ?' for k in kwargs)
    values = list(kwargs.values()) + [case_id]
    conn.execute(f'UPDATE cases SET {set_clause} WHERE id = ?', values)
    conn.commit()
    conn.close()


def delete_case(case_id):
    conn = get_db()
    conn.execute('DELETE FROM cases WHERE id = ?', (case_id,))
    conn.commit()
    conn.close()
