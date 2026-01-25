"""
core/memory.py
Handles ALL database operations
Separated from tracking logic for modularity
"""
import sqlite3
import threading
import os
import sys


def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()
DB_PATH = os.path.join(BASE_DIR, "pet_memory.db")


class Memory:
    """
    Database operations only
    - Load/save sessions
    - Load/save app categories
    - Thread-safe operations
    """

    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()

            # App categories cache
            c.execute('''
                      CREATE TABLE IF NOT EXISTS app_categories
                      (
                          app_name
                          TEXT
                          PRIMARY
                          KEY,
                          category
                          TEXT
                          NOT
                          NULL
                      )
                      ''')

            # Session history
            c.execute('''
                      CREATE TABLE IF NOT EXISTS sessions
                      (
                          id
                          INTEGER
                          PRIMARY
                          KEY
                          AUTOINCREMENT,
                          app
                          TEXT
                          NOT
                          NULL,
                          category
                          TEXT
                          NOT
                          NULL,
                          start_time
                          TEXT
                          NOT
                          NULL,
                          end_time
                          TEXT
                          NOT
                          NULL,
                          duration_seconds
                          REAL
                          NOT
                          NULL
                      )
                      ''')

            conn.commit()

    # ========================================================================
    # APP CATEGORIES
    # ========================================================================

    def get_all_categories(self) -> dict:
        """Load all app->category mappings"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT app_name, category FROM app_categories")
            return {app: cat for app, cat in c.fetchall()}

    def save_category(self, app_name: str, category: str):
        """Save a single app category"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute('''
                    INSERT OR REPLACE INTO app_categories (app_name, category)
                    VALUES (?, ?)
                ''', (app_name, category))
                conn.commit()

    def get_category(self, app_name: str) -> str:
        """Get category for an app (returns 'unknown' if not found)"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT category FROM app_categories WHERE app_name = ?", (app_name,))
            result = c.fetchone()
            return result[0] if result else 'unknown'

    # ========================================================================
    # SESSION HISTORY
    # ========================================================================

    def get_all_sessions(self) -> list:
        """Load all session records"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                      SELECT app, category, start_time, end_time, duration_seconds
                      FROM sessions
                      ORDER BY id
                      ''')

            return [
                {
                    'app': app,
                    'category': cat,
                    'startTime': start,
                    'endTime': end,
                    'durationSeconds': dur
                }
                for app, cat, start, end, dur in c.fetchall()
            ]

    def save_session(self, session: dict):
        """
        Save a single session
        session = {
            'app': str,
            'category': str,
            'startTime': str (ISO format),
            'endTime': str (ISO format),
            'durationSeconds': float
        }
        """
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute('''
                          INSERT INTO sessions (app, category, start_time, end_time, duration_seconds)
                          VALUES (?, ?, ?, ?, ?)
                          ''', (
                              session['app'],
                              session['category'],
                              session['startTime'],
                              session['endTime'],
                              session['durationSeconds']
                          ))
                conn.commit()

    def save_sessions_bulk(self, sessions: list):
        """Save multiple sessions at once (faster)"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.executemany('''
                              INSERT INTO sessions (app, category, start_time, end_time, duration_seconds)
                              VALUES (?, ?, ?, ?, ?)
                              ''', [
                                  (s['app'], s['category'], s['startTime'], s['endTime'], s['durationSeconds'])
                                  for s in sessions
                              ])
                conn.commit()

    def get_recent_sessions(self, limit=50) -> list:
        """Get last N sessions"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                      SELECT app, category, start_time, end_time, duration_seconds
                      FROM sessions
                      ORDER BY id DESC LIMIT ?
                      ''', (limit,))

            return [
                       {
                           'app': app,
                           'category': cat,
                           'startTime': start,
                           'endTime': end,
                           'durationSeconds': dur
                       }
                       for app, cat, start, end, dur in c.fetchall()
                   ][::-1]  # Reverse to chronological order

    # ========================================================================
    # STATS / QUERIES
    # ========================================================================

    def get_session_count(self) -> int:
        """Total number of sessions"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM sessions")
            return c.fetchone()[0]

    def get_stats_by_category(self) -> dict:
        """Get usage stats grouped by category"""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                      SELECT category,
                             COUNT(*) as count,
                       SUM(duration_seconds) as total_time,
                       AVG(duration_seconds) as avg_time
                      FROM sessions
                      GROUP BY category
                      ''')

            return {
                cat: {
                    'count': count,
                    'total_seconds': total,
                    'avg_seconds': avg
                }
                for cat, count, total, avg in c.fetchall()
            }