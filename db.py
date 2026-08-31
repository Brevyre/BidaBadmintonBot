# -*- coding: utf-8 -*-
"""SQLite storage for BBBot.

Everything lives in bbbot.db next to this file. Times are stored as UTC epoch
seconds (integers) so sorting and comparison are always correct regardless of
timezone or daylight saving.

Seat model
----------
A signup row is one person plus their guests. Two guest counters:
  confirmed_guests - guests holding a real seat
  waiting_guests   - guests queued for a seat
status is 'in'   -> the person themselves holds a seat
          'wait' -> the person is queued (confirmed_guests is 0)

Seats taken = sum over status='in' of (1 + confirmed_guests).
"""

import sqlite3
import time
from pathlib import Path

import config

# Relative paths sit next to this file; absolute paths (e.g. Railway's
# /data/bbbot.db volume mount) are used as given.
_p = Path(config.DB_PATH)
DB_PATH = _p if _p.is_absolute() else Path(__file__).with_name(str(_p))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_id      INTEGER PRIMARY KEY,
    username   TEXT,
    first_name TEXT,
    dm_ok      INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id            TEXT PRIMARY KEY,
    host_id       INTEGER NOT NULL,
    starts_at     INTEGER NOT NULL,
    duration_min  INTEGER NOT NULL,
    venue         TEXT NOT NULL,
    capacity      INTEGER NOT NULL,
    status        TEXT NOT NULL DEFAULT 'live',
    cancel_reason TEXT,
    created_at    INTEGER NOT NULL,
    announce_chat INTEGER,
    announce_msg  INTEGER
);

CREATE TABLE IF NOT EXISTS signups (
    event_id        TEXT NOT NULL,
    user_id         INTEGER NOT NULL,
    confirmed_guests INTEGER NOT NULL DEFAULT 0,
    waiting_guests   INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'in',
    joined_at       INTEGER NOT NULL,
    PRIMARY KEY (event_id, user_id)
);

CREATE TABLE IF NOT EXISTS manual_players (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id  TEXT NOT NULL,
    name      TEXT NOT NULL,
    added_by  INTEGER NOT NULL,
    added_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS declines (
    event_id      TEXT NOT NULL,
    user_id       INTEGER NOT NULL,
    declined_at   INTEGER NOT NULL,
    had_signed_up INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (event_id, user_id)
);

CREATE TABLE IF NOT EXISTS subhosts (
    event_id TEXT NOT NULL,
    user_id  INTEGER NOT NULL,
    PRIMARY KEY (event_id, user_id)
);

CREATE TABLE IF NOT EXISTS venues (
    name      TEXT PRIMARY KEY,
    last_used INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_start ON events(starts_at);
CREATE INDEX IF NOT EXISTS idx_signups_user ON signups(user_id);
"""


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    with connect() as con:
        con.executescript(SCHEMA)
        if get_meta("event_counter") is None:
            set_meta("event_counter", "0")
        if get_meta("stats_epoch") is None:
            set_meta("stats_epoch", "0")


# --------------------------------------------------------------------- meta --

def get_meta(key, default=None):
    with connect() as con:
        row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(key, value):
    with connect() as con:
        con.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )


# -------------------------------------------------------------------- users --

def upsert_user(tg_id, username, first_name, dm_ok=None):
    now = int(time.time())
    with connect() as con:
        existing = con.execute(
            "SELECT dm_ok FROM users WHERE tg_id = ?", (tg_id,)
        ).fetchone()
        keep_dm = existing["dm_ok"] if existing else 0
        con.execute(
            "INSERT INTO users(tg_id, username, first_name, dm_ok, created_at) "
            "VALUES(?, ?, ?, ?, ?) "
            "ON CONFLICT(tg_id) DO UPDATE SET "
            "  username = excluded.username, "
            "  first_name = excluded.first_name, "
            "  dm_ok = excluded.dm_ok",
            (
                tg_id,
                (username or "").lstrip("@").lower() or None,
                first_name,
                keep_dm if dm_ok is None else int(dm_ok),
                now,
            ),
        )
    return existing is not None


def get_user(tg_id):
    with connect() as con:
        return con.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()


def find_user_by_handle(handle):
    h = (handle or "").lstrip("@").lower()
    if not h:
        return None
    with connect() as con:
        return con.execute(
            "SELECT * FROM users WHERE username = ?", (h,)
        ).fetchone()


def user_label(row_or_id):
    """Human-friendly name for a user row or id."""
    row = row_or_id if not isinstance(row_or_id, int) else get_user(row_or_id)
    if row is None:
        return "someone"
    if row["username"]:
        return "@" + row["username"]
    return row["first_name"] or "someone"


# ------------------------------------------------------------------- events --

def next_event_id():
    n = int(get_meta("event_counter", "0")) + 1
    set_meta("event_counter", n)
    return "E%03d" % n


def create_event(eid, host_id, starts_at, duration_min, venue, capacity):
    now = int(time.time())
    with connect() as con:
        con.execute(
            "INSERT INTO events(id, host_id, starts_at, duration_min, venue, "
            "capacity, status, created_at) VALUES(?, ?, ?, ?, ?, ?, 'live', ?)",
            (eid, host_id, starts_at, duration_min, venue, capacity, now),
        )
        con.execute(
            "INSERT INTO venues(name, last_used) VALUES(?, ?) "
            "ON CONFLICT(name) DO UPDATE SET last_used = excluded.last_used",
            (venue, now),
        )


def get_event(eid):
    with connect() as con:
        return con.execute(
            "SELECT * FROM events WHERE id = ?", ((eid or "").upper(),)
        ).fetchone()


def set_announce_message(eid, chat_id, msg_id):
    with connect() as con:
        con.execute(
            "UPDATE events SET announce_chat = ?, announce_msg = ? WHERE id = ?",
            (chat_id, msg_id, eid),
        )


def update_event(eid, **fields):
    allowed = {"starts_at", "venue", "capacity", "duration_min"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k} = ?")
            vals.append(v)
    if not sets:
        return
    vals.append(eid)
    with connect() as con:
        con.execute(f"UPDATE events SET {', '.join(sets)} WHERE id = ?", vals)
        if "venue" in fields:
            con.execute(
                "INSERT INTO venues(name, last_used) VALUES(?, ?) "
                "ON CONFLICT(name) DO UPDATE SET last_used = excluded.last_used",
                (fields["venue"], int(time.time())),
            )


def cancel_event(eid, reason):
    with connect() as con:
        con.execute(
            "UPDATE events SET status = 'cancelled', cancel_reason = ? WHERE id = ?",
            (reason, eid),
        )


def remove_event(eid):
    with connect() as con:
        con.execute("DELETE FROM signups WHERE event_id = ?", (eid,))
        con.execute("DELETE FROM declines WHERE event_id = ?", (eid,))
        con.execute("DELETE FROM manual_players WHERE event_id = ?", (eid,))
        con.execute("DELETE FROM subhosts WHERE event_id = ?", (eid,))
        con.execute("DELETE FROM events WHERE id = ?", (eid,))


def upcoming_events():
    now = int(time.time())
    with connect() as con:
        return con.execute(
            "SELECT * FROM events WHERE status = 'live' AND starts_at >= ? "
            "ORDER BY starts_at",
            (now,),
        ).fetchall()


def count_all():
    with connect() as con:
        e = con.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
        s = con.execute("SELECT COUNT(*) c FROM signups").fetchone()["c"]
    return e, s


def wipe_all_events():
    with connect() as con:
        con.execute("DELETE FROM signups")
        con.execute("DELETE FROM declines")
        con.execute("DELETE FROM manual_players")
        con.execute("DELETE FROM subhosts")
        con.execute("DELETE FROM events")


def recent_venues(limit=3):
    with connect() as con:
        rows = con.execute(
            "SELECT name FROM venues ORDER BY last_used DESC LIMIT ?", (limit,)
        ).fetchall()
    return [r["name"] for r in rows]


# ------------------------------------------------------------------ signups --

def seats_taken(eid):
    """Telegram players and their guests, plus manually added names."""
    with connect() as con:
        row = con.execute(
            "SELECT COALESCE(SUM(1 + confirmed_guests), 0) t "
            "FROM signups WHERE event_id = ? AND status = 'in'",
            (eid,),
        ).fetchone()
        manual = con.execute(
            "SELECT COUNT(*) c FROM manual_players WHERE event_id = ?", (eid,)
        ).fetchone()["c"]
    return row["t"] + manual


def manual_players(eid):
    with connect() as con:
        return con.execute(
            "SELECT * FROM manual_players WHERE event_id = ? ORDER BY added_at, id",
            (eid,),
        ).fetchall()


def add_manual_player(eid, name, added_by):
    with connect() as con:
        cur = con.execute(
            "INSERT INTO manual_players(event_id, name, added_by, added_at) "
            "VALUES(?, ?, ?, ?)",
            (eid, name, added_by, int(time.time())),
        )
        return cur.lastrowid


def find_manual_player(eid, name):
    with connect() as con:
        return con.execute(
            "SELECT * FROM manual_players WHERE event_id = ? "
            "AND LOWER(name) = LOWER(?)",
            (eid, name),
        ).fetchone()


def remove_manual_player(row_id):
    with connect() as con:
        con.execute("DELETE FROM manual_players WHERE id = ?", (row_id,))


def seats_free(event_row):
    return max(0, event_row["capacity"] - seats_taken(event_row["id"]))


def get_signup(eid, user_id):
    with connect() as con:
        return con.execute(
            "SELECT * FROM signups WHERE event_id = ? AND user_id = ?",
            (eid, user_id),
        ).fetchone()


def confirmed_signups(eid):
    with connect() as con:
        return con.execute(
            "SELECT * FROM signups WHERE event_id = ? AND status = 'in' "
            "ORDER BY joined_at",
            (eid,),
        ).fetchall()


def waiting_signups(eid):
    """Everything queued, oldest first: people waiting and guests waiting."""
    with connect() as con:
        return con.execute(
            "SELECT * FROM signups WHERE event_id = ? "
            "AND (status = 'wait' OR waiting_guests > 0) ORDER BY joined_at",
            (eid,),
        ).fetchall()


def everyone_on_event(eid):
    with connect() as con:
        return con.execute(
            "SELECT * FROM signups WHERE event_id = ? ORDER BY joined_at", (eid,)
        ).fetchall()


def add_signup(eid, user_id, confirmed_guests, waiting_guests, status):
    with connect() as con:
        con.execute(
            "INSERT INTO signups(event_id, user_id, confirmed_guests, "
            "waiting_guests, status, joined_at) VALUES(?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(event_id, user_id) DO UPDATE SET "
            "  confirmed_guests = excluded.confirmed_guests, "
            "  waiting_guests = excluded.waiting_guests, "
            "  status = excluded.status",
            (eid, user_id, confirmed_guests, waiting_guests, status, int(time.time())),
        )


def remove_signup(eid, user_id):
    with connect() as con:
        con.execute(
            "DELETE FROM signups WHERE event_id = ? AND user_id = ?", (eid, user_id)
        )


def waitlist_position(eid, user_id):
    for i, row in enumerate(waiting_signups(eid), start=1):
        if row["user_id"] == user_id:
            return i
    return None


def promote_from_waitlist(eid):
    """Fill any free seats from the queue, oldest first.

    Returns a list of (user_id, kind, count) where kind is 'person' when the
    person themselves moved in, or 'guests' when only their guests did.
    """
    ev = get_event(eid)
    if ev is None or ev["status"] != "live":
        return []

    promoted = []
    free = seats_free(ev)
    if free <= 0:
        return []

    for row in waiting_signups(eid):
        if free <= 0:
            break
        uid = row["user_id"]

        if row["status"] == "wait":
            # The person needs a seat first, then as many guests as fit.
            free -= 1
            take = min(row["waiting_guests"], free)
            free -= take
            with connect() as con:
                con.execute(
                    "UPDATE signups SET status = 'in', confirmed_guests = ?, "
                    "waiting_guests = ? WHERE event_id = ? AND user_id = ?",
                    (take, row["waiting_guests"] - take, eid, uid),
                )
            promoted.append((uid, "person", 1 + take))
        else:
            take = min(row["waiting_guests"], free)
            if take <= 0:
                continue
            free -= take
            with connect() as con:
                con.execute(
                    "UPDATE signups SET confirmed_guests = confirmed_guests + ?, "
                    "waiting_guests = waiting_guests - ? "
                    "WHERE event_id = ? AND user_id = ?",
                    (take, take, eid, uid),
                )
            promoted.append((uid, "guests", take))

    return promoted


# ----------------------------------------------------------------- subhosts --

def add_decline(eid, user_id, had_signed_up=False):
    """Record that someone said they are not coming."""
    with connect() as con:
        con.execute(
            "INSERT INTO declines(event_id, user_id, declined_at, had_signed_up) "
            "VALUES(?, ?, ?, ?) "
            "ON CONFLICT(event_id, user_id) DO UPDATE SET "
            "  declined_at = excluded.declined_at, "
            "  had_signed_up = MAX(declines.had_signed_up, excluded.had_signed_up)",
            (eid, user_id, int(time.time()), int(had_signed_up)),
        )


def remove_decline(eid, user_id):
    """They changed their mind and signed up, so the no longer stands."""
    with connect() as con:
        con.execute(
            "DELETE FROM declines WHERE event_id = ? AND user_id = ?",
            (eid, user_id),
        )


def get_decline(eid, user_id):
    with connect() as con:
        return con.execute(
            "SELECT * FROM declines WHERE event_id = ? AND user_id = ?",
            (eid, user_id),
        ).fetchone()


def declines_for_event(eid):
    with connect() as con:
        return con.execute(
            "SELECT * FROM declines WHERE event_id = ? ORDER BY declined_at",
            (eid,),
        ).fetchall()


def decline_count(user_id):
    """How many times they have said no, since the last stats reset."""
    epoch = int(get_meta("stats_epoch", "0"))
    with connect() as con:
        return con.execute(
            "SELECT COUNT(*) c FROM declines d JOIN events e ON e.id = d.event_id "
            "WHERE d.user_id = ? AND e.starts_at >= ?",
            (user_id, epoch),
        ).fetchone()["c"]


def add_subhost(eid, user_id):
    with connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO subhosts(event_id, user_id) VALUES(?, ?)",
            (eid, user_id),
        )


def is_subhost(eid, user_id):
    with connect() as con:
        return (
            con.execute(
                "SELECT 1 FROM subhosts WHERE event_id = ? AND user_id = ?",
                (eid, user_id),
            ).fetchone()
            is not None
        )


# -------------------------------------------------------------------- stats --

def host_leaderboard(limit=10):
    epoch = int(get_meta("stats_epoch", "0"))
    now = int(time.time())
    with connect() as con:
        return con.execute(
            "SELECT host_id, COUNT(*) n FROM events "
            "WHERE status = 'live' AND starts_at < ? AND starts_at >= ? "
            "GROUP BY host_id ORDER BY n DESC, host_id LIMIT ?",
            (now, epoch, limit),
        ).fetchall()


def player_leaderboard(limit=10):
    epoch = int(get_meta("stats_epoch", "0"))
    now = int(time.time())
    with connect() as con:
        return con.execute(
            "SELECT s.user_id, COUNT(*) n FROM signups s "
            "JOIN events e ON e.id = s.event_id "
            "WHERE s.status = 'in' AND e.status = 'live' "
            "AND e.starts_at < ? AND e.starts_at >= ? "
            "GROUP BY s.user_id ORDER BY n DESC, s.user_id LIMIT ?",
            (now, epoch, limit),
        ).fetchall()


def stats_for(user_id):
    epoch = int(get_meta("stats_epoch", "0"))
    now = int(time.time())
    with connect() as con:
        hosted = con.execute(
            "SELECT COUNT(*) c FROM events WHERE host_id = ? AND status = 'live' "
            "AND starts_at < ? AND starts_at >= ?",
            (user_id, now, epoch),
        ).fetchone()["c"]
        played = con.execute(
            "SELECT COUNT(*) c FROM signups s JOIN events e ON e.id = s.event_id "
            "WHERE s.user_id = ? AND s.status = 'in' AND e.status = 'live' "
            "AND e.starts_at < ? AND e.starts_at >= ?",
            (user_id, now, epoch),
        ).fetchone()["c"]
    return hosted, played


def stats_population():
    """How many players and hosts a reset would affect."""
    return len(player_leaderboard(10000)), len(host_leaderboard(10000))


def reset_stats():
    """Non-destructive: only counts sessions from now on. Event data is kept."""
    set_meta("stats_epoch", int(time.time()))


def sessions_for(user_id):
    now = int(time.time())
    with connect() as con:
        return con.execute(
            "SELECT e.*, s.confirmed_guests, s.waiting_guests, s.status sstatus "
            "FROM signups s JOIN events e ON e.id = s.event_id "
            "WHERE s.user_id = ? AND e.status = 'live' AND e.starts_at >= ? "
            "ORDER BY e.starts_at",
            (user_id, now),
        ).fetchall()
