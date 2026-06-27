import service from './index'

export const tradingApi = {
  getConfig: () => service.get('/api/trading/config'),
  getBalance: () => service.get('/api/trading/balance'),
  getHistory: (limit = 50) => service.get('/api/trading/history', { params: { limit } }),
  getOpenOrders: (symbol = '') => service.get('/api/trading/orders', { params: symbol ? { symbol } : {} }),
  getPrice: (symbol) => service.get('/api/trading/price', { params: { symbol } }),
  sendWebhook: (payload) => service.post('/api/trading/webhook', payload),
}
