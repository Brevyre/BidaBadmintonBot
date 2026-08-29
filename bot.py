# -*- coding: utf-8 -*-
"""BBBot - badminton session bot.

Run locally:   py bot.py       (uses config.json)
Run on Railway: same file, configured entirely by environment variables.
"""

import logging
import re
import time
from datetime import date as _date
from datetime import timedelta

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatType, ParseMode
from telegram.error import Forbidden, BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

import config
import db
import helpers as H
import messages as M

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bbbot")

BOT_START = time.time()
MISSED = {"count": 0}

# Conversation states
C_DATE, C_TIME, C_VENUE, C_PLAYERS, C_REVIEW = range(5)
M_MENU, M_DATE, M_TIME, M_VENUE, M_PLAYERS = range(5, 10)


# ============================================================ send helpers ==

def kb(rows):
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t, callback_data=d) for t, d in row] for row in rows]
    )


def dm_button(context, label="Open a chat with me"):
    """A tap-through link that opens this bot's private chat.

    Returns None if the username isn't known yet, in which case the caller
    still sends its message - just without the shortcut.
    """
    uname = getattr(context.bot, "username", None)
    if not uname:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, url=f"https://t.me/{uname}")]]
    )


async def reply(update, context, text, markup=None, ok=True):
    """Reply, prefixing the offline apology if this message arrived while down."""
    prefix = ""
    late = context.user_data.pop("late_when", None) if context.user_data else None
    if late:
        tmpl = M.LATE_PREFIX_OK if ok else M.LATE_PREFIX_FAIL
        prefix = tmpl.format(when=late)

    target = update.effective_message
    if update.callback_query:
        return await update.callback_query.message.reply_text(
            prefix + text, reply_markup=markup
        )
    return await target.reply_text(prefix + text, reply_markup=markup)


async def dm(context, user_id, text, markup=None, document=None, caption=None):
    """Send a private message. Returns False if the user has never opened a chat."""
    try:
        if document is not None:
            await context.bot.send_document(
                user_id, document=document, caption=caption
            )
        if text:
            await context.bot.send_message(user_id, text, reply_markup=markup)
        return True
    except (Forbidden, BadRequest) as exc:
        log.info("Could not DM %s: %s", user_id, exc)
        db.upsert_user(user_id, None, None, dm_ok=0)
        return False


async def to_group(context, text, markup=None):
    if not config.GROUP_CHAT_ID:
        return None
    try:
        return await context.bot.send_message(
            config.GROUP_CHAT_ID, text, reply_markup=markup
        )
    except (Forbidden, BadRequest) as exc:
        log.warning("Could not post to group: %s", exc)
        return None


async def send_calendar(context, user_id, event_row, guests=0):
    """The .ics file - tapping it on a phone adds the session to the calendar."""
    try:
        await context.bot.send_document(
            user_id,
            document=H.build_ics(event_row, guests),
            filename=f"{event_row['id']}.ics",
            caption=M.ICS_CAPTION,
        )
        return True
    except (Forbidden, BadRequest) as exc:
        log.info("Could not send calendar file to %s: %s", user_id, exc)
        return False


# =============================================================== lookups ====

EID_OK = re.compile(r"^E\d{1,4}$", re.I)


async def resolve_event(update, context, args, cmd):
    """Parse and fetch an event ID from command args, replying on any problem."""
    if not args:
        await reply(update, context, M.ERR_NEED_ID.format(cmd=cmd), ok=False)
        return None
    raw = args[0].upper()
    if not EID_OK.match(raw):
        await reply(update, context, M.ERR_BAD_ID, ok=False)
        return None
    ev = db.get_event(raw)
    if ev is None:
        await reply(
            update, context, M.ERR_NO_EVENT.format(eid=raw),
            kb([[("See all events", "ev:all")]]), ok=False,
        )
        return None
    return ev


def register(update):
    u = update.effective_user
    if u:
        db.upsert_user(u.id, u.username, u.first_name)


# ================================================================ basics ====

async def cmd_start(update, context):
    u = update.effective_user
    existed = db.upsert_user(u.id, u.username, u.first_name, dm_ok=1)
    tmpl = M.START_AGAIN if existed else M.START_NEW
    await reply(update, context, tmpl.format(name=u.first_name or "there"))


async def cmd_help(update, context):
    register(update)
    await update.effective_message.reply_text(M.HELP, parse_mode=ParseMode.MARKDOWN)


async def cmd_whoami(update, context):
    register(update)
    u = update.effective_user
    await reply(
        update, context,
        f"Your Telegram ID is {u.id}\n"
        f"This chat's ID is {update.effective_chat.id}\n\n"
        "Put your ID in ADMIN_IDS to unlock admin commands.",
    )


async def cmd_sethere(update, context):
    register(update)
    if not H.is_admin(update.effective_user.id):
        await reply(update, context, M.ERR_ADMIN_ONLY, ok=False)
        return
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await reply(update, context, M.SETHERE_NOT_GROUP, ok=False)
        return
    config.GROUP_CHAT_ID = chat.id
    db.set_meta("group_chat_id", chat.id)
    await reply(
        update, context,
        M.SETHERE_DONE + f"\n\nMake it permanent: set GROUP_CHAT_ID={chat.id}",
    )


# ================================================================ create ====

def date_buttons():
    today = H.now_local().date()
    rows = [[("Today", f"cd:{today.isoformat()}"),
             ("Tomorrow", f"cd:{(today + timedelta(days=1)).isoformat()}")]]
    nxt = []
    for i in range(2, 9):
        d = today + timedelta(days=i)
        if d.weekday() in (5, 6):
            nxt.append((f"{d:%a} {d.day} {d:%b}", f"cd:{d.isoformat()}"))
        if len(nxt) == 2:
            break
    if nxt:
        rows.append(nxt)
    rows.append([("Cancel", "ccl")])
    return kb(rows)


def time_buttons():
    return kb([
        [("7:00pm", "ct:19:00"), ("8:00pm", "ct:20:00"), ("9:00pm", "ct:21:00")],
        [("Cancel", "ccl")],
    ])


def venue_buttons():
    vs = db.recent_venues(3)
    rows = [[(v, f"cv:{i}")] for i, v in enumerate(vs)]
    rows.append([("Cancel", "ccl")])
    return kb(rows), vs


def player_buttons():
    return kb([
        [("4", "cp:4"), ("6", "cp:6"), ("8", "cp:8"), ("12", "cp:12")],
        [("Cancel", "ccl")],
    ])


def review_buttons():
    return kb([[("Create & announce", "cok")],
               [("Start over", "crs"), ("Cancel", "ccl")]])


async def create_start(update, context):
    register(update)
    if update.effective_chat.type != ChatType.PRIVATE:
        await reply(update, context, M.ERR_PRIVATE_ONLY.format(cmd="/create"),
                    dm_button(context), ok=False)
        return ConversationHandler.END
    context.user_data["new"] = {}
    await reply(update, context, M.CREATE_STEP_DATE, date_buttons())
    return C_DATE


async def create_date_btn(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data["new"]["date"] = _date.fromisoformat(q.data[3:])
    await q.edit_message_reply_markup(None)
    await q.message.reply_text(M.CREATE_STEP_TIME, reply_markup=time_buttons())
    return C_TIME


async def create_date_txt(update, context):
    raw = update.effective_message.text
    d = H.parse_date(raw)
    if d is None:
        await reply(update, context, M.BAD_DATE.format(raw=raw[:40]),
                    date_buttons(), ok=False)
        return C_DATE
    if d < H.now_local().date():
        await reply(update, context, M.DATE_IN_PAST, date_buttons(), ok=False)
        return C_DATE
    context.user_data["new"]["date"] = d
    await reply(update, context, M.CREATE_STEP_TIME, time_buttons())
    return C_TIME


async def create_time_btn(update, context):
    q = update.callback_query
    await q.answer()
    hh, mm = q.data[3:].split(":")
    context.user_data["new"]["time"] = (int(hh), int(mm))
    await q.edit_message_reply_markup(None)
    markup, vs = venue_buttons()
    text = M.CREATE_STEP_VENUE if vs else M.CREATE_STEP_VENUE_NONE
    context.user_data["venue_choices"] = vs
    await q.message.reply_text(text, reply_markup=markup)
    return C_VENUE


async def create_time_txt(update, context):
    raw = update.effective_message.text
    t = H.parse_time(raw)
    if t is None:
        await reply(update, context, M.BAD_TIME.format(raw=raw[:40]),
                    time_buttons(), ok=False)
        return C_TIME
    context.user_data["new"]["time"] = t
    markup, vs = venue_buttons()
    context.user_data["venue_choices"] = vs
    await reply(update, context, M.CREATE_STEP_VENUE if vs
                else M.CREATE_STEP_VENUE_NONE, markup)
    return C_VENUE


async def create_venue_btn(update, context):
    q = update.callback_query
    await q.answer()
    idx = int(q.data[3:])
    vs = context.user_data.get("venue_choices", [])
    if idx >= len(vs):
        await q.message.reply_text(M.CREATE_STEP_VENUE_NONE)
        return C_VENUE
    context.user_data["new"]["venue"] = vs[idx]
    await q.edit_message_reply_markup(None)
    await q.message.reply_text(M.CREATE_STEP_PLAYERS, reply_markup=player_buttons())
    return C_PLAYERS


async def create_venue_txt(update, context):
    name = update.effective_message.text.strip()
    if not name:
        await reply(update, context, M.CREATE_STEP_VENUE_NONE, ok=False)
        return C_VENUE
    context.user_data["new"]["venue"] = name[:80]
    await reply(update, context, M.CREATE_STEP_PLAYERS, player_buttons())
    return C_PLAYERS


async def _show_review(update, context, via_query):
    n = context.user_data["new"]
    hh, mm = n["time"]
    epoch = H.to_epoch(n["date"], hh, mm)
    n["starts_at"] = epoch
    text = M.CREATE_REVIEW.format(
        when=H.fmt_when(epoch), venue=n["venue"], capacity=n["capacity"]
    )
    if via_query:
        await update.callback_query.message.reply_text(
            text, reply_markup=review_buttons()
        )
    else:
        await reply(update, context, text, review_buttons())
    return C_REVIEW


async def create_players_btn(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data["new"]["capacity"] = int(q.data[3:])
    await q.edit_message_reply_markup(None)
    return await _show_review(update, context, True)


async def create_players_txt(update, context):
    raw = update.effective_message.text.strip()
    try:
        n = int(raw)
        if not 2 <= n <= 40:
            raise ValueError
    except ValueError:
        await reply(update, context, M.BAD_NUMBER.format(raw=raw[:20]),
                    player_buttons(), ok=False)
        return C_PLAYERS
    context.user_data["new"]["capacity"] = n
    return await _show_review(update, context, False)


async def create_confirm(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_reply_markup(None)

    n = context.user_data.pop("new", None)
    if not n:
        return ConversationHandler.END

    eid = db.next_event_id()
    db.create_event(
        eid, update.effective_user.id, n["starts_at"],
        config.DEFAULT_DURATION_MIN, n["venue"], n["capacity"],
    )
    ev = db.get_event(eid)

    sent = await to_group(
        context,
        M.ANNOUNCE_NEW.format(
            eid=eid, when=H.fmt_when(ev["starts_at"]), venue=ev["venue"],
            capacity=ev["capacity"], host=db.user_label(update.effective_user.id),
        ),
        kb([[("I'm in", f"ply:{eid}"), ("Details", f"shw:{eid}")]]),
    )
    if sent:
        db.set_announce_message(eid, sent.chat_id, sent.message_id)
        await q.message.reply_text(M.CREATE_DONE.format(eid=eid))
    else:
        await q.message.reply_text(M.CREATE_DONE_NO_GROUP.format(eid=eid))
    return ConversationHandler.END


async def create_restart(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_reply_markup(None)
    context.user_data["new"] = {}
    await q.message.reply_text(M.CREATE_RESTART)
    await q.message.reply_text(M.CREATE_STEP_DATE, reply_markup=date_buttons())
    return C_DATE


async def create_abort(update, context):
    context.user_data.pop("new", None)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_reply_markup(None)
        await update.callback_query.message.reply_text(M.CREATE_CANCELLED)
    else:
        await reply(update, context, M.CREATE_CANCELLED)
    return ConversationHandler.END


# ================================================================= lists ====

async def cmd_events(update, context):
    register(update)
    evs = db.upcoming_events()
    if not evs:
        await reply(update, context, M.NO_EVENTS)
        return
    body = "\n\n".join(H.event_line(e) for e in evs)
    await reply(update, context, "\U0001F3F8 Upcoming sessions\n\n" + body)


async def cmd_open(update, context):
    register(update)
    evs = [e for e in db.upcoming_events() if db.seats_free(e) > 0]
    if not evs:
        await reply(update, context, M.NO_OPEN_EVENTS)
        return
    body = "\n\n".join(H.event_line(e) for e in evs)
    rows = [[(f"Join {e['id']}", f"ply:{e['id']}")] for e in evs[:6]]
    await reply(update, context,
                "\U0001F3F8 Sessions with spots\n\n" + body, kb(rows))


async def cmd_show(update, context):
    register(update)
    ev = await resolve_event(update, context, context.args, "show")
    if ev is None:
        return
    await _show_event(update, context, ev)


async def _show_event(update, context, ev):
    rows = []
    uid = update.effective_user.id
    mine = db.get_signup(ev["id"], uid)
    if ev["status"] == "live" and ev["starts_at"] > time.time():
        if mine:
            rows.append([("Change guests", f"cg:{ev['id']}"),
                         ("Back out", f"unp:{ev['id']}")])
        else:
            rows.append([("Sign me up", f"ply:{ev['id']}")])
        rows.append([("Calendar file", f"ics:{ev['id']}")])
    await reply(update, context, H.event_detail(ev), kb(rows) if rows else None)


async def cmd_mysessions(update, context):
    register(update)
    rows = db.sessions_for(update.effective_user.id)
    if not rows:
        await reply(update, context, M.NO_SESSIONS_YOU)
        return
    out = []
    for r in rows:
        tag = "waitlist" if r["sstatus"] == "wait" else "playing"
        g = H.guest_bit(r["confirmed_guests"])
        out.append(f"{r['id']} · {H.fmt_when(r['starts_at'])}\n"
                   f"   {r['venue']} · {tag}{g}")
    await reply(update, context, "\U0001F3F8 Your sessions\n\n" + "\n\n".join(out))


async def cmd_sessions(update, context):
    register(update)
    if not context.args:
        return await cmd_mysessions(update, context)
    handle = context.args[0]
    user = db.find_user_by_handle(handle)
    if user is None:
        await reply(update, context, M.ERR_NO_SUCH_USER.format(handle=handle),
                    ok=False)
        return
    rows = db.sessions_for(user["tg_id"])
    label = db.user_label(user)
    if not rows:
        await reply(update, context, M.NO_SESSIONS_THEM.format(handle=label))
        return
    out = [f"{r['id']} · {H.fmt_when(r['starts_at'])}\n   {r['venue']}"
           for r in rows]
    await reply(update, context, f"\U0001F3F8 {label}'s sessions\n\n"
                + "\n\n".join(out))


async def cmd_stats(update, context):
    register(update)
    if context.args:
        handle = context.args[0]
        user = db.find_user_by_handle(handle)
        if user is None:
            await reply(update, context,
                        M.ERR_NO_SUCH_USER.format(handle=handle), ok=False)
            return
        hosted, played = db.stats_for(user["tg_id"])
        await reply(update, context,
                    f"\U0001F4CA {db.user_label(user)}\n"
                    f"Sessions hosted: {hosted}\n"
                    f"Sessions played: {played}")
        return

    hosts = db.host_leaderboard()
    players = db.player_leaderboard()
    if not hosts and not players:
        await reply(update, context,
                    "No completed sessions yet, so there's nothing to rank.")
        return
    medals = ["\U0001F947", "\U0001F948", "\U0001F949"]
    out = ["\U0001F4CA Leaderboards"]
    if hosts:
        out.append("\nTop hosts")
        for i, r in enumerate(hosts):
            m = medals[i] if i < 3 else f"{i + 1}."
            out.append(f"{m} {db.user_label(r['host_id'])} — {r['n']}")
    if players:
        out.append("\nTop players")
        for i, r in enumerate(players):
            m = medals[i] if i < 3 else f"{i + 1}."
            out.append(f"{m} {db.user_label(r['user_id'])} — {r['n']}")
    await reply(update, context, "\n".join(out))


async def cmd_csv(update, context):
    register(update)
    ev = await resolve_event(update, context, context.args, "csv")
    if ev is None:
        return
    await update.effective_message.reply_document(
        document=H.build_csv(ev), filename=f"{ev['id']}.csv", caption=M.CSV_CAPTION
    )


# ================================================================ signup ====

async def cmd_play(update, context):
    register(update)
    ev = await resolve_event(update, context, context.args, "play")
    if ev is None:
        return
    await _begin_play(update, context, ev)


async def _begin_play(update, context, ev):
    uid = update.effective_user.id
    eid = ev["id"]

    if ev["status"] == "cancelled":
        await reply(update, context, M.ERR_CANCELLED_EVENT.format(eid=eid),
                    kb([[("See all events", "ev:all")]]), ok=False)
        return
    if ev["starts_at"] <= time.time():
        await reply(update, context,
                    M.ERR_PASSED.format(eid=eid,
                                        when=H.fmt_date_only(ev["starts_at"])),
                    kb([[("See what's coming up", "ev:all")]]), ok=False)
        return

    existing = db.get_signup(eid, uid)
    if existing and existing["status"] == "in":
        await reply(
            update, context,
            M.ERR_ALREADY_IN.format(
                eid=eid, guest_bit=H.guest_bit(existing["confirmed_guests"])),
            kb([[("Change guests", f"cg:{eid}"), ("Back out", f"unp:{eid}")]]),
            ok=False,
        )
        return

    taken = db.seats_taken(eid)
    if taken >= ev["capacity"]:
        await reply(
            update, context,
            M.ERR_FULL.format(eid=eid, taken=taken, capacity=ev["capacity"]),
            kb([[("Join the waitlist", f"pg:{eid}:0")],
                [("See events with spots", "ev:open")]]),
            ok=False,
        )
        return

    await reply(
        update, context,
        M.PLAY_ASK_GUESTS.format(
            eid=eid, when=H.fmt_when(ev["starts_at"]), venue=ev["venue"],
            taken=taken, capacity=ev["capacity"]),
        kb([[("Just me", f"pg:{eid}:0"), ("+1", f"pg:{eid}:1"),
             ("+2", f"pg:{eid}:2")]]),
    )


async def cb_play_guests(update, context):
    """The agreed rule: take the seat, waitlist any guests that don't fit."""
    q = update.callback_query
    _, eid, gstr = q.data.split(":")
    guests = int(gstr)
    uid = q.from_user.id
    db.upsert_user(uid, q.from_user.username, q.from_user.first_name)

    ev = db.get_event(eid)
    if ev is None or ev["status"] != "live":
        await q.answer("That session is gone.", show_alert=True)
        return
    await q.answer()
    try:
        await q.edit_message_reply_markup(None)
    except BadRequest:
        pass

    taken = db.seats_taken(eid)
    free = ev["capacity"] - taken

    if free <= 0:
        db.add_signup(eid, uid, 0, guests, "wait")
        pos = db.waitlist_position(eid, uid)
        await q.message.reply_text(M.PLAY_WAITLISTED.format(
            eid=eid, pos=pos, when=H.fmt_when(ev["starts_at"]), venue=ev["venue"]))
        return

    seats_for_guests = min(guests, free - 1)
    waiting = guests - seats_for_guests
    db.add_signup(eid, uid, seats_for_guests, waiting, "in")

    new_taken = db.seats_taken(eid)
    await send_calendar(context, uid, ev, seats_for_guests)

    if waiting > 0:
        text = M.PLAY_PARTIAL.format(
            seats=free, plural="" if free == 1 else "s", waiting=waiting,
            eid=eid, taken=new_taken, capacity=ev["capacity"])
    else:
        full = "\nSession is now full." if new_taken >= ev["capacity"] else ""
        text = M.PLAY_OK.format(
            guest_bit=H.guest_bit(seats_for_guests), eid=eid,
            when=H.fmt_when(ev["starts_at"]), venue=ev["venue"],
            taken=new_taken, capacity=ev["capacity"], full_bit=full)

    await q.message.reply_text(text)
    await _refresh_announcement(context, eid)


async def cmd_unplay(update, context):
    register(update)
    ev = await resolve_event(update, context, context.args, "unplay")
    if ev is None:
        return
    await _do_unplay(update, context, ev)


async def _do_unplay(update, context, ev):
    uid = update.effective_user.id
    eid = ev["id"]
    if db.get_signup(eid, uid) is None:
        await reply(update, context, M.ERR_NOT_IN.format(eid=eid),
                    kb([[("Sign me up", f"ply:{eid}")]]), ok=False)
        return

    db.remove_signup(eid, uid)
    promoted = db.promote_from_waitlist(eid)
    taken = db.seats_taken(eid)

    lines = [M.UNPLAY_OK.format(eid=eid, taken=taken, capacity=ev["capacity"])]
    for puid, kind, count in promoted:
        who = db.user_label(puid)
        if kind == "person":
            lines.append(M.UNPLAY_PROMOTED.format(who=who))
            sign = db.get_signup(eid, puid)
            await send_calendar(context, puid, ev,
                                sign["confirmed_guests"] if sign else 0)
            await dm(context, puid, M.PROMOTED_DM.format(
                eid=eid, when=H.fmt_when(ev["starts_at"]), venue=ev["venue"]))
        else:
            await dm(context, puid, M.PROMOTED_GUESTS_DM.format(
                n=count, eid=eid, when=H.fmt_when(ev["starts_at"]),
                venue=ev["venue"]))

    await reply(update, context, "\n".join(lines))
    await _refresh_announcement(context, eid)


async def _refresh_announcement(context, eid):
    """Keep the group announcement's spot count current."""
    ev = db.get_event(eid)
    if ev is None or not ev["announce_chat"] or not ev["announce_msg"]:
        return
    taken = db.seats_taken(eid)
    text = M.ANNOUNCE_NEW.format(
        eid=eid, when=H.fmt_when(ev["starts_at"]), venue=ev["venue"],
        capacity=ev["capacity"], host=db.user_label(ev["host_id"]),
    ).replace(f"0/{ev['capacity']}", f"{taken}/{ev['capacity']}")
    try:
        await context.bot.edit_message_text(
            chat_id=ev["announce_chat"], message_id=ev["announce_msg"], text=text,
            reply_markup=kb([[("I'm in", f"ply:{eid}"), ("Details", f"shw:{eid}")]]),
        )
    except BadRequest:
        pass


# =============================================================== hosting ====

async def cmd_invite(update, context):
    register(update)
    raw = update.effective_message.text.partition(" ")[2]
    if not raw.strip():
        await reply(update, context,
                    "Use: /invite E001 | Name1, @handle2", ok=False)
        return
    left, _, right = raw.partition("|")
    ev = await resolve_event(update, context, left.split(), "invite")
    if ev is None:
        return
    if not H.can_manage(ev, update.effective_user.id):
        await reply(update, context, M.ERR_NOT_HOST.format(
            eid=ev["id"], host=db.user_label(ev["host_id"])), ok=False)
        return

    names = [n.strip() for n in right.split(",") if n.strip()]
    if not names:
        await reply(update, context,
                    "Add the people after a | , like: /invite E001 | Ann, @bob",
                    ok=False)
        return

    notes = []
    for name in names:
        if name.startswith("@"):
            user = db.find_user_by_handle(name)
            if user is None:
                notes.append(M.INVITE_NO_DM.format(handle=name))
                continue
            sent = await dm(context, user["tg_id"], M.INVITE_DM.format(
                host=db.user_label(update.effective_user.id), eid=ev["id"],
                when=H.fmt_when(ev["starts_at"]), venue=ev["venue"],
                taken=db.seats_taken(ev["id"]), capacity=ev["capacity"]),
                kb([[("I'm in", f"ply:{ev['id']}")]]))
            if not sent:
                notes.append(M.INVITE_NO_DM.format(handle=name))

    out = M.INVITE_SENT.format(n=len(names), eid=ev["id"], names=", ".join(names))
    if notes:
        out += "\n" + "\n".join(notes)
    await reply(update, context, out)


async def cmd_subhost(update, context):
    register(update)
    ev = await resolve_event(update, context, context.args, "subhost")
    if ev is None:
        return
    if ev["host_id"] != update.effective_user.id and not H.is_admin(
            update.effective_user.id):
        await reply(update, context, M.ERR_NOT_HOST.format(
            eid=ev["id"], host=db.user_label(ev["host_id"])), ok=False)
        return
    if len(context.args) < 2:
        await reply(update, context, "Use: /subhost E001 @handle", ok=False)
        return
    handle = context.args[1]
    user = db.find_user_by_handle(handle)
    if user is None:
        await reply(update, context, M.ERR_NO_SUCH_USER.format(handle=handle),
                    ok=False)
        return
    db.add_subhost(ev["id"], user["tg_id"])
    await dm(context, user["tg_id"], M.SUBHOST_DM.format(
        host=db.user_label(update.effective_user.id), eid=ev["id"]))
    await reply(update, context, M.SUBHOST_DONE.format(
        handle=db.user_label(user), eid=ev["id"]))


async def cmd_uninvite(update, context):
    register(update)
    ev = await resolve_event(update, context, context.args, "uninvite")
    if ev is None:
        return
    if not H.can_manage(ev, update.effective_user.id):
        await reply(update, context, M.ERR_NOT_HOST.format(
            eid=ev["id"], host=db.user_label(ev["host_id"])), ok=False)
        return
    if len(context.args) < 2:
        await reply(update, context, "Use: /uninvite E001 @handle", ok=False)
        return
    handle = context.args[1]
    user = db.find_user_by_handle(handle)
    if user is None:
        await reply(update, context, M.ERR_NO_SUCH_USER.format(handle=handle),
                    ok=False)
        return
    if db.get_signup(ev["id"], user["tg_id"]) is None:
        await reply(update, context, f"{db.user_label(user)} isn't in "
                                     f"{ev['id']}.", ok=False)
        return

    db.remove_signup(ev["id"], user["tg_id"])
    promoted = db.promote_from_waitlist(ev["id"])
    await dm(context, user["tg_id"], M.UNINVITE_DM.format(
        eid=ev["id"], when=H.fmt_when(ev["starts_at"]), venue=ev["venue"]))
    for puid, kind, count in promoted:
        if kind == "person":
            await send_calendar(context, puid, ev)
            await dm(context, puid, M.PROMOTED_DM.format(
                eid=ev["id"], when=H.fmt_when(ev["starts_at"]),
                venue=ev["venue"]))
        else:
            await dm(context, puid, M.PROMOTED_GUESTS_DM.format(
                n=count, eid=ev["id"], when=H.fmt_when(ev["starts_at"]),
                venue=ev["venue"]))

    await reply(update, context, M.UNINVITE_DONE.format(
        handle=db.user_label(user), eid=ev["id"],
        taken=db.seats_taken(ev["id"]), capacity=ev["capacity"]))
    await _refresh_announcement(context, ev["id"])


# ================================================================ modify ====

async def modify_start(update, context):
    register(update)
    # Private only, like /create. The flow asks for plain text (a venue name,
    # a date), and with Telegram's group privacy mode ON - which is the setting
    # we want - the bot never sees non-command text in a group.
    if update.effective_chat.type != ChatType.PRIVATE:
        eid = context.args[0].upper() if context.args else "E001"
        await reply(update, context,
                    M.ERR_PRIVATE_ONLY.format(cmd=f"/modify {eid}"),
                    dm_button(context), ok=False)
        return ConversationHandler.END
    ev = await resolve_event(update, context, context.args, "modify")
    if ev is None:
        return ConversationHandler.END
    if not H.can_manage(ev, update.effective_user.id):
        await reply(update, context, M.ERR_NOT_HOST.format(
            eid=ev["id"], host=db.user_label(ev["host_id"])), ok=False)
        return ConversationHandler.END
    if ev["status"] == "cancelled":
        await reply(update, context,
                    M.ERR_CANCELLED_EVENT.format(eid=ev["id"]), ok=False)
        return ConversationHandler.END

    context.user_data["mod_eid"] = ev["id"]
    await reply(update, context,
                H.event_detail(ev) + "\n\n" + M.MODIFY_MENU.format(eid=ev["id"]),
                kb([[("Date", "md:date"), ("Time", "md:time")],
                    [("Venue", "md:venue"), ("Players", "md:players")],
                    [("Done", "md:done")]]))
    return M_MENU


async def modify_pick(update, context):
    q = update.callback_query
    await q.answer()
    what = q.data[3:]
    await q.edit_message_reply_markup(None)
    if what == "done":
        context.user_data.pop("mod_eid", None)
        await q.message.reply_text("Nothing else changed.")
        return ConversationHandler.END
    prompts = {
        "date": (M.CREATE_STEP_DATE, date_buttons(), M_DATE),
        "time": (M.CREATE_STEP_TIME, time_buttons(), M_TIME),
        "venue": (M.CREATE_STEP_VENUE_NONE, None, M_VENUE),
        "players": (M.CREATE_STEP_PLAYERS, player_buttons(), M_PLAYERS),
    }
    text, markup, state = prompts[what]
    await q.message.reply_text(text, reply_markup=markup)
    return state


async def _apply_modify(update, context, changes, **fields):
    eid = context.user_data.get("mod_eid")
    if not eid:
        return ConversationHandler.END
    db.update_event(eid, **fields)
    ev = db.get_event(eid)

    people = db.everyone_on_event(eid)
    for s in people:
        await dm(context, s["user_id"], M.MODIFY_DM.format(
            eid=eid, changes=changes, when=H.fmt_when(ev["starts_at"]),
            venue=ev["venue"]))
        await send_calendar(context, s["user_id"], ev, s["confirmed_guests"])

    promoted = db.promote_from_waitlist(eid)
    for puid, kind, count in promoted:
        await dm(context, puid, M.PROMOTED_DM.format(
            eid=eid, when=H.fmt_when(ev["starts_at"]), venue=ev["venue"])
            if kind == "person" else M.PROMOTED_GUESTS_DM.format(
                n=count, eid=eid, when=H.fmt_when(ev["starts_at"]),
                venue=ev["venue"]))

    context.user_data.pop("mod_eid", None)
    await reply(update, context, M.MODIFY_DONE.format(eid=eid, n=len(people)))
    await _refresh_announcement(context, eid)
    return ConversationHandler.END


async def modify_date(update, context):
    eid = context.user_data.get("mod_eid")
    ev = db.get_event(eid)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_reply_markup(None)
        d = _date.fromisoformat(update.callback_query.data[3:])
    else:
        raw = update.effective_message.text
        d = H.parse_date(raw)
        if d is None:
            await reply(update, context, M.BAD_DATE.format(raw=raw[:40]),
                        date_buttons(), ok=False)
            return M_DATE
        if d < H.now_local().date():
            await reply(update, context, M.DATE_IN_PAST, date_buttons(), ok=False)
            return M_DATE
    old = H.local_dt(ev["starts_at"])
    return await _apply_modify(update, context, "New date.",
                               starts_at=H.to_epoch(d, old.hour, old.minute))


async def modify_time(update, context):
    eid = context.user_data.get("mod_eid")
    ev = db.get_event(eid)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_reply_markup(None)
        hh, mm = update.callback_query.data[3:].split(":")
        t = (int(hh), int(mm))
    else:
        raw = update.effective_message.text
        t = H.parse_time(raw)
        if t is None:
            await reply(update, context, M.BAD_TIME.format(raw=raw[:40]),
                        time_buttons(), ok=False)
            return M_TIME
    old = H.local_dt(ev["starts_at"]).date()
    return await _apply_modify(update, context, "New time.",
                               starts_at=H.to_epoch(old, t[0], t[1]))


async def modify_venue(update, context):
    name = update.effective_message.text.strip()[:80]
    if not name:
        return M_VENUE
    return await _apply_modify(update, context, f"New venue: {name}.", venue=name)


async def modify_players(update, context):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_reply_markup(None)
        n = int(update.callback_query.data[3:])
    else:
        raw = update.effective_message.text.strip()
        try:
            n = int(raw)
            if not 2 <= n <= 40:
                raise ValueError
        except ValueError:
            await reply(update, context, M.BAD_NUMBER.format(raw=raw[:20]),
                        player_buttons(), ok=False)
            return M_PLAYERS
    return await _apply_modify(update, context, f"Now {n} players.", capacity=n)


# ================================================================ cancel ====

async def cmd_cancel_event(update, context):
    register(update)
    ev = await resolve_event(update, context, context.args, "cancel")
    if ev is None:
        return
    if not H.can_manage(ev, update.effective_user.id):
        await reply(update, context, M.ERR_NOT_HOST.format(
            eid=ev["id"], host=db.user_label(ev["host_id"])), ok=False)
        return
    if ev["status"] == "cancelled":
        await reply(update, context,
                    M.ERR_CANCELLED_EVENT.format(eid=ev["id"]), ok=False)
        return

    reason = " ".join(context.args[1:]).strip() or "no reason given"
    context.user_data["cancel_reason"] = reason
    n = len(db.everyone_on_event(ev["id"]))
    await reply(update, context, M.CANCEL_CONFIRM.format(
        eid=ev["id"], when=H.fmt_when(ev["starts_at"]), venue=ev["venue"],
        n=n, reason=reason),
        kb([[("Yes, cancel it", f"cxy:{ev['id']}"), ("No, keep it", "cxn")]]))


async def cb_cancel_yes(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_reply_markup(None)
    eid = q.data.split(":")[1]
    ev = db.get_event(eid)
    if ev is None or ev["status"] == "cancelled":
        await q.message.reply_text(M.ERR_NO_EVENT.format(eid=eid))
        return
    if not H.can_manage(ev, q.from_user.id):
        await q.message.reply_text(M.ERR_NOT_HOST.format(
            eid=eid, host=db.user_label(ev["host_id"])))
        return

    reason = context.user_data.pop("cancel_reason", "no reason given")
    people = db.everyone_on_event(eid)
    db.cancel_event(eid, reason)

    for s in people:
        await dm(context, s["user_id"], M.CANCEL_DM.format(
            eid=eid, when=H.fmt_when(ev["starts_at"]), venue=ev["venue"],
            reason=reason), kb([[("See other events", "ev:all")]]))

    await q.message.reply_text(M.CANCEL_DONE.format(eid=eid, n=len(people)))
    await to_group(context, M.CANCEL_DM.format(
        eid=eid, when=H.fmt_when(ev["starts_at"]), venue=ev["venue"],
        reason=reason))


async def cb_cancel_no(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_reply_markup(None)
    context.user_data.pop("cancel_reason", None)
    await q.message.reply_text(M.CANCEL_ABORTED)


# ================================================================= admin ====

async def cmd_removeevent(update, context):
    register(update)
    if not H.is_admin(update.effective_user.id):
        await reply(update, context, M.ERR_ADMIN_ONLY, ok=False)
        return
    ev = await resolve_event(update, context, context.args, "removeevent")
    if ev is None:
        return
    n = len(db.everyone_on_event(ev["id"]))
    await reply(update, context, M.REMOVE_CONFIRM.format(
        eid=ev["id"], when=H.fmt_when(ev["starts_at"]), venue=ev["venue"], n=n),
        kb([[("Yes, remove it", f"rmy:{ev['id']}"), ("No, keep it", "rmn")]]))


async def cb_remove_yes(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_reply_markup(None)
    if not H.is_admin(q.from_user.id):
        await q.message.reply_text(M.ERR_ADMIN_ONLY)
        return
    eid = q.data.split(":")[1]
    db.remove_event(eid)
    await q.message.reply_text(M.REMOVE_DONE.format(eid=eid))


async def cb_remove_no(update, context):
    q = update.callback_query
    await q.answer()
    await q.edit_message_reply_markup(None)
    await q.message.reply_text(M.REMOVE_ABORTED)


async def cmd_clearevents(update, context):
    register(update)
    if not H.is_admin(update.effective_user.id):
        await reply(update, context, M.ERR_ADMIN_ONLY, ok=False)
        return
    if not context.args or context.args[0].upper() != "CONFIRM":
        await reply(update, context, "Use: /clearevents CONFIRM", ok=False)
        return
    events, signups = db.count_all()
    if events == 0 and signups == 0:
        await reply(update, context, M.CLEAR_EMPTY)
        return
    context.user_data["await_word"] = ("DELETE", "clear")
    await reply(update, context,
                M.CLEAR_CONFIRM.format(events=events, signups=signups))


async def cmd_resetstats(update, context):
    register(update)
    if not H.is_admin(update.effective_user.id):
        await reply(update, context, M.ERR_ADMIN_ONLY, ok=False)
        return
    if not context.args or context.args[0].upper() != "CONFIRM":
        await reply(update, context, "Use: /resetstats CONFIRM", ok=False)
        return
    players, hosts = db.stats_population()
    context.user_data["await_word"] = ("RESET", "stats")
    await reply(update, context,
                M.RESET_CONFIRM.format(players=players, hosts=hosts))


async def on_confirm_word(update, context):
    """Second gate for the two wipe commands: the typed word must match."""
    pending = context.user_data.pop("await_word", None)
    if not pending:
        return
    word, action = pending
    typed = (update.effective_message.text or "").strip().upper()

    if typed != word:
        await reply(update, context,
                    M.CLEAR_ABORTED if action == "clear" else M.RESET_ABORTED)
        return
    if not H.is_admin(update.effective_user.id):
        await reply(update, context, M.ERR_ADMIN_ONLY, ok=False)
        return

    if action == "clear":
        events, signups = db.count_all()
        db.wipe_all_events()
        await reply(update, context,
                    M.CLEAR_DONE.format(events=events, signups=signups))
    else:
        players, hosts = db.stats_population()
        db.reset_stats()
        await reply(update, context,
                    M.RESET_DONE.format(players=players, hosts=hosts))


# ============================================================= callbacks ====

async def cb_router(update, context):
    """Buttons that aren't part of a conversation."""
    q = update.callback_query
    data = q.data
    db.upsert_user(q.from_user.id, q.from_user.username, q.from_user.first_name)

    if data == "ev:all":
        await q.answer()
        return await cmd_events(update, context)
    if data == "ev:open":
        await q.answer()
        return await cmd_open(update, context)
    if data == "help":
        await q.answer()
        return await cmd_help(update, context)

    kind, _, eid = data.partition(":")

    if kind == "ply":
        await q.answer()
        ev = db.get_event(eid)
        if ev is None:
            return await q.message.reply_text(M.ERR_NO_EVENT.format(eid=eid))
        return await _begin_play(update, context, ev)

    if kind == "cg":
        await q.answer()
        ev = db.get_event(eid)
        if ev is None:
            return await q.message.reply_text(M.ERR_NO_EVENT.format(eid=eid))
        taken = db.seats_taken(eid)
        return await q.message.reply_text(
            M.PLAY_ASK_GUESTS.format(
                eid=eid, when=H.fmt_when(ev["starts_at"]), venue=ev["venue"],
                taken=taken, capacity=ev["capacity"]),
            reply_markup=kb([[("Just me", f"pg:{eid}:0"), ("+1", f"pg:{eid}:1"),
                              ("+2", f"pg:{eid}:2")]]))

    if kind == "unp":
        await q.answer()
        ev = db.get_event(eid)
        if ev is None:
            return await q.message.reply_text(M.ERR_NO_EVENT.format(eid=eid))
        return await _do_unplay(update, context, ev)

    if kind == "shw":
        await q.answer()
        ev = db.get_event(eid)
        if ev is None:
            return await q.message.reply_text(M.ERR_NO_EVENT.format(eid=eid))
        return await _show_event(update, context, ev)

    if kind == "ics":
        await q.answer()
        ev = db.get_event(eid)
        if ev is None:
            return
        sign = db.get_signup(eid, q.from_user.id)
        ok = await send_calendar(context, q.from_user.id, ev,
                                 sign["confirmed_guests"] if sign else 0)
        if not ok:
            await q.message.reply_text(M.ERR_NO_DM,
                                       reply_markup=dm_button(context))
        return

    await q.answer()


# ============================================================= reminders ====

async def reminder_tick(context):
    now = int(time.time())
    soon_window = int(config.REMINDER_HOURS_BEFORE * 3600)

    for ev in db.upcoming_events():
        eid = ev["id"]
        start = ev["starts_at"]

        # 1) Evening before
        key_day = f"rem:{eid}:day"
        if not db.get_meta(key_day):
            ev_dt = H.local_dt(start)
            nl = H.now_local()
            day_before = (ev_dt.date() - nl.date()).days
            if day_before == 1 and nl.hour >= config.REMINDER_EVENING_HOUR:
                db.set_meta(key_day, now)
                for s in db.confirmed_signups(eid):
                    await dm(context, s["user_id"], M.REMIND_DAY_BEFORE.format(
                        eid=eid, when=H.fmt_when(start), venue=ev["venue"],
                        guest_bit=H.guest_bit(s["confirmed_guests"])),
                        kb([[("Back out", f"unp:{eid}")]]))
                free = db.seats_free(ev)
                if free > 0:
                    await to_group(context, M.REMIND_GROUP_OPEN.format(
                        eid=eid, free=free, when=H.fmt_when(start),
                        venue=ev["venue"]),
                        kb([[("I'm in", f"ply:{eid}")]]))

        # 2) Shortly before
        key_soon = f"rem:{eid}:soon"
        if not db.get_meta(key_soon) and 0 < start - now <= soon_window:
            db.set_meta(key_soon, now)
            for s in db.confirmed_signups(eid):
                await dm(context, s["user_id"], M.REMIND_SOON.format(
                    eid=eid, time=H.fmt_time(start), venue=ev["venue"]))


async def heartbeat(context):
    db.set_meta("last_seen", int(time.time()))


async def startup_notice(context):
    """Say hello only after a real gap, so redeploys don't spam the group."""
    if not config.ANNOUNCE_RESTARTS:
        return
    last = db.get_meta("last_seen")
    gap_min = (time.time() - int(last)) / 60 if last else 0
    if MISSED["count"] > 0:
        await to_group(context, M.OFFLINE_BACK.format(count=MISSED["count"]))
    elif last and gap_min >= config.OFFLINE_THRESHOLD_MIN:
        await to_group(context, M.OFFLINE_BACK_QUIET)


# =========================================================== plumbing ======

async def mark_late(update, context):
    """Flag updates that were sitting in Telegram's queue while we were down."""
    msg = update.effective_message
    if msg and msg.date and msg.date.timestamp() < BOT_START - 5:
        MISSED["count"] += 1
        if context.user_data is not None:
            context.user_data["late_when"] = H.fmt_when(int(msg.date.timestamp()))


async def unknown_command(update, context):
    register(update)
    await reply(update, context, M.ERR_UNKNOWN_CMD,
                kb([[("Show me what you can do", "help")]]), ok=False)


async def on_error(update, context):
    log.exception("Handler error", exc_info=context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text(
                "Something went wrong on my end, sorry. "
                "Try again, and tell the admin if it keeps happening."
            )
    except Exception:
        pass


async def post_init(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Register for DM reminders"),
        BotCommand("create", "Create a new session"),
        BotCommand("events", "All upcoming sessions"),
        BotCommand("open", "Sessions with spots free"),
        BotCommand("show", "Show a session's details"),
        BotCommand("play", "Sign up for a session"),
        BotCommand("unplay", "Back out of a session"),
        BotCommand("mysessions", "What you're signed up for"),
        BotCommand("stats", "Leaderboards"),
        BotCommand("help", "All commands"),
    ])


async def post_stop(app):
    if config.ANNOUNCE_RESTARTS and config.GROUP_CHAT_ID:
        try:
            await app.bot.send_message(config.GROUP_CHAT_ID, M.OFFLINE_SHUTDOWN)
        except Exception:
            pass


def main():
    problems = config.validate()
    if any("BOT_TOKEN" in p for p in problems):
        for p in problems:
            print("CONFIG PROBLEM: " + p)
        # Diagnostic: which of our settings actually reached the process?
        # Names and set/unset only - never values, so this is safe in logs.
        import os
        print("\n--- What this container can actually see ---")
        for key in ("BOT_TOKEN", "ADMIN_IDS", "TIMEZONE", "DB_PATH",
                    "GROUP_CHAT_ID"):
            raw = os.environ.get(key)
            if raw is None:
                state = "NOT SET"
            elif raw.strip() == "":
                state = "SET BUT EMPTY"
            else:
                state = f"set, {len(raw)} chars"
            print(f"  {key:<15} {state}")
        railway = sorted(k for k in os.environ if k.startswith("RAILWAY_"))
        print(f"  Running on Railway: {'yes' if railway else 'no'}")
        near = sorted(k for k in os.environ
                      if any(w in k.upper() for w in ("TOKEN", "ADMIN", "BOT")))
        if near:
            print(f"  Similar names present: {', '.join(near)}")
        print("  config.json present:", os.path.exists("config.json"))
        print("--- end diagnostic ---\n")
        raise SystemExit(1)
    for p in problems:
        log.warning(p)

    db.init_db()
    if not config.GROUP_CHAT_ID:
        saved = db.get_meta("group_chat_id")
        if saved:
            config.GROUP_CHAT_ID = int(saved)

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )

    app.add_handler(TypeHandler(Update, mark_late), group=-1)

    create_conv = ConversationHandler(
        entry_points=[CommandHandler("create", create_start)],
        states={
            C_DATE: [
                CallbackQueryHandler(create_date_btn, pattern=r"^cd:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_date_txt),
            ],
            C_TIME: [
                CallbackQueryHandler(create_time_btn, pattern=r"^ct:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_time_txt),
            ],
            C_VENUE: [
                CallbackQueryHandler(create_venue_btn, pattern=r"^cv:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_venue_txt),
            ],
            C_PLAYERS: [
                CallbackQueryHandler(create_players_btn, pattern=r"^cp:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, create_players_txt),
            ],
            C_REVIEW: [
                CallbackQueryHandler(create_confirm, pattern=r"^cok$"),
                CallbackQueryHandler(create_restart, pattern=r"^crs$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(create_abort, pattern=r"^ccl$"),
            CommandHandler("cancel", create_abort),
        ],
        per_message=False,
        conversation_timeout=600,
    )

    modify_conv = ConversationHandler(
        entry_points=[CommandHandler("modify", modify_start)],
        states={
            M_MENU: [CallbackQueryHandler(modify_pick, pattern=r"^md:")],
            M_DATE: [
                CallbackQueryHandler(modify_date, pattern=r"^cd:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, modify_date),
            ],
            M_TIME: [
                CallbackQueryHandler(modify_time, pattern=r"^ct:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, modify_time),
            ],
            M_VENUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, modify_venue)
            ],
            M_PLAYERS: [
                CallbackQueryHandler(modify_players, pattern=r"^cp:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, modify_players),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(create_abort, pattern=r"^ccl$"),
            CommandHandler("cancel", create_abort),
        ],
        per_message=False,
        conversation_timeout=600,
    )

    app.add_handler(create_conv)
    app.add_handler(modify_conv)

    for name, fn in [
        ("start", cmd_start), ("help", cmd_help), ("whoami", cmd_whoami),
        ("sethere", cmd_sethere), ("events", cmd_events), ("open", cmd_open),
        ("show", cmd_show), ("play", cmd_play), ("unplay", cmd_unplay),
        ("mysessions", cmd_mysessions), ("sessions", cmd_sessions),
        ("stats", cmd_stats), ("csv", cmd_csv), ("invite", cmd_invite),
        ("subhost", cmd_subhost), ("uninvite", cmd_uninvite),
        ("cancel", cmd_cancel_event), ("removeevent", cmd_removeevent),
        ("clearevents", cmd_clearevents), ("resetstats", cmd_resetstats),
    ]:
        app.add_handler(CommandHandler(name, fn))

    app.add_handler(CallbackQueryHandler(cb_play_guests, pattern=r"^pg:"))
    app.add_handler(CallbackQueryHandler(cb_cancel_yes, pattern=r"^cxy:"))
    app.add_handler(CallbackQueryHandler(cb_cancel_no, pattern=r"^cxn$"))
    app.add_handler(CallbackQueryHandler(cb_remove_yes, pattern=r"^rmy:"))
    app.add_handler(CallbackQueryHandler(cb_remove_no, pattern=r"^rmn$"))
    app.add_handler(CallbackQueryHandler(cb_router))

    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    app.add_handler(
        MessageHandler(filters.TEXT & filters.ChatType.PRIVATE, on_confirm_word)
    )
    app.add_error_handler(on_error)

    jq = app.job_queue
    jq.run_repeating(reminder_tick, interval=300, first=20)
    jq.run_repeating(heartbeat, interval=60, first=5)
    jq.run_once(startup_notice, when=10)

    log.info("BBBot starting (timezone %s, %d admin(s))",
             config.TIMEZONE, len(config.ADMIN_IDS))
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
