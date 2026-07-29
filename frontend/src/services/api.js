const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

async function request(path, { method = 'GET', body, headers = {} } = {}) {
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
  };

  if (body !== undefined) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, options);
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();

  if (!response.ok) {
    const message = typeof payload === 'string' ? payload : payload?.detail || 'Request failed';
    throw new Error(message);
  }

  return payload;
}

export async function healthCheck() {
  return request('/health');
}

export async function loginUser(credentials) {
  return request('/api/v1/auth/login', {
    method: 'POST',
    body: credentials,
  });
}

export async function getStoredToken() {
  return localStorage.getItem('dpeci_token');
}
