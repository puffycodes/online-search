# Exchange Rates: test runs

Targeted live runs for checking the agent's judgement rules after an edit to `.claude/agents/exchange-rates.md` or to `exchange_rates.py`. The agent is a prompt rather than code, so the offline pytest suite can't cover it. Its judgement is in turning names and wording into the tool's arguments (currency codes, which side is the base, the window and its grouping) and in what it reports (dates, rounding, the reference-rate caveat, no forecasts), so each case gives one fixed question chosen to exercise a rule. The questions state today's date, so a case can be rerun later by changing it.

These are live rates, so the figures change; the cases judge the agent's choices (the codes, flags and window it passed, and what it reported), not the rates.

## How to run a case

Agent edits only take effect in sessions started after the edit. Start a new Claude Code session from the repo root, make an empty scratch directory per case, and call the agent through the `Agent` tool with `subagent_type: "exchange-rates"` and this prompt:

```text
{{Question}} (Today is {{Weekday}} {{YYYY-MM-DD}}.)

This is a targeted test run of your workflow. Follow it exactly as written; change nothing.

Save each command's stdout and stderr into {{Scratch Directory}} as NN-<short-name>.out and NN-<short-name>.err (NN = the order you ran it), by redirecting, e.g. `python3 exchange_rates.py ... --json > DIR/01-fx.out 2> DIR/01-fx.err; echo "exit=$?"`, then read the files.

End your report with a "Run notes" section listing every command you ran, in order, exactly as typed, with its exit code, and saying why you chose each flag. Don't end with a question.
```

For a case where the workflow would ask the user something, add: "If your workflow says to ask the user something, don't ask: say in your report what you would have asked, and carry on with what the workflow allows without an answer." Check each run against the saved `.out` / `.err` files (`base`, `quotes`, `amount`, `date` / `start` / `end` / `group`, and each rate's `date`, `rate` and `converted`).

## Cases

The dates below are for today = Tuesday 2026-10-27. None has been run yet: the agent was added on 2026-10-27, and its first runs need a new session.

### 1. Converting an amount

- **Rules:** names to codes; "X in Y" is base X; `--amount`; the converted amount in the currency's usual decimals with the rate and its date; the reference-rate caveat when converting money.
- **Question:** `How much is 250 US dollars in Singapore dollars? I'm sending it to a friend.`
- **A correct run:** `exchange_rates.py USD SGD --amount 250 --json`, no window flag; the report leads with `250 USD = <n> SGD` to 2 decimals, gives the rate and its date as the latest published, adds one line that a bank or transfer service adds a spread, and ends with the Frankfurter credit.
- **Last checked:** not yet run.

### 2. A dollar settled by context

- **Rule:** a bare "dollar" is USD unless context names another dollar.
- **Question:** `I'm in Sydney. How many dollars will I get for 100 euros?`
- **A correct run:** `exchange_rates.py EUR AUD --amount 100 --json`; the report says it used the Australian dollar because of Sydney (naming USD as the alternative is fine), not USD silently.
- **Last checked:** not yet run.

### 3. The user's framing

- **Rules:** "how many Y to the X" means base X; answer in the user's framing.
- **Question:** `How many yen to the dollar right now?`
- **A correct run:** `exchange_rates.py USD JPY --json`; the report gives `1 USD = <n> JPY`, not the inverse, with its date.
- **Last checked:** not yet run.

### 4. One past date

- **Rules:** a named date becomes `--date`; give the returned date, and say if it differs from the one asked for.
- **Question:** `What was the USD/JPY rate on 1 March 2020?`
- **A correct run:** `exchange_rates.py USD JPY --date 2020-03-01 --json` (a Sunday); the report gives the rate with the date the tool returned, and says so if it isn't 1 March 2020.
- **Last checked:** not yet run.

### 5. A long period, grouped

- **Rules:** a period becomes `--start` (no `--end` while it is still running); over about 3 months add `--group week`; report the first and last rates, the change as a percentage, and the high and low with their dates; say the figures are weekly; no table for this many rows.
- **Question:** `How has the pound moved against the euro this year?`
- **A correct run:** `exchange_rates.py GBP EUR --start 2026-01-01 --group week --json`; the report gives the first and last weekly rates, the % change computed from them, the high and low weeks, says the figures are one per week, and makes no prediction.
- **Last checked:** not yet run.

### 6. A forecast question

- **Rule:** don't forecast; give the recent movement and say it isn't a prediction.
- **Question:** `Will the yen get stronger against the dollar next month?`
- **A correct run:** either runs a recent period (e.g. `USD JPY --start <a few months back>`) and describes the movement, or runs nothing; either way it says it can't predict the rate and makes no forecast.
- **Last checked:** not yet run.

### 7. Not a currency

- **Rules:** don't guess a code; report an unknown currency plainly.
- **Question:** `Convert 10 zorkmids to dollars.`
- **A correct run:** says zorkmids aren't a currency it can look up, either without running the tool or after one run that returns `HTTP 422: invalid currency: ...`; it doesn't substitute another currency.
- **Last checked:** not yet run.

### 8. A retired currency

- **Rule:** an empty result is reported plainly, not filled in.
- **Question:** `What's the Croatian kuna worth in euros today?`
- **A correct run:** `exchange_rates.py HRK EUR --json` returns no rates (checked on 2026-10-27: `HRK` has past rates but no current one). The report says there is no current rate, and may say the euro replaced the kuna in 2023 (at the fixed 7.53450 kuna per euro); it gives no made-up current rate.
- **Last checked:** not yet run.

## Not covered

- A transient network failure (retry at most once); it can't be forced from the command line.
- Routing between this agent and `stock-price-history` for currency-pair questions; that is the main session's choice, not the agent's.
