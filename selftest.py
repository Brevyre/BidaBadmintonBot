# -*- coding: utf-8 -*-
"""Offline checks for the parts that don't need Telegram.

Run:  py selftest.py
Uses a throwaway database so your real bbbot.db is never touched.
"""

import os
import sys
import tempfile

os.environ.setdefault("BOT_TOKEN", "0:selftest")
os.environ.setdefault("ADMIN_IDS", "1")
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "selftest.db")

import config  # noqa: E402
import db  # noqa: E402
import helpers as H  # noqa: E402

FAILS = []


def check(label, got, want):
    if got == want:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}\n         got  {got!r}\n         want {want!r}")
        FAILS.append(label)


def main():
    db.init_db()
    print("\nDate parsing")
    today = H.now_local().date()
    check("today", H.parse_date("today"), today)
    check("tomorrow", H.parse_date("tomorrow"), today.replace()
          .fromordinal(today.toordinal() + 1))
    check("6 Sep has day 6", H.parse_date("6 Sep").day, 6)
    check("6 Sep has month 9", H.parse_date("6 Sep").month, 9)
    check("Sep 6 matches 6 Sep", H.parse_date("sep 6"), H.parse_date("6 Sep"))
    check("06/09/2027", str(H.parse_date("06/09/2027")), "2027-09-06")
    check("2027-09-06 ISO", str(H.parse_date("2027-09-06")), "2027-09-06")
    check("nonsense rejected", H.parse_date("next saturday-ish"), None)
    check("31 Feb rejected", H.parse_date("31/02/2027"), None)

    print("\nTime parsing")
    check("8pm", H.parse_time("8pm"), (20, 0))
    check("20:00", H.parse_time("20:00"), (20, 0))
    check("7.30pm", H.parse_time("7.30pm"), (19, 30))
    check("1930", H.parse_time("1930"), (19, 30))
    check("bare 8 -> evening", H.parse_time("8"), (20, 0))
    check("12am", H.parse_time("12am"), (0, 0))
    check("nonsense rejected", H.parse_time("half seven"), None)
    check("25:00 rejected", H.parse_time("25:00"), None)

    print("\nSeats and the agreed guest rule")
    start = H.to_epoch(H.parse_date("6 Sep"), 20, 0)
    db.create_event("E001", 100, start, 120, "Test Hall", 8)
    ev = db.get_event("E001")

    db.add_signup("E001", 1, 0, 0, "in")          # 1 seat  -> 1
    db.add_signup("E001", 2, 2, 0, "in")          # 3 seats -> 4
    db.add_signup("E001", 3, 2, 0, "in")          # 3 seats -> 7
    check("seats taken", db.seats_taken("E001"), 7)
    check("seats free", db.seats_free(ev), 1)

    # The rule you chose: take the last seat, waitlist the extras.
    free = db.seats_free(ev)
    guests = 2
    for_guests = min(guests, free - 1)
    db.add_signup("E001", 4, for_guests, guests - for_guests, "in")
    check("player took last seat", db.get_signup("E001", 4)["status"], "in")
    check("guests waitlisted", db.get_signup("E001", 4)["waiting_guests"], 2)
    check("event now full", db.seats_taken("E001"), 8)

    # A fifth person arrives to a full event -> whole party waitlisted
    db.add_signup("E001", 5, 0, 1, "wait")
    check("waitlist position", db.waitlist_position("E001", 5), 2)

    print("\nWaitlist promotion")
    db.remove_signup("E001", 2)                   # frees 3 seats
    promoted = db.promote_from_waitlist("E001")
    check("two parties promoted", len(promoted), 2)
    check("user 4's guests first", promoted[0][:2], (4, "guests"))
    check("then user 5 themselves", promoted[1][:2], (5, "person"))
    check("user 4 has no one waiting",
          db.get_signup("E001", 4)["waiting_guests"], 0)
    check("user 5 is in", db.get_signup("E001", 5)["status"], "in")
    check("back to full", db.seats_taken("E001"), 8)

    print("\nOver-capacity safety")
    check("never exceeds capacity", db.seats_taken("E001") <= ev["capacity"], True)

    print("\nStats")
    past = H.to_epoch(H.parse_date("2020-01-05"), 20, 0)
    db.create_event("E002", 100, past, 120, "Old Hall", 4)
    db.add_signup("E002", 1, 0, 0, "in")
    hosted, played = db.stats_for(100)
    check("hosted counted", hosted, 1)
    check("played counted", db.stats_for(1)[1], 1)
    db.reset_stats()
    check("reset zeroes hosted", db.stats_for(100)[0], 0)
    check("reset keeps the event", db.get_event("E002") is not None, True)

    print("\nCalendar files")
    ics = H.build_ics(db.get_event("E001"), guests=2).getvalue().decode("utf-8")
    check("ics begins", ics.startswith("BEGIN:VCALENDAR"), True)
    check("ics ends", ics.strip().endswith("END:VCALENDAR"), True)
    check("ics uses CRLF", "\r\n" in ics, True)
    check("ics has one event", ics.count("BEGIN:VEVENT"), 1)
    check("ics has location", "LOCATION:Test Hall" in ics, True)
    check("ics mentions guests", "2 guests" in ics, True)
    check("ics has no alarm", "VALARM" in ics, False)
    check("no line over 75 octets",
          max(len(l.encode()) for l in ics.split("\r\n")) <= 75, True)

    csv = H.build_csv(db.get_event("E001")).getvalue().decode("utf-8")
    check("csv header", csv.startswith("Subject,Start Date"), True)
    check("csv has 2 rows", len([l for l in csv.strip().split("\r\n")]), 2)

    # A venue containing a comma must not break the CSV
    db.update_event("E001", venue='Hall A, Level 3 "West"')
    csv2 = H.build_csv(db.get_event("E001")).getvalue().decode("utf-8")
    check("csv quotes commas", '"Hall A, Level 3 ""West"""' in csv2, True)

    print("\nFormatting")
    check("fmt_time 8pm", H.fmt_time(H.to_epoch(H.parse_date("6 Sep"), 20, 0)),
          "8:00pm")
    check("fmt_time 9:30am",
          H.fmt_time(H.to_epoch(H.parse_date("6 Sep"), 9, 30)), "9:30am")
    check("fmt_time midnight",
          H.fmt_time(H.to_epoch(H.parse_date("6 Sep"), 0, 0)), "12:00am")
    check("guest_bit 0", H.guest_bit(0), "")
    check("guest_bit 1", H.guest_bit(1), ", with 1 guest")
    check("guest_bit 2", H.guest_bit(2), ", with 2 guests")

    print("\nEvent IDs")
    first = db.next_event_id()
    second = db.next_event_id()
    check("zero padded to 3 digits", len(first), 4)
    check("starts at E001", first, "E001")
    check("increments", second, "E002")
    check("never reused", first != second, True)

    print()
    if FAILS:
        print(f"{len(FAILS)} check(s) FAILED: {', '.join(FAILS)}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
