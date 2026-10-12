/**
 * Shared helpers for the dependency-free frontend contract tests.
 *
 *     node --test frontend/tests/
 *
 * No new dependencies: `node:test` and `fetch` are built in, so these tests add
 * nothing to the install. They drive the real Django API exactly the way
 * `src/api/client.js` does — CSRF token, session cookie, same endpoints.
 */

export const BASE = process.env.RENTAL_API_BASE || 'http://127.0.0.1:8000'
export const USER = process.env.RENTAL_TEST_USER || 'tester'
export const PASS = process.env.RENTAL_TEST_PASSWORD || 'TesterPass!2026'

/** Mutable session state shared by the tests in one file. */
export const session = { cookie: '', csrfToken: '' }

const jar = new Map()

/** Merge Set-Cookie values into the jar, so one response cannot drop another. */
function storeCookies(response) {
  for (const raw of response.headers.getSetCookie?.() ?? []) {
    const [pair] = raw.split(';')
    const index = pair.indexOf('=')
    if (index === -1) continue
    const name = pair.slice(0, index).trim()
    const value = pair.slice(index + 1).trim()
    if (value === '' || /expires=Thu, 01 Jan 1970/i.test(raw)) jar.delete(name)
    else jar.set(name, value)
  }
  session.cookie = [...jar.entries()].map(([name, value]) => `${name}=${value}`).join('; ')
}

/** Snapshot / restore the whole jar, used by the anonymous-access test. */
export function swapCookies(cookieString) {
  const snapshot = session.cookie
  if (cookieString === '') jar.clear()
  else for (const part of cookieString.split('; ')) {
    const index = part.indexOf('=')
    if (index !== -1) jar.set(part.slice(0, index), part.slice(index + 1))
  }
  session.cookie = [...jar.entries()].map(([name, value]) => `${name}=${value}`).join('; ')
  return snapshot
}

export async function request(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth && session.csrfToken) headers['X-CSRFToken'] = session.csrfToken
  if (auth && session.cookie) headers.Cookie = session.cookie

  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    redirect: 'manual',
  })

  if (auth) storeCookies(response)

  const text = await response.text()
  let json = null
  try { json = JSON.parse(text) } catch { /* non-JSON body */ }
  return { status: response.status, json, text, headers: response.headers }
}

/** Fetch CSRF, then sign in. Call from a test file's `before` hook. */
export async function authenticate() {
  const csrf = await request('/api/csrf/')
  if (csrf.status !== 200) {
    throw new Error(`CSRF endpoint returned ${csrf.status}: ${csrf.text.slice(0, 200)}`)
  }
  session.csrfToken = csrf.json?.csrfToken
  if (!session.csrfToken) throw new Error('CSRF endpoint returned no token')

  // The login view reads request.POST, so the credentials must be form-encoded
  // even though every other call in the app uses JSON.
  const form = new URLSearchParams({ username: USER, password: PASS })
  const response = await fetch(`${BASE}/login/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'text/html',
      'X-CSRFToken': session.csrfToken,
      Cookie: session.cookie,
    },
    body: form.toString(),
    redirect: 'manual',
  })

  storeCookies(response)

  if (![200, 302].includes(response.status)) {
    throw new Error(`login failed with ${response.status}`)
  }
  if (!session.cookie.includes('sessionid')) {
    throw new Error('login returned no session cookie')
  }

  // The login view calls session.cycle_key(), which rotates the CSRF token. The
  // React client handles this with resetCsrfToken() in api/client.js; mirror it
  // here, or every later POST is rejected with 403.
  const refreshed = await request('/api/csrf/')
  if (refreshed.json?.csrfToken) {
    session.csrfToken = refreshed.json.csrfToken
  }

  // Confirm the session actually works before any test depends on it.
  const probe = await request('/api/rooms/')
  if (probe.status !== 200) {
    throw new Error(
      `login did not establish a session: /api/rooms/ returned ${probe.status}`,
    )
  }
  return response
}


