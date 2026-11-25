# Order preview card - {{as_of}} {{clock_et}} ET

One card per order, before it is sent. Fill every line and write `unknown - why` instead of leaving a gap;
a card with a blank is not a preview. The same layout is the operator's standing requirement for paper and
live orders alike: **paper** may execute on the operator's stated intent, **live** never does without a fresh
yes against this exact card. Numbers come from the journal, the broker book and `config/risk.yaml` - never
from memory. Do not put account ids, tokens or chat ids on a card; this repo is public.

## The order

| Field | Value |
|---|---|
| Product | stock / ETF / option (say which) |
| Symbol | e.g. `US.NVDA` or `US.NVDA261218C150000` |
| Side | buy / sell |
| Quantity | shares, or contracts |
| Limit | the only order type the desk sends |
| Multiplier | 100 for a standard option, 1 otherwise |
| Est. cost | notional or premium, plus modeled fees |
| Playbook | PB-001 ballast / PB-002 tactical stock / PB-003 long option / PB-004 scalp / PB-007 pullback |
| Hold | `session` (flat by the session's exit time) or `swing` (exits on stop, target, expiry or hold-by) |

## Why this order

- Thesis: one plain sentence on what the desk expects to happen.
- Evidence: source and date (research artifact, news URL, chain capture), plus the playbook's own gate it passes.
- What must be true: the condition that makes the trade right, and the one that makes it wrong.

## Risk, in plain language

Six lines, always, because this is what the operator is agreeing to.

- **Strategy**: what the desk is actually doing, in words a first-time trader would follow.
- **%NAV**: order size as a share of the fund, and the risked dollars as a share of the fund.
- **Worst-case loss**: dollars and %NAV. For a stock, the loss is an *estimate* to the stop, not a cap; for a
  long option it is the entire premium plus fees. Say which.
- **Halts and gaps**: what happens if the name halts, if the market gaps past the stop overnight, if the limit
  never fills, and if the kill switch is engaged while this is open. Broker-native stops do not exist here -
  a stop is a rule the desk checks, and a gap can cost more than the plan.
- **Exit**: stop, target, time/deadline, and hold-by date - which one fires first wins. Name which exit is a
  real order resting at the broker (today: the take-profit, a DAY order re-armed each session) and which is
  only a rule someone has to act on. Say who is watching it.
- **Ladder**: adding in, partial takes, re-entry after an exit, and whether a missed entry gets re-asked or is
  simply gone.

## Authority

- Covering line: which standing approval or same-day envelope line authorizes it, its date, and the `setup_hash`
  it binds. If nothing covers it, say so - it needs a yes first.
- Kind of authorization: `envelope` / `telegram` / `protective`.
- Account: paper or live. Live always needs the operator's explicit yes on this card.
- Identity: the `request_id` that goes in the broker remark, and what a partial, cancelled or unknown status
  means (only a verified full fill counts as filled; a submitted order is not a fill).

## After it fills

- Journal rows written, and by which command.
- Position read back from the broker, not assumed.
- Next check time, and what would trigger an exit before then.

---

## Filled example (paper, 2026-11-25)

- Order: **option**, `US.NVDA261218C150000` (NVIDIA 18 Dec 150 call), buy 1 contract, limit 10.00 debit,
  multiplier 100. Est. cost about $1,002 plus about $2.29 fees. Playbook PB-003, hold `swing`.
- Why: the shares setup is a reclaim of the 24 Nov low with a 151-156 entry zone; the call is the leveraged
  expression of the same thesis. Evidence: `research/2026-11-25/watchlist.json` and the 25 Nov scout capture.
- Strategy: bet a small fixed amount that NVDA trades up before mid-December. The most that can be lost is
  known before the trade.
- %NAV: about 1.0% of the fund put at risk, inside the 1.5% per-option budget and the 5% aggregate premium cap.
- Worst-case loss: the whole premium plus fees, about $1,004, roughly 1.0% of NAV. There is no partial-loss floor.
- Halts and gaps: a halt on NVDA leaves the call untradeable too; a gap down can cut the premium far more than
  the underlying's own stop; the limit may not fill at all above 10.00 (a fresh proposal is allowed up to 5%
  over, then the entry is gone).
- Exit: underlying 141 stop, underlying 156 target, a 40% premium drawdown, or sold by 12:10 ET Fri 27 Nov -
  whichever comes first. All four are rules the desk acts on at each fire, not resting broker orders; the
  take-profit sells as a DAY order re-armed at the first fire of each session.
- Ladder: no adds, no partials, one contract. If it never fills, the entry is not re-asked after Friday's deadline.
- Authority: the standing paper approval for 25-27 Nov (PB-003 is switched on); no live account involved.
- After: `order.requested` / `.submitted` / `.filled` journaled, position read back from the broker, next check
  after the 09:30 ET open.
