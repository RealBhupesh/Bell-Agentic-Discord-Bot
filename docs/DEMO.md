# Bell demo walkthrough

A scripted demo of Bell's main features in a **private test server**, using synthetic data only.

**No real member data is needed or used.** Every step runs in a server you create for the demo,
with accounts you control and content you type yourself. Nothing here reads, imports or shows any
real community's messages, members or state files. The offline parts use the synthetic fixtures in
`tests/fixtures/` and made-up model names.

## 0. Setup (about 10 minutes)

1. **Create a throwaway server** in Discord ("Bell Demo"). Do not use a real community server.
2. **Use test accounts only.** You need your own account (owner and moderator) and, for the
   pairing and escalation parts, a second account you control (for example a secondary test
   account). Give it a fictional name such as `TestPlayer`. If you only have one account, skip the
   steps marked *(second account)*.
3. **Create channels**: `#general`, `#games`, `#mod-log`.
4. **Start from an empty state directory**, so no real data is loaded:

   ```bash
   mv data data.real-backup 2>/dev/null; mkdir data
   ```

   (Move it back afterwards. If this is a fresh clone there is no `data/` yet.)
5. **Configure `.env`** from `.env.example`: set `DISCORD_BOT_TOKEN`, and for the AI parts
   `AI_PROVIDER=groq` and `GROQ_API_KEY`. To make the budget caps visible during a short demo,
   lower these:

   ```
   CRUSH_GAME_DAILY_CAP=3
   AGENT_DAILY_CAP=3
   ```

6. Invite the bot (see the README quickstart), run `python bot.py`, and type `&help` in `#general`.
7. In `#general`, run `&setmodlog #mod-log`.

## 1. Moderation basics (2 minutes)

1. `&automod on`, then `&automod status`.
2. Add a made-up blocked word so you never have to type a real slur: append a line `bananaphone`
   to `data/bad_words.txt` and run `&reloadbadwords`.
3. *(second account)* Post "I love my bananaphone". The message is removed and an AutoMod entry
   appears in `#mod-log`.
4. `&warn @TestPlayer demo warning`, then `&warnings @TestPlayer`. Point out the `#mod-log` entry.

## 2. The crush consent game (5 minutes)

Talking points: the game only uses what the player types; pairings are dice rolls; nothing is read
from history or DMs; opt-out works at any time.

1. In `#games`, `&crush` first. It replies that the game is not enabled: **off by default**.
2. `&crushgame on #games`. The bot posts the one-time "Fun features notice" naming `&exclude` and
   `&wipe`. Run `&crushgame off` then `&crushgame on #games` again and show that the notice is
   **not** re-posted.
3. `&crush`: you are paired with a **fictional character** (a raccoon with a lemonade stand, a
   haunted rubber duck, ...). The result shows a fun prompt.
4. `&crush pineapple pizza and lo-fi beats`: the answer you typed drives your silly label. This is
   the only personal input the game stores, and only because you typed it.
5. *(second account)* `&crush @TestPlayer`. The result says "Random pairing ... pure dice roll,
   nothing about TestPlayer was looked at". Run it again: the same pair gets the same score for
   the rest of the UTC day, because it is seeded, not analysed.
6. Point at the disclaimer that ends every result ("Just a joke game! ...").
7. *(second account)* As TestPlayer, run `&exclude`. Then, as yourself, `&crush @TestPlayer`
   is refused, and `&roast @TestPlayer` / `&vibe @TestPlayer` also refuse. TestPlayer runs
   `&include` to opt back in, and `&wipe` to delete any saved answer.
8. Budget cap: keep playing. With `CRUSH_GAME_DAILY_CAP=3`, the fourth play replies "The
   Crush-o-Meter has used up its daily fun budget. Try again tomorrow!" No model was asked; the
   cap is enforced by the budget governor.

If Groq is configured, results may include one extra AI joke line. Its prompt contains only the
display names shown in the result, your typed answer and the random score.

## 3. Budget governor (3 minutes, partly offline)

### Offline (no Discord, no key)

```bash
python docs/demo_governor.py
```

Expected output, using fake model names and a throwaway counter file:

```
1) model fallback, then daily budget exhausted
   call 1: reply from model-a
   call 2: reply from model-a
   call 3: reply from model-b
   call 4: reply from model-b
   call 5: refused: AI budget used up for today. Please try again later.
2) per-feature daily cap (admission without a model call)
   play 1: admitted=True
   play 2: admitted=False
3) fail closed: restart with a corrupt counter file
[GROQ BUDGET] Usage counters unreadable; AI requests are blocked until fixed: stored counters are unreadable or corrupt
   refused: AI is paused: the bot could not safely record its usage limits. Please tell the bot owner.
```

Talking points:

- Each model has its own requests/tokens per minute and per day; when one runs out, the next model
  in the chain is used; when all run out, the bot refuses instead of calling Groq.
- Counters survive restarts. If they can't be read or saved, the bot **fails closed**
  (`QuotaPersistenceError`) rather than starting again from zero.

### Live (with Groq configured)

1. `&agent what channels can I see here?` three times. With `AGENT_DAILY_CAP=3`, the fourth request
   is refused for the rest of the UTC day.
2. Optional fail-closed demo, **only in the demo `data/` directory**: stop the bot, run
   `echo '{not json' > data/groq_budget_state.json`, start it again and try `&ai hello`. The reply is
   "AI is paused: the bot could not safely record its usage limits...", and the console prints a
   `[GROQ BUDGET]` line. Stop the bot, delete that file (accepting fresh counters) and restart to
   recover.

## 4. Agent tools and Confirm cards (3 minutes)

1. `&agent how many warnings does TestPlayer have?` (or ask about your own account). Read-only tools
   (`member_info`, `warn_count`, ...) run straight away.
2. In `#games`: `&agent lock this channel`. The agent cannot do it directly. It produces a
   **Confirm / Cancel card**. Click **Cancel** to show that nothing happens. Ask again and click
   **Confirm** as a moderator; the channel is locked and the action is logged in `#mod-log`. Run
   `&unlock` in `#games` afterwards.
3. Point out that cards expire after 10 minutes, and that only moderators with the right Discord
   permission can confirm.

## 5. Agentic automation: proposal and approval (5 minutes)

Talking points: everything is off by default; a moderator has to opt in per server; nothing
consequential is executed without a human click.

1. `&agentic status`: scheduled tasks, escalation and nudges are all **off**.
2. **Scheduled task**:
   - `&agentic scheduled on`
   - `&agentic task add demo-digest | @hourly | #general | Post a two-line friendly reminder to drink water.`
   - `&agentic status` shows the task as **disabled**. New tasks always start disabled.
   - `&agentic task enable demo-digest` and `&agentic task cap demo-digest 2`.
   - Schedules run in UTC on a one-minute loop. For a demo, use a cron line for the next minute
     instead of `@hourly` (for example `37 14 * * *` if it is 14:36 UTC). If the agent decides it
     wants a consequential tool, it can only post a Confirm card.
   - `&agentic task disable demo-digest` when done.
3. **Escalation proposal** *(second account, Groq configured)*:
   - TestPlayer must be a plain member, not a moderator, so that AutoMod acts on its messages.
     The proposal is drafted by the model (governor feature `agent_escalation`), so this step needs
     an AI key.
   - `&agentic escalation on 2 #mod-log` (threshold of 2 violations in 24 hours).
   - As TestPlayer, trigger AutoMod twice with the made-up blocked word `bananaphone`.
   - One proposal card (timeout / ban / watch) appears in `#mod-log`, based only on TestPlayer's
     warnings and AutoMod cases in this demo server.
   - Click **Confirm**: the decision is **recorded** in the mod log, and nothing is applied
     to TestPlayer. Bell never applies an escalation automatically. Trigger AutoMod again and show
     that no second proposal appears within 24 hours.
4. **Engagement nudges**:
   - `&agentic nudges on #general 5`.
   - Members get nudges only after their own `&nudges on`. Run `&nudges on`, then `&nudges` to show
     your status. A nudge is sent at most once per member per day, only while a streak is alive or a
     quest is open, and is templated (no model call).
5. Turn everything off: `&agentic scheduled off`, `&agentic escalation off`, `&agentic nudges off`,
   `&crushgame off`, `&automod off`.

## 6. Storage and migration preview (1 minute, offline)

```bash
python db/migrate_json_to_postgres.py --dry-run --data-dir tests/fixtures/json_state
```

This reads only the synthetic fixtures (placeholder ids like `111111111111111111`), never connects
to a database, and lists what would be copied to which table. The legacy aicrush file in the
fixtures is reported as "never migrated".

## Cleanup

```bash
rm -rf data
```

```bash
mv data.real-backup data 2>/dev/null
```

Delete the demo server (or kick the bot) when you're done.
