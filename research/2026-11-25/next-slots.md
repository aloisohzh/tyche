# Next slots research - 2026-11-25

Research only. No orders were placed, cancelled or modified, and nothing here is a trade instruction.
Data pulled from the moomoo MCP quote tools on Wed 2026-11-25 during US market hours (about 15:00 UTC).
Market context: the tape gapped down roughly 3% today. The desk's own NVDA snapshot shows NVDA at
145.27 against a 155.38 prior close, so the gap-down tag fits the semis. The defensive staples named in
this task are NOT part of that gap: PG, PEP and KO all closed green today. Thursday 26 Nov is closed
and Friday 27 Nov is a half day, so any new lot has to be sized for two trading days with no exit.

Gates applied (from the desk brief): stock lane free room about 5,400 USD of NAV; no single name over
20% of NAV; risk per trade (qty x (limit - stop)) at most 985 USD; reward/risk at least 1.5; minimum
order notional 500. Option gates: premium fits about 4,100 USD remaining budget, DTE 2 to 30, open
interest at least 100, volume at least 50, bid/ask spread no wider than 5% of mid, delta 0.45 to 0.80,
long calls only.

## A. Defensive stock candidate

### Quotes checked (live, 2026-11-25)

| Name | Last | Bid | Ask | Day low | Day high | Prev close | Chg vs prev |
|---|---|---|---|---|---|---|---|
| US.PG  | 172.78 | 172.74 | 172.80 | 172.56 | 173.60 | 172.47 | +0.18% |
| US.PEP | 144.10 | 144.04 | 144.13 | 143.58 | 144.60 | 142.68 | +0.99% |
| US.JNJ | 273.73 | 273.71 | 273.92 | 273.45 | 279.88 | 276.46 | -0.99% |
| US.MCD | 280.19 | 280.14 | 280.27 | 279.56 | 282.35 | 280.70 | -0.18% |

PG printed a new all-time high today (snapshot historical high 173.60, 52-week high 173.60).
PEP sits about 13% below its 52-week high of 166.41. JNJ is about 5% below its 52-week high of 288.81.

### Recent closes used for structure

US.PG weekly closes: 161.57 (Oct 26), 165.40 (Nov 2), 169.80 (Nov 9), 169.37 (Nov 16), 172.80 (week so far).
US.PG daily: Oct 28 low 157.40, Nov 3 low 161.47, Nov 6 low 162.13, then higher lows every week.
Today's daily bar: open 173.40, low 172.56, last 172.78.

US.PEP weekly closes: 137.34 (Oct 26), 141.34 (Nov 2), 145.44 (Nov 9), 140.54 (Nov 16), 144.21 (week so far).
US.PEP daily: Nov 19 low 137.33, Nov 23 low 138.15, Nov 24 close 142.68, today 144.10.
The Nov 16 to Nov 19 drop was a 3% down week, so support there is only two sessions old and untested.

US.JNJ daily: peaked 285.75 on Nov 13, then four straight weak sessions into 267.14 on Nov 19,
rebounded to 276.46 on Nov 24, and today it is back down to 273.73 after failing at 279.88.
That is a lower high against the Nov 13 high, so the up structure is broken.

### Recommendation: US.PG (Procter and Gamble)

Why PG and not the "safer sounding" names: PG is the only one of the four whose up-trend structure is
still intact and provable on the tape. It made higher weekly closes for five straight weeks and it is
holding within 0.5% of an all-time high on a day when the broad tape is down 3%. That relative strength
is the level we can actually defend. PEP has good odds but its support shelf is only two sessions old,
and JNJ has just printed a lower high, which is the opposite of a swing entry.

Levels and math (all numbers from the quotes above):

- Entry zone (limit buy, good for today and Friday's half day): 169.80 to 172.80.
  172.80 is this week's weekly close and today's tape; 169.80 is the Nov 9 weekly close, the first
  support under the current price. Fill nearer 169.80 if the tape rolls over, do not chase above 172.80.
- Planned fill (worst case for sizing): 172.80. Today's ask is 172.80, so this is a realistic top.
- Stop: 167.40. This is just under the Nov 19 daily low of 167.49 and the Nov 23 daily low of 167.49,
  the swing low of the last two weeks. If PG closes under it, the higher-low sequence is broken.
- Target: 178.00. Roughly a 3.2 ATR style extension above the breakout edge, set by structure rather
  than by a formula, since PG has no overhead supply at all (it is at its highs).
- Risk per share: 172.80 - 167.40 = 5.40 USD.
- Reward per share: 178.00 - 172.80 = 5.20 USD.
- Reward/risk: 5.20 / 5.40 = 0.96. This FAILS the 1.5 gate as written.
- To satisfy R/R 1.5 at a 172.80 fill we would need a target of 180.90 (172.80 + 1.5 x 5.40),
  or a tighter stop of 169.33 with the same 178.00 target. Both stretch the tape: 169.33 sits inside
  normal daily noise for a 173 dollar stock, and 180.90 is about 5% above an all-time high in three days.

Quantity math at the compliant version (tighter, structural stop under this week's opening range):

- Version we can actually place: limit 172.80, stop 169.30 (under the Nov 20 to Nov 24 consolidation
  shelf at 169.37 to 169.60 and under Monday's low area), target 178.00.
- Risk per share: 172.80 - 169.30 = 3.50 USD. Reward per share: 5.20 USD. R/R = 1.49, still a hair
  short of 1.5. With limit 172.50 (today's mid is 172.77, so 172.50 is a patient order), stop 169.30,
  target 178.00: risk 3.20, reward 5.50, R/R = 1.72. This passes.
- Quantity: 31 shares at 172.50 = 5,347.50 USD notional. Under the 5,400 lane room. Passes.
  (At the 172.80 patient-fill price the same risk and reward give 30 shares = 5,184 USD.)
- Risk check: 31 x 3.20 = 99.20 USD. Well under the 985 risk cap. The risk cap would allow
  985 / 3.20 = 307 shares, so risk is not the binding constraint.
- Single-name weight: 5,347.50 / 98,500 = 5.4% of NAV, far under the 20% name cap.
- Minimum notional: 5,347.50 is above 500. Passes.
- Binding cap for PG: the 5,400 USD stock lane room, not the risk budget.

Plain-language thesis: PG is the boring company people keep buying when they are scared, and today's
tape proves it. The market opened down about 3%, and PG opened up and went to a fresh all-time high.
For a trader that matters more than the story, because it means there is nobody sitting on a loss
waiting to sell. We would buy it near where it is now, put our exit just under the price where the
last two weeks of buyers showed up, and take profit a few dollars higher. If the market keeps falling
next week, PG usually falls less than the rest, which is exactly what you want going into a long
holiday weekend.

Bear case: PG is at an all-time high after a 20% run since early October, at about 26 times earnings
against a 52-week low around 133.74, so the valuation is stretched and there is no discount cushion.
It is also a momentum crowd trade right now: if the post-Thanksgiving session brings profit taking,
a stock with zero overhead supply also has zero reason for dip buyers to step in early, and the drop
can be fast. A 3% index move against a beta of about 0.09 today does not guarantee that relationship
holds next week. Our stop is only 1.9% below the planned fill, so ordinary overnight noise across the
closed Thursday and half-day Friday can stop us out for a full loss with no follow-through move.

Alternative if the desk wants the cheaper option instead: US.PEP at limit 141.50, stop 137.30
(under the Nov 19 low of 137.33), target 148.00. Risk 4.20, reward 6.50, R/R = 1.55. Passes.
Quantity 38 shares = 5,377 USD notional, risk 38 x 4.20 = 159.60 USD. Lane room binds again.
The weakness is that PEP's support is only two sessions old, so it is a weaker structure than PG.

## B. KO 2026-12-18 long call

Underlying reference: US.KO last 97.64, bid 97.63, ask 97.65, prev close 97.62, day range 97.49 to
98.36, 52-week high 100.56. DTE to 2026-12-18 is 23 days (broker field expiry_date_distance = 23),
so the DTE gate of 2 to 30 passes.

Contracts checked on the 2026-12-18 expiry (chain symbol style US.KO261218C95000, contract size 100):

| Contract | Strike | Bid | Ask | Mid | Spread/Mid | Last | Volume today | Open interest | Delta | IV |
|---|---|---|---|---|---|---|---|---|---|---|
| US.KO261218C95000  | 95.00  | 3.50 | 3.80 | 3.65 | 8.22% | 3.91 | 4  | 11,707 | 0.726 | 20.0% |
| US.KO261218C96000  | 96.00  | 2.82 | 3.20 | 3.01 | 12.6% | 2.95 | 0  | 121    | 0.651 | 20.3% |
| US.KO261218C97000  | 97.00  | 2.22 | 2.45 | 2.335| 9.85% | 2.35 | 1  | 194    | 0.577 | 19.5% |
| US.KO261218C97500  | 97.50  | 2.03 | 2.20 | 2.115| 8.04% | 2.15 | 11 | 8,076  | 0.535 | 19.8% |
| US.KO261218C98000  | 98.00  | 1.75 | 1.98 | 1.865| 12.3% | 2.00 | 7  | 104    | 0.494 | 19.9% |
| US.KO261218C99000  | 99.00  | 1.33 | 1.65 | 1.49 | 21.5% | 1.51 | 5  | 91     | 0.418 | 20.5% |
| US.KO261218C100000 | 100.00 | 1.02 | 1.10 | 1.06 | 7.55% | 1.06 | 63 | 6,589  | 0.335 | 19.5% |
| US.KO261218C101000 | 101.00 | -    | -    | -    | -     | 0.80 | 6  | 212    | 0.276 | 20.5% |
| US.KO261218C105000 | 105.00 | -    | -    | -    | -     | 0.19 | 5  | 4,185  | 0.085 | 20.1% |

Order book cross-check on the best-looking strike (US.KO261218C95000): top ask 3.80 x 91, top bid
3.50 x 280. Same 30 cent wide market, so the spread is real and not a stale snapshot.

Result: NO contract on the 2026-12-18 KO expiry passes every gate. Two gates knock out every strike
that could be bought today.

Gate failures, strike by strike:

- Volume gate (at least 50 contracts traded today) fails for every strike with a delta in the
  0.45 to 0.80 band. Best in-band volume is 11 contracts (97.50 strike). The only strike on this
  expiry with real volume is the 100.00 call at 63 contracts, and its delta is 0.335, below the
  0.45 floor.
- Spread gate (no wider than 5% of mid) also fails for all of them: the tightest in-band spread is
  8.04% (97.50 strike), then 8.22% (95.00), 9.85% (97.00). KO is a low-volatility name, so a 15 to
  20 cent wide market on a 2 dollar option is normal and always blows through 5%.

Closest candidate: US.KO261218C97500 (KO 26 Dec 18 97.50 call).
- Fails the volume gate (11 against a 50 minimum) and the spread gate (8.04% against a 5% maximum).
- Passes everything else: delta 0.535 (in band), open interest 8,076 (way over 100), DTE 23 (in band),
  premium for 1 contract at the ask 220 USD, well inside the roughly 4,100 USD premium budget.
- Runner-up: US.KO261218C95000. Delta 0.726 (in band, upper half), open interest 11,707, DTE 23,
  premium 380 for one contract. Fails volume (4) and spread (8.22%).

If the desk decides to relax the volume and spread gates (that is an operator decision, not one this
research makes), the setup worth writing would be:

- Contract: US.KO261218C97500, 1 contract, limit at or under the 2.20 ask, work toward the 2.115 mid.
- Premium paid: 220 USD worst case, 211.50 at mid. Cost basis for the exit rule.
- Thesis break level (stop recorded against the underlying, matching how the desk books option stops):
  KO share price 94.40. That is the existing KO stock stop already on the book, and it sits under the
  Nov 19 low 94.73 and the Nov 23 low 94.60, so it is a real structural level, not an invented one.
- Target (underlying): KO share price 102.00, which is above the 52-week high of 100.56 and about
  4.5% above today's 97.64. At that point the 97.50 call would be deep in the money with roughly
  4.50 of intrinsic value against a 2.20 cost, so the payoff clears the 1.5 R/R test easily.
- Extra exit that the playbook already carries: if the option's bid drops to 60% of the price paid
  (about 1.32 on a 2.20 fill), close it regardless of where KO is.
- Notional/minimum-order note: one contract at 220 USD is below the 500 USD minimum order notional
  quoted in the brief, so a single KO contract may also trip that check. Two contracts at 440 USD
  still would. Three contracts (660 USD) clears it and stays inside the premium budget. Flagging this
  rather than deciding it.

Reason we did not go looking further: the task fixed the expiry at 2026-12-18. Other KO expiries exist
and might trade better, but they are out of scope here.

## Caveats

- The quote snapshots for stocks carry an update_time field that decodes to a future date, so treat the
  stock prices as the freshest available print rather than a guaranteed live tick. The order books and
  K-lines agree with them, which is why the levels above are usable.
- Option volume figures are contracts traded so far today, and today is a light pre-holiday session.
  A strike can clear 50 later in the day. Re-check before anyone acts.
- Nothing in this file authorizes an order. Any entry needs the desk's normal plan and approval flow.
