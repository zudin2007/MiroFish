<template>
  <div class="trading-container">
    <!-- Navbar -->
    <nav class="navbar">
      <div class="nav-brand" @click="$router.push('/')" style="cursor:pointer">MIROFISH</div>
      <div class="nav-center">
        <span class="nav-badge" :class="configStatus.binance_configured ? 'badge-live' : 'badge-warn'">
          {{ configStatus.binance_configured ? (configStatus.testnet ? 'TESTNET' : 'LIVE') : 'NOT CONFIGURED' }}
        </span>
      </div>
      <div class="nav-links">
        <button class="refresh-btn" @click="loadAll" :disabled="loading">
          {{ loading ? 'Loading...' : '↺ Refresh' }}
        </button>
      </div>
    </nav>

    <div class="page-body">
      <!-- Page title -->
      <div class="page-header">
        <div>
          <h1 class="page-title">Trading Automation</h1>
          <p class="page-sub">TradingView → Binance auto-execution via webhook</p>
        </div>
        <div class="testnet-tag" v-if="configStatus.testnet">TESTNET MODE</div>
      </div>

      <!-- Top cards: Balance + Webhook setup -->
      <div class="cards-row">

        <!-- Balance card -->
        <div class="card">
          <div class="card-header">
            <span class="card-label">ACCOUNT BALANCE</span>
            <span class="status-dot" :class="configStatus.binance_configured ? 'dot-green' : 'dot-gray'"></span>
          </div>

          <div v-if="!configStatus.binance_configured" class="not-configured">
            <p>Binance API not configured.</p>
            <p class="hint">Set <code>BINANCE_API_KEY</code> and <code>BINANCE_API_SECRET</code> in <code>.env</code></p>
          </div>
          <div v-else-if="balanceError" class="error-text">{{ balanceError }}</div>
          <div v-else class="balance-list">
            <div v-if="balances.length === 0" class="empty-text">No non-zero balances</div>
            <div v-for="b in balances" :key="b.asset" class="balance-row">
              <span class="asset-name">{{ b.asset }}</span>
              <div class="asset-amounts">
                <span class="amount-free">{{ b.free.toFixed(6) }}</span>
                <span class="amount-locked" v-if="b.locked > 0"> (+{{ b.locked.toFixed(6) }} locked)</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Webhook setup card -->
        <div class="card">
          <div class="card-header">
            <span class="card-label">TRADINGVIEW SETUP</span>
          </div>
          <div class="setup-steps">
            <div class="setup-step">
              <span class="step-num">01</span>
              <div>
                <div class="step-title">Webhook URL</div>
                <div class="webhook-url-box">
                  <code>{{ serverOrigin }}/api/trading/webhook</code>
                  <button class="copy-btn" @click="copyWebhookUrl">Copy</button>
                </div>
              </div>
            </div>
            <div class="setup-step">
              <span class="step-num">02</span>
              <div>
                <div class="step-title">Alert Message (JSON)</div>
                <pre class="code-block">{{ webhookExample }}</pre>
              </div>
            </div>
            <div class="setup-step">
              <span class="step-num">03</span>
              <div>
                <div class="step-title">Secret validation</div>
                <div class="hint">
                  {{ configStatus.webhook_secret_set
                    ? 'Webhook secret is set. Add the same value in the JSON above.'
                    : 'No webhook secret set. Set TRADING_WEBHOOK_SECRET in .env for security.' }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Manual test panel -->
      <div class="card">
        <div class="card-header">
          <span class="card-label">MANUAL TEST ORDER</span>
          <span class="hint">Simulate a TradingView alert manually</span>
        </div>
        <div class="test-form">
          <div class="form-row">
            <div class="form-group">
              <label>Action</label>
              <select v-model="testForm.action" class="form-control">
                <option value="buy">BUY</option>
                <option value="sell">SELL</option>
              </select>
            </div>
            <div class="form-group">
              <label>Symbol</label>
              <input v-model="testForm.symbol" class="form-control" placeholder="BTCUSDT" />
            </div>
            <div class="form-group">
              <label>Order Type</label>
              <select v-model="testForm.order_type" class="form-control">
                <option value="market">MARKET</option>
                <option value="limit">LIMIT</option>
              </select>
            </div>
            <div class="form-group">
              <label>Quantity (base)</label>
              <input v-model.number="testForm.quantity" class="form-control" type="number" step="any" placeholder="0.001" />
            </div>
            <div class="form-group">
              <label>Quote Qty (USDT)</label>
              <input v-model.number="testForm.quote_quantity" class="form-control" type="number" step="any" placeholder="10" />
            </div>
            <div class="form-group" v-if="testForm.order_type === 'limit'">
              <label>Price</label>
              <input v-model.number="testForm.price" class="form-control" type="number" step="any" placeholder="65000" />
            </div>
          </div>
          <div class="form-actions">
            <button class="btn-primary" @click="sendTestOrder" :disabled="testLoading">
              {{ testLoading ? 'Sending...' : 'Send Test Order →' }}
            </button>
            <span v-if="testResult" :class="testResult.success ? 'result-ok' : 'result-err'">
              {{ testResult.success ? 'Order placed: ' + (testResult.order?.orderId || '') : 'Error: ' + testResult.error }}
            </span>
          </div>
        </div>
      </div>

      <!-- Trade history -->
      <div class="card">
        <div class="card-header">
          <span class="card-label">TRADE HISTORY</span>
          <span class="hint">Latest {{ history.length }} trades received by webhook</span>
        </div>
        <div v-if="history.length === 0" class="empty-text">No trades recorded yet.</div>
        <table v-else class="trade-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Symbol</th>
              <th>Action</th>
              <th>Type</th>
              <th>Qty</th>
              <th>Price</th>
              <th>Status</th>
              <th>Order ID</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(t, i) in history" :key="i" :class="t.status === 'FAILED' ? 'row-fail' : 'row-ok'">
              <td class="td-mono">{{ formatTime(t.timestamp) }}</td>
              <td class="td-symbol">{{ t.symbol }}</td>
              <td :class="t.side === 'BUY' ? 'td-buy' : 'td-sell'">{{ t.action?.toUpperCase() }}</td>
              <td class="td-mono">{{ t.order_type }}</td>
              <td class="td-mono">{{ t.quantity ?? '—' }}</td>
              <td class="td-mono">{{ t.price ?? '—' }}</td>
              <td>
                <span class="status-badge" :class="statusClass(t.status)">{{ t.status }}</span>
              </td>
              <td class="td-mono">{{ t.order_id ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Open orders -->
      <div class="card">
        <div class="card-header">
          <span class="card-label">OPEN ORDERS ON BINANCE</span>
          <div class="order-filter">
            <input v-model="orderSymbol" class="form-control-sm" placeholder="Filter by symbol..." />
            <button class="btn-sm" @click="loadOpenOrders">Fetch</button>
          </div>
        </div>
        <div v-if="!configStatus.binance_configured" class="not-configured">Binance not configured.</div>
        <div v-else-if="openOrdersError" class="error-text">{{ openOrdersError }}</div>
        <div v-else-if="openOrders.length === 0" class="empty-text">No open orders.</div>
        <table v-else class="trade-table">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Symbol</th>
              <th>Side</th>
              <th>Type</th>
              <th>Qty</th>
              <th>Price</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="o in openOrders" :key="o.orderId">
              <td class="td-mono">{{ o.orderId }}</td>
              <td class="td-symbol">{{ o.symbol }}</td>
              <td :class="o.side === 'BUY' ? 'td-buy' : 'td-sell'">{{ o.side }}</td>
              <td class="td-mono">{{ o.type }}</td>
              <td class="td-mono">{{ o.origQty }}</td>
              <td class="td-mono">{{ o.price }}</td>
              <td><span class="status-badge badge-open">{{ o.status }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { tradingApi } from '../api/trading'

const loading = ref(false)
const testLoading = ref(false)

const configStatus = ref({ binance_configured: false, testnet: true, webhook_secret_set: false })
const balances = ref([])
const balanceError = ref('')
const history = ref([])
const openOrders = ref([])
const openOrdersError = ref('')
const orderSymbol = ref('')
const testResult = ref(null)

const testForm = ref({
  action: 'buy',
  symbol: 'BTCUSDT',
  order_type: 'market',
  quantity: null,
  quote_quantity: 10,
  price: null,
})

const serverOrigin = computed(() => window.location.origin.replace('3000', '5001'))

const webhookExample = computed(() => JSON.stringify({
  action: 'buy',
  symbol: 'BTCUSDT',
  order_type: 'market',
  quote_quantity: 10,
  secret: configStatus.value.webhook_secret_set ? '<your-secret>' : '',
}, null, 2))

async function loadAll() {
  loading.value = true
  await Promise.allSettled([loadConfig(), loadBalance(), loadHistory(), loadOpenOrders()])
  loading.value = false
}

async function loadConfig() {
  try {
    const res = await tradingApi.getConfig()
    configStatus.value = res
  } catch {}
}

async function loadBalance() {
  balanceError.value = ''
  try {
    const res = await tradingApi.getBalance()
    if (res.error) { balanceError.value = res.error; return }
    balances.value = res.balances || []
  } catch (e) {
    balanceError.value = e.message || 'Failed to load balance'
  }
}

async function loadHistory() {
  try {
    const res = await tradingApi.getHistory(100)
    history.value = res.trades || []
  } catch {}
}

async function loadOpenOrders() {
  openOrdersError.value = ''
  try {
    const res = await tradingApi.getOpenOrders(orderSymbol.value)
    if (res.error) { openOrdersError.value = res.error; return }
    openOrders.value = res.orders || []
  } catch (e) {
    openOrdersError.value = e.message || 'Failed to load orders'
  }
}

async function sendTestOrder() {
  testLoading.value = true
  testResult.value = null
  const payload = { ...testForm.value }
  // Remove nulls
  Object.keys(payload).forEach(k => { if (payload[k] === null || payload[k] === '') delete payload[k] })
  try {
    const res = await tradingApi.sendWebhook(payload)
    testResult.value = res
    await loadHistory()
    await loadBalance()
  } catch (e) {
    testResult.value = { success: false, error: e.response?.data?.error || e.message }
  } finally {
    testLoading.value = false
  }
}

function copyWebhookUrl() {
  navigator.clipboard.writeText(`${serverOrigin.value}/api/trading/webhook`)
}

function formatTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

function statusClass(status) {
  if (!status) return ''
  if (status === 'FAILED') return 'badge-fail'
  if (['FILLED', 'PARTIALLY_FILLED'].includes(status)) return 'badge-fill'
  return 'badge-open'
}

onMounted(loadAll)
</script>

<style scoped>
:root {
  --black: #000;
  --white: #fff;
  --orange: #FF4500;
  --green: #00C851;
  --red: #FF4444;
  --gray: #666;
  --border: #E5E5E5;
  --mono: 'JetBrains Mono', monospace;
}

.trading-container {
  min-height: 100vh;
  background: #fff;
  font-family: 'Space Grotesk', system-ui, sans-serif;
}

/* Navbar */
.navbar {
  height: 60px;
  background: #000;
  color: #fff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 40px;
}
.nav-brand { font-family: var(--mono); font-weight: 800; font-size: 1.2rem; letter-spacing: 1px; }
.nav-center { display: flex; align-items: center; }
.nav-badge {
  font-family: var(--mono);
  font-size: 0.7rem;
  font-weight: 700;
  padding: 3px 10px;
  letter-spacing: 1px;
}
.badge-live { background: #00C851; color: #000; }
.badge-warn { background: #FF8800; color: #000; }
.nav-links { display: flex; gap: 12px; }
.refresh-btn {
  background: transparent;
  border: 1px solid #444;
  color: #fff;
  font-family: var(--mono);
  font-size: 0.8rem;
  padding: 6px 14px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.refresh-btn:hover:not(:disabled) { border-color: #FF4500; color: #FF4500; }
.refresh-btn:disabled { opacity: 0.5; cursor: default; }

/* Page body */
.page-body { max-width: 1400px; margin: 0 auto; padding: 40px; }

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 32px;
}
.page-title { font-size: 2.4rem; font-weight: 500; margin: 0 0 6px; }
.page-sub { color: #666; font-size: 0.95rem; margin: 0; }
.testnet-tag {
  background: #FF8800;
  color: #000;
  font-family: var(--mono);
  font-size: 0.75rem;
  font-weight: 700;
  padding: 6px 14px;
  letter-spacing: 1px;
  align-self: center;
}

/* Cards */
.cards-row { display: grid; grid-template-columns: 1fr 1.6fr; gap: 24px; margin-bottom: 24px; }
.card {
  border: 1px solid #E5E5E5;
  padding: 28px;
  margin-bottom: 24px;
}
.cards-row .card { margin-bottom: 0; }
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.card-label {
  font-family: var(--mono);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 1.5px;
  color: #999;
}

/* Status dot */
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot-green { background: #00C851; }
.dot-gray { background: #999; }

/* Balance */
.balance-list { display: flex; flex-direction: column; gap: 12px; }
.balance-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #F0F0F0; }
.asset-name { font-family: var(--mono); font-weight: 700; font-size: 1rem; }
.amount-free { font-family: var(--mono); font-size: 0.95rem; }
.amount-locked { font-family: var(--mono); font-size: 0.8rem; color: #999; }

/* Setup steps */
.setup-steps { display: flex; flex-direction: column; gap: 20px; }
.setup-step { display: flex; gap: 18px; align-items: flex-start; }
.step-num { font-family: var(--mono); font-weight: 700; opacity: 0.3; font-size: 1rem; min-width: 28px; }
.step-title { font-weight: 600; margin-bottom: 8px; font-size: 0.9rem; }
.webhook-url-box {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #F5F5F5;
  border: 1px solid #E5E5E5;
  padding: 8px 12px;
}
.webhook-url-box code { font-family: var(--mono); font-size: 0.8rem; flex: 1; word-break: break-all; }
.copy-btn {
  background: #000;
  color: #fff;
  border: none;
  padding: 4px 10px;
  font-family: var(--mono);
  font-size: 0.75rem;
  cursor: pointer;
  white-space: nowrap;
}
.code-block {
  background: #F5F5F5;
  border: 1px solid #E5E5E5;
  padding: 12px;
  font-family: var(--mono);
  font-size: 0.75rem;
  line-height: 1.6;
  margin: 0;
  overflow: auto;
}

/* Test form */
.test-form { }
.form-row { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 16px; }
.form-group { display: flex; flex-direction: column; gap: 6px; min-width: 140px; }
.form-group label { font-size: 0.78rem; font-family: var(--mono); color: #666; }
.form-control {
  border: 1px solid #DDD;
  padding: 8px 12px;
  font-family: var(--mono);
  font-size: 0.85rem;
  background: #FAFAFA;
  outline: none;
}
.form-control:focus { border-color: #000; }
.form-actions { display: flex; align-items: center; gap: 16px; }
.btn-primary {
  background: #000;
  color: #fff;
  border: none;
  padding: 10px 24px;
  font-family: var(--mono);
  font-size: 0.9rem;
  cursor: pointer;
  transition: background 0.2s;
}
.btn-primary:hover:not(:disabled) { background: #FF4500; }
.btn-primary:disabled { opacity: 0.5; cursor: default; }
.result-ok { color: #00C851; font-family: var(--mono); font-size: 0.85rem; }
.result-err { color: #FF4444; font-family: var(--mono); font-size: 0.85rem; }

/* Trade table */
.trade-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.trade-table th {
  font-family: var(--mono);
  font-size: 0.7rem;
  letter-spacing: 1px;
  color: #999;
  text-align: left;
  padding: 10px 12px;
  border-bottom: 2px solid #E5E5E5;
}
.trade-table td { padding: 10px 12px; border-bottom: 1px solid #F0F0F0; }
.trade-table .row-fail { background: #FFF5F5; }
.td-mono { font-family: var(--mono); font-size: 0.8rem; }
.td-symbol { font-family: var(--mono); font-weight: 700; }
.td-buy { color: #00C851; font-weight: 700; font-family: var(--mono); }
.td-sell { color: #FF4444; font-weight: 700; font-family: var(--mono); }

.status-badge {
  font-family: var(--mono);
  font-size: 0.7rem;
  padding: 2px 8px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.badge-fill { background: #E6FAF0; color: #00A040; }
.badge-fail { background: #FFF0F0; color: #CC0000; }
.badge-open { background: #F0F0FF; color: #4444CC; }

/* Open orders filter */
.order-filter { display: flex; gap: 8px; align-items: center; }
.form-control-sm {
  border: 1px solid #DDD;
  padding: 5px 10px;
  font-family: var(--mono);
  font-size: 0.8rem;
  background: #FAFAFA;
  outline: none;
}
.btn-sm {
  background: #000;
  color: #fff;
  border: none;
  padding: 5px 14px;
  font-family: var(--mono);
  font-size: 0.8rem;
  cursor: pointer;
}

/* Misc */
.not-configured, .empty-text { color: #999; font-size: 0.9rem; padding: 16px 0; }
.hint { color: #999; font-size: 0.8rem; line-height: 1.5; }
.hint code { background: #F0F0F0; padding: 2px 5px; font-family: var(--mono); font-size: 0.75rem; }
.error-text { color: #CC0000; font-family: var(--mono); font-size: 0.85rem; padding: 12px 0; }

@media (max-width: 900px) {
  .cards-row { grid-template-columns: 1fr; }
  .form-row { flex-direction: column; }
  .page-body { padding: 20px; }
}
</style>
