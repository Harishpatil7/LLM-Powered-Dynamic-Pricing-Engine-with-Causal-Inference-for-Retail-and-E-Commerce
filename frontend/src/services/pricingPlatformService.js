const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function jsonRequest(path, options = {}) {
  const token = localStorage.getItem('dpeci_token');
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) throw new Error(typeof payload === 'string' ? payload : payload?.detail || 'Request failed');
  return payload;
}

export function registerUser(credentials) {
  return jsonRequest('/api/v1/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(credentials) });
}
export function loginUser(credentials) {
  return jsonRequest('/api/v1/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(credentials) });
}
export function getCurrentUser() { return jsonRequest('/api/v1/auth/me'); }
export function healthCheck() { return jsonRequest('/health'); }

export function createRetailer(name) {
  return jsonRequest('/api/v1/retailers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
}
export function getRetailers() { return jsonRequest('/api/v1/retailers'); }
export function uploadDataset(retailerId, file) {
  const body = new FormData(); body.append('file', file);
  return jsonRequest(`/api/v1/datasets/retailers/${retailerId}`, { method: 'POST', body });
}
export function validateDataset(file) {
  const body = new FormData(); body.append('file', file);
  return jsonRequest('/api/v1/datasets/validate', { method: 'POST', body });
}
export function getDatasets(retailerId) { return jsonRequest(`/api/v1/datasets/retailers/${retailerId}`); }
export function getProducts(retailerId) { return jsonRequest(`/api/v1/retailers/${retailerId}/products`); }
export function runCausalAnalysis(retailerId, productId) { return jsonRequest(`/api/v1/retailers/${retailerId}/products/${productId}/causal-runs`, { method: 'POST' }); }
export function createRecommendation(retailerId, productId, modelRunId, constraints) {
  return jsonRequest(`/api/v1/retailers/${retailerId}/products/${productId}/model-runs/${modelRunId}/recommendations`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(constraints) });
}
export function previewReport(retailerId, productId, question) {
  return jsonRequest(`/api/v1/retailers/${retailerId}/products/${productId}/reports/preview`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) });
}
export function generateGeminiReport(retailerId, productId, question) {
  return jsonRequest(`/api/v1/retailers/${retailerId}/products/${productId}/reports/generate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question }) });
}
