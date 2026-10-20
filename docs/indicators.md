# Price indicators — plain-English guide

The functions in [`../indicators.py`](../indicators.py) take a list of prices
(usually daily closing prices, **oldest day first**) and turn it into something
easier to read. A "session" just means one trading day.

They all **describe the past**. None of them forecasts the future — they smooth,
compare, or summarise numbers that have already happened.

Sections 1–6 are about **direction** (where the price has been heading).
Sections 7–10 are **risk metrics**: they describe how **bumpy** the ride was —
how big the daily swings were, how deep the worst fall went, and whether two
prices tended to move together.

Quick map:

| Function | In one sentence |
|---|---|
| `moving_average` | The average price over the last N days, redrawn every day. |
| `price_vs_moving_average` | Is today's price above or below that average? |
| `moving_average_cross` | Which is on top: a fast (short) average or a slow (long) one? |
| `moving_average_cross_flip` | Flags the exact day the fast/slow order switches. |
| `rebase` | Redraws the whole series as a ratio to one chosen day, so that day reads 100. |
| `trend` | One word for a stretch of prices: `up`, `down`, or `flat`. |
| `returns` | Each day's change from the day before, as a fraction (`0.02` = up 2%). |
| `volatility` | How widely the price swung day to day, as a yearly percentage. |
| `max_drawdown` | The worst fall from a high to a later low, and whether it has recovered. |
| `correlation` | How closely two prices moved together, from −1 to +1. |

---

## 1. Moving average — `moving_average(prices, n)`

**What it tells you.** Instead of reacting to every daily wobble, you look at the
average of the last `n` days. Recomputed each day, these averages trace a smooth
line that shows the underlying direction.

**How to picture it.** A 10-day moving average answers "where has the price been
sitting, on average, over the last two weeks?" Each new day drops the oldest
price and adds the newest, so the line glides along.

**Example.**

```
prices:        1   2   3   4   5
3-day average: –   –   2   3   4
```

The first two days are blank (`None`) because you need three days of history
before the first 3-day average exists. Day 3's value is (1+2+3)/3 = 2, day 4's is
(2+3+4)/3 = 3, and so on.

**How to read it.**
- A **rising** average line means prices have been drifting up; a falling line,
  down.
- A **short** window (10, 20 days) stays close to the price and turns quickly. A
  **long** window (50, 200 days) is slower and smoother — better for the big
  picture, worse for spotting a fresh change.

**Watch out.** It *lags*. Because it averages the past, the line only turns
*after* the price has already changed direction.

---

## 2. Price vs. moving average — `price_vs_moving_average(prices, n)`

**What it tells you.** For each day, whether the closing price finished `"above"`,
`"below"`, or `"equal"` to its own `n`-day moving average.

**How to read it.** Price **above** its average = trading stronger than its recent
norm (often read as a positive sign). **Below** = weaker. Take the **last** value
in the list for today's reading.

**Example.**

```
prices:          10   10   10    7    13
vs 3-day average: –    –  equal below above
```

On the last day, 13 is compared with the average of (10, 7, 13) = 10, so it's
`"above"`.

**Watch out.** When the price is hovering right on its average, this flips
between `"above"` and `"below"` on tiny moves. One reading on its own is noise —
it's more useful as "price has been above its average for weeks."

---

## 3. Moving-average cross — `moving_average_cross(prices, fast, slow)`

**What it tells you.** It compares **two** moving averages — a `fast` (short)
one and a `slow` (long) one — and reports which is higher each day: `"above"`
means the fast average is above the slow one, `"below"` the opposite.

**Why two averages.** The fast average reflects *recent* momentum; the slow
average reflects the *longer* trend. When the fast one climbs above the slow one,
recent momentum has become stronger than the long-run trend — often read as an
uptrend taking hold. When it drops below, momentum is fading.

**The famous version.** With `fast=50` and `slow=200` days, the fast average
rising above the slow one is nicknamed a **"golden cross"** (bullish); dropping
below is a **"death cross"** (bearish).

**Example.**

```
prices:            1   2   3   4   5   6      (fast=2, slow=4)
fast vs slow MA:   –   –   –  above above above
```

The first three days are blank because the slow (4-day) average needs four days
of data before it exists.

**How to read it.** The value itself (`above` / `below`) tells you the current
alignment. The moment the value *changes* is the event traders name — and that's
what the next function isolates.

---

## 4. Moving-average cross "flip" — `moving_average_cross_flip(prices, fast, slow)`

**What it tells you.** A simple **yes/no** for each day: `True` only on the day
the cross switches sides (fast goes from below the slow to above it, or vice
versa). Every other day is `False`.

**Why it exists.** Rather than eyeballing a long `above / above / below / …` list
to find where it changed, this hands you the change days directly. On the
candlestick chart these are the green up-arrows and red down-arrows.

**"A few equals in between are ignored."** If the two averages land exactly equal
for a day or two while crossing over, the flip is still reported on the day the
new side first appears — the brief ties are stepped over.

**Example.**

```
prices:   3    1    1    2    3        (fast=1, slow=2)
flip:    None False False True False
```

The `True` marks the day the fast average finished above the slow one for the
first time.

**The three possible values.**
- `True` — the order flipped **today**.
- `False` — no flip today (unchanged, or still settling on a tie).
- `None` — not enough data yet for both averages to exist.

**Watch out.** With a short pair like `fast=5, slow=20`, the averages cross back
and forth constantly in a choppy market ("whipsaw") — you get lots of arrows,
most of them meaningless. Wider pairs (50/200) flip rarely but meaningfully.

---

## 5. Rebasing — `rebase(prices, n=0)`

**What it tells you.** Not a signal — a change of units. It redraws the whole
series as a **ratio to one chosen day**, scaled so that day reads exactly 100.
Every other value becomes "what 100 units invested on that day would be worth
today."

**Why it exists.** Raw prices don't compare well across different stocks — a
$900 stock and a $9 stock can't be eyeballed on the same chart, and neither
tells you which one has *performed* better. Rebasing both to 100 on the same
starting day turns the comparison into "which line climbed higher," regardless
of the starting share price or the currency it's quoted in.

**How to picture it.** Pick day `n` (by default the very first day in the
list). Divide every price — including day `n` itself — by the price on day
`n`, then multiply by 100.

**Example.**

```
prices:   50   100   150
rebased:  100  200   300
```

Day 0 was 50; by day 2 the price had tripled, so the rebased line reads 300 —
a 200% gain since day 0, read straight off the chart without doing the percent
maths yourself.

**Picking a different base day.** Pass `n` to rebase against any day in the
series, not just the first:

```
prices:            50   100   150
rebased (n=1):     50   100   150
```

Rebasing against day 1 (itself worth 100 before rescaling, coincidentally)
leaves this particular series unchanged — the point is that `n` can be
whichever day you want to treat as "the start," e.g. the day you'd have bought
in, or a date shared across several stocks you're comparing (see
[`stock_rebased_chart.py`](../README.md#stock_rebased_chartpy), which does
exactly this for a handful of tickers at once).

**How to read it.** Above 100 = up since the base day; below 100 = down.
Compare two rebased lines directly — whichever sits higher has done better
*since that specific day*, even if its raw price is much lower or higher than
the other stock's.

**Watch out.** The verdict is entirely relative to the base day you chose. The
same two stocks can look completely different rebased from last month versus
rebased from last year — there's no "correct" base day, only the one that
answers the question you're actually asking. It also divides by the base
day's price, so a base day priced at exactly zero (not realistic for a stock,
but worth knowing) would fail rather than produce a number.

---

## 6. Trend — `trend(prices, window=None, flat_threshold=0.01)`

**What it tells you.** One word for a run of prices: `"up"`, `"down"`, or
`"flat"`.

**How it decides.** It draws the single straight line that best fits through all
the prices (a "line of best fit"), then looks at which way that line tilts and by
how much. If the total rise or fall implied by the line is tiny — by default less
than **1% of the average price** — it calls the series `"flat"`, treating the
slope as noise. Otherwise the direction of the tilt decides `up` vs `down`.

**The two optional dials.**
- `window=N` — only consider the **last N days** (e.g. `window=20` for "the last
  month or so").
- `flat_threshold` — how big a move must be to count as a real trend. `0.01` =
  1%. **Raise** it to ignore weak drifts; **lower** it to be more sensitive.

**Example.**

```
trend([1, 2, 3, 4, 5])   ->  "up"
trend([5, 4, 3, 2, 1])   ->  "down"
trend([10, 10, 10, 10])  ->  "flat"
```

**Watch out.** It's a summary of the past, and it depends heavily on the window
you choose. A stock can be `"up"` over six months while the last two weeks are
`"down"` — checking a couple of windows tells you more than any single verdict.

---

## 7. Returns — `returns(prices)`

**What it tells you.** For each day, how much the price changed since the day
before, as a fraction: `0.02` means up 2%, `-0.05` means down 5%. The first day
is blank (`None`) because there's no earlier day to compare it with.

**Why it exists.** Prices themselves aren't comparable across stocks — a $5 move
is huge for a $20 stock and tiny for a $900 one. Percent changes are. The three
risk metrics below are built on these daily changes rather than on raw prices.

**Example.**

```
prices:   100   150    75
returns:   –    0.5  -0.5
```

From 100 to 150 is up 50% (`0.5`); from 150 to 75 is down 50% (`-0.5`).

**Watch out.** A fall of 50% followed by a rise of 50% does **not** get you back
to where you started: 100 → 50 → 75. The percentages don't simply add up.

---

## 8. Volatility — `volatility(prices, periods_per_year=252)`

**What it tells you.** How widely the price swung from day to day — one number,
written as a yearly percentage. `0.24` means "24% a year."

**How it decides.** It takes the daily returns (section 7) and measures how
spread out they are around their own average (the statistician's "standard
deviation"). A stock that moves ±0.3% most days has low volatility; one that
jumps ±4% has high volatility. That daily figure is then scaled up to a yearly
one by multiplying by the square root of the number of trading days in a year
(about 252), so a 3-month and a 1-year measurement read on the same scale.

**Rough sense of scale.** These vary a lot, but as a loose guide: big, steady
companies are often somewhere around 15–30% a year; small or speculative
companies and cryptocurrencies run well above that; major currency pairs are
often under 10%.

**The dial.** `periods_per_year` says how many data points make a year: 252 for
daily stock prices (the default), 365 for a crypto coin that trades every day,
52 for weekly prices, 12 for monthly. Pass `1` to get the plain day-to-day
figure without scaling it up.

**Example.**

```
volatility([10, 10, 10])                          ->  0.0    (never moved)
volatility([100, 150, 75], periods_per_year=1)    ->  0.707  (huge daily swings)
```

**Watch out.**
- It treats a jump **up** exactly like a drop **down** — a stock climbing in big
  leaps scores as "volatile" too. It measures bumpiness, not loss.
- A stock rising by the same amount every day has a volatility of zero, however
  far it has risen. It's about the *swings*, not the direction.
- It describes the period you measured. A calm six months doesn't promise a calm
  next month.

---

## 9. Maximum drawdown — `max_drawdown(prices)`

**What it tells you.** The worst fall from a high point to a later low point —
"if you'd bought at the worst possible moment in this period, how much would you
have been down at the bottom?" It also tells you **when** that happened and
whether the price has since climbed back.

**How it decides.** It walks through the prices day by day, remembering the
highest price seen so far. Each day it measures how far the price sits below
that high. The biggest such gap is the maximum drawdown.

**What you get back.** Four things:
- `drawdown` — the size of the fall, as a negative fraction: `-0.25` means "down
  25% from the high." `0.0` means the price never dipped below an earlier high.
- `peak` — which day the high was (its position in the list).
- `trough` — which day the low was.
- `recovery` — the first day afterwards that the price got back to the old high,
  or `None` if it hasn't yet.

**Example.**

```
prices:   100   120    90   110
               peak trough
```

The high was 120 (day 1), the low after it 90 (day 2): a fall of 30 from 120,
which is **−25%**. The price is at 110 by the end — still below 120 — so
`recovery` is `None`.

**How to read it.** It's closer to how people actually feel risk than volatility
is: "this stock once fell 40% before coming back" is easier to picture than "its
volatility was 35%."

**Watch out.** It depends heavily on the period you look at. A 1-month window
can't show a slide that took a year, and a single bad stretch decides the whole
number. Pair it with `recovery` — a 30% fall that recovered in three weeks is a
very different story from one that hasn't recovered at all.

---

## 10. Correlation — `correlation(prices_a, prices_b)`

**What it tells you.** Whether two prices tended to move together, as a number
from **−1 to +1**:
- near **+1** — they usually rose and fell on the same days (two big oil
  companies, say);
- near **0** — no consistent link between their daily moves;
- near **−1** — one tended to rise on the days the other fell.

**How it decides.** It lines up the two stocks' daily returns (section 7) day by
day and measures how consistently they moved in step. It deliberately uses the
daily *changes*, not the prices: two stocks that both drifted up over a year
would look closely linked on raw prices, even if their day-to-day moves had
nothing to do with each other.

**Example.**

```
A:  100   150    75       (up 50%, then down 50%)
B:   10    15   7.5       (up 50%, then down 50%)   ->  correlation  +1.0
C:  100    50    75       (down 50%, then up 50%)   ->  A vs C       −1.0
```

**Lining up the days.** The two lists must be the same length and match day for
day — element 5 of each must be the same date. Stocks on different exchanges
keep different holidays, so the caller has to keep only the dates both traded
before calling this.

**When there's no answer.** If one of the prices didn't swing at all over the
period (it was flat, or rose by exactly the same percentage every day), there's
nothing to compare its moves with, and you get `None` instead of a number.

**Watch out.**
- Correlation isn't cause: two stocks can move together because the whole market
  moved, not because one affects the other.
- It shifts over time. Two stocks that moved together last year may not this
  year, especially around a market shock, when many things suddenly move together.
- It says nothing about *size*: a stock that moves 1% every time another moves
  5% can still have a correlation of +1.

---

### Also in the file

`_ols_slope` is an internal helper (it computes the slope of that line of best
fit). The leading underscore means "not part of the public toolkit" — you won't
call it directly.
