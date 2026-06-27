/**
 * Frontend API wrappers for the /api/trading/* endpoints.
 * Supports both Binance (original) and OKX (new addition).
 */

import axios from 'axios'

const BASE = '/api/trading'

/**
 * Fetch public config (exchange name, demo/testnet flag, secret status).
 */
export const getConfig = () =>
  axios.get(`${BASE}/config`)

/**
 * Fetch account balances from the configured exchange.
 */
export const getBalance = () =>
  axios.get(`${BASE}/balance`)

/**
 * Fetch local in-memory trade history.
 * @param {number} limit - max records (default 50)
 */
export const getHistory = (limit = 50) =>
  axios.get(`${BASE}/history`, { params: { limit } })

/**
 * Fetch open orders from the exchange.
 * @param {string|null} symbol - filter by symbol (optional)
 *   OKX format: 'BTC-USDT' | Binance format: 'BTCUSDT'
 */
export const getOpenOrders = (symbol = null) =>
  axios.get(`${BASE}/orders`, { params: symbol ? { symbol } : {} })

/**
 * Get current ticker price.
 * @param {string} symbol - e.g. 'BTC-USDT' (OKX) or 'BTCUSDT' (Binance)
 */
export const getTickerPrice = (symbol) =>
  axios.get(`${BASE}/price`, { params: { symbol } })

/**
 * Send a TradingView-compatible webhook payload to place an order.
 *
 * Payload shape:
 * {
 *   secret:     string,    // must match TRADING_WEBHOOK_SECRET
 *   action:     'buy'|'sell',
 *   symbol:     string,    // 'BTC-USDT' (OKX) or 'BTCUSDT' (Binance)
 *   order_type: 'market'|'limit',
 *   quantity:   string,    // base currency amount (optional)
 *   quote_qty:  string,    // USDT amount for market buy (optional)
 *   price:      string,    // required for limit orders
 * }
 */
export const placeWebhookOrder = (payload) =>
  axios.post(`${BASE}/webhook`, payload)
