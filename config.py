# -*- coding: utf-8 -*-
"""Configuration loader.

Environment variables always win. That means:
  - locally you can use config.json (gitignored, never pushed)
  - on Railway you set variables in the dashboard and ship no secrets at all

Required: BOT_TOKEN. Everything else has a sensible default.
"""

import json
import os
from pathlib import Path

_JSON_PATH = Path(__file__).with_name("config.json")


def _load_json():
    if _JSON_PATH.exists():
        try:
            return json.loads(_JSON_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"config.json is not valid JSON ({exc}). Fix it or delete it."
            ) from exc
    return {}


_JSON = _load_json()


def _get(env_key, json_key, default=None, cast=str):
    raw = os.environ.get(env_key)
    if raw is None or raw == "":
        val = _JSON.get(json_key, default)
        return val
    try:
        if cast is bool:
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return cast(raw)
    except (TypeError, ValueError):
        raise SystemExit(f"{env_key} is set to '{raw}', which isn't a valid value.")


def _get_int_list(env_key, json_key):
    raw = os.environ.get(env_key)
    if raw:
        out = []
        for part in raw.replace(";", ",").split(","):
            part = part.strip()
            if part:
                try:
                    out.append(int(part))
                except ValueError:
                    raise SystemExit(
                        f"{env_key} should be comma-separated numbers, got '{part}'."
                    )
        return out
    return [int(x) for x in _JSON.get(json_key, []) if int(x) != 0]


BOT_TOKEN = _get("BOT_TOKEN", "bot_token", "")
ADMIN_IDS = _get_int_list("ADMIN_IDS", "admin_ids")
GROUP_CHAT_ID = _get("GROUP_CHAT_ID", "group_chat_id", 0, int) or 0
TIMEZONE = _get("TIMEZONE", "timezone", "Asia/Singapore")

DEFAULT_DURATION_MIN = int(
    _get("DEFAULT_DURATION_MINUTES", "default_duration_minutes", 120, int)
)
REMINDER_EVENING_HOUR = int(
    _get("REMINDER_EVENING_BEFORE_HOUR", "reminder_evening_before_hour", 18, int)
)
REMINDER_HOURS_BEFORE = float(
    _get("REMINDER_HOURS_BEFORE", "reminder_hours_before", 1, float)
)

ANNOUNCE_RESTARTS = bool(_get("ANNOUNCE_RESTARTS", "announce_restarts", False, bool))
OFFLINE_THRESHOLD_MIN = int(
    _get("OFFLINE_ANNOUNCE_THRESHOLD_MINUTES", "offline_announce_threshold_minutes",
         30, int)
)

# On Railway set DB_PATH=/data/bbbot.db and attach a Volume mounted at /data,
# otherwise the database is wiped on every deploy. See DEPLOY.md.
DB_PATH = _get("DB_PATH", "db_path", "bbbot.db")

# Railway sets this automatically; we use it only to soften startup chatter.
ON_SERVER = bool(os.environ.get("RAILWAY_ENVIRONMENT"))


def validate():
    problems = []
    if not BOT_TOKEN or "PASTE" in BOT_TOKEN:
        problems.append(
            "BOT_TOKEN is not set. Get one from @BotFather, then either set the "
            "BOT_TOKEN environment variable or put it in config.json."
        )
    if not ADMIN_IDS:
        problems.append(
            "ADMIN_IDS is empty. Send /whoami to the bot to find your numeric ID, "
            "then set ADMIN_IDS to it. Admin commands stay locked until you do."
        )
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(TIMEZONE)
    except Exception:
        problems.append(
            f"TIMEZONE '{TIMEZONE}' isn't a valid timezone name. "
            "Use something like Asia/Singapore or Europe/London."
        )
    return problems
