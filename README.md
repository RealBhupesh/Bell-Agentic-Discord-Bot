# Discord Moderation Bot

Discord moderation bot with prefix commands (default: `&`).

## 🧹 Message Wipe — remove one person's history, fast

Someone joins your server and starts reading through a member's old chats. That member may have thousands of messages, far too many to delete by hand, and getting themselves banned shouldn't be the only way out. **Message Wipe** finds every message one person sent across the server and deletes it in one go. Filters let you pick exactly which messages go.

```
&wipe <@user | user_id> [amount | all] [filters…]      (also /wipe with a user picker)
&wipeme [amount | all] [filters…]                       (members wipe their own messages, if enabled)
&wipestop        &selfwipe <on|off|status>        &wipehelp
```

**How it works**
1. Bell scans the channels you choose and shows live progress, with a **Stop** button.
2. You get a **preview**: how many messages matched, which channels they're in, the date range, and an estimated time.
3. Nothing is deleted until you press **Delete**. Messages under 14 days old are bulk-deleted 100 at a time; older ones are deleted one by one in the background.
4. A summary goes to the mod-log. **Message contents are never logged.**

**Filters** (combine freely)

| What | Syntax |
|---|---|
| Channels (default: all) | `#general #memes`, `in:general,memes`, `here`, `archived` (include archived threads) |
| Skip channels | `-#rules`, `exclude:announcements` |
| Message type (any of) | `text` `links` `invites` `attachments`/`files` `images` `videos` `audio` `embeds` `stickers` `mentions` `replies` `emoji` |
| Exclude a type | `-images`, `no:links` |
| Words | `contains:"my address"` (repeat = any of), `except:"keep this"`, `regex:pattern` |
| Time | `newer:7d`, `older:30d` (`s m h d w mo y`), `after:2025-01-01`, `before:2025-06-30` |
| Length | `minlen:5`, `maxlen:200` |
| Other | `pinned` (pinned messages are kept unless you add this), `preview` (count only), `scan:5000` (max messages read per channel) |

**Examples**
```
&wipe @someone all                                   # everything they ever sent
&wipe @someone 500 #general images links             # their newest 500 images/links in #general
&wipe 123456789012345678 all older:30d -#announcements   # works even after they left the server
&wipeme all contains:"my number" preview             # see how many of your messages mention it
```

**Safety:** `&wipe` needs *Manage Messages*, and it only scans channels where both you and Bell have that permission. You can't wipe someone whose top role is equal to or higher than yours, or the server owner. Only one wipe runs per server at a time. `&wipeme` is **off by default**; a server manager turns it on with `&selfwipe on`, and each member can use it once every 10 minutes.

## Features

- `&pb`: deletes bot/webhook messages from the most recent 20 messages in the current channel.
- `&pba`: deletes all bot/webhook messages from the current channel.
- `&clear <amount>`: bulk deletes recent messages.
- `&bulkdelete <#channel> <amount>`: bulk deletes messages in a specific channel.
- `&wipe <@user|id> [amount|all] [filters]` / `&wipeme`: delete one person's messages across the server with filters (see **Message Wipe** above).
- `&kick`, `&ban`, `&unban`
- `&mute`, `&unmute` (Discord timeout based)
- `&lock`, `&unlock`, `&slowmode`
- `&warn`, `&warnings`, `&clearwarns` (stored in `data/warnings.json`)
- `&automod <on|off|toggle|status>` (moderators can control AutoMod per server)
- `&setgenderroles <@male_role> <@female_role>` for per-server `aicrush` mapping
- `&genderroles`, `&cleargenderroles`
- Auto moderation:
  - blocked words from `data/bad_words.txt`
  - link blocking
  - spam detection + automatic timeout
- Mod-log channel support:
  - `&setmodlog [#channel]`
  - `&clearmodlog`
  - logs both manual moderation actions and automod actions
- `&reloadbadwords` to reload bad word entries without restarting the bot
- Utility/fun commands:
  - `&ping`
  - `&avatar [@member]`
  - `&userinfo [@member]`
  - `&serverinfo`
  - `&poll Question | Option 1 | Option 2`
  - `&snipe`
  - `&remind <minutes> <text>`
  - DM the bot with `remove timeout` to remove your active timeout (if bot has permission)
- AI commands:
  - `&ai <prompt>` or `&ask <prompt>`
  - `&aisummary [count]`
  - `&catchup [hours]`
  - `&catchupchannel <#channel> [hours]`
  - `&serverinsights [hours]` (Manage Server permission required)
  - `&aireset`
  - `&aimodel`
  - `&aimodels [limit]`
  - `&roast @user [soft|friendly|brutal]`
  - `&serverlore`
  - `&aicrush @user`
  - `&analyze @user`
  - `&lie_detector @user <message>`
  - `&futureme`
  - `&rizzcoach [smooth|funny|mysterious] <message>`
  - `&argument <topic>`
  - `&debate @user <topic>`
- Business Empire commands:
  - `&balance`, `&dailyclaim`, `&portfolio`, `&networth`
  - `&stocks`, `&market [symbol]`, `&buy <symbol> <qty>`, `&sell <symbol> <qty>`
  - `&commodities`, `&buycommodity <symbol> <qty>`, `&sellcommodity <symbol> <qty>`
  - `&crypto`, `&buycrypto <symbol> <qty>`, `&sellcrypto <symbol> <qty>`
  - `&plots`, `&buyplot <plot_id>`, `&upgrade <property_id>`, `&properties`
  - `&sellproperty <id> <price>`, `&buyproperty <id>`
  - `&loan`, `&takeloan <amount>`, `&repay <amount>`, `&debts`
  - `&startbiz <type> <name>`, `&mybiz`, `&bizhire <id> <count>`, `&bizfire <id> <count>`, `&bizexpand <id>`
  - `&salary`, `&taxes`, `&filetax [amount]`, `&credit`, `&markethalt`, `&economystatus`
  - `&trade ...`, `&trade_accept <id>`, `&trade_decline <id>`
  - `&auction_start ...`, `&bid <auction_id> <amount>`, `&auctions`
  - `&bizleaderboard [cash|networth|income]`, `&bizprofile [@user]`, `&marketnews`, `&ledger [@user]`
  - `&bizadmin ...` (moderator-only economy controls)
- Vibe commands:
  - `&myvibe [count]`
  - `&vibe @user [count]`
  - `&vibecheck @user`
- Music commands:
  - `&join`, `&leave`
  - `&play <youtube/spotify link or search>`
  - `&skip`, `&pause`, `&resume`, `&stop`
  - `&queue`, `&nowplaying`
  - Spotify playlist links are supported
- `&help`

Most new AI fun commands are hybrid, so you can use both prefix (`&...`) and slash (`/...`) after command sync.

## Setup

1. Create and activate a virtual environment (recommended).
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and set `DISCORD_BOT_TOKEN`.
4. If using AI features, set one provider:
   - OpenRouter:
     - `AI_PROVIDER=openrouter`
     - `OPENROUTER_API_KEY=...`
   - Groq:
     - `AI_PROVIDER=groq`
     - `GROQ_API_KEY=...`
5. If using music features:
   - Make sure `ffmpeg` is installed on your host.
   - For Spotify links/playlists, set:
     - `SPOTIFY_CLIENT_ID=...`
     - `SPOTIFY_CLIENT_SECRET=...`
6. Enable bot intents in Discord Developer Portal:
   - `MESSAGE CONTENT INTENT`
   - `SERVER MEMBERS INTENT`
7. Run:
   ```bash
   python bot.py
   ```

## Optional Environment Variables

- `MOD_LOG_CHANNEL_ID=` fallback mod-log channel id if `&setmodlog` is not used.
- `BOT_ACTIVITY_TEXT=with your crush`
- `AUTOMOD_ENABLED=false`
- `AUTOMOD_BLOCK_LINKS=true`
- `AUTOMOD_SPAM_MSG_THRESHOLD=6`
- `AUTOMOD_SPAM_INTERVAL_SECONDS=8`
- `AUTOMOD_SPAM_TIMEOUT_MINUTES=5`
- `OPENROUTER_API_KEY=`
- `OPENROUTER_MODEL=google/gemma-3-4b-it:free`
- `OPENROUTER_API_URL=https://openrouter.ai/api/v1/chat/completions`
- `OPENROUTER_MODELS_URL=https://openrouter.ai/api/v1/models`
- `OPENROUTER_APP_NAME=Discord Mod Bot`
- `OPENROUTER_HTTP_REFERER=`
- `AI_PROVIDER=openrouter`
- `GROQ_API_KEY=`
- `GROQ_MODEL=llama-3.1-8b-instant`
- `GROQ_API_URL=https://api.groq.com/openai/v1/chat/completions`
- `GROQ_MODELS_URL=https://api.groq.com/openai/v1/models`
- `AI_MAX_HISTORY=4`
- `AI_MAX_TOKENS=260`
- `AI_SUMMARY_MAX_TOKENS=320`
- `AI_CATCHUP_MAX_TOKENS=360`
- `AI_INSIGHTS_MAX_TOKENS=420`
- `AI_TIMEOUT_SECONDS=45`
- `SYNC_SLASH_COMMANDS=true`
- `VIBE_DEFAULT_MESSAGE_COUNT=200`
- `VIBE_MAX_MESSAGE_COUNT=800`
- `VIBE_MIN_REQUIRED_MESSAGES=25`
- `VIBE_MAX_PROMPT_MESSAGES=80`
- `VIBE_MAX_PROMPT_CHARS=12000`
- `AICRUSH_SCAN_PER_CHANNEL=450` (used when full-history scan is disabled)
- `AICRUSH_MAX_CHANNELS=0` (`0` means scan all visible text channels)
- `AICRUSH_FULL_HISTORY_SCAN=true`
- `AICRUSH_MAX_CONTEXT_CHARS=16000`
- `AICRUSH_MAX_HISTORY_MESSAGES=12000` (per-run safety cap)
- `AICRUSH_SCAN_PAUSE_EVERY=260` (small pacing interval)
- `AICRUSH_SCAN_PAUSE_SECONDS=0.12` (sleep duration for pacing)
- `AICRUSH_CACHE_SECONDS=900` (reuse recent result to avoid repeated scans)
- `BUSINESS_ENABLED=true`
- `WIPE_MAX_AMOUNT=100000` (largest number accepted for `&wipe <amount>`)
- `WIPE_CONFIRM_TIMEOUT_SECONDS=180`
- `WIPE_SELF_SERVICE_ENABLED=false` (default for `&selfwipe` when a server hasn't set it)
- `BUSINESS_STATE_FLUSH_SECONDS=30`
- `BUSINESS_GLOBAL_MODE=true`
- `BUSINESS_STARTER_CASH=10000`
- `BUSINESS_DAILY_CLAIM=1500`
- `BUSINESS_DAILY_CLAIM_STREAK_BONUS=250`
- `BUSINESS_HOURLY_INTEREST_RATE=0.0012`
- `BUSINESS_LOAN_GRACE_HOURS=24`
- `BUSINESS_MAX_DEBT_TO_NETWORTH=1.8`
- `BUSINESS_STOCK_COUNT=16`
- `BUSINESS_MARKET_EVENT_CHANCE=0.18`
- `BUSINESS_TRANSACTION_FEE_RATE=0.01`
- `BUSINESS_PROPERTY_MAINTENANCE_RATE=0.004`
- `BUSINESS_PROPERTY_TAX_RATE=0.006`
- `BUSINESS_AUCTION_SNIPING_WINDOW_SECONDS=30`
- `BUSINESS_AUCTION_SNIPING_EXTEND_SECONDS=60`
- `BUSINESS_MAX_OPEN_TRADES=5`
- `BUSINESS_MAX_OPEN_AUCTIONS=3`
- `BUSINESS_COMMAND_COOLDOWN_SECONDS=3`
- `BUSINESS_LEDGER_MAX_ENTRIES=50000`
- `BUSINESS_AI_PERSONALIZATION_ENABLED=true`
- `BUSINESS_AI_TUNING_ENABLED=true`
- `BUSINESS_AI_MAX_TOKENS=140`
- `BUSINESS_AI_PERSONALIZATION_CACHE_SECONDS=900`
- `BUSINESS_AI_DIRECTOR_INTERVAL_HOURS=3`
- `BUSINESS_SCHEMA_VERSION=2`
- `BUSINESS_MARKET_TICK_MINUTES=15`
- `BUSINESS_WORLD_EVENT_INTERVAL_MINUTES=120`
- `BUSINESS_WEEKLY_CYCLE_DAYS=7`
- `BUSINESS_EVENT_MAX_PER_DAY=6`
- `BUSINESS_ENABLE_COMMODITIES=true`
- `BUSINESS_ENABLE_CRYPTO=true`
- `BUSINESS_ENABLE_PRIVATE_BUSINESSES=true`
- `BUSINESS_CIRCUIT_BREAKER_DROP_PCT=25`
- `BUSINESS_MARKET_HALT_DROP_PCT=15`
- `BUSINESS_CAPITAL_GAINS_SHORT_RATE=0.15`
- `BUSINESS_CAPITAL_GAINS_LONG_RATE=0.10`
- `BUSINESS_CAPITAL_GAINS_LONG_HOLD_DAYS=7`
- `BUSINESS_INCOME_TAX_ENABLED=true`
- `MALE_ROLE_IDS=` (comma-separated role IDs for strict aicrush gender detection)
- `FEMALE_ROLE_IDS=` (comma-separated role IDs for strict aicrush gender detection)
- `MALE_ROLE_HINTS=` (optional extra keywords)
- `FEMALE_ROLE_HINTS=` (optional extra keywords)
- `VOICE_CONNECT_RETRIES=4`
- `VOICE_CONNECT_TIMEOUT=25`
- `VOICE_INTERNAL_RECONNECT=false`
- `WELCOME_DM_ENABLED=true`
- `WELCOME_MAX_CHANNEL_SUGGESTIONS=5`
- `CATCHUP_DEFAULT_HOURS=24`
- `CATCHUP_MAX_HOURS=168`
- `CATCHUP_MAX_MESSAGES=180`
- `INSIGHTS_DEFAULT_HOURS=48`
- `INSIGHTS_MAX_HOURS=168`
- `INSIGHTS_MAX_CHANNELS=10`
- `INSIGHTS_MAX_MESSAGES_PER_CHANNEL=350`
- `INSIGHTS_CHANNEL_SCAN_LIMIT=30`
- `ROAST_CONTEXT_TARGET_MESSAGES=220`
- `ROAST_CONTEXT_MIN_MESSAGES=35`
- `ROAST_CHANNEL_SCAN_LIMIT=14`
- `ROAST_HISTORY_PER_CHANNEL=280`
- `ROAST_CACHE_MAX_MESSAGES=1400`
- `OPENROUTER_FALLBACK_MODELS=google/gemma-3-4b-it:free,qwen/qwen3-4b:free,deepseek/deepseek-r1-0528:free`
- `GROQ_FALLBACK_MODELS=llama-3.1-8b-instant,gemma2-9b-it`
- `FFMPEG_PATH=ffmpeg`
- `MUSIC_MAX_PLAYLIST_ITEMS=50`
- `SPOTIFY_CLIENT_ID=`
- `SPOTIFY_CLIENT_SECRET=`

## Required Bot Permissions

Depending on which commands you use:
- Manage Messages
- Kick Members
- Ban Members
- Moderate Members
- Manage Channels
- Read Message History

## Notes

- `&pb` checks only the latest 20 messages and removes bot/webhook messages there.
- `&pba` scans full channel history and may take time on very large channels due to API rate limits.
- `data/bad_words.txt` is auto-created at first run; add one blocked word per line.
- AI commands work after provider key is set (`OPENROUTER_API_KEY` or `GROQ_API_KEY`).
- If your selected model becomes unavailable, bot auto-falls back to another free model.
- For fastest replies, use smaller models and lower `AI_MAX_TOKENS`.
- Spotify links require Spotify API credentials; otherwise only YouTube/search playback works.
- Spotify playlists must be Public when using client credentials (`SPOTIFY_CLIENT_ID/SECRET`).
- If hosted voice keeps failing with websocket `4006`, this is usually host/node UDP/network routing. Try another node/provider.
- Vibe reports are fun-only and may be inaccurate.
- Vibe output is paragraph-style and considers both the user’s messages and replies they receive (in the same channel window).
- Vibe analysis reads recent messages on-demand in the current channel; it does not store long-term message archives.
- New members can receive an optional AI onboarding DM with channel suggestions.
- `&catchup` summarizes missed conversation from recent hours without scanning full history.
- `&serverinsights` generates channel-level engagement insights for moderators.
- Roast now uses cached + bounded guild-wide message context for faster, more specific results.
- Business economy is persisted in `data/business_state.json` and shared globally across servers where the bot is present.
- Economy uses fast buckets: market tick every 15 minutes, world event tick every 2 hours, and weekly settlement cycle every 7 days.
- Stocks + commodities + crypto now share risk controls (cost basis, gains tax, temporary asset halts, market-wide halts).
- Private businesses settle in weekly cycles with payroll/maintenance/debt pressure and controlled liquidation on prolonged stress.
- Optional LLM market director can safely nudge economy values (market bias, event chance, small tax/fee shifts) within bounded ranges.
- Optional LLM advisor adds personalized one-line strategy tips in business commands with cache to avoid lag.
- If vibe AI times out, the bot falls back to a local heuristic narrative summary.
