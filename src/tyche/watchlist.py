"""Actionable scout plans. Research is not an order authorization."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tyche.models import OptionContract

Sleeve = Literal["equity", "defensive", "real_asset", "credit"]
Status = Literal["watch", "entered", "exited", "dropped"]


class WatchlistEntry(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    symbol: str
    sleeve: Sleeve
    strategy: str
    entry_low: float = Field(gt=0)
    entry_high: float = Field(gt=0)
    stop: float = Field(gt=0)
    target: float = Field(gt=0)
    expiry: date
    status: Status = "watch"
    thesis: str = ""
    setup_id: str = ""
    option: OptionContract | None = None
    direction: Literal["bullish", "bearish"] = "bullish"
    catalyst: str = ""
    sources: list[str] = Field(default_factory=list)
    reviewed_at: datetime | None = None
    invalidated: bool = False
    market_cap_usd: float | None = Field(default=None, gt=0)
    max_quantity: int | None = Field(default=None, gt=0)
    premium_limit: float | None = Field(default=None, gt=0)
    # Quote-confirmation samples are required by the tactical planner, not the LLM.
    confirmation_ticks: int = Field(default=2, ge=1, le=5)
    exit_at: datetime | None = None

    @property
    def underlying(self) -> str:
        return self.option.underlying if self.option else self.symbol

    @model_validator(mode="after")
    def _plan_levels(self) -> WatchlistEntry:
        if self.direction == "bullish":
            valid = self.stop < self.entry_low <= self.entry_high < self.target
        else:
            valid = self.target < self.entry_low <= self.entry_high < self.stop
        if not valid:
            raise ValueError("invalid directional entry/stop/target ordering")
        if self.option:
            if not self.option.matches(self.symbol):
                raise ValueError("option metadata does not match symbol")
            if (self.option.right == "put") != (self.direction == "bearish"):
                raise ValueError("only bullish long calls and bearish long puts supported")
            if self.premium_limit is None:
                raise ValueError("option plan needs a maximum debit per share")
        elif self.direction != "bullish":
            raise ValueError("bearish expression requires a long put; no short stocks")
        for stamp in (self.reviewed_at, self.exit_at):
            if stamp is not None and stamp.tzinfo is None:
                raise ValueError("watchlist timestamps must include timezone")
        return self


class Watchlist(BaseModel):
    as_of: date
    entries: list[WatchlistEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_symbols(self) -> Watchlist:
        symbols = [e.symbol for e in self.entries]
        if len(symbols) != len(set(symbols)):
            raise ValueError("duplicate symbols in watchlist")
        ids = [e.setup_id for e in self.entries if e.setup_id]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate setup ids")
        return self

    def stale(self, today: date) -> bool:
        return self.as_of != today

    def active(self, today: date) -> list[WatchlistEntry]:
        return [e for e in self.entries if e.status == "watch" and e.expiry >= today]
