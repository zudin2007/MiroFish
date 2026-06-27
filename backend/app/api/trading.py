"""
Trading API blueprint — TradingView webhook receiver + Binance trade management.

Endpoints:
  POST /api/trading/webhook     — receive TradingView alert
  GET  /api/trading/balance     — Binance account balances
  GET  /api/trading/history     — local trade history
  GET  /api/trading/orders      — open orders on Binance
  GET  /api/trading/config      — public config info (no secrets)
  GET  /api/trading/price       — current price for a symbol
"""

import hmac

from flask import jsonify, request

from ..config import Config
from ..utils.logger import get_logger
from . import trading_bp
from ..services.trading_manager import get_trading_manager

logger = get_logger('mirofish.api.trading')


# ---------------------------------------------------------------------------
# Webhook — TradingView → Binance
# ---------------------------------------------------------------------------

@trading_bp.route('/webhook', methods=['POST'])
def receive_webhook():
    """Receive a TradingView alert and execute a Binance order."""
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"success": False, "error": "Request body must be valid JSON"}), 400

    logger.info(f"Webhook received from {request.remote_addr}: action={payload.get('action')} symbol={payload.get('symbol')}")

    manager = get_trading_manager()

    # Validate webhook secret
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
# Open orders on Binance
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
    if not manager.binance.is_configured():
        return jsonify({"error": "Binance not configured"}), 503
    try:
        data = manager.binance.get_ticker_price(symbol)
        return jsonify(data)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Configuration info (no secrets returned)
# ---------------------------------------------------------------------------

@trading_bp.route('/config', methods=['GET'])
def get_config():
    return jsonify({
        "binance_configured": bool(Config.BINANCE_API_KEY and Config.BINANCE_API_SECRET),
        "testnet": Config.BINANCE_TESTNET,
        "webhook_secret_set": bool(Config.TRADING_WEBHOOK_SECRET),
        "webhook_endpoint": "/api/trading/webhook",
        "max_history": Config.TRADING_MAX_HISTORY,
    })
