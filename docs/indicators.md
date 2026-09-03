# Price indicators — plain-English guide

The functions in [`../indicators.py`](../indicators.py) take a list of prices
(usually daily closing prices, **oldest day first**) and turn it into something
easier to read. A "session" just means one trading day.

They all **describe the past**. None of them forecasts the future — they smooth,
compare, or summarise numbers that have already happened.

Quick map:

| Function | In one sentence |
|---|---|
| `moving_average` | The average price over the last N days, redrawn every day. |
| `price_vs_moving_average` | Is today's price above or below that average? |
| `moving_average_cross` | Which is on top: a fast (short) average or a slow (long) one? |
| `moving_average_cross_flip` | Flags the exact day the fast/slow order switches. |
| `trend` | One word for a stretch of prices: `up`, `down`, or `flat`. |

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

## 5. Trend — `trend(prices, window=None, flat_threshold=0.01)`

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

### Also in the file

`_ols_slope` is an internal helper (it computes the slope of that line of best
fit). The leading underscore means "not part of the public toolkit" — you won't
call it directly.
