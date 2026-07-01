"""
市场数据服务
为 Report Agent 提供真实的股票/加密货币行情数据，用于为预测报告提供事实依据
（区别于 zep_tools 中基于模拟图谱的检索工具）

数据来源（均为公开接口，无需 API Key）：
- 加密货币: Binance 公开行情接口 (ticker/24hr + klines)
- 股票: Stooq 免费历史行情 CSV 接口
"""

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from ..utils.logger import get_logger

logger = get_logger('mirofish.market_data')

_BINANCE_BASE_URL = "https://api.binance.com"
_STOOQ_BASE_URL = "https://stooq.com/q/d/l/"
_REQUEST_TIMEOUT = 10

_CRYPTO_QUOTE_SUFFIXES = ("USDT", "BUSD", "USDC", "FDUSD", "BTC", "ETH")


class MarketDataError(Exception):
    """行情数据获取失败"""
    pass


@dataclass
class MarketDataResult:
    """市场行情快照"""
    symbol: str
    asset_type: str  # "crypto" | "stock"
    source: str
    price: float
    change_pct_24h: Optional[float]
    sma20: Optional[float]
    sma50: Optional[float]
    rsi14: Optional[float]
    week52_high: Optional[float]
    week52_low: Optional[float]
    as_of: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "asset_type": self.asset_type,
            "source": self.source,
            "price": self.price,
            "change_pct_24h": self.change_pct_24h,
            "sma20": self.sma20,
            "sma50": self.sma50,
            "rsi14": self.rsi14,
            "week52_high": self.week52_high,
            "week52_low": self.week52_low,
            "as_of": self.as_of,
        }

    def to_text(self) -> str:
        """转换为文本格式，供LLM理解"""
        asset_label = "加密货币" if self.asset_type == "crypto" else "股票"
        lines = [
            f"【真实市场数据 - {self.symbol}】（{asset_label}，数据来源: {self.source}，截至 {self.as_of}）",
            f"当前价格: {self.price}",
        ]
        if self.change_pct_24h is not None:
            lines.append(f"24小时涨跌幅: {self.change_pct_24h:+.2f}%")
        if self.sma20 is not None:
            lines.append(f"20日均线 (SMA20): {self.sma20:.4f}")
        if self.sma50 is not None:
            lines.append(f"50日均线 (SMA50): {self.sma50:.4f}")
        if self.rsi14 is not None:
            lines.append(f"14日相对强弱指标 (RSI14): {self.rsi14:.2f}")
        if self.week52_high is not None and self.week52_low is not None:
            lines.append(f"52周区间: {self.week52_low} - {self.week52_high}")
        lines.append("注意: 以上为真实市场数据，用于为预测报告提供事实依据，本身不构成模拟结果或投资建议。")
        return "\n".join(lines)


class MarketDataService:
    """行情数据服务：自动识别股票/加密货币，抓取真实行情并计算基础技术指标"""

    def get_market_snapshot(self, symbol: str, asset_type: str = "auto") -> MarketDataResult:
        symbol = (symbol or "").strip().upper()
        if not symbol:
            raise MarketDataError("symbol 不能为空")

        resolved_type = asset_type if asset_type in ("crypto", "stock") else self._detect_asset_type(symbol)

        if resolved_type == "crypto":
            return self._fetch_crypto(symbol)
        return self._fetch_stock(symbol)

    def _detect_asset_type(self, symbol: str) -> str:
        if any(symbol.endswith(suffix) for suffix in _CRYPTO_QUOTE_SUFFIXES):
            return "crypto"
        return "stock"

    # ------------------------------------------------------------------
    # 加密货币: Binance 公开接口（无需 API Key）
    # ------------------------------------------------------------------

    def _fetch_crypto(self, symbol: str) -> MarketDataResult:
        try:
            ticker_resp = requests.get(
                f"{_BINANCE_BASE_URL}/api/v3/ticker/24hr",
                params={"symbol": symbol},
                timeout=_REQUEST_TIMEOUT,
            )
            klines_resp = requests.get(
                f"{_BINANCE_BASE_URL}/api/v3/klines",
                params={"symbol": symbol, "interval": "1d", "limit": 100},
                timeout=_REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise MarketDataError(f"无法连接行情数据源(Binance): {exc}") from exc

        if not ticker_resp.ok or not klines_resp.ok:
            raise MarketDataError(f"未找到加密货币交易对 '{symbol}' 的行情数据")

        ticker = ticker_resp.json()
        klines = klines_resp.json()
        if not isinstance(klines, list) or not klines:
            raise MarketDataError(f"未找到加密货币交易对 '{symbol}' 的历史行情数据")

        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        sma20, sma50, rsi14 = self._compute_indicators(closes)

        return MarketDataResult(
            symbol=symbol,
            asset_type="crypto",
            source="Binance",
            price=float(ticker.get("lastPrice", closes[-1])),
            change_pct_24h=float(ticker.get("priceChangePercent", 0.0)),
            sma20=sma20,
            sma50=sma50,
            rsi14=rsi14,
            week52_high=max(highs),
            week52_low=min(lows),
            as_of=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        )

    # ------------------------------------------------------------------
    # 股票: Stooq 免费历史行情 CSV 接口（无需 API Key）
    # ------------------------------------------------------------------

    def _fetch_stock(self, symbol: str) -> MarketDataResult:
        stooq_symbol = symbol.lower() if "." in symbol else f"{symbol.lower()}.us"
        try:
            resp = requests.get(
                _STOOQ_BASE_URL,
                params={"s": stooq_symbol, "i": "d"},
                timeout=_REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise MarketDataError(f"无法连接行情数据源(Stooq): {exc}") from exc

        if not resp.ok or "No data" in resp.text[:50]:
            raise MarketDataError(f"未找到股票代码 '{symbol}' 的行情数据")

        rows = list(csv.DictReader(io.StringIO(resp.text)))
        if not rows:
            raise MarketDataError(f"未找到股票代码 '{symbol}' 的历史行情数据")

        closes = [float(r["Close"]) for r in rows if r.get("Close")]
        highs = [float(r["High"]) for r in rows if r.get("High")]
        lows = [float(r["Low"]) for r in rows if r.get("Low")]
        if not closes:
            raise MarketDataError(f"股票代码 '{symbol}' 的行情数据为空")

        sma20, sma50, rsi14 = self._compute_indicators(closes)
        change_pct = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 else None

        recent_highs = highs[-252:] if len(highs) >= 252 else highs
        recent_lows = lows[-252:] if len(lows) >= 252 else lows

        return MarketDataResult(
            symbol=symbol,
            asset_type="stock",
            source="Stooq",
            price=closes[-1],
            change_pct_24h=change_pct,
            sma20=sma20,
            sma50=sma50,
            rsi14=rsi14,
            week52_high=max(recent_highs) if recent_highs else None,
            week52_low=min(recent_lows) if recent_lows else None,
            as_of=rows[-1].get("Date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        )

    # ------------------------------------------------------------------
    # 技术指标计算（纯 Python 实现，不依赖 numpy/pandas）
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_indicators(closes: List[float]):
        """基于收盘价序列（按时间升序排列）计算 SMA20 / SMA50 / RSI14"""

        def sma(period: int) -> Optional[float]:
            if len(closes) < period:
                return None
            return sum(closes[-period:]) / period

        def rsi(period: int = 14) -> Optional[float]:
            if len(closes) < period + 1:
                return None
            gains, losses = [], []
            window = closes[-(period + 1):]
            for prev, curr in zip(window[:-1], window[1:]):
                delta = curr - prev
                gains.append(max(delta, 0.0))
                losses.append(max(-delta, 0.0))
            avg_gain = sum(gains) / period
            avg_loss = sum(losses) / period
            if avg_loss == 0:
                return 100.0
            rs = avg_gain / avg_loss
            return 100.0 - (100.0 / (1.0 + rs))

        return sma(20), sma(50), rsi()
