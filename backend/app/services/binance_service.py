"""
Binance Spot REST API service.
Uses HMAC-SHA256 signing — no extra dependencies beyond the standard library + requests.
Docs: https://binance-docs.github.io/apidocs/spot/en/
"""

import hashlib
import hmac
import time
from urllib.parse import urlencode

import requests

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.binance')

_LIVE_URL = "https://api.binance.com"
_TESTNET_URL = "https://testnet.binance.vision"


class BinanceError(Exception):
    def __init__(self, message: str, code: int = None):
        super().__init__(message)
        self.code = code


class BinanceService:
    def __init__(self):
        self.api_key = Config.BINANCE_API_KEY
        self.api_secret = Config.BINANCE_API_SECRET
        self.testnet = Config.BINANCE_TESTNET
        self.base_url = _TESTNET_URL if self.testnet else _LIVE_URL

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sign(self, params: dict) -> str:
        query = urlencode(params)
        return hmac.new(
            self.api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _headers(self) -> dict:
        return {"X-MBX-APIKEY": self.api_key}

    def _request(self, method: str, endpoint: str, params: dict = None, signed: bool = False):
        params = dict(params or {})
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["signature"] = self._sign(params)

        url = self.base_url + endpoint
        try:
            resp = requests.request(
                method, url,
                headers=self._headers(),
                params=params,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise BinanceError(f"Network error: {exc}") from exc

        if not resp.ok:
            data = resp.json() if resp.content else {}
            msg = data.get("msg", resp.text)
            code = data.get("code")
            raise BinanceError(f"Binance {resp.status_code}: {msg}", code=code)

        return resp.json()

    # ------------------------------------------------------------------
    # Public API (no signature)
    # ------------------------------------------------------------------

    def get_ticker_price(self, symbol: str) -> dict:
        """Current price for a symbol."""
        return self._request("GET", "/api/v3/ticker/price", {"symbol": symbol.upper()})

    def get_exchange_info(self, symbol: str = None) -> dict:
        params = {"symbol": symbol.upper()} if symbol else {}
        return self._request("GET", "/api/v3/exchangeInfo", params)

    def get_lot_size(self, symbol: str) -> dict:
        """Return minQty, maxQty, stepSize for a symbol's LOT_SIZE filter."""
        info = self.get_exchange_info(symbol)
        for sym in info.get("symbols", []):
            if sym["symbol"] == symbol.upper():
                for f in sym.get("filters", []):
                    if f["filterType"] == "LOT_SIZE":
                        return {
                            "minQty": float(f["minQty"]),
                            "maxQty": float(f["maxQty"]),
                            "stepSize": float(f["stepSize"]),
                        }
        return {}

    # ------------------------------------------------------------------
    # Private / signed API
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        return self._request("GET", "/api/v3/account", signed=True)

    def get_balances(self) -> list:
        """Non-zero balances."""
        account = self.get_account()
        return [
            {
                "asset": b["asset"],
                "free": float(b["free"]),
                "locked": float(b["locked"]),
            }
            for b in account.get("balances", [])
            if float(b["free"]) > 0 or float(b["locked"]) > 0
        ]

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float = None,
        quote_order_qty: float = None,
        price: float = None,
        time_in_force: str = "GTC",
    ) -> dict:
        params = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
        }
        if quantity is not None:
            params["quantity"] = quantity
        if quote_order_qty is not None:
            params["quoteOrderQty"] = quote_order_qty
        if order_type.upper() == "LIMIT":
            if price is None:
                raise BinanceError("price required for LIMIT orders")
            params["price"] = price
            params["timeInForce"] = time_in_force

        logger.info(f"Placing order: {params}")
        return self._request("POST", "/api/v3/order", params, signed=True)

    def get_open_orders(self, symbol: str = None) -> list:
        params = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request("GET", "/api/v3/openOrders", params, signed=True)

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        return self._request(
            "DELETE", "/api/v3/order",
            {"symbol": symbol.upper(), "orderId": order_id},
            signed=True,
        )

    def get_my_trades(self, symbol: str, limit: int = 50) -> list:
        return self._request(
            "GET", "/api/v3/myTrades",
            {"symbol": symbol.upper(), "limit": limit},
            signed=True,
        )
