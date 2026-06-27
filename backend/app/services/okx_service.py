"""
OKX Spot/Swap REST API v5 service.
Uses HMAC-SHA256 signing — no extra dependencies beyond standard library + requests.
Docs: https://www.okx.com/docs-v5/en/

Mirrors the BinanceService interface so TradingManager can use either exchange
via the TRADING_EXCHANGE config key ('binance' | 'okx').
"""

import base64
import hashlib
import hmac
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.okx')

_LIVE_URL  = "https://www.okx.com"
_DEMO_URL  = "https://www.okx.com"          # same host; demo uses x-simulated-trading header


class OKXError(Exception):
    def __init__(self, message: str, code: str = None):
        super().__init__(message)
        self.code = code


class OKXService:
    """
    OKX API v5 client.

    Supports:
      - Spot orders  (instType=SPOT)
      - Swap/Futures (instType=SWAP)  via instrument like BTC-USDT-SWAP
      - Account balances (unified account)
      - Open orders, cancel order, ticker price
    """

    def __init__(self):
        self.api_key    = Config.OKX_API_KEY
        self.api_secret = Config.OKX_API_SECRET
        self.passphrase = Config.OKX_PASSPHRASE
        self.demo       = Config.OKX_DEMO          # True = paper trading
        self.base_url   = _DEMO_URL if self.demo else _LIVE_URL

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret and self.passphrase)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _timestamp(self) -> str:
        """ISO-8601 UTC timestamp required by OKX."""
        return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

    def _sign(self, timestamp: str, method: str, path: str, body: str = '') -> str:
        """
        OKX signature = base64( HMAC-SHA256( secret, timestamp+method+path+body ) )
        method must be uppercase, path includes query string for GET.
        """
        prehash = timestamp + method.upper() + path + (body or '')
        mac = hmac.new(
            self.api_secret.encode(),
            prehash.encode(),
            hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode()

    def _headers(self, timestamp: str, sign: str) -> dict:
        h = {
            "OK-ACCESS-KEY":        self.api_key,
            "OK-ACCESS-SIGN":       sign,
            "OK-ACCESS-TIMESTAMP":  timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type":         "application/json",
        }
        if self.demo:
            h["x-simulated-trading"] = "1"
        return h

    def _request(
        self,
        method: str,
        path: str,
        params: dict = None,
        json_body: dict = None,
    ):
        """
        Execute a signed OKX API v5 request.

        GET  → params go into query string; body is empty for signing.
        POST → params go into JSON body; query string is empty for signing.
        """
        import json as _json

        method = method.upper()
        ts     = self._timestamp()

        if method == "GET":
            qs      = ("?" + urlencode(params)) if params else ""
            sign_path = path + qs
            body_str  = ""
            url        = self.base_url + path
            req_params = params
            req_json   = None
        else:
            qs        = ""
            body_str  = _json.dumps(json_body or {})
            sign_path = path
            url        = self.base_url + path
            req_params = None
            req_json   = json_body or {}

        sign = self._sign(ts, method, sign_path, body_str)

        try:
            resp = requests.request(
                method, url,
                headers=self._headers(ts, sign),
                params=req_params,
                json=req_json,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise OKXError(f"Network error: {exc}") from exc

        if not resp.ok:
            raise OKXError(f"HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        # OKX wraps all responses: {"code":"0","msg":"","data":[...]}
        code = data.get("code", "0")
        if code != "0":
            msg = data.get("msg", "Unknown OKX error")
            raise OKXError(f"OKX API error {code}: {msg}", code=code)

        return data.get("data", data)

    # ------------------------------------------------------------------
    # Public / market data (no auth needed for ticker)
    # ------------------------------------------------------------------

    def get_ticker_price(self, inst_id: str) -> dict:
        """
        Current best bid/ask + last price for an instrument.
        inst_id examples: BTC-USDT (spot), BTC-USDT-SWAP (perp)
        """
        data = self._request("GET", "/api/v5/market/ticker", {"instId": inst_id.upper()})
        if data:
            t = data[0]
            return {
                "instId": t["instId"],
                "last":   t["last"],
                "bid":    t["bidPx"],
                "ask":    t["askPx"],
                "ts":     t["ts"],
            }
        raise OKXError(f"No ticker data for {inst_id}")

    # ------------------------------------------------------------------
    # Account (unified account)
    # ------------------------------------------------------------------

    def get_balances(self) -> list:
        """
        Non-zero balances from the unified trading account.
        Returns list of {"asset", "available", "frozen", "total"}.
        """
        data = self._request("GET", "/api/v5/account/balance")
        balances = []
        if data:
            for detail in data[0].get("details", []):
                avail = float(detail.get("availBal", 0))
                frozen = float(detail.get("frozenBal", 0))
                total  = float(detail.get("cashBal", 0))
                if total > 0:
                    balances.append({
                        "asset":     detail["ccy"],
                        "available": avail,
                        "frozen":    frozen,
                        "total":     total,
                    })
        return balances

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_order(
        self,
        inst_id: str,
        side: str,           # 'buy' | 'sell'
        order_type: str,     # 'market' | 'limit'
        quantity: float = None,    # sz in base currency (for limit / market qty)
        quote_order_qty: float = None,  # sz in quote (market buy by USDT amount)
        price: float = None,
        td_mode: str = "cash",     # 'cash' for spot, 'cross'/'isolated' for margin/swap
    ) -> dict:
        """
        Place a spot or swap order via OKX Trade API.

        OKX order types mapping:
          market → market
          limit  → limit
        """
        inst_id    = inst_id.upper()
        side       = side.lower()
        order_type = order_type.lower()

        body: dict = {
            "instId":  inst_id,
            "tdMode":  td_mode,
            "side":    side,
            "ordType": order_type,
        }

        if order_type == "market":
            # For market BUY you can specify sz in quote currency (USDT)
            # For market SELL specify sz in base currency
            if side == "buy" and quote_order_qty is not None:
                body["sz"]      = str(quote_order_qty)
                body["tgtCcy"]  = "quote_ccy"   # sz is in quote currency
            elif quantity is not None:
                body["sz"] = str(quantity)
            else:
                raise OKXError("market order requires quantity or quote_order_qty")
        elif order_type == "limit":
            if quantity is None or price is None:
                raise OKXError("limit order requires quantity and price")
            body["sz"]  = str(quantity)
            body["px"]  = str(price)
        else:
            raise OKXError(f"Unsupported order type: {order_type}")

        logger.info(f"Placing OKX order: {body}")
        result = self._request("POST", "/api/v5/trade/order", json_body=body)
        if result:
            return result[0]
        return {}

    def get_open_orders(self, inst_id: str = None) -> list:
        """Pending orders. Optionally filter by instrument."""
        params = {}
        if inst_id:
            params["instId"] = inst_id.upper()
        data = self._request("GET", "/api/v5/trade/orders-pending", params)
        return data or []

    def cancel_order(self, inst_id: str, ord_id: str) -> dict:
        body = {"instId": inst_id.upper(), "ordId": ord_id}
        result = self._request("POST", "/api/v5/trade/cancel-order", json_body=body)
        return result[0] if result else {}

    def get_order_detail(self, inst_id: str, ord_id: str) -> dict:
        data = self._request(
            "GET", "/api/v5/trade/order",
            {"instId": inst_id.upper(), "ordId": ord_id},
        )
        return data[0] if data else {}
