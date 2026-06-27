"""
TradingManager — exchange-agnostic signal processor.

Reads TRADING_EXCHANGE from config to decide which service to use:
  'binance' → BinanceService  (original PR #2)
  'okx'     → OKXService      (new addition)

Payload fields (same for both exchanges):
  {
    "secret":      "...",          # must match TRADING_WEBHOOK_SECRET
    "action":      "buy"|"sell",
    "symbol":      "BTC-USDT",    # OKX format; Binance auto-normalises to BTCUSDT
    "quantity":    "0.001",        # base currency qty (optional if quote_qty set)
    "quote_qty":   "50",           # quote currency qty (market buy in USDT)
    "order_type":  "market"|"limit",
    "price":       "65000"         # required for limit
  }
"""

import hmac
import threading
import time
from collections import deque
from typing import Optional

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.trading_manager')

_manager_lock = threading.Lock()
_manager: Optional["TradingManager"] = None


def get_trading_manager() -> "TradingManager":
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = TradingManager()
    return _manager


class TradingManager:
    """
    Exchange-agnostic trading manager.
    Instantiates the correct exchange service based on TRADING_EXCHANGE config.
    """

    def __init__(self):
        exchange = Config.TRADING_EXCHANGE.lower()

        if exchange == "okx":
            from .okx_service import OKXService
            self.exchange = OKXService()
            self.exchange_name = "okx"
            logger.info("TradingManager initialised with OKX backend")
        else:
            from .binance_service import BinanceService
            self.exchange = BinanceService()
            self.exchange_name = "binance"
            logger.info("TradingManager initialised with Binance backend")

        self._history: deque = deque(maxlen=Config.TRADING_MAX_HISTORY)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Webhook secret validation
    # ------------------------------------------------------------------

    def validate_secret(self, payload: dict) -> bool:
        """Constant-time comparison to prevent timing attacks."""
        expected = Config.TRADING_WEBHOOK_SECRET
        if not expected:
            logger.warning("TRADING_WEBHOOK_SECRET not set — accepting all webhooks (INSECURE)")
            return True
        received = payload.get("secret", "")
        return hmac.compare_digest(
            expected.encode("utf-8"),
            received.encode("utf-8"),
        )

    # ------------------------------------------------------------------
    # Signal processing
    # ------------------------------------------------------------------

    def process_signal(self, payload: dict) -> dict:
        """
        Parse TradingView alert payload and place order on the configured exchange.
        Returns a result dict with success / error / trade_record.
        """
        action     = payload.get("action", "").lower()
        symbol     = payload.get("symbol", "").strip()
        qty_str    = payload.get("quantity")
        quote_str  = payload.get("quote_qty")
        order_type = payload.get("order_type", "market").lower()
        price_str  = payload.get("price")

        # --- basic validation ---
        if action not in ("buy", "sell"):
            return {"success": False, "error": f"Invalid action: '{action}'. Use 'buy' or 'sell'."}
        if not symbol:
            return {"success": False, "error": "Missing 'symbol' in payload."}

        quantity   = float(qty_str)   if qty_str   else None
        quote_qty  = float(quote_str) if quote_str else None
        price      = float(price_str) if price_str else None

        if quantity is None and quote_qty is None:
            return {"success": False, "error": "Provide 'quantity' (base) or 'quote_qty' (quote currency)."}

        if not self.exchange.is_configured():
            return {
                "success": False,
                "error": f"{self.exchange_name.upper()} API credentials not configured.",
            }

        # --- normalise symbol per exchange ---
        norm_symbol = self._normalise_symbol(symbol)

        try:
            if self.exchange_name == "okx":
                result = self.exchange.place_order(
                    inst_id=norm_symbol,
                    side=action,
                    order_type=order_type,
                    quantity=quantity,
                    quote_order_qty=quote_qty,
                    price=price,
                )
            else:
                # Binance
                result = self.exchange.place_order(
                    symbol=norm_symbol,
                    side=action,
                    order_type=order_type,
                    quantity=quantity,
                    quote_order_qty=quote_qty,
                    price=price,
                )

            record = self._make_record(payload, norm_symbol, action, order_type, result, success=True)
            self._save(record)
            logger.info(f"Order placed: {record}")
            return {"success": True, "trade": record}

        except Exception as exc:
            record = self._make_record(payload, norm_symbol, action, order_type, {}, success=False, error=str(exc))
            self._save(record)
            logger.error(f"Order failed: {exc}")
            return {"success": False, "error": str(exc), "trade": record}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalise_symbol(self, symbol: str) -> str:
        """
        OKX uses dashes:  BTC-USDT, BTC-USDT-SWAP
        Binance uses run-together: BTCUSDT

        If TRADING_EXCHANGE=okx and user passes 'BTCUSDT', convert to 'BTC-USDT'.
        Simple heuristic: if no dash and exchange is okx, insert dash before USDT/BTC/ETH quote.
        """
        symbol = symbol.upper().strip()
        if self.exchange_name == "okx" and "-" not in symbol:
            for quote in ("USDT", "USDC", "BTC", "ETH"):
                if symbol.endswith(quote):
                    base = symbol[: -len(quote)]
                    symbol = f"{base}-{quote}"
                    break
        elif self.exchange_name == "binance" and "-" in symbol:
            symbol = symbol.replace("-", "")
        return symbol

    def _make_record(
        self,
        payload: dict,
        symbol: str,
        action: str,
        order_type: str,
        result: dict,
        success: bool,
        error: str = None,
    ) -> dict:
        record = {
            "timestamp":   int(time.time() * 1000),
            "exchange":    self.exchange_name,
            "symbol":      symbol,
            "action":      action,
            "order_type":  order_type,
            "quantity":    payload.get("quantity"),
            "quote_qty":   payload.get("quote_qty"),
            "price":       payload.get("price"),
            "success":     success,
            "raw_result":  result,
        }
        if error:
            record["error"] = error
        # Extract order ID from exchange response
        if self.exchange_name == "okx":
            record["order_id"] = result.get("ordId")
            record["client_order_id"] = result.get("clOrdId")
        else:
            record["order_id"] = result.get("orderId")
            record["client_order_id"] = result.get("clientOrderId")
        return record

    def _save(self, record: dict):
        with self._lock:
            self._history.appendleft(record)

    # ------------------------------------------------------------------
    # Query methods (called by API routes)
    # ------------------------------------------------------------------

    def get_balance(self) -> dict:
        if not self.exchange.is_configured():
            return {"error": f"{self.exchange_name.upper()} not configured", "balances": []}
        try:
            balances = self.exchange.get_balances()
            return {"exchange": self.exchange_name, "balances": balances}
        except Exception as exc:
            return {"error": str(exc), "balances": []}

    def get_history(self, limit: int = 50) -> list:
        with self._lock:
            return list(self._history)[:limit]

    def get_open_orders(self, symbol: str = None) -> dict:
        if not self.exchange.is_configured():
            return {"error": f"{self.exchange_name.upper()} not configured", "orders": []}
        try:
            norm = self._normalise_symbol(symbol) if symbol else None
            if self.exchange_name == "okx":
                orders = self.exchange.get_open_orders(inst_id=norm)
            else:
                orders = self.exchange.get_open_orders(symbol=norm)
            return {"exchange": self.exchange_name, "orders": orders}
        except Exception as exc:
            return {"error": str(exc), "orders": []}
