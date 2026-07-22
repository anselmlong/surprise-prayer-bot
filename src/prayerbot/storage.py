"""SQLite storage for users, pairings, and messages."""
from __future__ import annotations

import random
import sqlite3
import threading
import time
from dataclasses import dataclass


@dataclass
class User:
    user_id: int
    username: str
    display_name: str
    in_pool: bool


@dataclass
class Pairing:
    prayer_id: int
    prayee_id: int
    prayer_name: str
    prayee_name: str


class Storage:
    def __init__(self, db_path: str) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id      INTEGER PRIMARY KEY,
                username     TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                in_pool      INTEGER NOT NULL DEFAULT 1,
                joined_at    REAL NOT NULL DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS pairings (
                prayer_id    INTEGER NOT NULL,
                prayee_id    INTEGER NOT NULL,
                assigned_at  REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (prayer_id)
            )
        """)
        self._conn.commit()

    def join_pool(self, user_id: int, username: str, display_name: str) -> bool:
        """Add user to pool. Returns True if newly joined."""
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                "SELECT in_pool FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if cur:
                if cur[0]:
                    return False  # already in pool
                self._conn.execute(
                    "UPDATE users SET in_pool = 1, username = ?, display_name = ? WHERE user_id = ?",
                    (username, display_name, user_id),
                )
            else:
                self._conn.execute(
                    "INSERT INTO users (user_id, username, display_name, in_pool, joined_at) VALUES (?, ?, ?, 1, ?)",
                    (user_id, username, display_name, now),
                )
            self._conn.commit()
        return True

    def leave_pool(self, user_id: int) -> bool:
        """Remove user from pool. Returns True if was in pool."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT in_pool FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not cur or not cur[0]:
                return False
            self._conn.execute(
                "UPDATE users SET in_pool = 0 WHERE user_id = ?", (user_id,)
            )
            # Also clear any pairing they had
            self._conn.execute(
                "DELETE FROM pairings WHERE prayer_id = ?", (user_id,)
            )
            self._conn.commit()
        return True

    def get_pool_size(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM users WHERE in_pool = 1"
            ).fetchone()
        return row[0] if row else 0

    def is_in_pool(self, user_id: int) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT in_pool FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        return row is not None and bool(row[0])

    def assign_prayee(self, prayer_id: int) -> int | None:
        """Assign a random person from the pool (not self, not already assigned)."""
        with self._lock:
            rows = self._conn.execute("""
                SELECT u.user_id FROM users u
                WHERE u.in_pool = 1
                  AND u.user_id != ?
                  AND u.user_id NOT IN (
                      SELECT prayee_id FROM pairings WHERE prayer_id = ?
                  )
            """, (prayer_id, prayer_id)).fetchall()

            candidates = [r[0] for r in rows]
            if not candidates:
                return None

            chosen = random.choice(candidates)
            now = time.time()
            self._conn.execute(
                "INSERT OR REPLACE INTO pairings (prayer_id, prayee_id, assigned_at) VALUES (?, ?, ?)",
                (prayer_id, chosen, now),
            )
            self._conn.commit()
        return chosen

    def get_pairing(self, user_id: int) -> Pairing | None:
        """Return the pairing for a prayer, or None."""
        with self._lock:
            row = self._conn.execute("""
                SELECT p.prayer_id, p.prayee_id,
                       COALESCE(u1.display_name, '') AS prayer_name,
                       COALESCE(u2.display_name, '') AS prayee_name
                FROM pairings p
                JOIN users u1 ON u1.user_id = p.prayer_id
                JOIN users u2 ON u2.user_id = p.prayee_id
                WHERE p.prayer_id = ?
            """, (user_id,)).fetchone()
        if row:
            return Pairing(row[0], row[1], row[2], row[3])
        return None

    def get_user(self, user_id: int) -> User | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT user_id, username, display_name, in_pool FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row:
            return User(row[0], row[1], row[2], bool(row[3]))
        return None

    def get_all_pool_members(self) -> list[User]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT user_id, username, display_name, in_pool FROM users WHERE in_pool = 1"
            ).fetchall()
        return [User(r[0], r[1], r[2], bool(r[3])) for r in rows]

    def reshuffle(self) -> None:
        """Clear all pairings so everyone gets a new person."""
        with self._lock:
            self._conn.execute("DELETE FROM pairings")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()