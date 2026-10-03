const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export function getCookie(name) {
  if (!document.cookie) return ''
  const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.split('=')[1]) : ''
}

/**
 * Build an Error carrying the HTTP status (and backend payload when available),
 * so callers can tell "request failed" apart from "no data returned".
 */
function apiError(message, status, payload) {
  const error = new Error(message)
  error.status = status || 0
  if (payload !== undefined) error.payload = payload
  return error
}

/** Extract the most useful human-readable message from a Django JSON error body. */
function extractMessage(payload, status) {
  if (payload && typeof payload === 'object') {
    if (typeof payload.message === 'string' && payload.message) return payload.message
    if (typeof payload.detail === 'string' && payload.detail) return payload.detail
    if (typeof payload.error === 'string' && payload.error) return payload.error
    if (Array.isArray(payload.errors) && payload.errors.length) return payload.errors.join(', ')
    if (Array.isArray(payload.non_field_errors) && payload.non_field_errors.length) {
      return payload.non_field_errors.join(', ')
    }
  }
  if (typeof payload === 'string' && payload.trim()) return payload.trim()
  return `Request failed with HTTP ${status}.`
}

export async function apiFetch(path, options = {}) {
  const { headers: callerHeaders, body, ...rest } = options
  const isFormData = body instanceof FormData

  const response = await fetch(`${API_BASE}${path}`, {
    cache: 'no-store',
    credentials: 'include',
    redirect: 'manual',
    ...rest,
    // Built last on purpose: a caller can extend headers but can never drop or
    // overwrite the CSRF token, and FormData keeps its browser-set boundary.
    headers: {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(callerHeaders || {}),
      'X-CSRFToken': getCookie('csrftoken') || '',
    },
    body,
  })

  const contentType = response.headers.get('content-type') || ''
  const url = response.url || ''

  if (response.type === 'opaqueredirect' || response.status === 302 || response.status === 401) {
    throw apiError('Authentication required. Please log in again.', response.status)
  }

  if (response.status === 403) {
    throw apiError('Access denied. Check staff permissions or CSRF protection.', 403)
  }

  if (contentType.includes('text/html') && (url.includes('/login/') || url.includes('next='))) {
    throw apiError('Authentication required. Please log in again.', response.status)
  }

  if (contentType.includes('application/json')) {
    let payload
    try {
      payload = await response.json()
    } catch {
      throw apiError(`Server returned an unreadable response (HTTP ${response.status}).`, response.status)
    }
    if (!response.ok) {
      throw apiError(extractMessage(payload, response.status), response.status, payload)
    }
    return payload
  }

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    if (text.includes('login') || text.includes('csrfmiddlewaretoken')) {
      throw apiError('Authentication required. Please log in again.', response.status)
    }
    throw apiError(
      `Request failed with HTTP ${response.status}.`,
      response.status,
      text ? text.slice(0, 300) : undefined,
    )
  }

  return null
}

export function buildLoginRequestBody({ username, password }) {
  const formData = new FormData()
  formData.append('username', username)
  formData.append('password', password)
  return formData
}

export async function login({ username, password }) {
  const csrfResponse = await fetch(`${API_BASE}/login/`, {
    method: 'GET',
    credentials: 'include',
    // A cached login page can carry a stale csrfmiddlewaretoken.
    cache: 'no-store',
  })
  if (!csrfResponse.ok) {
    throw new Error('Unable to start a secure login request.')
  }

  const response = await fetch(`${API_BASE}/login/`, {
    method: 'POST',
    credentials: 'include',
    redirect: 'manual',
    headers: {
      'X-CSRFToken': getCookie('csrftoken') || '',
    },
    body: buildLoginRequestBody({ username, password }),
  })

  if (response.type === 'opaqueredirect' || response.status === 302) return
  if (response.status === 403) {
    throw new Error('Login was blocked by CSRF protection. Refresh the page and try again.')
  }
  if (response.ok) {
    throw new Error('Login failed. Please verify your username and password.')
  }
  throw new Error('Login request failed. Please try again.')
}

export async function logout() {
  await fetch(`${API_BASE}/logout/`, {
    method: 'GET',
    credentials: 'include',
    redirect: 'manual',
    // Never replay a cached logout redirect.
    cache: 'no-store',
  })
}
