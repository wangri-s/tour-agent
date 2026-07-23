// =============================================================================
// API 层 — 对接后端 /chat 和 /health
// =============================================================================

const BASE = ''   // Vite proxy 已转发到 localhost:8000

export async function checkHealth() {
  const res = await fetch(`${BASE}/health`)
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`)
  return res.json()
}

export async function sendMessage({ session_id, customer_id, channel, message, language }) {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id, customer_id, channel, message, language })
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Request failed: ${res.status}`)
  }
  return res.json()
}
