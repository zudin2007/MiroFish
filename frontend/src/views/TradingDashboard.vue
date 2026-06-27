<template>
  <div class="trading-dashboard">
    <div class="dashboard-header">
      <h1>Trading Dashboard</h1>
      <div class="exchange-badge" :class="exchangeName">
        <span class="dot"></span>
        {{ exchangeLabel }}
        <span v-if="isDemo" class="demo-tag">DEMO</span>
        <span v-else-if="isTestnet" class="testnet-tag">TESTNET</span>
      </div>
    </div>

    <!-- ============ BALANCE PANEL ============ -->
    <section class="panel">
      <h2>Account Balance</h2>
      <button @click="fetchBalance" :disabled="loadingBalance" class="btn-refresh">
        {{ loadingBalance ? 'Loading...' : 'Refresh' }}
      </button>
      <div v-if="balanceError" class="error-msg">{{ balanceError }}</div>
      <table v-else-if="balances.length" class="data-table">
        <thead>
          <tr>
            <th>Asset</th>
            <th v-if="exchangeName === 'okx'">Available</th>
            <th v-if="exchangeName === 'okx'">Frozen</th>
            <th v-if="exchangeName === 'okx'">Total</th>
            <th v-if="exchangeName === 'binance'">Free</th>
            <th v-if="exchangeName === 'binance'">Locked</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in balances" :key="b.asset">
            <td><strong>{{ b.asset }}</strong></td>
            <template v-if="exchangeName === 'okx'">
              <td>{{ fmt(b.available) }}</td>
              <td>{{ fmt(b.frozen) }}</td>
              <td>{{ fmt(b.total) }}</td>
            </template>
            <template v-else>
              <td>{{ fmt(b.free) }}</td>
              <td>{{ fmt(b.locked) }}</td>
            </template>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">No balances found — check API credentials.</p>
    </section>

    <!-- ============ TRADINGVIEW SETUP GUIDE ============ -->
    <section class="panel">
      <h2>TradingView Setup Guide</h2>

      <div class="setup-steps">
        <div class="step">
          <span class="step-num">1</span>
          <div>
            <strong>Webhook URL</strong>
            <div class="code-block">
              <code>{{ webhookUrl }}</code>
              <button @click="copy(webhookUrl)" class="btn-copy">Copy</button>
            </div>
            <p class="hint">Paste ini di TradingView Alert → Notifications → Webhook URL</p>
          </div>
        </div>

        <div class="step">
          <span class="step-num">2</span>
          <div>
            <strong>Alert Message JSON</strong>
            <p class="hint">Pilih template sesuai exchange:</p>

            <!-- OKX Templates -->
            <div v-if="exchangeName === 'okx'">
              <p class="label">Spot Market Buy (BTC dengan 50 USDT):</p>
              <div class="code-block">
                <pre><code>{{ okxBuyTemplate }}</code></pre>
                <button @click="copy(okxBuyTemplate)" class="btn-copy">Copy</button>
              </div>
              <p class="label">Spot Market Sell (0.001 BTC):</p>
              <div class="code-block">
                <pre><code>{{ okxSellTemplate }}</code></pre>
                <button @click="copy(okxSellTemplate)" class="btn-copy">Copy</button>
              </div>
              <p class="label">Limit Buy:</p>
              <div class="code-block">
                <pre><code>{{ okxLimitTemplate }}</code></pre>
                <button @click="copy(okxLimitTemplate)" class="btn-copy">Copy</button>
              </div>
              <p class="label">Perpetual Swap (BTC-USDT-SWAP):</p>
              <div class="code-block">
                <pre><code>{{ okxSwapTemplate }}</code></pre>
                <button @click="copy(okxSwapTemplate)" class="btn-copy">Copy</button>
              </div>
            </div>

            <!-- Binance Templates -->
            <div v-else>
              <p class="label">Market Buy (50 USDT):</p>
              <div class="code-block">
                <pre><code>{{ binanceBuyTemplate }}</code></pre>
                <button @click="copy(binanceBuyTemplate)" class="btn-copy">Copy</button>
              </div>
              <p class="label">Market Sell (0.001 BTC):</p>
              <div class="code-block">
                <pre><code>{{ binanceSellTemplate }}</code></pre>
                <button @click="copy(binanceSellTemplate)" class="btn-copy">Copy</button>
              </div>
            </div>

            <div class="secret-status" :class="config.webhook_secret_set ? 'ok' : 'warn'">
              {{ config.webhook_secret_set
                ? '✅ TRADING_WEBHOOK_SECRET sudah diset'
                : '⚠️ TRADING_WEBHOOK_SECRET belum diset — webhook tidak aman!' }}
            </div>
          </div>
        </div>

        <div class="step" v-if="exchangeName === 'okx'">
          <span class="step-num">3</span>
          <div>
            <strong>OKX API Key Setup</strong>
            <ol class="guide-list">
              <li>Login OKX → Profile (pojok kanan atas) → API</li>
              <li>Klik <strong>Create API Key</strong></li>
              <li>Permission: centang <strong>Read</strong> dan <strong>Trade</strong> saja</li>
              <li><strong>JANGAN</strong> centang Withdraw</li>
              <li>Set Passphrase (wajib — simpan baik-baik)</li>
              <li>Jika testing: gunakan OKX Demo Account + set <code>OKX_DEMO=true</code></li>
              <li>Isi <code>OKX_API_KEY</code>, <code>OKX_API_SECRET</code>, <code>OKX_PASSPHRASE</code> di file <code>.env</code></li>
            </ol>
          </div>
        </div>
      </div>
    </section>

    <!-- ============ MANUAL TEST ORDER ============ -->
    <section class="panel">
      <h2>Test Order Manual</h2>
      <div class="form-grid">
        <div class="form-group">
          <label>Symbol</label>
          <input v-model="order.symbol" :placeholder="exchangeName === 'okx' ? 'BTC-USDT' : 'BTCUSDT'" />
        </div>
        <div class="form-group">
          <label>Action</label>
          <select v-model="order.action">
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
          </select>
        </div>
        <div class="form-group">
          <label>Order Type</label>
          <select v-model="order.order_type">
            <option value="market">Market</option>
            <option value="limit">Limit</option>
          </select>
        </div>
        <div class="form-group" v-if="order.order_type === 'limit'">
          <label>Price</label>
          <input v-model="order.price" type="number" placeholder="65000" />
        </div>
        <div class="form-group">
          <label>Quantity (base)</label>
          <input v-model="order.quantity" type="number" placeholder="0.001" />
        </div>
        <div class="form-group">
          <label>Quote Qty (USDT)</label>
          <input v-model="order.quote_qty" type="number" placeholder="50" />
        </div>
      </div>
      <p class="hint">
        Market buy: isi <em>Quote Qty</em> (berapa USDT yang mau dipakai) <br>
        Market sell / limit: isi <em>Quantity</em> (jumlah base coin)
      </p>
      <button @click="placeTestOrder" :disabled="loadingOrder" class="btn-primary">
        {{ loadingOrder ? 'Placing...' : '🚀 Place Order' }}
      </button>
      <div v-if="orderResult" class="result-box" :class="orderResult.success ? 'success' : 'error'">
        <pre>{{ JSON.stringify(orderResult, null, 2) }}</pre>
      </div>
    </section>

    <!-- ============ TRADE HISTORY ============ -->
    <section class="panel">
      <h2>Trade History</h2>
      <button @click="fetchHistory" class="btn-refresh">Refresh</button>
      <table v-if="history.length" class="data-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Exchange</th>
            <th>Symbol</th>
            <th>Action</th>
            <th>Type</th>
            <th>Qty / Quote</th>
            <th>Order ID</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in history" :key="t.timestamp" :class="t.success ? '' : 'row-error'">
            <td>{{ fmtTime(t.timestamp) }}</td>
            <td>{{ t.exchange }}</td>
            <td>{{ t.symbol }}</td>
            <td>{{ t.action }}</td>
            <td>{{ t.order_type }}</td>
            <td>{{ t.quantity || t.quote_qty }}</td>
            <td class="mono">{{ t.order_id || '—' }}</td>
            <td>{{ t.success ? '✅' : '❌ ' + t.error }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">Belum ada trade history.</p>
    </section>

    <!-- ============ OPEN ORDERS ============ -->
    <section class="panel">
      <h2>Open Orders</h2>
      <div class="row-inline">
        <input
          v-model="filterSymbol"
          :placeholder="exchangeName === 'okx' ? 'BTC-USDT (optional)' : 'BTCUSDT (optional)'"
        />
        <button @click="fetchOrders" class="btn-refresh">Refresh</button>
      </div>
      <table v-if="openOrders.length" class="data-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th>Type</th>
            <th>Price</th>
            <th>Qty</th>
            <th>Order ID</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="o in openOrders" :key="o.ordId || o.orderId">
            <td>{{ o.instId || o.symbol }}</td>
            <td>{{ o.side }}</td>
            <td>{{ o.ordType || o.type }}</td>
            <td>{{ o.px || o.price || '—' }}</td>
            <td>{{ o.sz || o.origQty }}</td>
            <td class="mono">{{ o.ordId || o.orderId }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">Tidak ada open order.</p>
    </section>
  </div>
</template>

<script>
import { getBalance, getHistory, getOpenOrders, placeWebhookOrder, getConfig } from '../api/trading.js'

export default {
  name: 'TradingDashboard',
  data() {
    return {
      config: {},
      exchangeName: 'binance',
      balances: [],
      balanceError: null,
      loadingBalance: false,
      history: [],
      openOrders: [],
      filterSymbol: '',
      order: {
        symbol: '',
        action: 'buy',
        order_type: 'market',
        quantity: '',
        quote_qty: '',
        price: '',
      },
      orderResult: null,
      loadingOrder: false,
    }
  },
  computed: {
    isDemo()     { return this.config.demo },
    isTestnet()  { return this.config.testnet },
    exchangeLabel() {
      if (this.exchangeName === 'okx') return 'OKX'
      return 'Binance'
    },
    webhookUrl() {
      return `${window.location.origin}/api/trading/webhook`
    },
    /* OKX templates */
    okxBuyTemplate() {
      return JSON.stringify({
        secret: 'WEBHOOK_SECRET_ANDA',
        action: 'buy',
        symbol: 'BTC-USDT',
        order_type: 'market',
        quote_qty: '50'
      }, null, 2)
    },
    okxSellTemplate() {
      return JSON.stringify({
        secret: 'WEBHOOK_SECRET_ANDA',
        action: 'sell',
        symbol: 'BTC-USDT',
        order_type: 'market',
        quantity: '0.001'
      }, null, 2)
    },
    okxLimitTemplate() {
      return JSON.stringify({
        secret: 'WEBHOOK_SECRET_ANDA',
        action: 'buy',
        symbol: 'BTC-USDT',
        order_type: 'limit',
        quantity: '0.001',
        price: '60000'
      }, null, 2)
    },
    okxSwapTemplate() {
      return JSON.stringify({
        secret: 'WEBHOOK_SECRET_ANDA',
        action: 'buy',
        symbol: 'BTC-USDT-SWAP',
        order_type: 'market',
        quantity: '1'
      }, null, 2)
    },
    /* Binance templates */
    binanceBuyTemplate() {
      return JSON.stringify({
        secret: 'WEBHOOK_SECRET_ANDA',
        action: 'buy',
        symbol: 'BTCUSDT',
        order_type: 'market',
        quote_qty: '50'
      }, null, 2)
    },
    binanceSellTemplate() {
      return JSON.stringify({
        secret: 'WEBHOOK_SECRET_ANDA',
        action: 'sell',
        symbol: 'BTCUSDT',
        order_type: 'market',
        quantity: '0.001'
      }, null, 2)
    },
  },
  async mounted() {
    await this.loadConfig()
    await this.fetchBalance()
    await this.fetchHistory()
  },
  methods: {
    async loadConfig() {
      try {
        const res = await getConfig()
        this.config = res.data
        this.exchangeName = this.config.exchange || 'binance'
      } catch (e) {
        console.error('Config load failed', e)
      }
    },
    async fetchBalance() {
      this.loadingBalance = true
      this.balanceError = null
      try {
        const res = await getBalance()
        this.balances = res.data.balances || []
        if (res.data.error) this.balanceError = res.data.error
      } catch (e) {
        this.balanceError = e.message
      } finally {
        this.loadingBalance = false
      }
    },
    async fetchHistory() {
      try {
        const res = await getHistory()
        this.history = res.data.trades || []
      } catch (e) { console.error(e) }
    },
    async fetchOrders() {
      try {
        const res = await getOpenOrders(this.filterSymbol || null)
        this.openOrders = res.data.orders || []
      } catch (e) { console.error(e) }
    },
    async placeTestOrder() {
      this.loadingOrder = true
      this.orderResult = null
      try {
        const payload = {
          secret:     this.config.webhook_secret_set ? '[from env]' : '',
          action:     this.order.action,
          symbol:     this.order.symbol,
          order_type: this.order.order_type,
        }
        if (this.order.quantity)  payload.quantity  = this.order.quantity
        if (this.order.quote_qty) payload.quote_qty = this.order.quote_qty
        if (this.order.price)     payload.price     = this.order.price

        const res = await placeWebhookOrder(payload)
        this.orderResult = res.data
        await this.fetchHistory()
      } catch (e) {
        this.orderResult = { success: false, error: e.message }
      } finally {
        this.loadingOrder = false
      }
    },
    copy(text) {
      navigator.clipboard.writeText(text).catch(() => {})
    },
    fmt(n) {
      return n != null ? parseFloat(n).toFixed(6) : '—'
    },
    fmtTime(ts) {
      return new Date(ts).toLocaleString('id-ID')
    },
  },
}
</script>

<style scoped>
.trading-dashboard { max-width: 1100px; margin: 0 auto; padding: 24px; font-family: sans-serif; }
.dashboard-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.exchange-badge { display: flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 20px; font-weight: 600; font-size: 14px; }
.exchange-badge.okx { background: #1a1a2e; color: #00d4ff; }
.exchange-badge.binance { background: #1a1a0e; color: #f0b90b; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.demo-tag, .testnet-tag { font-size: 11px; padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,0.15); }
.panel { background: #1e1e2e; border-radius: 12px; padding: 24px; margin-bottom: 20px; }
.panel h2 { color: #cdd6f4; margin-top: 0; }
.data-table { width: 100%; border-collapse: collapse; color: #cdd6f4; font-size: 13px; }
.data-table th, .data-table td { padding: 8px 12px; border-bottom: 1px solid #313244; text-align: left; }
.data-table th { color: #a6adc8; }
.row-error td { color: #f38ba8; }
.form-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; margin-bottom: 12px; }
.form-group label { display: block; font-size: 12px; color: #a6adc8; margin-bottom: 4px; }
input, select { width: 100%; padding: 8px; border-radius: 6px; border: 1px solid #45475a; background: #181825; color: #cdd6f4; }
.btn-primary { background: #89b4fa; color: #1e1e2e; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-weight: 600; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-refresh { background: #313244; color: #cdd6f4; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; margin-bottom: 12px; }
.btn-copy { background: #45475a; color: #cdd6f4; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; }
.code-block { display: flex; align-items: flex-start; gap: 8px; background: #181825; border-radius: 8px; padding: 10px; margin: 8px 0; }
.code-block code, .code-block pre { flex: 1; margin: 0; color: #a6e3a1; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
.error-msg { color: #f38ba8; padding: 8px; }
.muted { color: #6c7086; }
.hint { color: #a6adc8; font-size: 12px; }
.label { color: #cba6f7; font-size: 12px; margin: 8px 0 2px; }
.secret-status { margin-top: 12px; padding: 8px 12px; border-radius: 8px; font-size: 13px; }
.secret-status.ok { background: #1e3a2e; color: #a6e3a1; }
.secret-status.warn { background: #3a2e1e; color: #fab387; }
.result-box { margin-top: 12px; padding: 12px; border-radius: 8px; }
.result-box.success { background: #1e3a2e; }
.result-box.error { background: #3a1e1e; }
.result-box pre { color: #cdd6f4; font-size: 12px; margin: 0; white-space: pre-wrap; }
.step { display: flex; gap: 16px; margin-bottom: 20px; }
.step-num { width: 28px; height: 28px; border-radius: 50%; background: #89b4fa; color: #1e1e2e; display: flex; align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0; }
.guide-list li { margin: 6px 0; color: #cdd6f4; font-size: 13px; }
.row-inline { display: flex; gap: 8px; margin-bottom: 12px; }
.row-inline input { max-width: 220px; }
.mono { font-family: monospace; font-size: 11px; }
</style>
