"""Scout watchlist: shortlisted counters with crafted strategies and entry/exit plans.

The researcher writes this at pre-market only; intraday runs monitor the plans
instead of re-running discovery. The working copy lives in the Drive locker
(/data/drive/tyche-raw/watchlist.json) so it survives ephemeral cloud sessions;
data/watchlist.json in the repo is the sanitized snapshot. Symbols and levels
only — never account ids or tokens.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Sleeve = Literal["equity", "defensive", "real_asset", "credit"]
Status = Literal["watch", "entered", "exited", "dropped"]


class WatchlistEntry(BaseModel):
    symbol: str
    sleeve: Sleeve
    strategy: str
    entry_low: float
    entry_high: float
    stop: float
    target: float
    expiry: date
    status: Status = "watch"
    thesis: str = ""

    @model_validator(mode="after")
    def _long_plan_levels(self) -> WatchlistEntry:
        if self.entry_low <= 0:
            raise ValueError("prices must be positive")
        if not self.stop < self.entry_low <= self.entry_high < self.target:
            raise ValueError("long plan requires stop < entry_low <= entry_high < target")
        return self


class Watchlist(BaseModel):
    as_of: date
    entries: list[WatchlistEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_symbols(self) -> Watchlist:
        symbols = [e.symbol for e in self.entries]
        if len(symbols) != len(set(symbols)):
            raise ValueError("duplicate symbols in watchlist")
        return self

    def stale(self, today: date) -> bool:
        return self.as_of < today

    def active(self, today: date) -> list[WatchlistEntry]:
        return [e for e in self.entries if e.status == "watch" and e.expiry >= today]