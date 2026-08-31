# -*- coding: utf-8 -*-
"""Dates, calendar files and permission checks."""

import io
import re
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import config
import db

TZ = ZoneInfo(config.TIMEZONE)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_WEEKDAYS = {
    "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3,
    "fri": 4, "sat": 5, "sun": 6,
}


# ------------------------------------------------------------------- times --

def now_local():
    return datetime.now(TZ)


def to_epoch(d, hour, minute):
    return int(datetime(d.year, d.month, d.day, hour, minute, tzinfo=TZ).timestamp())


def local_dt(epoch):
    return datetime.fromtimestamp(epoch, TZ)


def fmt_when(epoch):
    """'Sat 6 Sep, 8:00pm'"""
    dt = local_dt(epoch)
    return f"{dt:%a} {dt.day} {dt:%b}, {fmt_time(epoch)}"


def fmt_time(epoch):
    """'8:00pm'"""
    dt = local_dt(epoch)
    hour = dt.hour % 12 or 12
    ampm = "am" if dt.hour < 12 else "pm"
    return f"{hour}:{dt:%M}{ampm}"


def fmt_date_only(epoch):
    dt = local_dt(epoch)
    return f"{dt:%a} {dt.day} {dt:%b}"


def fmt_duration(minutes):
    """60 -> '1 hour', 90 -> '1.5 hours', 75 -> '1h 15m'."""
    if minutes % 60 == 0:
        h = minutes // 60
        return "1 hour" if h == 1 else f"{h} hours"
    if minutes % 30 == 0:
        return f"{minutes / 60:g} hours"
    if minutes < 60:
        return f"{minutes} mins"
    return f"{minutes // 60}h {minutes % 60}m"


def fmt_when_range(epoch, minutes):
    """'Sat 6 Sep, 8:00pm-9:00pm' - start and finish, so people can plan."""
    end = epoch + minutes * 60
    return f"{fmt_when(epoch)}-{fmt_time(end)}"


def parse_duration(text):
    """Accepts 1 / 2 / 1.5 / 1.5h / 90 / 90 mins / 1h30. Returns minutes.

    A bare number of 6 or less means hours; anything larger means minutes.
    Range is 30 minutes to 6 hours.
    """
    s = (text or "").strip().lower().replace(" ", "")
    if not s:
        return None

    # 1h30 / 1hr30
    m = re.fullmatch(r"(\d{1,2})h(?:rs?|ours?)?(\d{1,2})", s)
    if m:
        mins = int(m.group(1)) * 60 + int(m.group(2))
        return mins if 30 <= mins <= 360 else None

    m = re.fullmatch(r"(\d+(?:\.\d+)?)(h|hr|hrs|hour|hours|m|min|mins|minute|minutes)?",
                     s)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2)

    if unit in ("m", "min", "mins", "minute", "minutes"):
        mins = val
    elif unit in ("h", "hr", "hrs", "hour", "hours"):
        mins = val * 60
    else:
        mins = val * 60 if val <= 6 else val

    mins = int(round(mins))
    return mins if 30 <= mins <= 360 else None


def parse_date(text):
    """Accepts today / tomorrow / Sat / 6 Sep / 6 September / 06-09 / 06/09/2026.

    Returns a date, or None. Bare day-month without a year rolls to next year
    when the date has already passed.
    """
    s = (text or "").strip().lower().replace(",", " ")
    s = re.sub(r"\s+", " ", s)
    if not s:
        return None

    today = now_local().date()

    if s in ("today", "tonight"):
        return today
    if s in ("tomorrow", "tmr", "tmrw"):
        return today + timedelta(days=1)

    # Bare weekday name -> the next one coming up
    wd = _WEEKDAYS.get(s[:5]) if s[:5] in _WEEKDAYS else _WEEKDAYS.get(s[:4], _WEEKDAYS.get(s[:3]))
    if wd is not None and s.replace(" ", "").isalpha():
        ahead = (wd - today.weekday()) % 7 or 7
        return today + timedelta(days=ahead)

    # ISO: 2026-09-06
    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    # 06/09/2026 or 6-9-26 or 06/09  (day first)
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})(?:[-/.](\d{2,4}))?", s)
    if m:
        day, mon = int(m.group(1)), int(m.group(2))
        if m.group(3):
            year = int(m.group(3))
            year += 2000 if year < 100 else 0
        else:
            year = today.year
        d = _safe_date(year, mon, day)
        if d and not m.group(3) and d < today:
            d = _safe_date(year + 1, mon, day)
        return d

    # 6 Sep  /  Sep 6  /  6 September
    m = re.fullmatch(r"(\d{1,2}) ?([a-z]{3,9})\.?(?: (\d{2,4}))?", s)
    if not m:
        m2 = re.fullmatch(r"([a-z]{3,9})\.? ?(\d{1,2})(?: (\d{2,4}))?", s)
        if m2:
            mon_name, day, yr = m2.group(1), int(m2.group(2)), m2.group(3)
        else:
            return None
    else:
        day, mon_name, yr = int(m.group(1)), m.group(2), m.group(3)

    mon = _MONTHS.get(mon_name[:4]) or _MONTHS.get(mon_name[:3])
    if not mon:
        return None
    if yr:
        year = int(yr)
        year += 2000 if year < 100 else 0
    else:
        year = today.year
    d = _safe_date(year, mon, day)
    if d and not yr and d < today:
        d = _safe_date(year + 1, mon, day)
    return d


def _safe_date(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_time(text):
    """Accepts 8pm / 8 pm / 20:00 / 7.30pm / 1930 / 8. Returns (hour, minute)."""
    s = (text or "").strip().lower().replace(" ", "")
    if not s:
        return None

    m = re.fullmatch(r"(\d{1,2})(?:[:.h](\d{2}))?(am|pm)?", s)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        elif ampm is None and 1 <= hour <= 11 and m.group(2) is None:
            # A bare hour means evening - badminton is an after-work game.
            # "9am" or "09:00" still get you the morning, and the review step
            # shows the interpreted time before anything is created.
            hour += 12
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
        return None

    m = re.fullmatch(r"(\d{3,4})", s)  # 1930 / 930
    if m:
        raw = m.group(1).zfill(4)
        hour, minute = int(raw[:2]), int(raw[2:])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    return None


# -------------------------------------------------------------- permissions --

def is_admin(user_id):
    return user_id in config.ADMIN_IDS


def can_manage(event_row, user_id):
    """Host, sub-host or admin."""
    if event_row is None:
        return False
    return (
        event_row["host_id"] == user_id
        or is_admin(user_id)
        or db.is_subhost(event_row["id"], user_id)
    )


# --------------------------------------------------------- calendar files ---

def _ics_escape(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold(line):
    """RFC 5545 caps lines at 75 octets; continuations start with a space."""
    raw = line.encode("utf-8")
    if len(raw) <= 73:
        return line
    out, chunk = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(chunk) + len(b) > 73:
            out.append(chunk.decode("utf-8"))
            chunk = b" " + b
        else:
            chunk += b
    out.append(chunk.decode("utf-8"))
    return "\r\n".join(out)


def build_ics(event_row, guests=0):
    """A single-event .ics file. Tapping it on a phone opens the calendar app."""
    start = datetime.fromtimestamp(event_row["starts_at"], timezone.utc)
    end = start + timedelta(minutes=event_row["duration_min"])
    stamp = datetime.now(timezone.utc)

    guest_note = ""
    if guests == 1:
        guest_note = " You are bringing 1 guest."
    elif guests > 1:
        guest_note = f" You are bringing {guests} guests."

    desc = (
        f"Badminton session {event_row['id']}. "
        f"{event_row['capacity']} players.{guest_note}"
    )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BBBot//Badminton//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{event_row['id']}-{event_row['created_at']}@bbbot",
        f"DTSTAMP:{stamp:%Y%m%dT%H%M%S}Z",
        f"DTSTART:{start:%Y%m%dT%H%M%S}Z",
        f"DTEND:{end:%Y%m%dT%H%M%S}Z",
        _fold(f"SUMMARY:Badminton {_ics_escape(event_row['id'])}"),
        _fold(f"LOCATION:{_ics_escape(event_row['venue'])}"),
        _fold(f"DESCRIPTION:{_ics_escape(desc)}"),
        "STATUS:CONFIRMED",
        # No VALARM on purpose: the bot sends its own reminder DMs, and a
        # calendar alarm on top of that means two buzzes seconds apart.
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    data = "\r\n".join(lines) + "\r\n"
    buf = io.BytesIO(data.encode("utf-8"))
    buf.name = f"{event_row['id']}.ics"
    return buf


def build_csv(event_row):
    """Google Calendar import format. Desktop web only: Settings > Import."""
    start = local_dt(event_row["starts_at"])
    end = start + timedelta(minutes=event_row["duration_min"])

    def d(x):
        return f"{x:%m/%d/%Y}"

    def t(x):
        hour = x.hour % 12 or 12
        return f"{hour:02d}:{x:%M} {'AM' if x.hour < 12 else 'PM'}"

    def q(x):
        return '"' + str(x).replace('"', '""') + '"'

    header = (
        "Subject,Start Date,Start Time,End Date,End Time,"
        "All Day Event,Description,Location,Private"
    )
    row = ",".join([
        q(f"Badminton {event_row['id']}"),
        q(d(start)), q(t(start)), q(d(end)), q(t(end)),
        "False",
        q(f"Badminton session {event_row['id']}. {event_row['capacity']} players."),
        q(event_row["venue"]),
        "True",
    ])
    buf = io.BytesIO((header + "\r\n" + row + "\r\n").encode("utf-8"))
    buf.name = f"{event_row['id']}.csv"
    return buf


# ------------------------------------------------------------------ format --

def guest_bit(confirmed_guests):
    if confirmed_guests == 1:
        return ", with 1 guest"
    if confirmed_guests > 1:
        return f", with {confirmed_guests} guests"
    return ""


def event_line(event_row):
    taken = db.seats_taken(event_row["id"])
    free = event_row["capacity"] - taken
    tag = "FULL" if free <= 0 else f"{free} free"
    return (
        f"{event_row['id']} · {fmt_when(event_row['starts_at'])}\n"
        f"   {event_row['venue']} · {taken}/{event_row['capacity']} · {tag}"
    )


def event_detail(event_row):
    eid = event_row["id"]
    taken = db.seats_taken(eid)
    host = db.user_label(event_row["host_id"])

    lines = [
        f"\U0001F3F8 {eid} — "
        f"{fmt_when_range(event_row['starts_at'], event_row['duration_min'])}",
        f"\U0001F4CD {event_row['venue']}",
        f"\U0001F465 {taken}/{event_row['capacity']} spots taken",
        f"Host: {host}",
    ]

    if event_row["status"] == "cancelled":
        lines.insert(1, f"❌ CANCELLED — {event_row['cancel_reason']}")

    playing = db.confirmed_signups(eid)
    manual = db.manual_players(eid)
    if playing or manual:
        lines.append("\nPlaying:")
        i = 0
        for s in playing:
            i += 1
            extra = f" (+{s['confirmed_guests']})" if s["confirmed_guests"] else ""
            lines.append(f"  {i}. {db.user_label(s['user_id'])}{extra}")
        for mp in manual:
            i += 1
            lines.append(f"  {i}. {mp['name']} (added by host)")

    waiting = [w for w in db.waiting_signups(eid)]
    if waiting:
        lines.append("\nWaitlist:")
        pos = 1
        for w in waiting:
            if w["status"] == "wait":
                extra = f" (+{w['waiting_guests']})" if w["waiting_guests"] else ""
                lines.append(f"  {pos}. {db.user_label(w['user_id'])}{extra}")
            else:
                lines.append(
                    f"  {pos}. {w['waiting_guests']} guest(s) of "
                    f"{db.user_label(w['user_id'])}"
                )
            pos += 1

    declined = db.declines_for_event(eid)
    if declined:
        names = ", ".join(db.user_label(d["user_id"]) for d in declined)
        lines.append(f"\nNot coming ({len(declined)}): {names}")

    return "\n".join(lines)
