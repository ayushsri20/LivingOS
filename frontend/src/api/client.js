const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export function getCookie(name) {
  if (!document.cookie) return ''
  const match = document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.split('=')[1]) : ''
}

/**
 * CSRF token held in memory for the page's lifetime.
 *
 * On the same origin (local dev) the `csrftoken` cookie is readable and this
 * stays null. When the app is served from a different origin than the API
 * (Vercel -> Render) the cookie belongs to the API's domain, so
 * `document.cookie` can never see it — that is why the token is fetched from
 * GET /api/csrf/ and kept here instead.
 */
let csrfToken = null

/** Drop the cached token; needed whenever Django rotates it (e.g. on login). */
export function resetCsrfToken() {
  csrfToken = null
}

/**
 * Return a usable CSRF token, fetching one from the API only if the cookie
 * approach cannot work. Never throws on the local cookie path.
 */
export async function fetchCsrfToken() {
  if (csrfToken) return csrfToken

  // Same-origin case: keep using the cookie exactly as before.
  const cookieToken = getCookie('csrftoken')
  if (cookieToken) {
    csrfToken = cookieToken
    return csrfToken
  }

  // Cross-origin case: the cookie is on the API's domain, so ask for the token.
  const response = await fetch(`${API_BASE}/api/csrf/`, {
    method: 'GET',
    credentials: 'include',
    cache: 'no-store',
  })
  if (!response.ok) {
    throw new Error('Unable to obtain a CSRF token from the server.')
  }
  const data = await response.json()
  csrfToken = data.csrfToken || ''
  if (!csrfToken) {
    throw new Error('The server did not return a CSRF token.')
  }
  return csrfToken
}

/** Methods Django's CSRF middleware actually validates. */
const CSRF_SAFE_METHODS = ['GET', 'HEAD', 'OPTIONS', 'TRACE']

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
  const method = String(rest.method || 'GET').toUpperCase()

  // Only unsafe methods are validated by Django's CSRF middleware, so a token
  // is only fetched when one is actually needed.
  if (!CSRF_SAFE_METHODS.includes(method)) {
    await fetchCsrfToken()
  }

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
      'X-CSRFToken': csrfToken || getCookie('csrftoken') || '',
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
  // Get a CSRF token first. Locally this still comes from the cookie; when the
  // app and API are on different origins it comes from GET /api/csrf/.
  const token = await fetchCsrfToken()

  const response = await fetch(`${API_BASE}/login/`, {
    method: 'POST',
    credentials: 'include',
    redirect: 'manual',
    headers: {
      'X-CSRFToken': token,
    },
    body: buildLoginRequestBody({ username, password }),
  })

  // Django rotates the CSRF token on login, so the cached one is now stale.
  resetCsrfToken()

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
