# Stock Trend: test runs

Targeted live runs for checking the agent's judgement rules after an edit to `.claude/agents/stock-trend.md`. The agent is a prompt rather than code, so the offline pytest suite can't cover it. These cases cover the risk line added on 2026-10-27 (volatility and worst fall, from the prices already fetched) and the window and reporting rules around it.

Prices change daily, so the cases judge the agent's choices (the ticker, the window, the file path, what it reported and left out), not the figures. Each run makes one price call: EODHD's free plan allows 20 a day (check `https://eodhd.com/api/user` first; reading it costs nothing).

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root, make an empty scratch directory per case, and call the agent through the `Agent` tool with `subagent_type: "stock-trend"` and this prompt:

```text
{{Question}} (Today is {{Weekday}} {{YYYY-MM-DD}}.)

This is a targeted test run of your workflow. Follow it exactly as written; change nothing.

Save each command's stdout and stderr into {{Scratch Directory}} as NN-<short-name>.out and NN-<short-name>.err (NN = the order you ran it), by redirecting, then read the files. Where the workflow writes its own price file, keep that as written and also copy it into the scratch directory.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code, and saying why you chose each flag. Don't end with a question.
```

To check a run before a new session, a general-purpose agent on Sonnet (the agent's model) can stand in: tell it to read `.claude/agents/stock-trend.md` and follow it. Check each run against the saved price file and the snippet's output (`volatility` and `worst fall` lines).

## Cases

The dates below are for today = Tuesday 2026-10-27. Both cases ran on 2026-10-27 through a general-purpose stand-in on Sonnet, with `PRICE_PROVIDER=yahoo` set in `.env`, so the prices came from Yahoo.

### 1. A stock, default window

- **Rules:** no window named → `--range 6mo`; the verdict, then one line on the ride (volatility a year, the worst fall with its dates, recovered or not); the shorter windows when they disagree.
- **Question:** `Is Nvidia trending up?`
- **A correct run:** `stock_price_history.py NVDA --range 6mo --json`; the report gives the verdict with its dates, one line with the volatility (252 sessions a year) and the worst fall with its peak, trough and recovery dates, and no more on risk than that line.
- **Last checked:** 2026-10-27, passed on the risk rules: `NVDA --range 6mo` (127 sessions), "up" overall but down over the last 20 and 5 sessions, -0.3% over the span (it explained the "up" is the fitted line, not a net gain), "about 39% annualized volatility … the worst fall was 19.3% from the 2026-05-14 high to the 2026-07-29 low, and the price got back to that peak on 2026-10-05", all matching the snippet's output. The snippet first failed with `FileNotFoundError: /tmp/stock_trend.json` (see below).

### 2. Crypto, "lately"

- **Rules:** "lately" → `--range 3mo`; crypto volatility over 365 sessions a year; a worst fall that hasn't recovered; today's bar called still-moving.
- **Question:** `Which way has Bitcoin been heading lately?`
- **A correct run:** `stock_price_history.py BTC-USD --range 3mo --json`; the snippet prints `365 sessions/year`; the report says the worst fall hasn't recovered, and that the last price is today's still-moving bar.
- **Last checked:** 2026-10-27, passed on the risk rules: `BTC-USD --range 3mo` (93 sessions), up overall (+25.1%) but down over the last 20 and 5, "about 38% annualized volatility (365 sessions a year)", "the worst fall was 7.9%, from 2026-09-21 to 2026-10-27, and it has not yet recovered … that trough is today's bar", and today's bar "still moving". It hit the same `/tmp` failure, then read case 1's NVDA file, which had overwritten the shared `/tmp/stock_trend.json`; it noticed, restored its own file and reran.

## Found on 2026-10-27

- **The price file path.** The agent wrote `/tmp/stock_trend.json` from Git Bash and opened `"/tmp/stock_trend.json"` inside Python. On Windows those are different folders (Git Bash's `/tmp` is the user's temp folder; Python reads `C:\tmp`), so the snippet couldn't find the file; and one fixed name let two runs at once overwrite each other. Fixed the same day: the file is named after the symbol (`/tmp/stock_trend_<SYMBOL>.json`) and passed to the snippet as an argument (`python3 - /tmp/stock_trend_<SYMBOL>.json`), which Git Bash translates for Python. The fixed snippet was checked on case 2's saved prices and gave the same figures; the cases haven't been rerun through the agent since.
- **The source caveat with `PRICE_PROVIDER=yahoo`.** Both stand-ins noted that the agent's closing caveat names EODHD, and that its `notes` rule reads any note as a shorter history, while these runs' note was about the Yahoo source. Not changed here.

## Not covered

- A window too short for the volatility (under 3 sessions) or with no fall at all; the snippet's handling of both was checked offline on synthetic prices.
- An Indian stock (raw closes, as Alpha Vantage has no adjusted close on the free plan).
