import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api/client'
import { formatDate, getRoomNumber, money, normalizeRoomStatus, statusColors } from '../utils'
import { EmptyState, LoadingShell, MetricCard } from './shared'

const PAYMENT_METHODS = [
  { value: 'cash', label: 'Cash' },
  { value: 'check', label: 'Check' },
  { value: 'bank_transfer', label: 'Bank Transfer' },
  { value: 'upi', label: 'UPI' },
  { value: 'card', label: 'Card' },
]

/** Small labelled value used across the drawer. Presentational only. */
function Detail({ label, value }) {
  return (
    <div>
      <span className="eyebrow" style={{ display: 'block', color: '#5c564c', fontSize: 10 }}>{label}</span>
      <strong style={{ fontFamily: 'var(--font-display)', fontSize: 16 }}>{value}</strong>
    </div>
  )
}

export default function RoomDrawer({ room, onClose, onRefresh, onToast, onPaymentsCollected }) {
  const [tab, setTab] = useState('overview')

  // Generate / update bill
  const [reading, setReading] = useState('')
  const [billLoading, setBillLoading] = useState(false)
  const [billError, setBillError] = useState('')
  const [billResult, setBillResult] = useState(null)

  // Collect payment
  const [amount, setAmount] = useState('')
  const [method, setMethod] = useState('cash')
  const [reference, setReference] = useState('')
  const [collectLoading, setCollectLoading] = useState(false)
  const [collectError, setCollectError] = useState('')

  // Payment history
  const [historyOpen, setHistoryOpen] = useState(false)
  const [history, setHistory] = useState(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState('')

  // Resident profile (all active tenants of this room)
  const [guests, setGuests] = useState([])
  const [guestLoading, setGuestLoading] = useState(false)
  const [guestError, setGuestError] = useState('')
  const [guestLoaded, setGuestLoaded] = useState(false)

  const closeRef = useRef(null)
  const roomId = room?.id
  const roomNumber = getRoomNumber(room)
  const hasBill = room?.current_reading !== null && room?.current_reading !== undefined
  const status = normalizeRoomStatus(room)
  const residentName = room?.resident && room.resident !== 'No resident' ? room.resident : 'Vacant Room'

  // Plays the exit transition before the parent unmounts the drawer, so closing
  // does not snap away. Same pattern as the shared Modal.
  const [closing, setClosing] = useState(false)
  const closeTimer = useRef(null)
  const requestClose = useCallback(() => {
    if (closing) return
    setClosing(true)
    closeTimer.current = setTimeout(onClose, 180)
  }, [closing, onClose])

  useEffect(() => {
    closeRef.current?.focus()
    const onKeyDown = (event) => { if (event.key === 'Escape') requestClose() }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [requestClose])

  useEffect(() => () => clearTimeout(closeTimer.current), [])

  // Reconcile from the backend after any mutation. The parent owns the rooms list, so
  // refetching it updates the drawer, the cards, and every other view at once.
  async function reconcile(okMessage) {
    try {
      await onRefresh()
    } catch {
      // The mutation already succeeded; a refresh failure must not look like a
      // failed action, but the user should know the screen may be slightly behind.
      onToast?.({ type: 'error', message: 'Saved, but the latest figures could not be reloaded.' })
      return
    }
    onToast?.({ type: 'success', message: okMessage })
  }

  async function handleBillSubmit(event) {
    event.preventDefault()
    if (billLoading) return
    if (reading === '') {
      setBillError('Enter the current meter reading.')
      return
    }
    setBillLoading(true)
    setBillError('')
    setBillResult(null)
    try {
      const data = await apiFetch(`/api/rooms/${roomId}/generate-bill/`, {
        method: 'POST',
        body: JSON.stringify({ current_reading: reading }),
      })
      setBillResult(data)
      setReading('')
      await reconcile(`Bill saved for Room ${roomNumber}.`)
    } catch (err) {
      setBillError(err.message || 'Unable to generate the bill.')
    } finally {
      setBillLoading(false)
    }
  }

  async function handleCollectSubmit(event) {
    event.preventDefault()
    if (collectLoading) return
    if (amount === '') {
      setCollectError('Enter the amount collected.')
      return
    }
    setCollectLoading(true)
    setCollectError('')
    try {
      await apiFetch(`/api/rooms/${roomId}/collect/`, {
        method: 'POST',
        body: JSON.stringify({
          amount,
          payment_method: method,
          reference_number: reference,
        }),
      })
      setAmount('')
      setReference('')
      // The payment exists now: refresh this drawer's own history (when it has
      // been loaded) and tell the parent to invalidate its cached copy for this
      // room only. Reconcile stays authoritative for the room figures either way.
      onPaymentsCollected?.(roomId)
      if (history !== null) loadHistory()
      await reconcile(`Payment recorded for Room ${roomNumber}.`)
    } catch (err) {
      setCollectError(err.message || 'Unable to record the payment.')
    } finally {
      setCollectLoading(false)
    }
  }

  async function loadHistory() {
    setHistoryLoading(true)
    setHistoryError('')
    try {
      const data = await apiFetch(`/api/rooms/${roomId}/payments/`)
      setHistory(data.payments || [])
    } catch (err) {
      setHistoryError(err.message || 'Unable to load payment history.')
    } finally {
      setHistoryLoading(false)
    }
  }

  function toggleHistory() {
    if (historyOpen) {
      setHistoryOpen(false)
      return
    }
    setHistoryOpen(true)
    if (!history) loadHistory()
  }

  async function openProfile() {
    setTab('profile')
    if (guestLoaded) return
    setGuestLoading(true)
    setGuestError('')
    try {
      // Authoritative per-room roster: shows every active resident of a
      // double-occupied room instead of the snapshot's single `resident` field.
      const data = await apiFetch(`/api/room/${roomId}/tenants/`)
      const list = (data.tenants || []).map((tenant) => ({
        id: tenant.id,
        full_name: tenant.name,
        phone: tenant.phone,
        email: tenant.email,
        check_in_date: tenant.check_in,
        check_out_date: tenant.check_out,
        id_type: tenant.id_type,
        id_number: tenant.id_number,
        student_college: tenant.student_college,
        city: tenant.city,
      }))
      setGuests(list)
      setGuestLoaded(true)
    } catch (err) {
      setGuestError(err.message || 'Unable to load resident details.')
    } finally {
      setGuestLoading(false)
    }
  }

  return (
    <>
      <div className={`drawer-backdrop${closing ? ' closing' : ''}`} onClick={requestClose} aria-hidden="true" />
      <aside className={`drawer${closing ? ' closing' : ''}`} role="dialog" aria-modal="true" aria-label={`Room ${roomNumber} details`}>
        <div className="drawer-header">
          <div>
            <span className="eyebrow" style={{ color: 'var(--ink)' }}>BUILDING {room?.building || '—'}</span>
            <h2 style={{ margin: 0, fontSize: 32, fontFamily: 'var(--font-display)', letterSpacing: '-0.04em' }}>
              {tab === 'profile' ? 'RESIDENT PROFILE' : `ROOM ${roomNumber}`}
            </h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="ghost-button"
            onClick={requestClose}
            style={{ padding: '8px 12px', fontSize: 20 }}
            aria-label="Close room details"
          >
            ×
          </button>
        </div>

        <div className="drawer-tabs" role="tablist" aria-label="Room sections">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'overview'}
            className={`pill ${tab === 'overview' ? 'active' : ''}`}
            onClick={() => setTab('overview')}
          >
            Room overview
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'profile'}
            className={`pill ${tab === 'profile' ? 'active' : ''}`}
            onClick={openProfile}
          >
            Resident profile
          </button>
        </div>

        <div className="drawer-content">
          {tab === 'profile' ? (
            guestLoading ? (
              <LoadingShell label="Loading resident details…" />
            ) : guestError ? (
              <div className="error-state">
                <span>{guestError}</span>
                <button
                  type="button"
                  className="retry-button"
                  onClick={() => { setGuestLoaded(false); setGuestError(''); openProfile() }}
                >
                  Retry
                </button>
              </div>
            ) : guests.length === 0 ? (
              <EmptyState message={`No active resident is assigned to Room ${roomNumber}.`} />
            ) : (
              <>
                {guests.map((resident, index) => (
                  <div key={resident.id}>
                    <div className="surface resident-profile-card">
                      <div className="resident-profile-heading">
                        <div>
                          <span className="eyebrow" style={{ color: '#5c564c' }}>
                            {guests.length > 1 ? `Resident ${index + 1} of ${guests.length}` : 'Primary resident'}
                          </span>
                          <h3>{resident.full_name}</h3>
                        </div>
                        <span className={`status-tag ${statusColors[status] || 'pending'}`}>{status}</span>
                      </div>
                      <p>Room {roomNumber} · Building {room?.building || '—'}</p>
                    </div>

                    <div className="surface resident-room-details">
                      <div className="section-head" style={{ marginTop: 0 }}>
                        <h2>{guests.length > 1 ? `Contact — Resident ${index + 1}` : 'Contact'}</h2>
                      </div>
                      <div className="resident-detail-grid">
                        <div><span className="eyebrow">Phone</span><strong>{resident.phone || '—'}</strong></div>
                        <div><span className="eyebrow">Email</span><strong>{resident.email || '—'}</strong></div>
                        <div><span className="eyebrow">Check-in</span><strong>{formatDate(resident.check_in_date)}</strong></div>
                        <div><span className="eyebrow">Check-out</span><strong>{resident.check_out_date ? formatDate(resident.check_out_date) : 'Active'}</strong></div>
                      </div>
                    </div>

                    <div className="surface resident-room-details">
                      <div className="section-head" style={{ marginTop: 0 }}>
                        <h2>{guests.length > 1 ? `Identification — Resident ${index + 1}` : 'Identification'}</h2>
                      </div>
                      <div className="resident-detail-grid">
                        <div><span className="eyebrow">ID type</span><strong>{resident.id_type || '—'}</strong></div>
                        <div><span className="eyebrow">ID number</span><strong>{resident.id_number || '—'}</strong></div>
                        <div><span className="eyebrow">College</span><strong>{resident.student_college || '—'}</strong></div>
                        <div><span className="eyebrow">City</span><strong>{resident.city || '—'}</strong></div>
                      </div>
                    </div>
                  </div>
                ))}

                {/* Room-level: rendered once — financials belong to the room, not a resident. */}
                <div className="surface resident-room-details">
                  <div className="section-head" style={{ marginTop: 0 }}>
                    <h2>Room Assignment</h2>
                    <span>Room-level</span>
                  </div>
                  <div className="resident-detail-grid">
                    <div><span className="eyebrow">Room ID</span><strong>{roomNumber}</strong></div>
                    <div><span className="eyebrow">Building</span><strong>{room?.building || '—'}</strong></div>
                    <div><span className="eyebrow">Occupancy</span><strong>{guests.length}/2</strong></div>
                    <div><span className="eyebrow">Agreed rent</span><strong>{money(room?.agreed_rent)}</strong></div>
                    <div><span className="eyebrow">Payment status</span><strong>{status}</strong></div>
                  </div>
                </div>
              </>
            )
          ) : (
            <>
              <div className="surface" style={{ marginBottom: 20 }}>
                <div className="resident-profile-heading">
                  <div>
                    <span className="eyebrow" style={{ color: '#5c564c' }}>Primary Resident</span>
                    <h3>{residentName}</h3>
                  </div>
                  <span className={`status-tag ${statusColors[status] || 'pending'}`}>{status}</span>
                </div>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={openProfile}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  View Resident Profile →
                </button>
              </div>

              <div className="surface" style={{ marginBottom: 20 }}>
                <div className="section-head" style={{ marginTop: 0 }}>
                  <h2>Billing &amp; Usage</h2>
                  <span>Current month</span>
                </div>
                <div className="metrics-grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                  <MetricCard label="Agreed rent" value={money(room?.agreed_rent)} />
                  <MetricCard label="Electricity" value={money(room?.electricity_amount)} color="blue" />
                  <MetricCard label="Collected" value={money(room?.collected_amount)} color="green" />
                  <MetricCard
                    label="Outstanding"
                    value={money(room?.outstanding_amount)}
                    color={(room?.outstanding_amount ?? 0) > 0 ? 'red' : 'blue'}
                  />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
                  <Detail label="Prev reading" value={room?.previous_reading ?? '—'} />
                  <Detail label="Curr reading" value={room?.current_reading ?? '—'} />
                  <Detail label="Units used" value={room?.units_used ?? '—'} />
                </div>
                <div style={{ padding: '14px 16px', background: 'var(--yellow)', border: '3px solid var(--ink)', boxShadow: '4px 4px 0 var(--ink)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
                  <span style={{ fontWeight: 700, textTransform: 'uppercase', fontSize: 12, letterSpacing: '0.04em' }}>Total room bill</span>
                  <strong style={{ fontSize: 26, fontFamily: 'var(--font-display)', letterSpacing: '-0.03em' }}>{money(room?.total_bill)}</strong>
                </div>
              </div>

              <div className="surface" style={{ marginBottom: 20 }}>
                <div className="section-head" style={{ marginTop: 0 }}>
                  <h2>{hasBill ? 'Update Electricity Reading' : 'Generate Bill'}</h2>
                  <span>{hasBill ? `${room?.units_used ?? 0} units billed` : 'No bill for this month yet'}</span>
                </div>
                <form onSubmit={handleBillSubmit} aria-busy={billLoading}>
                  <div className="field-group">
                    <label htmlFor="drawer-reading">Current meter reading</label>
                    <input
                      id="drawer-reading"
                      name="current_reading"
                      type="number"
                      inputMode="decimal"
                      step="0.01"
                      min="0"
                      className="field-input"
                      placeholder={room?.previous_reading != null ? `Previous: ${room.previous_reading}` : 'Enter reading'}
                      value={reading}
                      onChange={(event) => { setReading(event.target.value); if (billError) setBillError('') }}
                      disabled={billLoading}
                      required
                    />
                  </div>
                  {billError && <div className="field-error" role="alert">{billError}</div>}
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={billLoading}
                    style={{ width: '100%', justifyContent: 'center', minHeight: 48 }}
                  >
                    {billLoading ? 'Saving…' : hasBill ? 'Update Reading' : 'Generate Bill'}
                  </button>
                </form>
                {billResult && (
                  <div className="toast success" style={{ marginTop: 12 }} role="status">
                    {billResult.units_used} units · {money(billResult.electricity_amount)} electricity ·
                    total {money(billResult.total_bill)}
                  </div>
                )}
              </div>

              <div className="surface" style={{ marginBottom: 20 }}>
                <div className="section-head" style={{ marginTop: 0 }}>
                  <h2>Collect Payment</h2>
                  <span>Outstanding {money(room?.outstanding_amount)}</span>
                </div>
                <form onSubmit={handleCollectSubmit} aria-busy={collectLoading}>
                  <div className="field-group">
                    <label htmlFor="drawer-amount">Amount collected (₹)</label>
                    <input
                      id="drawer-amount"
                      name="amount"
                      type="number"
                      inputMode="decimal"
                      step="0.01"
                      min="0.01"
                      className="field-input"
                      placeholder="0.00"
                      value={amount}
                      onChange={(event) => { setAmount(event.target.value); if (collectError) setCollectError('') }}
                      disabled={collectLoading}
                      required
                    />
                  </div>
                  <div className="field-group">
                    <label htmlFor="drawer-method">Payment method</label>
                    <select
                      id="drawer-method"
                      name="payment_method"
                      className="field-input"
                      value={method}
                      onChange={(event) => setMethod(event.target.value)}
                      disabled={collectLoading}
                    >
                      {PAYMENT_METHODS.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </div>
                  <div className="field-group">
                    <label htmlFor="drawer-reference">Reference number (optional)</label>
                    <input
                      id="drawer-reference"
                      name="reference_number"
                      type="text"
                      className="field-input"
                      value={reference}
                      onChange={(event) => setReference(event.target.value)}
                      disabled={collectLoading}
                    />
                  </div>
                  {collectError && <div className="field-error" role="alert">{collectError}</div>}
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={collectLoading}
                    style={{ width: '100%', justifyContent: 'center', minHeight: 48 }}
                  >
                    {collectLoading ? 'Recording…' : 'Collect Payment'}
                  </button>
                  <p style={{ margin: '10px 0 0', fontSize: 12, color: '#5c564c' }}>
                    Collected, outstanding and payment status are returned by the backend — this screen
                    never calculates them itself.
                  </p>
                </form>
              </div>

              <div className="surface" style={{ marginBottom: 20 }}>
                <div className="section-head" style={{ marginTop: 0 }}>
                  <h2>Payment History</h2>
                  <span>{history ? `${history.length} record${history.length === 1 ? '' : 's'}` : 'Not loaded'}</span>
                </div>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={toggleHistory}
                  aria-expanded={historyOpen}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  {historyOpen ? 'Hide history' : 'Show payment history'}
                </button>
                {historyOpen && (
                  historyLoading ? (
                    <LoadingShell label="Loading payment history…" />
                  ) : historyError ? (
                    <div className="error-state" style={{ marginTop: 12 }}>
                      <span>{historyError}</span>
                      <button type="button" className="retry-button" onClick={loadHistory}>Retry</button>
                    </div>
                  ) : history && history.length > 0 ? (
                    <div className="payment-history-list" style={{ marginTop: 12 }}>
                      {history.map((record) => (
                        <div className="payment-history-item" key={record.id}>
                          <div>
                            <span className="eyebrow">Date</span>
                            <strong>{formatDate(record.date)}</strong>
                          </div>
                          <div>
                            <span className="eyebrow">Method</span>
                            <strong>{PAYMENT_METHODS.find((option) => option.value === record.method)?.label || record.method}</strong>
                          </div>
                          <strong>{money(record.amount)}</strong>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ marginTop: 12 }}>
                      <EmptyState message="No payments have been recorded for this room." />
                    </div>
                  )
                )}
              </div>
            </>
          )}
        </div>
      </aside>
    </>
  )
}