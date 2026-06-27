"""
TradingManager — bridges TradingView webhook payloads to Binance order execution.

Expected TradingView alert message JSON:
{
  "action":        "buy" | "sell" | "close",
  "symbol":        "BTCUSDT",
  "order_type":    "market" | "limit",   (default: market)
  "quantity":      0.001,                (base-asset qty; mutually exclusive with quote_quantity)
  "quote_quantity": 100,                 (USDT amount to spend; market orders only)
  "price":         65000,               (required for limit orders)
  "secret":        "your-webhook-secret" (optional validation)
}
"""

import hmac
from datetime import datetime, timezone
from typing import Optional

from ..config import Config
from ..utils.logger import get_logger
from .binance_service import BinanceError, BinanceService

logger = get_logger('mirofish.trading')


class TradingManager:
    def __init__(self):
        self._binance = BinanceService()
        self._history: list[dict] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def binance(self) -> BinanceService:
        return self._binance

    def validate_secret(self, payload: dict) -> bool:
        """Return True if webhook secret matches (or none is configured)."""
        expected = Config.TRADING_WEBHOOK_SECRET
        if not expected:
            return True
        received = str(payload.get("secret", ""))
        return hmac.compare_digest(received, expected)

    def process_signal(self, payload: dict) -> dict:
        """
        Parse a TradingView alert payload and place a Binance order.
        Returns a result dict with keys: success, [order|error], record.
        """
        action = str(payload.get("action", "")).lower()
        symbol = str(payload.get("symbol", "")).strip().upper()
        order_type = str(payload.get("order_type", "market")).upper()
        quantity = payload.get("quantity")
        quote_qty = payload.get("quote_quantity")
        price = payload.get("price")

        # --- basic validation ---
        if not symbol:
            return self._fail("symbol is required", payload)
        if action not in ("buy", "sell", "close"):
            return self._fail(f"Unknown action '{action}'. Use buy/sell/close.", payload)
        if order_type not in ("MARKET", "LIMIT"):
            return self._fail(f"Unknown order_type '{order_type}'. Use market/limit.", payload)
        if quantity is None and quote_qty is None:
            return self._fail("Provide quantity or quote_quantity.", payload)
        if not self._binance.is_configured():
            return self._fail("Binance API credentials not configured.", payload)

        side = "SELL" if action in ("sell", "close") else "BUY"

        try:
            result = self._binance.place_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=float(quantity) if quantity is not None else None,
                quote_order_qty=float(quote_qty) if quote_qty is not None else None,
                price=float(price) if price is not None else None,
            )
            record = self._make_record(
                symbol=symbol, action=action, side=side,
                order_type=order_type, quantity=quantity or quote_qty,
                price=price, status=result.get("status", "UNKNOWN"),
                order_id=result.get("orderId"),
            )
            self._append(record)
            logger.info(f"Order placed: {record['order_id']} {symbol} {side}")
            return {"success": True, "order": result, "record": record}

        except BinanceError as exc:
            record = self._make_record(
                symbol=symbol, action=action, side=side,
                order_type=order_type, quantity=quantity or quote_qty,
                price=price, status="FAILED", error=str(exc),
            )
            self._append(record)
            logger.error(f"Order failed: {exc}")
            return {"success": False, "error": str(exc), "record": record}

    def get_history(self, limit: int = 50) -> list:
        return self._history[:limit]

    def get_balance(self) -> dict:
        if not self._binance.is_configured():
            return {"configured": False, "balances": []}
        try:
            return {"configured": True, "testnet": self._binance.testnet, "balances": self._binance.get_balances()}
        except BinanceError as exc:
            return {"configured": True, "error": str(exc), "balances": []}

    def get_open_orders(self, symbol: str = None) -> dict:
        if not self._binance.is_configured():
            return {"configured": False, "orders": []}
        try:
            orders = self._binance.get_open_orders(symbol)
            return {"configured": True, "orders": orders}
        except BinanceError as exc:
            return {"configured": True, "error": str(exc), "orders": []}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fail(self, msg: str, payload: dict) -> dict:
        record = self._make_record(
            symbol=payload.get("symbol", ""),
            action=payload.get("action", ""),
            side="", order_type="", quantity=None,
            price=None, status="FAILED", error=msg,
        )
        self._append(record)
        return {"success": False, "error": msg, "record": record}

    def _make_record(self, *, symbol, action, side, order_type, quantity,
                     price, status, error=None, order_id=None) -> dict:
        return {
            "order_id": order_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol,
            "action": action,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,
            "status": status,
            "error": error,
        }

    def _append(self, record: dict):
        self._history.insert(0, record)
        max_hist = Config.TRADING_MAX_HISTORY
        if len(self._history) > max_hist:
            self._history = self._history[:max_hist]


# --------------------------------------------------------------------------
# Module-level singleton
# --------------------------------------------------------------------------
_instance: Optional[TradingManager] = None


def get_trading_manager() -> TradingManager:
    global _instance
    if _instance is None:
        _instance = TradingManager()
    return _instance
