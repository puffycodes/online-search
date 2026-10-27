# Stock Rebased Chart: test runs

Targeted live runs for checking the agent's judgement rules after an edit to `.claude/agents/stock-rebased-chart.md`. The agent is a prompt rather than code, so the offline pytest suite can't cover it. These cases cover the correlation step added on 2026-10-27: running `stock_risk.py` on the chart's symbols and window only when the user asks how closely they moved together.

Prices change daily, so the cases judge the agent's choices (the tickers, the window flags passed to each script, whether `stock_risk.py` ran, what it reported), not the figures. Each symbol costs one price call per script: EODHD's free plan allows 20 a day (check `https://eodhd.com/api/user` first; reading it costs nothing).

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root, make an empty scratch directory per case, and call the agent through the `Agent` tool with `subagent_type: "stock-rebased-chart"` and this prompt:

```text
{{Question}} (Today is {{Weekday}} {{YYYY-MM-DD}}.)

This is a targeted test run of your workflow. Follow it exactly as written; change nothing.

Save each command's stdout and stderr into {{Scratch Directory}} as NN-<short-name>.out and NN-<short-name>.err (NN = the order you ran it), by redirecting, then read the files. Write the chart where the workflow says to.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code, and saying why you chose each flag. Don't end with a question.
```

To check a run before a new session, a general-purpose agent on Sonnet (the agent's model) can stand in: tell it to read `.claude/agents/stock-rebased-chart.md` and follow it. Check each run against the saved `stock_risk.py` JSON (`correlations`: `a`, `b`, `sessions`, `start`, `end`, `correlation`).

## Cases

The dates below are for today = Tuesday 2026-10-27. Every case ran on 2026-10-27 through a general-purpose stand-in on Sonnet, with `PRICE_PROVIDER=yahoo` set in `.env`, so the prices came from Yahoo; every correlation reported matched the saved output.

### 1. No correlation asked

- **Rule:** run `stock_risk.py` only when the user asks how closely the instruments moved together.
- **Question:** `Compare Apple and Microsoft this year.`
- **A correct run:** `stock_rebased_chart.py AAPL MSFT --range ytd -o /tmp/rebased_AAPL_MSFT.png` and nothing else; no correlation in the report.
- **Last checked:** 2026-10-27, passed: only the chart command ran; "the correlation step was skipped because the question didn't ask how closely they moved together".

### 2. Correlation asked, default window

- **Rules:** run `stock_risk.py` with the same symbols in the same order; with no window on the chart, pass `--range 6mo` (not `stock_risk.py`'s `1y` default); a plain reading of each number; correlation isn't where the lines end up, nor causation.
- **Question:** `Chart Shell and BP for me. How closely do they move together?`
- **A correct run:** `stock_rebased_chart.py SHEL.L BP.L -o /tmp/rebased_SHEL_L_BP_L.png`, then `stock_risk.py SHEL.L BP.L --range 6mo --json`; the report gives the correlation with its reading and window after the chart summary.
- **Last checked:** 2026-10-27, passed: both commands as above; "+0.86, so they moved closely together day to day", over 2026-04-27 to 2026-10-23 (127 shared sessions); "here they track each other but end about 12 points apart"; "correlation does not mean one drives the other".

### 3. Crypto against an index, a named start

- **Rules:** the chart's `--start` / `--end` passed unchanged; no `--benchmark` when two instruments are compared with each other; mention the shared sessions when far fewer than the window (crypto trades at weekends).
- **Question:** `Does Bitcoin move with the Nasdaq? Chart them since June.`
- **A correct run:** `stock_rebased_chart.py BTC-USD ^IXIC --start 2026-06-01 [--end …] -o …`, then `stock_risk.py BTC-USD ^IXIC` with the same window flags and `--json`; the report names the shared sessions against Bitcoin's own count.
- **Last checked:** 2026-10-27, passed: both with `--start 2026-06-01 --end 2026-10-27`, no benchmark; "+0.44 … 103 shared sessions against 149 BTC sessions, because crypto trades every day and the Nasdaq does not", read as "somewhat together", with the not-where-they-end and not-causation lines.

## Found on 2026-10-27

All three passed with no change to the agent. The stand-ins also noted that `-o /tmp/...` lands in the user's temp folder on Windows (`Wrote C:/Users/.../AppData/Local/Temp/...`); the agent reports the path the tool printed, so this is harmless.

## Not covered

- A benchmark with the correlation (`--benchmark` passed to both scripts); the benchmark joins every pair in `stock_risk.py`.
- `stock_risk.py` failing after the chart succeeded (keep the chart, report the error).
