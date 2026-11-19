# region imports
from AlgorithmImports import *
# endregion


class PB001Research(QCAlgorithm):
    """Research-only reference implementation of PB-001 (ADR 0015 lane).

    Venue: local LEAN engine, adjusted daily bars from the research dataset.
    This is hypothesis evidence, NOT the trading kernel: no tyche risk kernel,
    no moomoo execution. Deviations from the kernel reference are disclosed in
    docs/validation (weekly check vs daily drift band, sleeve cap scaling
    without redistribution, IB fee/slippage models).
    """

    TICKERS = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ", "HYG"]
    SLEEVE = {
        "SPY": "equity", "QQQ": "equity", "IWM": "equity", "EFA": "equity", "EEM": "equity",
        "TLT": "defensive", "IEF": "defensive",
        "GLD": "real_asset", "DBC": "real_asset", "VNQ": "real_asset",
        "HYG": "credit",
    }
    CAP = {
        "SPY": 0.30, "QQQ": 0.30, "IWM": 0.15, "EFA": 0.20, "EEM": 0.15,
        "TLT": 0.25, "IEF": 0.25, "GLD": 0.20, "DBC": 0.15, "VNQ": 0.15, "HYG": 0.20,
    }
    SLEEVE_CAPS = {
        "risk_on": {"equity": 0.80, "defensive": 0.40, "real_asset": 0.25, "credit": 0.15},
        "neutral": {"equity": 0.50, "defensive": 0.50, "real_asset": 0.20, "credit": 0.10},
        "risk_off": {"equity": 0.20, "defensive": 0.60, "real_asset": 0.30, "credit": 0.0},
    }
    HORIZONS = [(63, 0.5), (126, 0.3), (252, 0.2)]
    SKIP = 5
    VOL_TARGET = 0.10

    def initialize(self):
        self.set_start_date(2023, 1, 3)
        self.set_end_date(2026, 11, 18)
        self.set_cash(1000000)
        self.set_brokerage_model(BrokerageName.InteractiveBrokersBrokerage)
        self.symbols = {}
        for ticker in self.TICKERS:
            equity = self.add_equity(ticker, Resolution.DAILY, data_normalization_mode=DataNormalizationMode.RAW)
            self.symbols[ticker] = equity.symbol
        self.spy = self.symbols["SPY"]
        self.ieff = self.symbols["IEF"]
        self.hyg = self.symbols["HYG"]
        self._week = None

    def on_data(self, data):
        if self.spy not in data.bars:
            return
        week = self.time.isocalendar()[1]
        if week == self._week:
            return
        self._week = week
        self.rebalance()

    def _closes(self, ticker):
        history = self.history(self.symbols[ticker], 262, Resolution.DAILY)
        if history.empty:
            return None
        return history["close"].to_numpy()

    def _vol(self, closes, window):
        if len(closes) < window + 1:
            return None
        returns = np.diff(closes[-(window + 1):]) / closes[-(window + 1):-1]
        return float(np.std(returns, ddof=1) * np.sqrt(252))

    def _momentum(self, closes):
        total, weight = 0.0, 0.0
        for horizon, w in self.HORIZONS:
            if len(closes) >= horizon + self.SKIP + 1:
                total += w * (closes[-self.SKIP - 1] / closes[-self.SKIP - 1 - horizon] - 1.0)
                weight += w
        return total / weight if weight else None

    def _regime(self, series):
        spy, ief, hyg = series["SPY"], series["IEF"], series["HYG"]
        checks = 0
        if len(spy) >= 200 and spy[-1] > np.mean(spy[-200:]):
            checks += 1
        if len(spy) >= 200 and np.mean(spy[-50:]) > np.mean(spy[-200:]):
            checks += 1
        v20, v252 = self._vol(spy, 20), self._vol(spy, 252)
        if v20 is not None and v252 and v20 <= 1.25 * v252:
            checks += 1
        if len(ief) >= 63 and len(hyg) >= 63:
            ratio = hyg[-63:] / ief[-63:]
            if ratio[-1] > np.mean(ratio):
                checks += 1
        if checks >= 3:
            return "risk_on", checks
        if checks == 2:
            return "neutral", checks
        return "risk_off", checks

    def rebalance(self):
        series = {}
        for ticker in self.TICKERS:
            closes = self._closes(ticker)
            if closes is None or len(closes) < 70:
                return
            series[ticker] = closes
        regime, checks = self._regime(series)

        scored = []
        for ticker in self.TICKERS:
            mom = self._momentum(series[ticker])
            vol = self._vol(series[ticker], 63)
            if mom is not None and vol and mom > 0:
                scored.append((mom / vol, ticker, vol))
        scored.sort(reverse=True)
        selected = scored[:4]
        if not selected:
            targets = {ticker: 0.0 for ticker in self.TICKERS}
        else:
            inv = np.array([1.0 / vol for _, _, vol in selected])
            weights = inv / inv.sum()
            returns = np.array([
                np.diff(series[t][-127:]) / series[t][-127:-1] for _, t, _ in selected
            ])
            cov = np.cov(returns) * 252
            port_vol = float(np.sqrt(weights @ cov @ weights))
            scale = min(1.0, self.VOL_TARGET / port_vol) if port_vol else 0.0
            targets = {ticker: 0.0 for ticker in self.TICKERS}
            for (_, ticker, _), w in zip(selected, weights * scale):
                targets[ticker] = float(w)
            for sleeve, cap in self.SLEEVE_CAPS[regime].items():
                members = [t for t in targets if self.SLEEVE[t] == sleeve]
                total = sum(targets[t] for t in members)
                if total > cap:
                    for t in members:
                        targets[t] *= cap / total
            for ticker in targets:
                targets[ticker] = min(targets[ticker], self.CAP[ticker])
            invested = sum(targets.values())
            if invested > 0.95:
                targets = {t: w * 0.95 / invested for t, w in targets.items()}

        nav = float(self.portfolio.total_portfolio_value)
        current = {
            ticker: float(self.portfolio[self.symbols[ticker]].holdings_value) / nav
            if self.portfolio[self.symbols[ticker]].invested else 0.0
            for ticker in self.TICKERS
        }
        orders = []
        for ticker in self.TICKERS:
            target, held = targets[ticker], current[ticker]
            if target > 0 and held > 0:
                gap = abs(target - held)
                if gap < 0.20 * max(target, held):
                    continue
            if abs(target - held) * nav < max(500.0, 0.005 * nav):
                continue
            orders.append((ticker, target))
        orders.sort(key=lambda item: item[1] - current[item[0]])
        for ticker, target in orders:
            self.set_holdings(self.symbols[ticker], target)