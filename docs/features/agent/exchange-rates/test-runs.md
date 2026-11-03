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

The dates below are for today = Tuesday 2026-10-27. Every case ran on Sonnet, the agent's model, on the day the agent was added; every figure reported matched the saved output.

### 1. Converting an amount

- **Rules:** names to codes; "X in Y" is base X; `--amount`; the converted amount in the currency's usual decimals with the rate and its date; the reference-rate caveat when converting money.
- **Question:** `How much is 250 US dollars in Singapore dollars? I'm sending it to a friend.`
- **A correct run:** `exchange_rates.py USD SGD --amount 250 --json`, no window flag; the report leads with `250 USD = <n> SGD` to 2 decimals, gives the rate and its date as the latest published, adds one line that a bank or transfer service adds a spread, and ends with the Frankfurter credit.
- **Last checked:** 2026-10-27, passed: `USD SGD --amount 250`, `250 USD = 319.85 SGD` at 1.2794, "the latest published rate, dated 27 October 2026", the spread caveat ("your friend will likely receive somewhat less") and the credit. Rerun after the 2026-10-27 tightening (see below): passed, the same, caveat kept. Rerun on the agent itself in a new session: passed, `USD SGD --amount 250`, `250 USD = 319.88 SGD` at 1.2795 (saved `converted` 319.875), the spread caveat and the credit.

### 2. A dollar settled by context

- **Rule:** a bare "dollar" is USD unless context names another dollar.
- **Question:** `I'm in Sydney. How many dollars will I get for 100 euros?`
- **A correct run:** `exchange_rates.py EUR AUD --amount 100 --json`; the report says it used the Australian dollar because of Sydney (naming USD as the alternative is fine), not USD silently.
- **Last checked:** 2026-10-27, passed: `EUR AUD --amount 100`, `100 EUR = 159.60 AUD` at 1.596, "you are in Sydney, so I used the Australian dollar", with USD offered as the alternative.

### 3. The user's framing

- **Rules:** "how many Y to the X" means base X; answer in the user's framing.
- **Question:** `How many yen to the dollar right now?`
- **A correct run:** `exchange_rates.py USD JPY --json`; the report gives `1 USD = <n> JPY`, not the inverse, with its date.
- **Last checked:** 2026-10-27, passed: `USD JPY`, `1 USD = 157.27 JPY`, the latest published, dated 27 October 2026. It also added the reference-rate spread line, which the agent asks for only when money is being converted; harmless. Rerun after the tightening (see below): passed, no caveat. Rerun on the agent itself in a new session: passed, `USD JPY`, `1 USD = 157.29 JPY` dated 27 October 2026, no caveat ("a plain rate question and not an amount being exchanged").

### 4. One past date

- **Rules:** a named date becomes `--date`; give the returned date, and say if it differs from the one asked for.
- **Question:** `What was the USD/JPY rate on 1 March 2020?`
- **A correct run:** `exchange_rates.py USD JPY --date 2020-03-01 --json` (a Sunday); the report gives the rate with the date the tool returned, and says so if it isn't 1 March 2020.
- **Last checked:** 2026-10-27, passed: `USD JPY --date 2020-03-01`, `1 USD = 109.0 JPY`; the returned date was the date asked for, and it noted the day was a Sunday.

### 5. A long period, grouped

- **Rules:** a period becomes `--start` (no `--end` while it is still running); over about 3 months add `--group week`; report the first and last rates, the change as a percentage, and the high and low with their dates; say the figures are weekly; no table for this many rows.
- **Question:** `How has the pound moved against the euro this year?`
- **A correct run:** `exchange_rates.py GBP EUR --start 2026-01-01 --group week --json`; the report gives the first and last weekly rates, the % change computed from them, the high and low weeks, says the figures are one per week, and makes no prediction.
- **Last checked:** 2026-10-27, passed: `GBP EUR --start 2026-01-01 --group week` (43 weekly points), first 1.1471 (1 January) and last 1.1907 (22 October, "not a rate for today"), +3.80%, high 1.1907 on 22 October and low 1.1453 on 26 February, "one figure per week", no table, "not a prediction". It added "each weekly figure is the rate on the date shown", which Frankfurter's docs don't say; a small overstatement. Rerun after the tightening (see below): passed, the same figures, "one per week, labelled with each week's first date", with no claim about how each is chosen. Rerun on the agent itself in a new session: passed, the same command and figures, "one per week, each labelled with the week's first date", the last figure "not a rate for 27 October", no table, "not a prediction".

### 6. A forecast question

- **Rule:** don't forecast; give the recent movement and say it isn't a prediction.
- **Question:** `Will the yen get stronger against the dollar next month?`
- **A correct run:** either runs a recent period (e.g. `USD JPY --start <a few months back>`) and describes the movement, or runs nothing; either way it says it can't predict the rate and makes no forecast.
- **Last checked:** 2026-10-27, passed: opened with "I can't tell you whether the yen will get stronger … I don't forecast", then ran `USD JPY --start 2026-09-27` for the past month: 158.11 to 157.27 (-0.53%), high 158.45 on 14 October, low 157.00 on 25 October, and "a month of data like this says nothing reliable about the next month".

### 7. Not a currency

- **Rules:** don't guess a code; report an unknown currency plainly.
- **Question:** `Convert 10 zorkmids to dollars.`
- **A correct run:** says zorkmids aren't a currency it can look up, either without running the tool or after one run that returns `HTTP 422: invalid currency: ...`; it doesn't substitute another currency.
- **Last checked:** 2026-10-27, passed: one run, `ZORKMID USD --amount 10`, exit 1 with `HTTP 422: invalid currency: ZORKMID`; it said zorkmids are a fictional currency and converted nothing.

### 8. A retired currency

- **Rule:** an empty result is reported plainly, not filled in.
- **Question:** `What's the Croatian kuna worth in euros today?`
- **A correct run:** `exchange_rates.py HRK EUR --json` returns no rates (checked on 2026-10-27: `HRK` has past rates but no current one). The report says there is no current rate, and may say the euro replaced the kuna in 2023 (at the fixed 7.53450 kuna per euro); it gives no made-up current rate.
- **Last checked:** 2026-10-27, passed: `HRK EUR` returned no rates; it said there is no current rate because the euro replaced the kuna in 2023, and gave no figure (it didn't mention the fixed conversion rate, which the case leaves optional).

## Found on 2026-10-27

The first runs passed, with two slips: case 3 added the reference-rate spread line to a plain rate question, and case 5 said each weekly figure is the rate on its date, which Frankfurter's docs don't say. The agent's reporting rules were tightened the same day: the spread caveat is for an amount of money being spent, sent or exchanged only, with the cases it must be left out of named, and grouped figures are described as labelled with each period's first date, without saying how a figure is chosen. Cases 1, 3 and 5 were rerun after the edit by a general-purpose agent on Sonnet told to read `.claude/agents/exchange-rates.md` and follow it (the edit might not reach the agent itself until a new session), and all three passed. They were rerun the same day on the `exchange-rates` agent itself in a new session, and all three passed again, with every figure matching the saved output.

## Not covered

- A transient network failure (retry at most once); it can't be forced from the command line.
- Routing between this agent and `stock-price-history` for currency-pair questions; that is the main session's choice, not the agent's.
