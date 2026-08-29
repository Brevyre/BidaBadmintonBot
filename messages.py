# -*- coding: utf-8 -*-
"""Every message the bot sends, in one place.

Tone (agreed): friendly wording, kept short. Emoji only where it earns its place.
Edit the text here and restart the bot -- no other file needs touching.
"""

# ---------------------------------------------------------------- welcome ---

START_NEW = (
    "\U0001F3F8 Hi {name}, you're registered!\n"
    "I'll DM you reminders for any session you sign up for.\n\n"
    "Type /help to see what I can do."
)

START_AGAIN = (
    "\U0001F44B You're already registered, {name}.\n"
    "Type /help if you need a refresher."
)

HELP = (
    "\U0001F3F8 *Badminton bot*\n\n"
    "*Everyone*\n"
    "/create - create a new session\n"
    "/events - all upcoming sessions\n"
    "/open - sessions with spots free\n"
    "/show E001 - full details\n"
    "/play E001 - sign up\n"
    "/unplay E001 - back out\n"
    "/mysessions - what you're signed up for\n"
    "/sessions @handle - someone else's sessions\n"
    "/stats - leaderboards\n"
    "/csv E001 - calendar file as CSV\n\n"
    "*If you're hosting*\n"
    "/add E001 | Ann, @bob - put players straight in\n"
    "/invite E001 | @bob - ask them first\n"
    "/subhost E001 @handle - add a sub-host\n"
    "/uninvite E001 @handle - remove a player\n"
    "/modify E001 - edit the session\n"
    "/cancel E001 reason - call it off\n\n"
    "*Admin*\n"
    "/removeevent E001\n"
    "/clearevents CONFIRM\n"
    "/resetstats CONFIRM"
)

# ---------------------------------------------------------------- offline ---

OFFLINE_SHUTDOWN = (
    "\U0001F634 Going offline for now. Anything you send I'll pick up when I'm back."
)

OFFLINE_BACK = (
    "\U0001F44B Back online. I missed {count} messages while I was away "
    "— sorting them now."
)

OFFLINE_BACK_QUIET = "\U0001F44B Back online."

LATE_PREFIX_OK = (
    "Sorry for the wait — I was offline when you sent this ({when}). "
    "All sorted:\n\n"
)

LATE_PREFIX_FAIL = (
    "Sorry for the wait — I was offline when you sent this ({when}), "
    "and things have moved on since.\n\n"
)

PINNED_NOTICE = (
    "A note on me: I'm online around the clock, but I do get restarted for "
    "updates now and then. If I go quiet for a minute, your command isn't lost "
    "— I'll pick it up as soon as I'm back."
)

# ----------------------------------------------------------------- create ---

CREATE_STEP_DATE = (
    "\U0001F3F8 New session — step 1 of 5\nWhen? Tap a day, or type a date."
)
CREATE_STEP_TIME = (
    "Step 2 of 5 — What time does it start?\n"
    "Tap one, or type it (8pm, 20:00, 7.30pm all work)."
)
CREATE_STEP_DURATION = (
    "Step 3 of 5 — How long is the court booked for?\n"
    "Tap one, or type it (90 mins, 1.5h both work)."
)
CREATE_STEP_VENUE = "Step 4 of 5 — Which venue?\nTap a recent one, or type a new name."
CREATE_STEP_VENUE_NONE = "Step 4 of 5 — Which venue?\nType the name."
CREATE_STEP_PLAYERS = "Step 5 of 5 — How many players?\nTap one, or type a number."

CREATE_REVIEW = (
    "—— REVIEW ——\n"
    "Ready to go:\n"
    "\U0001F3F8 {when}\n"
    "⏱ {duration}\n"
    "\U0001F4CD {venue}\n"
    "\U0001F465 {capacity} players\n"
    "Host: you"
)

CREATE_DONE = "✅ Created {eid} — announced to the group."
CREATE_DONE_NO_GROUP = (
    "✅ Created {eid}.\n"
    "I couldn't announce it — no group chat is set up yet. "
    "Add me to your group and run /sethere there."
)
CREATE_CANCELLED = "No problem, nothing created."
CREATE_RESTART = "Starting over."

BAD_DATE = (
    "I couldn't read \"{raw}\" as a date. "
    "Try something like 6 Sep, 06/09, or tap a button."
)
BAD_TIME = "I couldn't read \"{raw}\" as a time. Try 8pm, 20:00 or 7.30pm."
BAD_NUMBER = "I need a whole number between 2 and 40. \"{raw}\" won't work."
BAD_DURATION = (
    "I couldn't read \"{raw}\" as a length. Try 1, 2, 1.5h or 90 mins "
    "(anything from 30 minutes to 6 hours)."
)
DATE_IN_PAST = "That's in the past. Give me a date from today onwards."

# --------------------------------------------------------------- announce ---

ANNOUNCE_NEW = (
    "\U0001F3F8 New session — {eid}\n"
    "{when}\n"
    "\U0001F4CD {venue}\n"
    "\U0001F465 0/{capacity} spots taken\n"
    "Host: {host}"
)

# ----------------------------------------------------------------- signup ---

PLAY_ASK_GUESTS = (
    "\U0001F3F8 {eid} — {when}\n"
    "{venue} · {taken}/{capacity} spots taken\n\n"
    "Bringing anyone?"
)

PLAY_OK = (
    "✅ You're in{guest_bit}.\n"
    "{eid} · {when} · {venue}\n"
    "{taken}/{capacity} spots taken{full_bit}\n"
    "Calendar file attached \U0001F447"
)

PLAY_PARTIAL = (
    "✅ You're in — but only {seats} spot{plural} was left, so your {waiting} "
    "guests are on the waitlist. They'll move up automatically if anyone drops out.\n"
    "{eid} is now full ({taken}/{capacity}).\n"
    "Calendar file attached \U0001F447"
)

PLAY_WAITLISTED = (
    "\U0001F4DD {eid} is full, so you're on the waitlist — position {pos}.\n"
    "{when} · {venue}\n"
    "I'll DM you the moment a spot opens."
)

UNPLAY_OK = "✅ You're out of {eid} — {taken}/{capacity} spots taken now."
UNPLAY_PROMOTED = "{who} moves off the waitlist into your spot."

PROMOTED_DM = (
    "\U0001F389 A spot opened up — you're in for {eid}!\n"
    "{when} · {venue}\n"
    "Calendar file attached \U0001F447"
)

PROMOTED_GUESTS_DM = (
    "\U0001F389 {n} of your guests moved off the waitlist for {eid}.\n"
    "{when} · {venue}"
)

# ----------------------------------------------------------------- errors ---

ERR_NO_EVENT = "I can't find {eid}."
ERR_FULL = "{eid} is full ({taken}/{capacity})."
ERR_ALREADY_IN = "You're already in for {eid}{guest_bit}."
ERR_NOT_IN = "You're not signed up for {eid}."
ERR_NOT_HOST = "Only the host can change {eid} — that's {host}."
ERR_ADMIN_ONLY = "That one's admin-only, sorry."
ERR_NO_DM = "I can't message you privately until we've spoken once."
ERR_PASSED = "{eid} was on {when} — been and gone."
ERR_UNKNOWN_CMD = "I don't know that one."
ERR_BAD_ID = "That doesn't look like an event ID. They look like E001."
ERR_NEED_ID = "I need an event ID, like /{cmd} E001."
ERR_NO_SUCH_USER = "I don't know {handle} yet — they need to send me /start first."
ERR_CANCELLED_EVENT = "{eid} was cancelled and can't be changed."
ERR_PRIVATE_ONLY = (
    "Let's do this in a private chat — this one needs typed answers, and I "
    "can't read those in a group.\n\n"
    "Tap below, then send me: {cmd}"
)

# ------------------------------------------------------------ destructive ---

CANCEL_CONFIRM = (
    "⚠️ Cancel {eid}?\n"
    "{when} · {venue}\n"
    "{n} players signed up — they'll all be notified.\n"
    "Reason: \"{reason}\""
)
CANCEL_DONE = "✅ {eid} cancelled. {n} players notified."
CANCEL_ABORTED = "Kept it. Nothing changed."

CANCEL_DM = (
    "\U0001F614 {eid} has been cancelled.\n"
    "{when} · {venue}\n"
    "Reason: {reason}"
)

REMOVE_CONFIRM = (
    "⚠️ Remove {eid} completely?\n"
    "{when} · {venue}\n"
    "{n} signups will be deleted. Players are NOT notified.\n"
    "This cannot be undone."
)
REMOVE_DONE = "✅ {eid} removed."
REMOVE_ABORTED = "Kept it. Nothing changed."

CLEAR_CONFIRM = (
    "⚠️ This wipes {events} events and {signups} signups.\n"
    "It cannot be undone.\n"
    "Type DELETE to go ahead, or anything else to stop."
)
CLEAR_DONE = "✅ Wiped {events} events and {signups} signups."
CLEAR_ABORTED = "Stopped. Nothing was deleted."
CLEAR_EMPTY = "There's nothing to wipe."

RESET_CONFIRM = (
    "⚠️ This zeroes stats for {players} players and {hosts} hosts.\n"
    "It cannot be undone.\n"
    "Type RESET to go ahead, or anything else to stop."
)
RESET_DONE = "✅ Stats reset for {players} players and {hosts} hosts."
RESET_ABORTED = "Stopped. Nothing was reset."

# -------------------------------------------------------------- reminders ---

REMIND_DAY_BEFORE = (
    "\U0001F3F8 Badminton tomorrow!\n"
    "{eid} · {when} · {venue}\n"
    "You're in{guest_bit}.\n"
    "Can't make it?"
)

REMIND_SOON = "\U0001F3F8 {eid} starts at {time} — {venue}.\nSee you there!"

REMIND_GROUP_OPEN = (
    "\U0001F3F8 {eid} is tomorrow and still has {free} spots.\n"
    "{when} · {venue}"
)

# ------------------------------------------------------------------ lists ---

NO_EVENTS = "Nothing on the calendar yet. Be the first — /create"
NO_OPEN_EVENTS = "Every upcoming session is full. Try /events to see them all."
NO_SESSIONS_YOU = "You're not signed up for anything yet. /open shows what has spots."
NO_SESSIONS_THEM = "{handle} isn't signed up for anything upcoming."

# ------------------------------------------------------------------- misc ---

ADD_USAGE = (
    "Use: /add E001 | Ann, @bob\n"
    "Adds them straight into the session. Use /invite instead if you'd rather "
    "ask them first."
)
ADD_DONE = "✅ {eid} — {taken}/{capacity} spots taken."
ADD_LINE_MANUAL = "  • {name} — added (not on Telegram, you're vouching)"
ADD_LINE_TOLD = "  • {handle} — added and told"
ADD_LINE_NO_DM = "  • {handle} — added, but couldn't DM (no /start yet)"
ADD_LINE_UNKNOWN = "  • {handle} — I don't know them yet, so I can't add them"
ADD_LINE_ALREADY = "  • {who} — already in {eid}"
ADD_LINE_WAITLIST = "  • {who} — session was full, so they're on the waitlist"

ADD_DM = (
    "\U0001F3F8 {host} added you to {eid}.\n"
    "{when} · {venue}\n"
    "You're in — {taken}/{capacity} spots taken.\n"
    "Can't make it?"
)

ADD_DM_WAITLIST = (
    "\U0001F3F8 {host} tried to add you to {eid}, but it's full.\n"
    "{when} · {venue}\n"
    "You're on the waitlist at position {pos} — I'll DM you if a spot opens."
)

INVITE_NEEDS_HANDLE = (
    "\"{name}\" isn't a Telegram handle, so I can't send them an invitation.\n"
    "To put them in the session anyway, use: /add {eid} | {name}"
)

UNINVITE_MANUAL_DONE = (
    "✅ Removed {name} from {eid}. {taken}/{capacity} spots taken now."
)

INVITE_SENT = "✅ Invited {n} to {eid}: {names}"
INVITE_DM = (
    "\U0001F3F8 {host} invited you to {eid}!\n"
    "{when} · {venue} · {taken}/{capacity} spots taken"
)
INVITE_NO_DM = "(couldn't DM {handle} — they haven't sent me /start)"

SUBHOST_DONE = "✅ {handle} is now a sub-host of {eid}."
SUBHOST_DM = (
    "\U0001F3F8 {host} made you a sub-host of {eid}. You can now edit and cancel it."
)

UNINVITE_DONE = "✅ Removed {handle} from {eid}. {taken}/{capacity} spots taken now."
UNINVITE_DM = "The host removed you from {eid}.\n{when} · {venue}"

MODIFY_MENU = "What would you like to change on {eid}?"
MODIFY_DONE = "✅ {eid} updated — {n} players notified."
MODIFY_DM = (
    "✏️ {eid} has changed.\n"
    "{changes}\n"
    "New details: {when} · {venue}\n"
    "Updated calendar file attached \U0001F447"
)

SETHERE_DONE = "✅ Got it — I'll announce new sessions in this chat."
SETHERE_NOT_GROUP = "Run this inside the group chat you want announcements in."

CSV_CAPTION = (
    "CSV for Google Calendar. Import it on desktop: "
    "Calendar → Settings → Import & export."
)
ICS_CAPTION = "Tap to add to your calendar."
