# Intrinsic-value methods — plain-English guide

The functions in [`../valuation.py`](../valuation.py) estimate what a share is
*worth* based on the business behind it, as opposed to what the market is
charging for it today. That gap — worth vs. price — is what "is it cheap or
expensive?" really asks.

**There is no single true number.** Every method needs assumptions (how fast will
cash flow grow? what return do you demand?), and the answer swings a lot when
those assumptions change. These functions are just the arithmetic; you supply the
assumptions — or [`../stock_intrinsic_value.py`](../stock_intrinsic_value.py)
pulls them from Yahoo Finance and runs all of them for you.

All rates are **fractions**: `0.09` means 9%.

---

## Words you need first

| Term | Plain meaning |
|---|---|
| **Free cash flow (FCF)** | The cash a company has left after paying its bills *and* reinvesting to keep running — the money that could, in principle, go to owners. |
| **Discount rate** | How much you shrink a future dollar to value it today, because money later is worth less than money now (time + risk). Higher risk → higher discount rate → lower value today. Often ~8–10% for a big, stable company. |
| **Terminal / perpetual growth** | How fast you assume cash flow grows *forever*, after your detailed forecast ends. Kept small — usually 2–3%, roughly long-run economic growth. |
| **Multiple** | A shortcut ratio. "Trades at 20× earnings" (a P/E of 20) means the price is 20 times the annual earnings per share. |
| **Enterprise value (EV)** | The price of the *whole business*: what you'd pay for all the shares, **plus** taking on its debt, **minus** its cash. |
| **Net debt** | Total debt minus cash. A **negative** number means "net cash" — more cash than debt. |
| **Equity value** | The part that belongs to shareholders = enterprise value − net debt. Divide by share count for a per-share figure. |

---

## 1. Gordon growth value — `gordon_growth_value(cash_flow, discount_rate, growth)`

**The idea.** What is a stream of cash worth today if it grows at the same small
rate *forever*? The formula is short:

```
value = next_year's_cash / (discount_rate − growth_rate)
```

**One formula, three uses.** It's called the **Gordon growth model**; when the
cash is dividends it's the **dividend discount model**; and it's the "everything
after the forecast" tail (the **terminal value**) inside a full DCF.

**Example.** A stock will pay a **$5** dividend next year, you want an **8%**
return, and you expect the dividend to grow **3%** a year forever:

```
5 / (0.08 − 0.03) = 5 / 0.05 = $100
```

**How to read it.** The value is extremely sensitive to the *gap* between the
discount rate and the growth rate. 8% vs 3% divides by 0.05; 8% vs 6% divides by
0.02 — the same cash is worth 2.5× as much from a 3-point change in one guess.

**Watch out.** Growth must be **below** the discount rate, or the maths explodes
(the function refuses with an error). It's only realistic for slow, steady
compounders — not fast growers.

---

## 2. Discounted cash flow — `discounted_cash_flow(...)`  *(the main method)*

**The idea.** Estimate the company's free cash flow for each of the next several
years, convert every future year back into today's money with the discount rate,
add a lump-sum **terminal value** for everything beyond the forecast, then
subtract debt and divide by the share count to get a worth **per share**.

**Two stages:**
1. **Explicit forecast** — e.g. "FCF starts at $100 and grows 5% a year for 5
   years." You can pass one growth rate, or a list of per-year rates.
2. **Terminal value** — the Gordon formula above, applied at a small perpetual
   growth rate, for all the years after the forecast.

**Inputs:** starting FCF, discount rate, growth, number of years, terminal
growth, net debt, share count.

**Example.**

```
discounted_cash_flow(fcf=100, discount_rate=0.09, growth=0.05, years=5)
  ->  ≈ 1656.27
```

No share count was given, so that's the **whole-company** equity value. Pass
`shares=...` to get a per-share number.

**How to read it.** Compare the per-share result to the current market price:
- result **well below** price → the model says expensive (for these assumptions)
- result **above** price → the model says there's a margin of safety

**Watch out.**
- The **terminal value is usually most of the answer**, so the terminal-growth
  and discount-rate guesses dominate everything.
- Small input changes → large output swings. Always try a few assumption sets
  (a cautious one, a middle one, an optimistic one) and look at the *range*.
- It needs **positive** free cash flow to mean anything — a loss-making company
  gives nonsense.

---

## 3. Price multiple — `multiple_value(metric_per_share, multiple)`

**The idea.** Decide what ratio is *fair* ("this business deserves to trade at
18× earnings"), then multiply it by the matching per-share number:

```
18 × $6.50 earnings per share = $117 fair price
```

**Use it for equity multiples:** P/E (earnings), P/S (sales per share), P/B (book
value per share), P/FCF (free cash flow per share).

**How to read it.** It just relocates the hard question to "what multiple is
fair?" — usually answered by comparing to the company's own history or to
similar companies.

**Watch out.** If you feed in the multiple the stock **already** trades at, you
get back exactly today's price — that's not an independent estimate. It's only
informative with a *different*, considered multiple.

---

## 4. Enterprise multiple — `ev_multiple_value(metric, multiple, net_debt=0, shares=None)`

**The idea.** Same as above, but for ratios that value the **whole business** —
EV/EBITDA, EV/Sales. Multiply the company-wide metric (total EBITDA) by the
multiple to get an enterprise value, then bridge back to shareholders: subtract
net debt, divide by shares.

**Example.**

```
EBITDA 120,000 × 14        = 1,680,000   enterprise value
        − net debt 200,000 = 1,480,000   equity value
        ÷ 15,000 shares    ≈ $98.67      per share
```

**Watch out.** Same "don't reuse the current multiple" caveat as method 3. Also,
EBITDA deliberately ignores interest, tax, and capital spending — it's a *rough*
stand-in for cash generation, not the real thing.

---

## 5. Equity from enterprise — `equity_from_enterprise(enterprise_value, net_debt=0, shares=None)`

**The idea.** A small bridge used by the two methods above, and handy on its own.
Given the value of the whole business, subtract net debt to get the part that
belongs to shareholders, then optionally divide by shares.

```
equity_from_enterprise(1,680,000, net_debt=-50,000, shares=15,000)
  ->  (1,680,000 + 50,000) / 15,000  ≈  $115.33
```

(Net **cash** — a negative net-debt figure — gets *added* back.)

**A good sanity check:** take a data provider's reported enterprise value,
subtract net debt, divide by shares. The result should land near the actual share
price. A big gap means one of the reported figures is stale.

---

## 6. Implied growth rate — `implied_growth_rate(price, fcf, discount_rate, years, ...)`  *(reverse DCF)*

**The idea.** Flip the DCF around. Instead of "given a growth rate, what's it
worth?", ask **"given today's price, what growth rate would justify it?"** The
function tries growth rates until the DCF value matches the market price.

**Example.**

```
implied_growth_rate(price=1656.27, fcf=100, discount_rate=0.09, years=5)
  ->  ≈ 0.05   (5% — it reverses the DCF example in method 2)
```

**How to read it.** Compare the answer to what people actually expect:
- price implies **17%/yr** growth for a decade, but analysts expect **8%** →
  the market is paying for an optimistic story
- price implies **3%**, but the company is growing **10%** → the market may be
  too gloomy

**Watch out.** It holds *every other* assumption fixed (discount rate, terminal
growth, horizon), so the implied growth only means something alongside those
specific choices. Extreme prices can be unsolvable, and then it raises an error.

---

## Putting them together

- **DCF** is the core estimate of worth.
- **Reverse DCF** turns it into a reality check on the *price*: "what would have
  to go right?"
- **Multiples** are a quick cross-check — but only when you have a defensible
  "fair" multiple, not the current one.
- **Gordon / dividend model** applies only to steady, real dividend payers.
- Always run a **range** of assumptions. A single number hides how uncertain the
  estimate is.

None of this is investment advice — it's a structured way to reason about price
versus worth.
