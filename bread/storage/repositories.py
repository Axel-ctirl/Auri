from __future__ import annotations

import time
import uuid
from typing import Any

from bread.storage.json_store import JSONStore

GUILD_CONFIG_DEFAULTS: dict[str, Any] = {
    "modlog_channel": None,
    "jail_role": None,
    "jail_channel": None,
    "mute_role": None,
    "autorole": {"human": [], "bot": []},
    "vanity": None,
    "antiraid": {"enabled": False, "threshold": 5, "window": 10, "action": "alert"},
    "antinuke": {
        "enabled": False,
        "threshold": 3,
        "window": 10,
        "punishment": "strip_roles",
        "whitelist": [],
    },
    "filters": [],
    "autoresponders": [],
}


def _gkey(guild_id: int) -> str:
    return str(guild_id)


def _ukey(user_id: int) -> str:
    return str(user_id)


class GuildConfigRepo:
    def __init__(self) -> None:
        self._store = JSONStore("guild_configs", default={})

    def _bucket(self, data: dict, guild_id: int) -> dict:
        key = _gkey(guild_id)
        if key not in data:
            data[key] = {k: (v.copy() if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
                         for k, v in GUILD_CONFIG_DEFAULTS.items()}
        else:
            for k, v in GUILD_CONFIG_DEFAULTS.items():
                data[key].setdefault(k, v)
        return data[key]

    async def get(self, guild_id: int) -> dict:
        data = await self._store.read()
        return self._bucket(data, guild_id)

    async def set_modlog_channel(self, guild_id: int, channel_id: int | None) -> None:
        await self._store.mutate(lambda d: self._bucket(d, guild_id).__setitem__("modlog_channel", channel_id))

    async def set_jail(self, guild_id: int, role_id: int | None, channel_id: int | None) -> None:
        def _m(d: dict) -> None:
            bucket = self._bucket(d, guild_id)
            bucket["jail_role"] = role_id
            bucket["jail_channel"] = channel_id

        await self._store.mutate(_m)

    async def set_mute_role(self, guild_id: int, role_id: int | None) -> None:
        await self._store.mutate(lambda d: self._bucket(d, guild_id).__setitem__("mute_role", role_id))

    async def add_autorole(self, guild_id: int, role_id: int, kind: str) -> None:
        def _m(d: dict) -> None:
            roles = self._bucket(d, guild_id)["autorole"][kind]
            if role_id not in roles:
                roles.append(role_id)

        await self._store.mutate(_m)

    async def remove_autorole(self, guild_id: int, role_id: int, kind: str) -> bool:
        def _m(d: dict) -> bool:
            roles = self._bucket(d, guild_id)["autorole"][kind]
            if role_id in roles:
                roles.remove(role_id)
                return True
            return False

        return await self._store.mutate(_m)

    async def set_vanity(self, guild_id: int, role_id: int | None, phrase: str | None) -> None:
        def _m(d: dict) -> None:
            bucket = self._bucket(d, guild_id)
            bucket["vanity"] = None if role_id is None else {"role_id": role_id, "phrase": phrase}

        await self._store.mutate(_m)

    async def set_antiraid(self, guild_id: int, **kwargs: Any) -> dict:
        def _m(d: dict) -> dict:
            bucket = self._bucket(d, guild_id)
            bucket["antiraid"].update({k: v for k, v in kwargs.items() if v is not None})
            return bucket["antiraid"]

        return await self._store.mutate(_m)

    async def set_antinuke(self, guild_id: int, **kwargs: Any) -> dict:
        def _m(d: dict) -> dict:
            bucket = self._bucket(d, guild_id)
            bucket["antinuke"].update({k: v for k, v in kwargs.items() if v is not None})
            return bucket["antinuke"]

        return await self._store.mutate(_m)

    async def antinuke_whitelist_add(self, guild_id: int, user_id: int) -> None:
        def _m(d: dict) -> None:
            whitelist = self._bucket(d, guild_id)["antinuke"]["whitelist"]
            if user_id not in whitelist:
                whitelist.append(user_id)

        await self._store.mutate(_m)

    async def antinuke_whitelist_remove(self, guild_id: int, user_id: int) -> bool:
        def _m(d: dict) -> bool:
            whitelist = self._bucket(d, guild_id)["antinuke"]["whitelist"]
            if user_id in whitelist:
                whitelist.remove(user_id)
                return True
            return False

        return await self._store.mutate(_m)

    async def add_filter(self, guild_id: int, word: str) -> None:
        def _m(d: dict) -> None:
            filters = self._bucket(d, guild_id)["filters"]
            if word.lower() not in filters:
                filters.append(word.lower())

        await self._store.mutate(_m)

    async def remove_filter(self, guild_id: int, word: str) -> bool:
        def _m(d: dict) -> bool:
            filters = self._bucket(d, guild_id)["filters"]
            if word.lower() in filters:
                filters.remove(word.lower())
                return True
            return False

        return await self._store.mutate(_m)

    async def add_autoresponder(self, guild_id: int, trigger: str, response: str, exact: bool) -> None:
        def _m(d: dict) -> None:
            self._bucket(d, guild_id)["autoresponders"].append(
                {"trigger": trigger.lower(), "response": response, "exact": exact}
            )

        await self._store.mutate(_m)

    async def remove_autoresponder(self, guild_id: int, trigger: str) -> bool:
        def _m(d: dict) -> bool:
            responders = self._bucket(d, guild_id)["autoresponders"]
            for entry in list(responders):
                if entry["trigger"] == trigger.lower():
                    responders.remove(entry)
                    return True
            return False

        return await self._store.mutate(_m)


class WarningsRepo:
    def __init__(self) -> None:
        self._store = JSONStore("warnings", default={})

    def _bucket(self, data: dict, guild_id: int) -> dict:
        key = _gkey(guild_id)
        return data.setdefault(key, {"next_case_id": 1, "cases": []})

    async def add_case(self, guild_id: int, user_id: int, mod_id: int, type_: str, reason: str) -> dict:
        def _m(d: dict) -> dict:
            bucket = self._bucket(d, guild_id)
            case = {
                "id": bucket["next_case_id"],
                "user_id": user_id,
                "mod_id": mod_id,
                "type": type_,
                "reason": reason,
                "timestamp": int(time.time()),
            }
            bucket["cases"].append(case)
            bucket["next_case_id"] += 1
            return case

        return await self._store.mutate(_m)

    async def list_cases(self, guild_id: int, user_id: int | None = None) -> list[dict]:
        data = await self._store.read()
        cases = self._bucket(data, guild_id)["cases"]
        if user_id is not None:
            cases = [c for c in cases if c["user_id"] == user_id]
        return sorted(cases, key=lambda c: c["id"], reverse=True)

    async def get_case(self, guild_id: int, case_id: int) -> dict | None:
        data = await self._store.read()
        for case in self._bucket(data, guild_id)["cases"]:
            if case["id"] == case_id:
                return case
        return None

    async def delete_case(self, guild_id: int, case_id: int) -> bool:
        def _m(d: dict) -> bool:
            bucket = self._bucket(d, guild_id)
            for case in list(bucket["cases"]):
                if case["id"] == case_id:
                    bucket["cases"].remove(case)
                    return True
            return False

        return await self._store.mutate(_m)

    async def clear_cases(self, guild_id: int, user_id: int) -> int:
        def _m(d: dict) -> int:
            bucket = self._bucket(d, guild_id)
            before = len(bucket["cases"])
            bucket["cases"] = [c for c in bucket["cases"] if c["user_id"] != user_id]
            return before - len(bucket["cases"])

        return await self._store.mutate(_m)


class EconomyRepo:
    DAILY_AMOUNT = 250
    WORK_MIN, WORK_MAX = 50, 200
    DAILY_COOLDOWN = 24 * 3600
    WORK_COOLDOWN = 3600

    def __init__(self) -> None:
        self._store = JSONStore("economy", default={})

    def _bucket(self, data: dict, guild_id: int, user_id: int) -> dict:
        guild_bucket = data.setdefault(_gkey(guild_id), {})
        return guild_bucket.setdefault(_ukey(user_id), {"balance": 0, "last_daily": None, "last_work": None})

    async def get_balance(self, guild_id: int, user_id: int) -> int:
        data = await self._store.read()
        return self._bucket(data, guild_id, user_id)["balance"]

    async def add_balance(self, guild_id: int, user_id: int, amount: int) -> int:
        def _m(d: dict) -> int:
            bucket = self._bucket(d, guild_id, user_id)
            bucket["balance"] = max(0, bucket["balance"] + amount)
            return bucket["balance"]

        return await self._store.mutate(_m)

    async def transfer(self, guild_id: int, from_user: int, to_user: int, amount: int) -> bool:
        def _m(d: dict) -> bool:
            sender = self._bucket(d, guild_id, from_user)
            if sender["balance"] < amount:
                return False
            sender["balance"] -= amount
            receiver = self._bucket(d, guild_id, to_user)
            receiver["balance"] += amount
            return True

        return await self._store.mutate(_m)

    async def claim_daily(self, guild_id: int, user_id: int) -> tuple[bool, int]:
        now = int(time.time())

        def _m(d: dict) -> tuple[bool, int]:
            bucket = self._bucket(d, guild_id, user_id)
            last = bucket["last_daily"]
            if last is not None and now - last < self.DAILY_COOLDOWN:
                return False, self.DAILY_COOLDOWN - (now - last)
            bucket["last_daily"] = now
            bucket["balance"] += self.DAILY_AMOUNT
            return True, self.DAILY_AMOUNT

        return await self._store.mutate(_m)

    async def claim_work(self, guild_id: int, user_id: int) -> tuple[bool, int]:
        import random

        now = int(time.time())

        def _m(d: dict) -> tuple[bool, int]:
            bucket = self._bucket(d, guild_id, user_id)
            last = bucket["last_work"]
            if last is not None and now - last < self.WORK_COOLDOWN:
                return False, self.WORK_COOLDOWN - (now - last)
            bucket["last_work"] = now
            earned = random.randint(self.WORK_MIN, self.WORK_MAX)
            bucket["balance"] += earned
            return True, earned

        return await self._store.mutate(_m)

    async def leaderboard(self, guild_id: int, limit: int = 10) -> list[tuple[int, int]]:
        data = await self._store.read()
        guild_bucket = data.get(_gkey(guild_id), {})
        ranked = sorted(guild_bucket.items(), key=lambda kv: kv[1]["balance"], reverse=True)
        return [(int(uid), entry["balance"]) for uid, entry in ranked[:limit]]


class ReactionRoleRepo:
    def __init__(self) -> None:
        self._store = JSONStore("reaction_roles", default={})

    async def add(self, guild_id: int, message_id: int, emoji: str, role_id: int) -> None:
        def _m(d: dict) -> None:
            entries = d.setdefault(_gkey(guild_id), [])
            entries.append({"message_id": message_id, "emoji": emoji, "role_id": role_id})

        await self._store.mutate(_m)

    async def remove(self, guild_id: int, message_id: int, emoji: str) -> bool:
        def _m(d: dict) -> bool:
            entries = d.setdefault(_gkey(guild_id), [])
            for entry in list(entries):
                if entry["message_id"] == message_id and entry["emoji"] == emoji:
                    entries.remove(entry)
                    return True
            return False

        return await self._store.mutate(_m)

    async def list(self, guild_id: int) -> list[dict]:
        data = await self._store.read()
        return list(data.get(_gkey(guild_id), []))

    async def find(self, guild_id: int, message_id: int, emoji: str) -> dict | None:
        for entry in await self.list(guild_id):
            if entry["message_id"] == message_id and entry["emoji"] == emoji:
                return entry
        return None


class GiveawayRepo:
    def __init__(self) -> None:
        self._store = JSONStore("giveaways", default={})

    async def create(
        self,
        guild_id: int,
        channel_id: int,
        prize: str,
        end_ts: int,
        winners_count: int,
        host_id: int,
        required_role: int | None,
    ) -> dict:
        def _m(d: dict) -> dict:
            entries = d.setdefault(_gkey(guild_id), [])
            giveaway = {
                "id": uuid.uuid4().hex[:10],
                "guild_id": guild_id,
                "channel_id": channel_id,
                "message_id": None,
                "prize": prize,
                "end_ts": end_ts,
                "winners_count": winners_count,
                "required_role": required_role,
                "entrants": [],
                "host_id": host_id,
                "ended": False,
            }
            entries.append(giveaway)
            return giveaway

        return await self._store.mutate(_m)

    async def set_message_id(self, guild_id: int, giveaway_id: str, message_id: int) -> None:
        def _m(d: dict) -> None:
            for entry in d.get(_gkey(guild_id), []):
                if entry["id"] == giveaway_id:
                    entry["message_id"] = message_id
                    return

        await self._store.mutate(_m)

    async def get(self, guild_id: int, giveaway_id: str) -> dict | None:
        data = await self._store.read()
        for entry in data.get(_gkey(guild_id), []):
            if entry["id"] == giveaway_id:
                return entry
        return None

    async def list_active(self, guild_id: int) -> list[dict]:
        data = await self._store.read()
        return [e for e in data.get(_gkey(guild_id), []) if not e["ended"]]

    async def list_all_active(self) -> list[dict]:
        data = await self._store.read()
        return [e for guild_entries in data.values() for e in guild_entries if not e["ended"]]

    async def add_entrant(self, guild_id: int, giveaway_id: str, user_id: int) -> bool:
        def _m(d: dict) -> bool:
            for entry in d.get(_gkey(guild_id), []):
                if entry["id"] == giveaway_id:
                    if user_id in entry["entrants"]:
                        return False
                    entry["entrants"].append(user_id)
                    return True
            return False

        return await self._store.mutate(_m)

    async def end(self, guild_id: int, giveaway_id: str) -> dict | None:
        def _m(d: dict) -> dict | None:
            for entry in d.get(_gkey(guild_id), []):
                if entry["id"] == giveaway_id:
                    entry["ended"] = True
                    return entry
            return None

        return await self._store.mutate(_m)

    async def cancel(self, guild_id: int, giveaway_id: str) -> bool:
        def _m(d: dict) -> bool:
            entries = d.get(_gkey(guild_id), [])
            for entry in list(entries):
                if entry["id"] == giveaway_id:
                    entries.remove(entry)
                    return True
            return False

        return await self._store.mutate(_m)


class TicketRepo:
    def __init__(self) -> None:
        self._store = JSONStore("tickets", default={})

    def _bucket(self, data: dict, guild_id: int) -> dict:
        return data.setdefault(
            _gkey(guild_id),
            {"panel_channel": None, "category": None, "support_role": None, "open_tickets": {}},
        )

    async def set_config(
        self, guild_id: int, panel_channel: int, category: int, support_role: int
    ) -> None:
        def _m(d: dict) -> None:
            bucket = self._bucket(d, guild_id)
            bucket.update(panel_channel=panel_channel, category=category, support_role=support_role)

        await self._store.mutate(_m)

    async def get_config(self, guild_id: int) -> dict:
        data = await self._store.read()
        return self._bucket(data, guild_id)

    async def open_ticket(self, guild_id: int, channel_id: int, opener_id: int) -> None:
        def _m(d: dict) -> None:
            bucket = self._bucket(d, guild_id)
            bucket["open_tickets"][str(channel_id)] = {
                "opener_id": opener_id,
                "claimed_by": None,
                "created_ts": int(time.time()),
            }

        await self._store.mutate(_m)

    async def claim_ticket(self, guild_id: int, channel_id: int, mod_id: int) -> None:
        def _m(d: dict) -> None:
            bucket = self._bucket(d, guild_id)
            ticket = bucket["open_tickets"].get(str(channel_id))
            if ticket:
                ticket["claimed_by"] = mod_id

        await self._store.mutate(_m)

    async def close_ticket(self, guild_id: int, channel_id: int) -> dict | None:
        def _m(d: dict) -> dict | None:
            bucket = self._bucket(d, guild_id)
            return bucket["open_tickets"].pop(str(channel_id), None)

        return await self._store.mutate(_m)

    async def get_ticket(self, guild_id: int, channel_id: int) -> dict | None:
        data = await self._store.read()
        return self._bucket(data, guild_id)["open_tickets"].get(str(channel_id))


class AfkRepo:
    def __init__(self) -> None:
        self._store = JSONStore("afk", default={})

    async def set_afk(self, guild_id: int, user_id: int, reason: str) -> dict:
        entry = {"reason": reason, "since": int(time.time())}

        def _m(d: dict) -> dict:
            guild_bucket = d.setdefault(_gkey(guild_id), {})
            guild_bucket[_ukey(user_id)] = entry
            return entry

        return await self._store.mutate(_m)

    async def get_afk(self, guild_id: int, user_id: int) -> dict | None:
        data = await self._store.read()
        return data.get(_gkey(guild_id), {}).get(_ukey(user_id))

    async def clear_afk(self, guild_id: int, user_id: int) -> dict | None:
        def _m(d: dict) -> dict | None:
            guild_bucket = d.setdefault(_gkey(guild_id), {})
            return guild_bucket.pop(_ukey(user_id), None)

        return await self._store.mutate(_m)


class FakePermsRepo:
    def __init__(self) -> None:
        self._store = JSONStore("fake_perms", default={})

    async def grant(self, guild_id: int, role_id: int, permission: str) -> None:
        def _m(d: dict) -> None:
            guild_bucket = d.setdefault(_gkey(guild_id), {})
            perms = guild_bucket.setdefault(str(role_id), [])
            if permission not in perms:
                perms.append(permission)

        await self._store.mutate(_m)

    async def revoke(self, guild_id: int, role_id: int, permission: str) -> bool:
        def _m(d: dict) -> bool:
            guild_bucket = d.setdefault(_gkey(guild_id), {})
            perms = guild_bucket.get(str(role_id), [])
            if permission in perms:
                perms.remove(permission)
                return True
            return False

        return await self._store.mutate(_m)

    async def list_guild(self, guild_id: int) -> dict[str, list[str]]:
        data = await self._store.read()
        return dict(data.get(_gkey(guild_id), {}))

    async def has_permission(self, guild_id: int, role_ids: list[int], permission: str) -> bool:
        guild_perms = await self.list_guild(guild_id)
        return any(permission in guild_perms.get(str(rid), []) for rid in role_ids)


# Singletons: every cog imports these rather than constructing its own repo, since each
# JSONStore caches its file in memory after first read — separate instances backed by the
# same file would drift out of sync with each other within a single running process.
guild_configs = GuildConfigRepo()
warnings = WarningsRepo()
economy = EconomyRepo()
reaction_roles = ReactionRoleRepo()
giveaways = GiveawayRepo()
tickets = TicketRepo()
afk = AfkRepo()
fake_perms = FakePermsRepo()
