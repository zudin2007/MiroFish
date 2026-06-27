"""
Trading API blueprint — TradingView webhook receiver + exchange trade management.
Supports Binance (original) and OKX (new addition).

Endpoints:
  POST /api/trading/webhook  — receive TradingView alert → place order
  GET  /api/trading/balance  — account balances
  GET  /api/trading/history  — local trade history
  GET  /api/trading/orders   — open orders on exchange
  GET  /api/trading/price    — current ticker price
  GET  /api/trading/config   — public config info (no secrets)
"""

import hmac

from flask import jsonify, request

from ..config import Config
from ..utils.logger import get_logger
from . import trading_bp
from ..services.trading_manager import get_trading_manager

logger = get_logger('mirofish.api.trading')


# ---------------------------------------------------------------------------
# Webhook — TradingView → Exchange
# ---------------------------------------------------------------------------

@trading_bp.route('/webhook', methods=['POST'])
def receive_webhook():
    """Receive a TradingView alert and execute an order on the configured exchange."""
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "Request body must be valid JSON"}), 400

    logger.info(
        f"Webhook received from {request.remote_addr}: "
        f"action={payload.get('action')} symbol={payload.get('symbol')}"
    )

    manager = get_trading_manager()

    if not manager.validate_secret(payload):
        logger.warning("Webhook rejected: secret mismatch")
        return jsonify({"success": False, "error": "Invalid webhook secret"}), 401

    result = manager.process_signal(payload)
    return jsonify(result), 200 if result["success"] else 400


# ---------------------------------------------------------------------------
# Account & balance
# ---------------------------------------------------------------------------

@trading_bp.route('/balance', methods=['GET'])
def get_balance():
    manager = get_trading_manager()
    return jsonify(manager.get_balance())


# ---------------------------------------------------------------------------
# Trade history (in-memory)
# ---------------------------------------------------------------------------

@trading_bp.route('/history', methods=['GET'])
def get_history():
    limit = request.args.get('limit', 50, type=int)
    manager = get_trading_manager()
    trades = manager.get_history(limit=limit)
    return jsonify({"trades": trades, "total": len(trades)})


# ---------------------------------------------------------------------------
# Open orders on exchange
# ---------------------------------------------------------------------------

@trading_bp.route('/orders', methods=['GET'])
def get_open_orders():
    symbol = request.args.get('symbol')
    manager = get_trading_manager()
    return jsonify(manager.get_open_orders(symbol))


# ---------------------------------------------------------------------------
# Current price
# ---------------------------------------------------------------------------

@trading_bp.route('/price', methods=['GET'])
def get_price():
    symbol = request.args.get('symbol', '').strip().upper()
    if not symbol:
        return jsonify({"error": "symbol parameter required"}), 400

    manager = get_trading_manager()
    if not manager.exchange.is_configured():
        return jsonify({"error": f"{manager.exchange_name.upper()} not configured"}), 503

    try:
        if manager.exchange_name == "okx":
            # OKX uses inst_id format: BTC-USDT
            data = manager.exchange.get_ticker_price(symbol)
        else:
            data = manager.exchange.get_ticker_price(symbol)
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Configuration info (no secrets returned)
# ---------------------------------------------------------------------------

@trading_bp.route('/config', methods=['GET'])
def get_config():
    manager = get_trading_manager()
    exchange = Config.TRADING_EXCHANGE.lower()

    base = {
        "exchange":             exchange,
        "webhook_secret_set":   bool(Config.TRADING_WEBHOOK_SECRET),
        "webhook_endpoint":     "/api/trading/webhook",
        "max_history":          Config.TRADING_MAX_HISTORY,
    }

    if exchange == "okx":
        base.update({
            "okx_configured": bool(Config.OKX_API_KEY and Config.OKX_API_SECRET and Config.OKX_PASSPHRASE),
            "demo":           Config.OKX_DEMO,
        })
    else:
        base.update({
            "binance_configured": bool(Config.BINANCE_API_KEY and Config.BINANCE_API_SECRET),
            "testnet":            Config.BINANCE_TESTNET,
        })

    return jsonify(base)
