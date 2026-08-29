# BBBot — setup, step by step

Two stages. **Part A** gets the bot running on your PC so you can play with it
privately. **Part B** puts it on Railway so it runs 24/7 without your PC.

Do Part A first. It takes about 10 minutes and means you find any problems
before GitHub and Railway are involved.

---

## Part A — get it running locally

### 1. Create the bot and get a token

1. Open Telegram, search for **@BotFather**, press Start.
2. Send `/newbot`.
3. Give it a display name (e.g. `Badminton Bot`) — this is what people see.
4. Give it a username. It must end in `bot`, e.g. `sg_badminton_bot`.
5. BotFather replies with a token that looks like
   `8123456789:AAF-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.

**Treat that token like a password.** Anyone with it controls your bot.
It must never go into GitHub — `.gitignore` is already set up to prevent that.

**Leave privacy mode alone.** BotFather defaults it to *Enabled*, which is what
you want. Enabled means the bot only receives messages that start with `/` or
that @mention it — so every command still works in the group, but your group's
ordinary chatter never reaches the bot at all.

`/create` and `/modify` are private-chat only for exactly this reason: they ask
for plain text (a date, a venue name), which the bot cannot see in a group with
privacy on. Everything else works fine in the group.

### 2. Create your config file

In the `BBBot` folder, copy `config.example.json` to `config.json`, then open it
and paste your token in:

```bash
cp config.example.json config.json
```

Set `bot_token`. Leave the rest for now. `config.json` is gitignored, so it
will never be pushed anywhere.

### 3. Install the dependencies

```bash
py -m pip install -r requirements.txt
```

### 4. Check the logic is sound

```bash
py selftest.py
```

You should see `All checks passed.` This tests the seat maths, the waitlist
promotion rule, date and time parsing, and the calendar files — no Telegram
connection needed.

### 5. Start the bot

Double-click `run.bat`, or:

```bash
py bot.py
```

It will warn that `ADMIN_IDS` is empty. That's expected — fix it next.

### 6. Make yourself the admin

In Telegram, open a private chat with your bot and send:

```
/whoami
```

It replies with your numeric Telegram ID. Stop the bot (Ctrl+C in the window),
put that number into `config.json`:

```json
"admin_ids": [123456789]
```

Start it again. Admin commands are now unlocked for you.

### 7. Add it to your badminton group

1. Open your group chat → group name → **Add members** → search your bot's
   username → add it.
2. Make it an **admin** of the group. Without this it often cannot post
   announcements in larger groups.
3. In the group, send `/sethere`.

The bot replies with the chat ID and confirms it will announce sessions there.
It saves this to its database, and also shows you the ID so you can set it as a
Railway variable later.

### 8. Try the whole flow

In a **private** chat with the bot:

```
/start
/create
```

Walk through the five steps, confirm at the review screen, and check the
announcement appears in your group. Then tap **I'm in**, choose **+1**, and
confirm you receive the `.ics` calendar file. Tap it — it should open your phone's
calendar with an Add button.

Then in the group, pin this message so newcomers know what to do:

> A note on me: I'm online around the clock, but I do get restarted for updates
> now and then. If I go quiet for a minute, your command isn't lost — I'll pick
> it up as soon as I'm back.

---

## Part B — put it on GitHub and Railway

### 9. Push to GitHub

Create a **private** repository. There are no secrets in the code, but a private
repo is the right default for something with your group's names in its database.

```bash
git init
git add .
git commit -m "BBBot: badminton session bot"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/BBBot.git
git push -u origin main
```

Before pushing, confirm your token is not included:

```bash
git check-ignore -v config.json
```

It must print a line naming `.gitignore` — that means the file is ignored and
will not be pushed. If it prints nothing, **stop**: your token would go to
GitHub. Fix `.gitignore` first.

### 10. Deploy on Railway

1. Go to railway.app and sign in with GitHub.
2. **New Project** → **Deploy from GitHub repo** → pick `BBBot`.
3. Railway detects Python from `requirements.txt` and uses the start command in
   `railway.json`. The first build takes a couple of minutes.

It will start, then crash — it has no token yet. That's expected.

### 11. Set the environment variables

In your Railway service → **Variables** → add these:

| Variable | Value | Notes |
|---|---|---|
| `BOT_TOKEN` | your BotFather token | required |
| `ADMIN_IDS` | your numeric ID | comma-separated for several admins |
| `GROUP_CHAT_ID` | from `/sethere` | usually starts with `-100` |
| `TIMEZONE` | `Asia/Singapore` | change if you're elsewhere |
| `DB_PATH` | `/data/bbbot.db` | **see the next step — this matters** |
| `REMINDER_HOURS_BEFORE` | `1` | second reminder, hours before start |
| `REMINDER_EVENING_BEFORE_HOUR` | `18` | first reminder, hour of the day before |
| `ANNOUNCE_RESTARTS` | `false` | keep false, or every deploy posts to the group |

Environment variables always override `config.json`, so nothing local leaks
into production and you never ship a secret.

### 12. Add a Volume — do not skip this

**Railway containers have a temporary filesystem.** Without a volume, every
redeploy and every restart wipes `bbbot.db` — all your events, signups and
stats, gone silently. You will not get an error; the bot will simply start
empty one day.

1. In your Railway service → **Settings** → **Volumes** → **New Volume**.
2. Mount path: `/data`
3. Confirm `DB_PATH` is set to `/data/bbbot.db` (step 11).
4. Redeploy.

Nothing else in this guide can lose your data. This step can.

### 13. Verify it's live

- Railway → **Deployments** → the log should end with
  `BBBot starting (timezone Asia/Singapore, 1 admin(s))` and no traceback after it.
- In Telegram, send `/events` — you should get a reply within a second or two.
- **Stop the local copy on your PC.** Two copies polling the same token fight
  over updates and each will drop roughly half of them. Only ever run one.

---

## Running one copy at a time

This is the single most common way to break it. Telegram lets only one process
long-poll a token at a time. If you want to work on the bot locally again:

1. Railway → your service → **Settings** → **Remove** the deployment, or pause
   the service.
2. Do your local work.
3. Push, redeploy, and stop the local copy.

If both run at once, symptoms look like the bot randomly ignoring commands.

---

## Changing the wording

Every message the bot sends lives in `messages.py`, and nothing else needs
touching. Edit the text, commit, push — Railway redeploys automatically.

## Changing the reminder timings

Set `REMINDER_EVENING_BEFORE_HOUR` (default 18, meaning 6pm the day before) and
`REMINDER_HOURS_BEFORE` (default 1) in Railway's Variables. No code change.

## Backing up

Your whole database is one file, `/data/bbbot.db` on the volume. Railway's
dashboard lets you browse and download volume contents directly — that is the
simplest route, and worth doing before any big change.

The Railway CLI can also open a shell into the running container (`railway ssh`),
but check their current docs for the exact command, as the CLI changes. Note
that `railway run` does *not* do this — it runs a command on your own machine
with the service's variables injected, so it will not see the volume.

---

## Command reference

**Everyone**

| Command | What it does |
|---|---|
| `/start` | Register for DM reminders |
| `/create` | Create a session, step by step |
| `/events` | All upcoming sessions |
| `/open` | Only sessions with spots free |
| `/show E001` | Full details including who's playing |
| `/play E001` | Sign up, then pick guests |
| `/unplay E001` | Back out |
| `/mysessions` | What you're signed up for |
| `/sessions @handle` | Someone else's sessions |
| `/stats` | Host and player leaderboards |
| `/stats @handle` | One person's stats |
| `/csv E001` | Calendar file as CSV (desktop Google Calendar) |
| `/whoami` | Your Telegram ID |

**Host and sub-host**

| Command | What it does |
|---|---|
| `/add E001 \| Ann, @bob` | Put players straight in, no acceptance needed |
| `/invite E001 \| @bob` | Ask them first - they must tap "I'm in" |
| `/subhost E001 @handle` | Let someone else manage it |
| `/uninvite E001 @handle` | Remove a player |
| `/modify E001` | Edit date, time, length, venue or size |
| `/cancel E001 reason` | Call it off and notify everyone |

**Admin**

| Command | What it does |
|---|---|
| `/sethere` | Set the announcement group |
| `/removeevent E001` | Delete an event silently |
| `/clearevents CONFIRM` | Wipe everything (then type `DELETE`) |
| `/resetstats CONFIRM` | Zero the leaderboards (then type `RESET`) |

---

## How a few things behave

**Guests that don't fit.** If you ask for +2 but only one spot is left, you take
the spot and your two guests go on the waitlist. They're promoted automatically,
in order, the moment anyone drops out.

**The waitlist** is one queue ordered by when people joined. Waiting guests and
waiting people are promoted in that same order, so nobody jumps ahead.

**`/resetstats` does not delete anything.** It moves a marker so only sessions
from that point on are counted. Your event history stays intact, which means an
accidental reset costs you leaderboard numbers, not data.

**Session length is per-session.** `/create` asks how long the court is booked
for - 1 hour, 1.5, 2 or 3, or type anything from 30 minutes to 6 hours. This
sets the calendar file's finish time, so a 1-hour game no longer blocks out two
hours in everyone's diary. Change it later with `/modify` -> Length.

**`/add` versus `/invite`.** `/add` puts people straight into the session -
use it when you've already agreed it in person. `/invite` asks them and waits
for them to tap "I'm in". Only `/add` accepts plain names for people who aren't
on Telegram; they hold a real seat, show in `/show`, and you remove them with
`/uninvite E001 Ann`.

**Bare times mean evening.** Typing `8` gets you 8:00pm, because badminton is an
after-work game. Type `8am` or `08:00` if you mean the morning — and the review
screen always shows the interpreted time before anything is created.
