import asyncio
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import discord  # noqa: E402

import message_wipe as mw  # noqa: E402

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
CHANNELS = {"general": 111111111111111111, "memes": 222222222222222222, "rules": 333333333333333333}


def resolve(raw: str):
    raw = raw.strip()
    if raw.startswith("<#") and raw.endswith(">"):
        return int(raw[2:-1])
    return CHANNELS.get(raw.lstrip("#").lower())


def msg(
    mid,
    author_id=1,
    content="",
    *,
    age=timedelta(hours=1),
    attachments=(),
    embeds=(),
    stickers=(),
    mentions=(),
    reference=None,
    pinned=False,
):
    return SimpleNamespace(
        id=mid,
        author=SimpleNamespace(id=author_id),
        content=content,
        created_at=NOW - age,
        attachments=list(attachments),
        embeds=list(embeds),
        stickers=list(stickers),
        mentions=list(mentions),
        role_mentions=[],
        mention_everyone=False,
        reference=reference,
        pinned=pinned,
    )


def image(name="a.png"):
    return SimpleNamespace(filename=name, content_type="image/png")


class ParseTests(unittest.TestCase):
    def parse(self, text):
        return mw.parse_filters(text, resolve_channel=resolve, now=NOW)

    def test_empty(self):
        f = self.parse("")
        self.assertEqual(f.channel_ids, set())
        self.assertFalse(f.include_pinned)

    def test_channels_and_excludes(self):
        f = self.parse("<#111111111111111111> in:memes -<#333333333333333333> exclude:rules")
        self.assertEqual(f.channel_ids, {CHANNELS["general"], CHANNELS["memes"]})
        self.assertEqual(f.exclude_channel_ids, {CHANNELS["rules"]})

    def test_types_keywords_time(self):
        f = self.parse('links images -videos contains:"my number" except:keep newer:7d minlen:3 pinned preview')
        self.assertEqual(f.types, {"links", "images"})
        self.assertEqual(f.exclude_types, {"videos"})
        self.assertEqual(f.keywords, ["my number"])
        self.assertEqual(f.exclude_keywords, ["keep"])
        self.assertEqual(f.after, NOW - timedelta(days=7))
        self.assertEqual(f.min_length, 3)
        self.assertTrue(f.include_pinned and f.preview_only)

    def test_dates(self):
        f = self.parse("after:2025-01-01 before:2025-06-30")
        self.assertEqual(f.after, datetime(2025, 1, 1, tzinfo=timezone.utc))

    def test_errors(self):
        for bad in ["banana", "in:nowhere", "newer:7x", "regex:(", "after:2025-02-01 before:2025-01-01",
                    "links -links", "minlen:9 maxlen:2", 'contains:"oops']:
            with self.assertRaises(mw.WipeFilterError, msg=bad):
                self.parse(bad)

    def test_amount(self):
        self.assertIsNone(mw.parse_amount("all", maximum=100))
        self.assertEqual(mw.parse_amount("2k", maximum=5000), 2000)
        self.assertEqual(mw.parse_amount("1,500", maximum=5000), 1500)
        with self.assertRaises(mw.WipeFilterError):
            mw.parse_amount("0", maximum=5)
        with self.assertRaises(mw.WipeFilterError):
            mw.parse_amount("99", maximum=5)
        self.assertTrue(mw.looks_like_amount("10k"))
        self.assertFalse(mw.looks_like_amount("links"))


class MatchTests(unittest.TestCase):
    def f(self, text=""):
        return mw.parse_filters(text, resolve_channel=resolve, now=NOW)

    def test_types(self):
        self.assertEqual(mw.message_types(msg(1, content="hello")), {"text"})
        self.assertIn("links", mw.message_types(msg(1, content="see https://x.com")))
        self.assertIn("invites", mw.message_types(msg(1, content="join discord.gg/abc")))
        self.assertIn("images", mw.message_types(msg(1, attachments=[image()])))
        self.assertIn("emoji", mw.message_types(msg(1, content="😂😂 <:pog:123456789012345678>")))
        self.assertNotIn("emoji", mw.message_types(msg(1, content="lol 😂")))
        self.assertIn("replies", mw.message_types(msg(1, content="x", reference=object())))

    def test_pinned_kept_by_default(self):
        self.assertFalse(mw.message_matches(msg(1, content="x", pinned=True), self.f()))
        self.assertTrue(mw.message_matches(msg(1, content="x", pinned=True), self.f("pinned")))

    def test_type_or_and_exclusions(self):
        f = self.f("links images")
        self.assertTrue(mw.message_matches(msg(1, content="https://a.b"), f))
        self.assertTrue(mw.message_matches(msg(1, attachments=[image()]), f))
        self.assertFalse(mw.message_matches(msg(1, content="plain"), f))
        self.assertFalse(mw.message_matches(msg(1, attachments=[image()]), self.f("-images")))

    def test_keywords_and_time(self):
        f = self.f('contains:secret older:1d')
        self.assertTrue(mw.message_matches(msg(1, content="My SECRET", age=timedelta(days=3)), f))
        self.assertFalse(mw.message_matches(msg(1, content="My SECRET", age=timedelta(hours=2)), f))
        self.assertFalse(mw.message_matches(msg(1, content="nothing", age=timedelta(days=3)), f))
        self.assertFalse(mw.message_matches(msg(1, content="secret keep", age=timedelta(days=3)),
                                            self.f("contains:secret except:keep")))


class FakeChannel:
    def __init__(self, cid, messages, forbidden=False):
        self.id = cid
        self.mention = f"<#{cid}>"
        self.messages = sorted(messages, key=lambda m: m.created_at, reverse=True)
        self.forbidden = forbidden
        self.bulk_calls = []
        self.single_deletes = []

    def history(self, *, limit=None, before=None, after=None, oldest_first=False):
        channel = self

        async def gen():
            if channel.forbidden:
                raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "no")
            count = 0
            for m in channel.messages:
                if before and m.created_at >= before:
                    continue
                if after and m.created_at <= after:
                    continue
                if limit is not None and count >= limit:
                    return
                count += 1
                yield m

        return gen()

    async def delete_messages(self, objs, reason=None):
        assert len(objs) <= 100
        self.bulk_calls.append([o.id for o in objs])

    def get_partial_message(self, mid):
        channel = self

        class Partial:
            async def delete(self_inner):
                channel.single_deletes.append(mid)

        return Partial()


class EngineTests(unittest.TestCase):
    def make_job(self, amount=None, text=""):
        filters = mw.parse_filters(text, resolve_channel=resolve)
        return mw.WipeJob(guild_id=1, target_id=42, moderator_id=7, self_service=False,
                          filters=filters, amount=amount)

    def test_scan_and_delete_all(self):
        real_now = datetime.now(timezone.utc)
        recent = [SimpleNamespace(**{**vars(msg(i, 42, "hi")), "created_at": real_now - timedelta(hours=i)})
                  for i in range(1, 251)]
        old = [SimpleNamespace(**{**vars(msg(1000 + i, 42, "old")), "created_at": real_now - timedelta(days=30 + i)})
               for i in range(5)]
        others = [SimpleNamespace(**{**vars(msg(5000 + i, 99, "hi")), "created_at": real_now - timedelta(hours=i)})
                  for i in range(50)]
        a = FakeChannel(1, recent + others)
        b = FakeChannel(2, old)
        c = FakeChannel(3, [], forbidden=True)
        job = self.make_job()
        asyncio.run(mw.scan_channels(job, [a, b, c]))
        self.assertEqual(len(job.matches), 255)
        self.assertEqual(job.scanned, 305)
        self.assertEqual(job.skipped_channels, ["<#3>"])
        self.assertEqual(job.split_by_age(), (250, 5))

        asyncio.run(mw.delete_matches(job, {1: a, 2: b, 3: c}))
        self.assertEqual(job.deleted, 255)
        self.assertEqual([len(x) for x in a.bulk_calls], [100, 100, 50])
        self.assertEqual(len(b.single_deletes), 5)
        self.assertEqual(job.phase, "done")
        deleted_ids = {i for call in a.bulk_calls for i in call}
        self.assertFalse(deleted_ids & {m.id for m in others})

    def test_amount_picks_newest_across_channels(self):
        a = FakeChannel(1, [msg(i, 42, "a", age=timedelta(hours=2 * i)) for i in range(1, 20)])
        b = FakeChannel(2, [msg(100 + i, 42, "b", age=timedelta(hours=2 * i + 1)) for i in range(1, 20)])
        job = self.make_job(amount=4)
        asyncio.run(mw.scan_channels(job, [a, b]))
        self.assertEqual([m.message_id for m in job.matches], [1, 101, 2, 102])

    def test_cancel_stops_deleting(self):
        real_now = datetime.now(timezone.utc)
        old = [SimpleNamespace(**{**vars(msg(i, 42, "x")), "created_at": real_now - timedelta(days=40 + i)})
               for i in range(10)]
        ch = FakeChannel(1, old)
        job = self.make_job()
        asyncio.run(mw.scan_channels(job, [ch]))

        async def progress(j):
            if j.deleted >= 3:
                j.cancel_event.set()

        asyncio.run(mw.delete_matches(job, {1: ch}, progress=progress, progress_interval=0))
        self.assertEqual(job.phase, "cancelled")
        self.assertLess(job.deleted, 10)


if __name__ == "__main__":
    unittest.main()
