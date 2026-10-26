# Stock Deep Dive: test runs

Targeted live runs for checking the agent's judgement rules after an edit to `.claude/agents/stock-deep-dive.md` or to one of the six scripts it chains. The agent is a prompt rather than code, so the offline pytest suite can't cover it. Each case gives one fixed request chosen to exercise a rule.

These are live market data, so the figures change; the cases judge the agent's choices (which tools it ran or skipped, when it stopped, how it read and labelled the figures), not the figures. Each full run uses one of EODHD's 20 free calls a day, so keep reruns few.

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root and call the agent through the `Agent` tool with `subagent_type: "stock-deep-dive"` and this prompt:

```text
{{Request}} (Today is {{Weekday}} {{YYYY-MM-DD}}.)

This is a targeted test run of your workflow. Follow it exactly as written; change nothing.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code, and saying why you ran, retried or skipped each tool. Don't end with a question.
```

For a case where the workflow would ask the user something, add: "If your workflow says to ask the user something, don't ask: say in your report what you would have asked, and carry on with what the workflow allows without an answer." Check each run against the files in its `/tmp/deep_dive_<ticker>` directory.

## Cases

The cases were written on Monday 2026-10-26. The digest step was checked by hand that day on AAPL's six outputs (about 8 KB of digest from about 80 KB of JSON); none of the cases has been run through the agent yet.

### 1. A full US report

- **Rule:** run the fundamentals first, then the other five tools with their defaults, read the results through the digest, and write every section without a buy / sell / hold view.
- **Request:** `Give me a deep dive on Apple.`
- **A correct run:** `AAPL`; `stock_fundamental.py` first, then the other five with `--trades-only` for holders and `--range 1y` for prices; all nine report sections; the multiple-based valuation rows not presented as estimates; insider sales not read as a signal; EODHD's one-year note passed on; closes with the caveat and no verdict of its own.
- **Last checked:** not yet run.

### 2. Singapore listing: no price section

- **Rule:** skip `stock_price_history.py` for `.SI` and `.T`, and say the report has no trend or risk section because the price source doesn't cover them.
- **Request:** `Do a full stock report on DBS Group.`
- **A correct run:** `D05.SI`; five tools run, no price fetch; the trend and risk section replaced by a one-line gap; holder trade values in USD and fund values in SGD, kept apart; analyst actions described as unavailable for a non-US listing, not as no activity.
- **Last checked:** not yet run.

### 3. Not a company

- **Rule:** decline an index, currency pair, crypto coin or ETF without running anything, and point to `stock-trend` or `stock-risk`.
- **Request:** `Deep dive on the S&P 500.`
- **A correct run:** no commands run; the report says the deep dive covers company stocks only and suggests `stock-trend` / `stock-risk` for the index.
- **Last checked:** not yet run.

### 4. Unknown ticker stops early

- **Rule:** when the fundamentals check fails for a ticker the user gave, retry once, then stop without running the other five tools.
- **Request:** `Deep dive on ticker ZZZQX.`
- **A correct run:** `stock_fundamental.py ZZZQX` run twice (the ticker came from the user), both exit 1; no other tool run; the report says Yahoo returned no data for that ticker and suggests checking it.
- **Last checked:** not yet run.

### 5. User assumptions reach the valuation

- **Rule:** pass the user's stated valuation assumptions to `stock_intrinsic_value.py` as fractions, and keep the other tools on their defaults.
- **Request:** `Full report on Microsoft, valuing it at a 10% discount rate and 7% growth.`
- **A correct run:** `stock_intrinsic_value.py MSFT --discount-rate 0.10 --growth 0.07 --json`; the valuation section states those assumptions as the user's; the other tools unchanged.
- **Last checked:** not yet run.
