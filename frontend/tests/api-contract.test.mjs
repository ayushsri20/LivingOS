/**
 * Frontend API contract tests — dependency-free, using Node's built-in runner.
 *
 *     npm run test:contract
 *
 * These run against a live Django server seeded with the synthetic dataset and
 * assert the contract the React client actually depends on: CSRF handling,
 * auth, payload shape, and the invariants the UI would otherwise break on.
 */
import assert from 'node:assert/strict'
import { before, describe, it } from 'node:test'

import { authenticate, request, swapCookies } from './helpers.mjs'

before(authenticate)

describe('authentication contract', () => {
  it('rejects an anonymous request to the rooms API', async () => {
    const saved = swapCookies('')
    const response = await request('/api/rooms/', { auth: false })
    swapCookies(saved)
    assert.notEqual(response.status, 200, 'anonymous access must be refused')
    assert.ok(response.status < 500, 'refusal must not be a server error')
  })

  it('serves the rooms API to an authenticated admin', async () => {
    const response = await request('/api/rooms/')
    assert.equal(response.status, 200)
    assert.equal(response.json.success, true)
  })
})

describe('room payload contract', () => {
  it('returns 36 rooms across 6 buildings', async () => {
    const { json } = await request('/api/rooms/')
    assert.equal(json.count, 36)
    assert.equal(json.rooms.length, 36)
    assert.equal(json.buildings.length, 6)
  })

  it('gives every room snapshot every field the views render', async () => {
    const { json } = await request('/api/rooms/')
    const required = [
      'id', 'room', 'building', 'resident', 'agreed_rent', 'current_bill',
      'previous_reading', 'current_reading', 'units_used', 'electricity_rate',
      'new_bill_rate', 'electricity_amount', 'collected_amount',
      'outstanding_amount', 'payment_status', 'total_bill',
    ]
    for (const room of json.rooms) {
      for (const field of required) {
        assert.ok(field in room, `room ${room.room} is missing "${field}"`)
      }
    }
  })

  it('never emits NaN, null or a negative value in a monetary field', async () => {
    const { json } = await request('/api/rooms/')
    const money = [
      'agreed_rent', 'electricity_amount', 'total_bill',
      'collected_amount', 'outstanding_amount',
    ]
    for (const room of json.rooms) {
      for (const field of money) {
        const value = room[field]
        assert.equal(typeof value, 'number', `${room.room}.${field} must be a number`)
        assert.ok(Number.isFinite(value), `${room.room}.${field} must be finite`)
        assert.ok(value >= 0, `${room.room}.${field} must not be negative`)
      }
    }
  })

  it('only reports statuses the badge component knows', async () => {
    const allowed = new Set(['PAID', 'PARTIAL', 'DUE'])
    const { json } = await request('/api/rooms/')
    for (const room of json.rooms) {
      assert.ok(allowed.has(room.payment_status), `unknown status ${room.payment_status}`)
    }
  })

  it('reports outstanding as bill minus collected, clamped at zero', async () => {
    const { json } = await request('/api/rooms/')
    for (const room of json.rooms) {
      const expected = Math.max(0, room.total_bill - room.collected_amount)
      assert.ok(
        Math.abs(room.outstanding_amount - expected) < 0.01,
        `${room.room}: outstanding ${room.outstanding_amount} != ${expected}`,
      )
    }
  })

  it('exercises every visual record state in one payload', async () => {
    const { json } = await request('/api/rooms/')
    const statuses = new Set(json.rooms.map((r) => r.payment_status))
    for (const expected of ['PAID', 'PARTIAL', 'DUE']) {
      assert.ok(statuses.has(expected), `no ${expected} room in the payload`)
    }
    const vacant = json.rooms.filter((r) => r.resident === 'No resident')
    assert.equal(vacant.length, 6, 'expected six vacant rooms')
  })
})

describe('error contract', () => {
  it('returns 404 for an unknown room', async () => {
    const response = await request('/api/rooms/999999/')
    assert.equal(response.status, 404)
  })

  it('returns a 4xx with a message for a bad payment, never a 500', async () => {
    const { json } = await request('/api/rooms/')
    const room = json.rooms.find((r) => r.resident !== 'No resident')
    for (const amount of ['0', '-1', 'abc', '']) {
      const response = await request(`/api/rooms/${room.id}/collect/`, {
        method: 'POST',
        body: { amount },
      })
      assert.ok(
        response.status >= 400 && response.status < 500,
        `amount "${amount}" produced ${response.status}`,
      )
      assert.equal(response.json.success, false)
      assert.ok(
        typeof response.json.message === 'string' && response.json.message.length > 0,
        'a rejection must explain itself',
      )
    }
  })

  it('rejects a meter reading lower than the previous one', async () => {
    const { json } = await request('/api/rooms/')
    const room = json.rooms.find((r) => r.previous_reading > 0)
    const response = await request(`/api/rooms/${room.id}/generate-bill/`, {
      method: 'POST',
      body: { current_reading: String(room.previous_reading - 50) },
    })
    assert.equal(response.status, 400)
    assert.equal(response.json.success, false)
  })

  it('rejects a missing meter reading', async () => {
    const { json } = await request('/api/rooms/')
    const room = json.rooms[0]
    const response = await request(`/api/rooms/${room.id}/generate-bill/`, {
      method: 'POST',
      body: {},
    })
    assert.equal(response.status, 400)
    assert.equal(response.json.success, false)
  })

  it('returns an empty list, not an error, for a room with no payments', async () => {
    const { json } = await request('/api/rooms/')
    const vacant = json.rooms.find((r) => r.resident === 'No resident')
    const response = await request(`/api/rooms/${vacant.id}/payments/`)
    assert.equal(response.status, 200)
    assert.equal(response.json.success, true)
    assert.ok(Array.isArray(response.json.payments))
  })
})

describe('dashboard and analytics contract', () => {
  it('returns finite metrics that reconcile with the room list', async () => {
    const rooms = (await request('/api/rooms/')).json.rooms
    const metrics = (await request('/api/dashboard/metrics/')).json

    assert.equal(metrics.success, true)
    assert.equal(metrics.meta.total_rooms, 36)
    for (const key of [
      'expected_yield', 'realized_revenue', 'accounts_receivable',
      'collection_efficiency', 'occupancy_rate',
    ]) {
      assert.ok(Number.isFinite(metrics.metrics[key]), `${key} must be finite`)
    }

    const expected = rooms.reduce((sum, room) => sum + room.total_bill, 0)
    assert.ok(
      Math.abs(metrics.metrics.expected_yield - expected) < 0.05,
      `dashboard expected_yield ${metrics.metrics.expected_yield} != room sum ${expected}`,
    )
  })

  it('returns a monthly report covering all six buildings', async () => {
    const response = await request('/api/reports/monthly/')
    assert.equal(response.status, 200)
    assert.equal(response.json.income.length, 6)
    for (const line of response.json.income) {
      assert.ok(Number.isFinite(line.gross_expected), `${line.building} gross_expected`)
      assert.ok(Number.isFinite(line.collected), `${line.building} collected`)
    }
  })

  it('returns a yearly report with twelve months', async () => {
    const response = await request('/api/reports/yearly/')
    assert.equal(response.status, 200)
    assert.equal(response.json.months.length, 12)
  })
})

