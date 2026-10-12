import { useCallback, useEffect, useRef, useState, lazy, Suspense } from 'react'
import './components.css'
import './App.css'
import './panesar-auth.css'
import { apiFetch } from './api/client'
import { formatDate, getRoomNumber, money, normalizeRoomStatus, statusColors } from './utils'
import { TopBar, LoadingShell, Toast, MetricCard, EmptyState, Modal, FieldGroup } from './components/shared'
import { AuthProvider, useAuth } from './context/AuthContext'

const RoomDrawer = lazy(() => import('./components/RoomDrawer'))
const AssignResidentModal = lazy(() => import('./components/AssignResident'))

/**
 * Single source of truth for each authenticated page's banner copy.
 * The H1 names the page; the eyebrow groups it in the product. No descriptive
 * paragraph is rendered — every page's real state is stated by its own figures,
 * and prose that restated the title added no information.
 */
const VIEW_META = {
  dashboard: {
    // Uppercase eyebrow matches every other page; a phone-only CSS rule renders
    // the dashboard banner editorially without touching this shared copy.
    eyebrow: 'Property Operations Overview',
    title: 'DASHBOARD',
  },
  rooms: {
    eyebrow: 'Property Directory',
    title: 'ROOMS',
  },
  residents: {
    eyebrow: 'Occupancy Register',
    title: 'RESIDENTS',
  },
  electricity: {
    eyebrow: 'Utility Operations',
    title: 'ELECTRICITY',
  },
  payments: {
    eyebrow: 'Room-first collections',
    title: 'PAYMENTS',
  },
  expenses: {
    eyebrow: 'Maintenance & operations',
    title: 'EXPENSES',
  },
  analytics: {
    eyebrow: 'Performance',
    title: 'ANALYTICS',
  },
}

/**
 * Briefly highlights a figure when its value changes, so a refreshed total is
 * visibly updated rather than silently swapped. Purely presentational: the number
 * rendered is always the backend value passed in.
 */
function useValueFlash(value) {
  const [flash, setFlash] = useState(false)
  const previous = useRef(value)
  const seeded = useRef(value !== undefined && value !== null)

  useEffect(() => {
    // The first real value is the baseline, not a change: loading figures for
    // the first time must not look like money just moved.
    if (!seeded.current) {
      if (value === undefined || value === null) return undefined
      seeded.current = true
      previous.current = value
      return undefined
    }
    if (previous.current === value) return undefined

    previous.current = value
    setFlash(true)
    const timer = setTimeout(() => setFlash(false), 600)
    return () => clearTimeout(timer)
  }, [value])

  return flash
}

/** Format the metrics API `last_updated` timestamp for the dashboard header. */
function formatUpdated(value) {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  return parsed.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * A room's expected amount for the billing period is the `current_bill` the
 * backend computes per room (rent + electricity); `collected_amount` is the
 * matching collected figure. Summing the whole snapshot reproduces
 * expected_yield / realized_revenue / accounts_receivable from
 * /api/dashboard/metrics/ exactly, which is why these fields are the single
 * basis for every derived figure below. A room counts as fully paid only when it
 * is occupied AND collected >= expected — never from a status label.
 */
function isRoomOccupied(room) {
  return Boolean(room?.resident) && room.resident !== 'No resident'
}

function summarizeRooms(list) {
  let expected = 0
  let collected = 0
  let fullyPaid = 0
  let occupied = 0

  list.forEach((room) => {
    const roomExpected = Number(room.current_bill ?? 0)
    const roomCollected = Number(room.collected_amount ?? 0)
    expected += roomExpected
    collected += roomCollected
    if (isRoomOccupied(room)) {
      occupied += 1
      if (roomCollected >= roomExpected && roomExpected > 0) fullyPaid += 1
    }
  })

  return { expected, collected, due: expected - collected, fullyPaid, occupied }
}

/** Compact label/value row used on room and electricity cards. Presentational only. */
function StatRow({ label, value, tone }) {
  return (
    <div className="stat-row">
      <span className="stat-row-label">{label}</span>
      <strong className="stat-row-value" style={{ color: tone }}>{value}</strong>
    </div>
  )
}

function RoomsView({ rooms, buildings, selectedBuilding: selectedBuildingProp = '', onBuildingChange, loading, error, onOpenRoom, onRetry, onRefresh, onToast, onResidentsChanged }) {
  const [internalBuilding, setInternalBuilding] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [occupancyMap, setOccupancyMap] = useState({})
  const [assignRoom, setAssignRoom] = useState(null)

  // The building is lifted so the dashboard directory can navigate here already
  // filtered; with no external value (or a click inside Rooms) the local value is used.
  const selectedBuilding = selectedBuildingProp || internalBuilding
  const setSelectedBuilding = (name) => {
    setInternalBuilding(name)
    onBuildingChange?.(name)
  }

  // Derived rather than stored in state, so no effect is needed to pick a default
  // once the buildings arrive from the backend (which already orders M1,1..5).
  const activeBuilding = selectedBuilding || buildings[0]?.name || ''
  const query = searchQuery.trim().toLowerCase()

  // Occupancy comes from the authoritative per-room tenants endpoint — it is
  // never inferred from the snapshot's single `resident` field. Only the rooms
  // of the active building are fetched, and a superseded run is discarded.
  useEffect(() => {
    const targets = rooms.filter((room) => room.building === activeBuilding)
    let cancelled = false
    Promise.allSettled(targets.map((room) => apiFetch(`/api/room/${room.id}/tenants/`)))
      .then((results) => {
        if (cancelled) return
        const next = {}
        results.forEach((result, index) => {
          if (result.status === 'fulfilled' && Array.isArray(result.value?.tenants)) {
            next[targets[index].id] = result.value.tenants.length
          }
        })
        setOccupancyMap(next)
      })
    return () => { cancelled = true }
  }, [rooms, activeBuilding])

  const visibleRooms = rooms.filter((room) => {
    if (room.building !== activeBuilding) return false
    if (!query) return true
    return `${getRoomNumber(room)} ${room.resident || ''}`.toLowerCase().includes(query)
  })

  if (loading) return <LoadingShell label="Loading rooms…" />

  if (error) {
    return (
      <div className="surface">
        <div className="section-head" style={{ marginTop: 0 }}>
          <h2>Rooms unavailable</h2>
          <span>Rooms API</span>
        </div>
        <div className="error-state">
          <span>{error}</span>
          <button type="button" className="retry-button" onClick={onRetry}>Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="building-grid">
        {buildings.map((building) => (
          <button
            key={building.name}
            type="button"
            className={`building-card ${activeBuilding === building.name ? 'active' : ''}`}
            aria-pressed={activeBuilding === building.name}
            onClick={() => setSelectedBuilding(building.name)}
          >
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', marginBottom: 4 }}>BUILDING</div>
            <div style={{ fontSize: 24, fontFamily: 'var(--font-display)', fontWeight: 700 }}>{building.name}</div>
            <div style={{ fontSize: 11, fontWeight: 700, marginTop: 4 }}>{building.rooms?.length ?? 0} rooms</div>
          </button>
        ))}
      </div>

      <div className="surface" style={{ padding: '12px 16px', marginBottom: 24, display: 'flex', gap: 12 }}>
        <input
          id="rooms-search"
          type="search"
          className="field-input"
          aria-label={`Search rooms in building ${activeBuilding}`}
          placeholder="Search by room number or resident…"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          style={{ flex: 1, minHeight: 44, border: 'none', outline: 'none', background: 'transparent', boxShadow: 'none' }}
        />
      </div>

      {visibleRooms.length === 0 ? (
        <EmptyState message={`No rooms in Building ${activeBuilding} match your search.`} />
      ) : (
        <div className="room-grid">
          {visibleRooms.map((room) => {
            const status = normalizeRoomStatus(room)
            const occupied = status !== 'VACANT'
            const occupancyCount = occupancyMap[room.id]
            const occupancyLabel = occupancyCount === undefined ? '—' : `${occupancyCount}/2`
            const canAssign = occupancyCount === 0
            const canAdd = occupancyCount === 1

            return (
              <article
                key={room.id}
                className="room-card"
                onClick={() => onOpenRoom(room)}
                style={{ textAlign: 'left', width: '100%' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10, marginBottom: 12 }}>
                  <div>
                    <span className="eyebrow" style={{ color: '#5c564c', fontSize: 10 }}>BUILDING {room.building}</span>
                    <h3 style={{ margin: '2px 0 0', fontFamily: 'var(--font-display)', fontSize: 28, letterSpacing: '-0.04em' }}>
                      {getRoomNumber(room)}
                    </h3>
                  </div>
                  <span className={`status-tag ${statusColors[status] || 'pending'}`}>{status}</span>
                </div>

                <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 14 }}>
                  {occupied ? room.resident : <span style={{ color: '#9d968a' }}>Vacant Room</span>}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, borderTop: '2px dashed var(--ink)', paddingTop: 12 }}>
                  <StatRow
                    label="Occupancy"
                    value={occupancyLabel}
                    tone={occupancyCount === 2 ? 'var(--green)' : undefined}
                  />
                  <StatRow label="Agreed rent" value={money(room.agreed_rent)} />
                  <StatRow label="Electricity" value={money(room.electricity_amount)} />
                  <StatRow label="Total bill" value={money(room.total_bill)} />
                  <StatRow label="Collected" value={money(room.collected_amount)} tone="var(--green)" />
                  <StatRow
                    label="Outstanding"
                    value={money(room.outstanding_amount)}
                    tone={(room.outstanding_amount ?? 0) > 0 ? 'var(--red)' : undefined}
                  />
                </div>

                <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    className="ghost-button"
                    style={{ flex: 1, justifyContent: 'center', minWidth: 120 }}
                    onClick={(event) => { event.stopPropagation(); onOpenRoom(room) }}
                    aria-label={`Open room ${getRoomNumber(room)}`}
                  >
                    OPEN ROOM →
                  </button>
                  {(canAssign || canAdd) && (
                    <button
                      type="button"
                      className="btn-primary"
                      style={{ flex: 1, justifyContent: 'center', minWidth: 150 }}
                      onClick={(event) => { event.stopPropagation(); setAssignRoom(room) }}
                      aria-label={`${canAssign ? 'Assign' : 'Add'} a resident to room ${getRoomNumber(room)}`}
                    >
                      {canAssign ? 'ASSIGN RESIDENT' : 'ADD RESIDENT'}
                    </button>
                  )}
                </div>
              </article>
            )
          })}
        </div>
      )}

      {assignRoom && (
        <Suspense fallback={null}>
          <AssignResidentModal
            room={assignRoom}
            occupancy={occupancyMap[assignRoom.id]}
            onClose={() => setAssignRoom(null)}
            onRefresh={onRefresh}
            onToast={onToast}
            onResidentsChanged={onResidentsChanged}
          />
        </Suspense>
      )}
    </div>
  )
}

/**
 * Residents register backed by /api/guests/. The guests payload carries the room
 * it is attached to but not the building, so the room inventory snapshot (already
 * loaded by MainShell) supplies building and billing context per resident.
 */
function TenantProfile({ guest, room, onBack }) {
  const [profileData, setProfileData] = useState(null)
  const roomId = room?.id ?? guest.room?.id
  const [loading, setLoading] = useState(Boolean(roomId))
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false

    if (!roomId) {
      return () => { cancelled = true }
    }

    Promise.all([
      apiFetch(`/api/room/${roomId}/tenants/`),
      apiFetch(`/api/rooms/${roomId}/`),
      apiFetch(`/api/room/${roomId}/payment-history/`),
      apiFetch(`/api/room/${roomId}/electricity-history/`),
    ])
      .then(([tenantResponse, roomResponse, paymentResponse, electricityResponse]) => {
        if (cancelled) return
        const resident = (tenantResponse.tenants || []).find((tenant) => tenant.id === guest.id)
        if (!resident) {
          throw new Error('This resident is no longer listed in the assigned room. Return to Residents and refresh the list.')
        }
        setProfileData({
          resident,
          room: roomResponse.room,
          activeResidents: (tenantResponse.tenants || []).length,
          payments: paymentResponse.history || [],
          electricity: electricityResponse.history || [],
        })
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Unable to load this resident profile.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [guest.id, roomId, reloadKey])

  const retry = () => {
    setLoading(true)
    setError('')
    setReloadKey((key) => key + 1)
  }

  if (loading) return <LoadingShell label="Loading resident profile…" />

  if (error) {
    return (
      <div className="surface">
        <div className="tenant-profile-toolbar">
          <button type="button" className="ghost-button" onClick={onBack}>← Back to Residents</button>
        </div>
        <div className="section-head" style={{ marginTop: 0 }}><h2>Profile unavailable</h2></div>
        <div className="error-state">
          <span>{error}</span>
          <button type="button" className="retry-button" onClick={retry}>Retry</button>
        </div>
      </div>
    )
  }

  const resident = profileData?.resident || guest
  const roomDetails = profileData?.room
  const gender = resident.gender || guest.gender || ''
  const genderLabel = { M: 'Male', F: 'Female', O: 'Other' }[gender] || gender || '—'
  const documents = [
    ['Government ID photo', resident.govt_id_photo, true],
    ['Aadhaar front', resident.aadhar_front, Boolean(profileData?.resident)],
    ['Aadhaar back', resident.aadhar_back, Boolean(profileData?.resident)],
    ['College ID photo', resident.college_id_photo, true],
    ['Document verification image', resident.document_verification_image, Boolean(profileData?.resident)],
  ]

  return (
    <div className="tenant-profile">
      <div className="tenant-profile-toolbar">
        <button type="button" className="ghost-button" onClick={onBack}>← Back to Residents</button>
        <span className="eyebrow">TENANT PROFILE</span>
      </div>

      <section className="surface tenant-profile-section">
        <div className="section-head" style={{ marginTop: 0 }}><h2>Profile Overview</h2></div>
        <div className="resident-profile-heading">
          <div>
            <h3>{guest.full_name || '—'}</h3>
          </div>
          <span className={`status-tag ${guest.is_active ? 'paid' : 'pending'}`}>
            {guest.is_active ? 'ACTIVE' : 'INACTIVE'}
          </span>
        </div>
        <div className="tenant-profile-grid">
          <div><span className="eyebrow">Resident ID</span><strong>{guest.id}</strong></div>
          <div><span className="eyebrow">Building</span><strong>{roomDetails?.building || room?.building || '—'}</strong></div>
          <div><span className="eyebrow">Room</span><strong>{roomDetails?.room || getRoomNumber(room || guest.room)}</strong></div>
          <div><span className="eyebrow">Check-in</span><strong>{formatDate(guest.check_in_date)}</strong></div>
        </div>
      </section>

      <section className="surface tenant-profile-section">
        <div className="section-head" style={{ marginTop: 0 }}><h2>Personal &amp; Contact Details</h2></div>
        <div className="tenant-profile-grid">
          <div><span className="eyebrow">Full name</span><strong>{guest.full_name || '—'}</strong></div>
          <div><span className="eyebrow">Date of birth</span><strong>{formatDate(guest.date_of_birth)}</strong></div>
          <div><span className="eyebrow">Gender</span><strong>{genderLabel}</strong></div>
          <div><span className="eyebrow">Phone</span><strong>{guest.phone || '—'}</strong></div>
          <div><span className="eyebrow">Email</span><strong>{guest.email || '—'}</strong></div>
          <div><span className="eyebrow">Address</span><strong>{resident.address || guest.address || '—'}</strong></div>
          <div><span className="eyebrow">City</span><strong>{resident.city || guest.city || '—'}</strong></div>
          <div><span className="eyebrow">State</span><strong>{resident.state || guest.state || '—'}</strong></div>
          <div><span className="eyebrow">Country</span><strong>{resident.country || guest.country || '—'}</strong></div>
          <div><span className="eyebrow">Postal code</span><strong>{resident.zip_code || guest.zip_code || '—'}</strong></div>
        </div>
      </section>

      <section className="surface tenant-profile-section">
        <div className="section-head" style={{ marginTop: 0 }}><h2>Identity Documents</h2></div>
        <div className="tenant-profile-grid">
          <div><span className="eyebrow">ID type</span><strong>{guest.id_type || '—'}</strong></div>
          <div><span className="eyebrow">ID number</span><strong>{guest.id_number || '—'}</strong></div>
          <div><span className="eyebrow">College / student ID</span><strong>{resident.college_id || guest.college_id || '—'}</strong></div>
          <div><span className="eyebrow">College</span><strong>{guest.student_college || '—'}</strong></div>
          {documents.map(([label, path, known]) => (
            <div key={label}>
              <span className="eyebrow">{label}</span>
              <strong>{!known ? 'Not available from this API' : path ? 'On file' : 'Not on file'}</strong>
            </div>
          ))}
        </div>
        <p className="tenant-profile-note">Document images are not displayed in this profile.</p>
      </section>

      <section className="surface tenant-profile-section">
        <div className="section-head" style={{ marginTop: 0 }}><h2>Room &amp; Occupancy</h2></div>
        {roomDetails ? (
          <div className="tenant-profile-grid">
            <div><span className="eyebrow">Building</span><strong>{roomDetails.building || '—'}</strong></div>
            <div><span className="eyebrow">Room</span><strong>{roomDetails.room || '—'}</strong></div>
            <div><span className="eyebrow">Active residents in room</span><strong>{profileData.activeResidents}</strong></div>
            <div><span className="eyebrow">Check-out</span><strong>{guest.check_out_date ? formatDate(guest.check_out_date) : '—'}</strong></div>
          </div>
        ) : <p className="tenant-profile-note">No room is currently assigned to this resident.</p>}
      </section>

      <section className="surface tenant-profile-section">
        <div className="section-head" style={{ marginTop: 0 }}>
          <h2>Rent &amp; Financial Summary</h2>
          <span>Room-level billing</span>
        </div>
        {roomDetails ? (
          <>
            <div className="tenant-profile-grid">
              <div><span className="eyebrow">Current monthly rent</span><strong>{money(roomDetails.agreed_rent)}</strong></div>
              <div><span className="eyebrow">Current total bill</span><strong>{money(roomDetails.total_bill)}</strong></div>
              <div><span className="eyebrow">Collected</span><strong>{money(roomDetails.collected_amount)}</strong></div>
              <div><span className="eyebrow">Outstanding</span><strong>{money(roomDetails.outstanding_amount)}</strong></div>
              <div><span className="eyebrow">Current status</span><strong>{roomDetails.payment_status || '—'}</strong></div>
            </div>
            <p className="tenant-profile-note">Rent and collections are recorded for the room and are not attributed to an individual tenant.</p>
          </>
        ) : <p className="tenant-profile-note">Room-level billing is unavailable until a room is assigned.</p>}
      </section>

      <section className="surface tenant-profile-section">
        <div className="section-head" style={{ marginTop: 0 }}><h2>Payment History</h2><span>Room-level records</span></div>
        {!roomDetails ? <p className="tenant-profile-note">No room payment history is available.</p> : profileData.payments.length === 0 ? (
          <p className="tenant-profile-note">No rent payment records are available for this room.</p>
        ) : (
          <div className="tenant-profile-records">
            {profileData.payments.map((payment) => (
              <article className="tenant-profile-record" key={payment.id}>
                <div className="tenant-profile-record-heading"><strong>{payment.month}</strong><span>{payment.status}</span></div>
                <div className="tenant-profile-grid">
                  <div><span className="eyebrow">Rent</span><strong>{money(payment.rent_amount)}</strong></div>
                  <div><span className="eyebrow">Paid</span><strong>{money(payment.paid_amount)}</strong></div>
                  <div><span className="eyebrow">Remaining</span><strong>{money(payment.remaining)}</strong></div>
                </div>
                {(payment.records || []).map((record, index) => (
                  <div className="tenant-profile-record-detail" key={`${payment.id}-${record.date}-${index}`}>
                    {formatDate(record.date)} · {money(record.amount)} · {record.method || '—'}
                    {record.ref ? ` · Ref ${record.ref}` : ''}
                  </div>
                ))}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="surface tenant-profile-section">
        <div className="section-head" style={{ marginTop: 0 }}><h2>Electricity &amp; Bills</h2><span>Room-level bills</span></div>
        {!roomDetails ? <p className="tenant-profile-note">No room electricity history is available.</p> : profileData.electricity.length === 0 ? (
          <p className="tenant-profile-note">No electricity bills are recorded for this room.</p>
        ) : (
          <div className="tenant-profile-records">
            {profileData.electricity.map((bill) => (
              <article className="tenant-profile-record" key={bill.id}>
                <div className="tenant-profile-record-heading"><strong>{bill.month}</strong><span>{bill.status}</span></div>
                <div className="tenant-profile-grid">
                  <div><span className="eyebrow">Units</span><strong>{bill.units}</strong></div>
                  <div><span className="eyebrow">Rate</span><strong>₹{bill.rate} per unit</strong></div>
                  <div><span className="eyebrow">Bill amount</span><strong>{money(bill.bill_amount)}</strong></div>
                  <div><span className="eyebrow">Paid</span><strong>{money(bill.paid_amount)}</strong></div>
                  <div><span className="eyebrow">Remaining</span><strong>{money(bill.remaining)}</strong></div>
                  <div><span className="eyebrow">Due date</span><strong>{formatDate(bill.due_date)}</strong></div>
                </div>
              </article>
            ))}
          </div>
        )}
        {roomDetails && <p className="tenant-profile-note">Electricity bills are recorded for the room and are not attributed to an individual tenant.</p>}
      </section>

      <section className="surface tenant-profile-section">
        <div className="section-head" style={{ marginTop: 0 }}><h2>Additional Records</h2></div>
        <div className="tenant-profile-grid">
          <div><span className="eyebrow">Status</span><strong>{guest.is_active ? 'Active' : 'Inactive'}</strong></div>
          <div><span className="eyebrow">Registered</span><strong>{formatDate(guest.created_at)}</strong></div>
          <div className="tenant-profile-wide"><span className="eyebrow">Notes</span><strong>{guest.notes || '—'}</strong></div>
        </div>
      </section>
    </div>
  )
}

function ResidentsView({ rooms, buildings, syncToken = 0 }) {
  const [guests, setGuests] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [selectedBuilding, setSelectedBuilding] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedResidentId, setSelectedResidentId] = useState(null)

  useEffect(() => {
    let cancelled = false
    apiFetch('/api/guests/')
      .then((data) => {
        if (cancelled) return
        setGuests(data.guests || [])
        setError('')
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Unable to load residents.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
    // `syncToken` is bumped by MainShell after a successful assignment, so a
    // mounted register refetches fresh guest data.
  }, [reloadKey, syncToken])

  // Resets stay in the click handler so the effect never sets state synchronously.
  const retry = () => {
    setLoading(true)
    setError('')
    setReloadKey((key) => key + 1)
  }

  if (loading) return <LoadingShell label="Loading residents…" />

  if (error) {
    return (
      <div className="surface">
        <div className="section-head" style={{ marginTop: 0 }}>
          <h2>Residents unavailable</h2>
          <span>Guests API</span>
        </div>
        <div className="error-state">
          <span>{error}</span>
          <button type="button" className="retry-button" onClick={retry}>Retry</button>
        </div>
      </div>
    )
  }

  const query = searchQuery.trim().toLowerCase()
  const roomById = new Map(rooms.map((room) => [room.id, room]))

  const visibleResidents = guests.filter((guest) => {
    const snapshot = guest.room ? roomById.get(guest.room.id) : null
    if (selectedBuilding && (snapshot?.building || '') !== selectedBuilding) return false
    if (!query) return true
    const haystack = [
      guest.full_name,
      getRoomNumber(snapshot || guest.room),
      snapshot?.building,
      guest.phone,
      guest.email,
    ].filter(Boolean).join(' ').toLowerCase()
    return haystack.includes(query)
  })

  if (selectedResidentId !== null) {
    const guest = guests.find((resident) => resident.id === selectedResidentId)
    if (!guest) {
      return (
        <div className="surface">
          <div className="tenant-profile-toolbar">
            <button type="button" className="ghost-button" onClick={() => setSelectedResidentId(null)}>← Back to Residents</button>
          </div>
          <EmptyState message="This resident is no longer in the current list." />
        </div>
      )
    }
    const room = guest.room ? roomById.get(guest.room.id) || guest.room : null
    return (
      <TenantProfile
        key={`${guest.id}:${room?.id || 'unassigned'}`}
        guest={guest}
        room={room}
        onBack={() => setSelectedResidentId(null)}
      />
    )
  }

  return (
    <div>
      <div className="building-grid">
        <button
          type="button"
          className={`building-card ${selectedBuilding === '' ? 'active' : ''}`}
          aria-pressed={selectedBuilding === ''}
          onClick={() => setSelectedBuilding('')}
        >
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', marginBottom: 4 }}>FILTER</div>
          <div style={{ fontSize: 24, fontFamily: 'var(--font-display)', fontWeight: 700 }}>ALL</div>
          <div style={{ fontSize: 11, fontWeight: 700, marginTop: 4 }}>{guests.length} residents</div>
        </button>
        {buildings.map((building) => (
          <button
            key={building.name}
            type="button"
            className={`building-card ${selectedBuilding === building.name ? 'active' : ''}`}
            aria-pressed={selectedBuilding === building.name}
            onClick={() => setSelectedBuilding(building.name)}
          >
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', marginBottom: 4 }}>BUILDING</div>
            <div style={{ fontSize: 24, fontFamily: 'var(--font-display)', fontWeight: 700 }}>{building.name}</div>
            <div style={{ fontSize: 11, fontWeight: 700, marginTop: 4 }}>{building.rooms?.length ?? 0} rooms</div>
          </button>
        ))}
      </div>

      <div className="surface" style={{ padding: '12px 16px', marginBottom: 24, display: 'flex', gap: 12 }}>
        <input
          id="residents-search"
          type="search"
          className="field-input"
          aria-label="Search residents"
          placeholder="Search by name, room, phone or email…"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          style={{ flex: 1, minHeight: 44, border: 'none', outline: 'none', background: 'transparent', boxShadow: 'none' }}
        />
      </div>

      {visibleResidents.length === 0 ? (
        <EmptyState
          message={
            guests.length === 0
              ? 'No active residents are registered.'
              : 'No residents match your search.'
          }
        />
      ) : (
        <div className="room-grid">
          {visibleResidents.map((guest) => {
            const snapshot = guest.room ? roomById.get(guest.room.id) : null
            const roomNumber = getRoomNumber(snapshot || guest.room)
            const status = snapshot ? normalizeRoomStatus(snapshot) : null
            const rent = snapshot
              ? money(snapshot.agreed_rent)
              : guest.room
                ? money(guest.room.agreed_rent ?? guest.room.price)
                : '—'

            const card = (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10, marginBottom: 12 }}>
                  <div>
                    <span className="eyebrow" style={{ color: '#5c564c', fontSize: 10 }}>
                      {snapshot ? `BUILDING ${snapshot.building}` : 'NO ROOM ASSIGNED'}
                    </span>
                    <h3 style={{ margin: '2px 0 0', fontFamily: 'var(--font-display)', fontSize: 28, letterSpacing: '-0.04em' }}>
                      {roomNumber}
                    </h3>
                  </div>
                  {status && <span className={`status-tag ${statusColors[status] || 'pending'}`}>{status}</span>}
                </div>

                <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 14 }}>
                  {guest.full_name || '—'}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, borderTop: '2px dashed var(--ink)', paddingTop: 12 }}>
                  <StatRow label="Phone" value={guest.phone || '—'} />
                  <StatRow label="Checked in" value={formatDate(guest.check_in_date)} />
                  <StatRow label="Agreed rent" value={rent} />
                </div>

              </>
            )

            return (
              <article key={guest.id} className="room-card resident-card" style={{ cursor: 'default' }}>
                {card}
                <button
                  type="button"
                  className="resident-profile-action"
                  onClick={() => setSelectedResidentId(guest.id)}
                  aria-label={`View profile for ${guest.full_name || 'resident'}`}
                >
                  View Profile
                </button>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------------ *
 * Dashboard blocks.
 *
 * Everything rendered below is derived from the two authoritative payloads
 * this view already fetches — /api/dashboard/metrics/ (money + occupancy) and
 * /api/rooms/ (inventory, per-building rooms). No figure is hardcoded and no
 * calculation is invented here: the most these helpers do is sum the same
 * per-room snapshot the metrics endpoint is built from.
 * ------------------------------------------------------------------------ */

/**
 * One inventory figure. No card chrome, no coloured panel: a rule, a large
 * number and a tracked label, so property state never reads like money.
 */
function SnapshotFigure({ label, value, note, flash }) {
  return (
    <div className="snapshot-figure">
      <strong className={`snapshot-value${flash ? ' flash' : ''}`}>{value ?? '—'}</strong>
      <span className="snapshot-label">{label}</span>
      {note && <span className="snapshot-note">{note}</span>}
    </div>
  )
}

/**
 * One money figure. The label leads and the rupee value follows, and the tone
 * is only ever applied to the value so a due total is never a red panel.
 */
function CollectionFigure({ label, value, tone, flash }) {
  const toneClass = tone ? ` is-${tone}` : ''
  return (
    <div className="collection-figure">
      <span className="collection-label">{label}</span>
      <strong className={`collection-value${toneClass}${flash ? ' flash' : ''}`}>{value}</strong>
    </div>
  )
}

/**
 * Compact pulse row: label, percentage and one thin rule. The bar is marked
 * decorative because the percentage beside it is the real, readable value.
 *
 * `dial` / `breakdown` are phone-only renderings of the same backend-derived
 * values: the dial names occupancy in the brief's circular form and the
 * breakdown rows state occupied / vacant / total from the same numbers the
 * note already carries. Desktop keeps rendering label + bar + note only.
 */
function PulseRow({ label, value, tone, note, flash, dial, breakdown }) {
  const safe = Number.isFinite(value) ? value : 0
  const width = `${Math.min(100, Math.max(0, safe))}%`
  return (
    <div className="pulse-row">
      <div className="pulse-head">
        <span className="pulse-label">{label}</span>
        <strong className={`pulse-value${flash ? ' flash' : ''}`}>{safe.toFixed(1)}%</strong>
      </div>
      {dial && (
        <div className="pulse-dial" aria-hidden="true">
          <svg viewBox="0 0 100 100" className="pulse-dial-svg" focusable="false">
            <circle className="pulse-dial-track" cx="50" cy="50" r="42" />
            <circle
              className={`pulse-dial-arc pulse-dial-arc--${tone}`}
              cx="50"
              cy="50"
              r="42"
              strokeDasharray={`${(safe / 100) * 264} 264`}
            />
          </svg>
          <span className="pulse-dial-text">
            <strong>{safe.toFixed(1)}%</strong>
            <span>Occupied</span>
          </span>
        </div>
      )}
      <div className="progress-track progress-track--compact" aria-hidden="true">
        <div className={`progress-fill ${tone}`} style={{ '--bar-width': width }} />
      </div>
      <span className="pulse-note">{note}</span>
      {breakdown && (
        <dl className="pulse-breakdown">
          {breakdown.map(({ term, detail }) => (
            <div className="pulse-breakdown-row" key={term}>
              <dt>{term}</dt>
              <dd>{detail}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

/**
 * One building as a small architectural object rather than an admin card:
 * identity photo, its six-room facade, one occupancy line, what the building
 * still owes, and the route into Rooms. The facade draws one cell per real
 * room from the building's own snapshot, so occupied/vacant colour is never
 * hardcoded, and every total comes from the same authoritative per-room data
 * the metrics endpoint reports. The whole card is the control — it reuses the
 * existing dashboard → Rooms building navigation.
 *
 * The photo is a phone-only brand treatment reusing the approved header
 * artwork (`/branding/plh-final.webp`); it carries no data and is hidden from
 * assistive tech. Desktop renders the name-led card exactly as before.
 */
function BuildingObject({ building, rooms, onOpen }) {
  const list = building.rooms?.length
    ? building.rooms
    : rooms.filter((room) => room.building === building.name)
  const summary = summarizeRooms(list)
  const total = list.length
  const vacant = total - summary.occupied
  const owes = summary.due > 0

  return (
    <button
      type="button"
      className="building-object"
      onClick={() => onOpen?.(building.name)}
      aria-label={`Open rooms in building ${building.name}: ${total} rooms, ${summary.occupied} occupied, ${vacant} vacant, ${owes ? `${money(summary.due)} due` : 'nothing due'}`}
    >
      <span className="building-object-photo" aria-hidden="true">
        {building.name === 'M1' ? (
          <img src="/branding/building_M1.jpeg" alt="" loading="lazy" />
        ) : building.name === '1' ? (
          <img src="/branding/building_1.jpeg" alt="" loading="lazy" />
        ) : building.name === '2' ? (
          <img src="/branding/building_2.jpeg" alt="" loading="lazy" />
        ) : building.name === '3' ? (
          <img src="/branding/building_3.jpeg" alt="" loading="lazy" />
        ) : building.name === '4' ? (
          <img src="/branding/building_4.jpeg" alt="" loading="lazy" />
        ) : (
          <img src="/branding/building_5.jpeg" alt="" loading="lazy" />
        )}
        <span className="building-object-photo-name">{building.name}</span>
      </span>
      <span className="building-object-head">
        <span className="building-object-name">{building.name}</span>
        <span className="building-object-occupancy">
          {total} rooms · {summary.occupied} occupied · {vacant} vacant
        </span>
      </span>

      {/* Six-room facade: 3 across × 2 down, one cell per real room. */}
      <span className="building-facade" aria-hidden="true">
        {list.map((room) => {
          const occupied = isRoomOccupied(room)
          return (
            <span
              key={room.id}
              className={`facade-room${occupied ? ' is-occupied' : ''}`}
              title={`${getRoomNumber(room)} · ${occupied ? 'Occupied' : 'Vacant'}`}
            />
          )
        })}
      </span>

      <span className="building-object-foot">
        <span className={`building-object-status${owes ? ' is-due' : ' is-clear'}`}>
          {owes ? `${money(summary.due)} due` : 'Clear'}
        </span>
        <span className="building-object-action">View rooms →</span>
      </span>
      <span className="building-object-caption">Property block</span>
    </button>
  )
}

function DashboardView({ syncToken = 0, onOpenBuilding }) {
  const [metrics, setMetrics] = useState(null)
  const [meta, setMeta] = useState(null)
  const [buildings, setBuildings] = useState([])
  const [rooms, setRooms] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [roomsError, setRoomsError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  // Highlight a figure only when the backend reports a different value.
  const flashExpected = useValueFlash(metrics?.expected_yield)
  const flashCollected = useValueFlash(metrics?.realized_revenue)
  const flashDue = useValueFlash(metrics?.accounts_receivable)

  // Occupancy counts animate only when the backend reports a different figure.
  // Read straight from `meta` because the derived names below are declared after
  // the early returns, where hooks may no longer be called.
  const flashOccupied = useValueFlash(meta?.occupied_rooms)
  const flashVacant = useValueFlash(meta ? Number(meta.total_rooms) - Number(meta.occupied_rooms) : undefined)
  const flashOccupancyRate = useValueFlash(metrics?.occupancy_rate)

  // Resets live in the click handler rather than the effect body, so the effect
  // never calls setState synchronously (keeps react/set-state-in-effect clean).
  const retry = () => {
    setLoading(true)
    setError('')
    setRoomsError('')
    setReloadKey((key) => key + 1)
  }

  useEffect(() => {
    let cancelled = false

    // Metrics are authoritative for money/occupancy. The metrics payload carries no
    // building information, so the existing room inventory endpoint is the only
    // source for the building directory. Settled so a directory outage cannot blank
    // out the primary metrics.
    Promise.allSettled([
      apiFetch('/api/dashboard/metrics/'),
      apiFetch('/api/rooms/'),
    ]).then(([metricsResult, roomsResult]) => {
      if (cancelled) return

      if (metricsResult.status === 'rejected') {
        setError(metricsResult.reason?.message || 'Unable to load dashboard metrics.')
        setLoading(false)
        return
      }

      setMetrics(metricsResult.value.metrics || {})
      setMeta(metricsResult.value.meta || {})

      if (roomsResult.status === 'fulfilled') {
        setBuildings(roomsResult.value.buildings || [])
        setRooms(roomsResult.value.rooms || [])
      } else {
        setRoomsError(roomsResult.reason?.message || 'Building directory is unavailable.')
      }

      setLoading(false)
    })

    return () => { cancelled = true }
    // `syncToken` is bumped by MainShell after a successful financial mutation, so
    // the dashboard refetches authoritative metrics instead of adjusting state
    // locally from the mutation response.
  }, [reloadKey, syncToken])

  if (loading) return <LoadingShell label="Loading dashboard metrics…" />

  if (error) {
    return (
      <div className="surface">
        <div className="section-head" style={{ marginTop: 0 }}>
          <h2>Dashboard unavailable</h2>
          <span>Metrics API</span>
        </div>
        <div className="error-state">
          <span>{error}</span>
          <p style={{ margin: 0, fontSize: 13, color: '#5c564c' }}>
            These figures come from the backend metrics API, so nothing is displayed until it responds.
          </p>
          <button type="button" className="retry-button" onClick={retry}>
            Retry
          </button>
        </div>
      </div>
    )
  }

  const totalRooms = meta?.total_rooms ?? null
  const occupiedRooms = meta?.occupied_rooms ?? null
  const vacantRooms = totalRooms !== null && occupiedRooms !== null ? totalRooms - occupiedRooms : null
  const occupancyRate = Number(metrics?.occupancy_rate ?? 0)
  const collectionEfficiency = Number(metrics?.collection_efficiency ?? 0)
  const amountDue = Number(metrics?.accounts_receivable ?? 0)

  // The four blocks below run in a fixed order — inventory, money, pulse,
  // directory — so the page reads top-down as a property-operations console
  // instead of as an even wall of equal cards. Spacing, rules and typography
  // carry that hierarchy; no block needs a coloured panel to stand out.
  return (
    <div className="dashboard-layout">
      {/* 1 — PROPERTY SNAPSHOT. Inventory only. The rupees are stated once, in
          the next block, so no figure appears under two different names. */}
      <section
        className="dash-block metric-group metric-group--property"
        aria-labelledby="dash-snapshot"
      >
        <header className="dash-head">
          <h2 className="dash-title" id="dash-snapshot">Property Snapshot</h2>
          <span className="dash-meta">Updated {formatUpdated(meta?.last_updated)}</span>
        </header>
        <div className="snapshot-grid">
          <SnapshotFigure label="Buildings" value={roomsError ? '—' : buildings.length} />
          <SnapshotFigure label="Rooms" value={totalRooms ?? '—'} />
          <SnapshotFigure
            label="Occupied"
            value={occupiedRooms ?? '—'}
            note={`${occupancyRate.toFixed(1)}% occupancy`}
            flash={flashOccupied}
          />
          <SnapshotFigure label="Vacant" value={vacantRooms ?? '—'} flash={flashVacant} />
        </div>
      </section>

      {/* 2 — MONTHLY COLLECTION. Money only, straight from the metrics
          endpoint. Tones mark state on the value, never on the panel. The
          share bar below is the phone-only compact progress form of these
          same three backend-derived figures. */}
      <section
        className="dash-block metric-group metric-group--finance"
        aria-labelledby="dash-collection"
      >
        <header className="dash-head">
          <h2 className="dash-title" id="dash-collection">Monthly Collection</h2>
          <span className="dash-meta">Entire portfolio</span>
        </header>
        <div className="collection-grid">
          <CollectionFigure
            label="Expected"
            value={money(metrics?.expected_yield ?? 0)}
            flash={flashExpected}
          />
          <CollectionFigure
            label="Collected"
            value={money(metrics?.realized_revenue ?? 0)}
            tone="positive"
            flash={flashCollected}
          />
          <CollectionFigure
            label="Due"
            value={money(amountDue)}
            tone={amountDue > 0 ? 'attention' : undefined}
            flash={flashDue}
          />
        </div>
        <div
          className="collection-share"
          aria-hidden="true"
        >
          <span
            className="collection-share-fill"
            style={{ '--bar-width': `${Math.min(100, Math.max(0, collectionEfficiency))}%` }}
          />
        </div>
      </section>

      {/* 3 — PORTFOLIO PULSE. Two compact bars: a five-second operational
          read, not a second wall of metrics. */}
      <section className="dash-block" aria-labelledby="dash-pulse">
        <header className="dash-head">
          <h2 className="dash-title" id="dash-pulse">Portfolio Pulse</h2>
          <span className="dash-meta">Current month</span>
        </header>
        <div className="pulse-grid">
          <PulseRow
            label="Collection"
            value={collectionEfficiency}
            tone="green"
            note="Collected against expected"
          />
          <PulseRow
            label="Occupancy"
            value={occupancyRate}
            tone="blue"
            note={`${occupiedRooms ?? '—'} of ${totalRooms ?? '—'} rooms occupied`}
            flash={flashOccupancyRate}
            dial
            breakdown={[
              { term: 'Occupied', detail: occupiedRooms ?? '—' },
              { term: 'Vacant', detail: vacantRooms ?? '—' },
              { term: 'Total', detail: totalRooms ?? '—' },
            ]}
          />
        </div>
      </section>

      {/* 4 — BUILDING DIRECTORY. The portfolio map: six architectural
          objects, each drawn from its own room snapshots. */}
      <section className="dash-block dash-block--directory" aria-labelledby="dash-directory">
        <header className="dash-head">
          <h2 className="dash-title" id="dash-directory">Building Directory</h2>
          <span className="dash-meta">{roomsError ? 'Unavailable' : `${buildings.length} buildings`}</span>
        </header>
        {roomsError ? (
          <div className="error-state">
            <span>{roomsError}</span>
            <button type="button" className="retry-button" onClick={retry}>
              Retry
            </button>
          </div>
        ) : buildings.length === 0 ? (
          <EmptyState message="No building data is available." />
        ) : (
          <div className="dir-grid">
            {buildings.map((building) => (
              <BuildingObject
                key={building.name}
                building={building}
                rooms={rooms}
                onOpen={onOpenBuilding}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function ElectricityView({ rooms, buildings, loading, error, onOpenRoom, onRetry }) {
  const [selectedBuilding, setSelectedBuilding] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  const activeBuilding = selectedBuilding || buildings[0]?.name || ''
  const query = searchQuery.trim().toLowerCase()

  // Strict equality on purpose: a substring match made building "1" also list "M1" rooms.
  const visibleRooms = rooms.filter((room) => {
    if (room.building !== activeBuilding) return false
    if (!query) return true
    return `${getRoomNumber(room)} ${room.resident || ''}`.toLowerCase().includes(query)
  })

  // The configured per-unit rate is reported by the backend snapshot, not hardcoded here.
  const configuredRate = rooms[0]?.new_bill_rate

  if (loading) return <LoadingShell label="Loading electricity data…" />

  if (error) {
    return (
      <div className="surface">
        <div className="section-head" style={{ marginTop: 0 }}>
          <h2>Electricity unavailable</h2>
          <span>Rooms API</span>
        </div>
        <div className="error-state">
          <span>{error}</span>
          <button type="button" className="retry-button" onClick={onRetry}>Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="surface" style={{ padding: '16px 20px', marginBottom: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--yellow)', border: '3px solid var(--ink)', boxShadow: '6px 6px 0 var(--ink)' }}>
        <div>
          <h2 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 'clamp(20px, 4vw, 24px)', letterSpacing: '-0.02em' }}>ELECTRICITY READING</h2>
          <div style={{ fontSize: 13, color: 'var(--ink)', fontWeight: 700, marginTop: 4 }}>
            Configured rate: {configuredRate != null ? `${money(configuredRate)}/unit` : '—'} · Building {activeBuilding} · {visibleRooms.length} rooms
          </div>
        </div>
        <div className="brand-mark" style={{ width: 48, height: 48, fontSize: 24, background: 'var(--white)' }}>⚡</div>
      </div>

      <div className="building-grid">
        {buildings.map((building) => (
          <button
            key={building.name}
            type="button"
            className={`building-card ${activeBuilding === building.name ? 'active' : ''}`}
            aria-pressed={activeBuilding === building.name}
            onClick={() => setSelectedBuilding(building.name)}
          >
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', marginBottom: 4 }}>BUILDING</div>
            <div style={{ fontSize: 24, fontFamily: 'var(--font-display)', fontWeight: 700 }}>{building.name}</div>
            <div style={{ fontSize: 11, fontWeight: 700, marginTop: 4 }}>{building.rooms?.length ?? 0} rooms</div>
          </button>
        ))}
      </div>

      <div className="surface" style={{ padding: '12px 16px', marginBottom: 24, display: 'flex', gap: 12 }}>
        <input
          id="electricity-search"
          type="search"
          className="field-input"
          aria-label={`Search rooms in building ${activeBuilding}`}
          placeholder="Search by room number or resident…"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          style={{ flex: 1, minHeight: 44, border: 'none', outline: 'none', background: 'transparent', boxShadow: 'none' }}
        />
      </div>

      {visibleRooms.length === 0 ? (
        <EmptyState message={`No rooms in Building ${activeBuilding} match your search.`} />
      ) : (
        <div className="room-grid">
          {visibleRooms.map((room) => (
            <button
              key={room.id}
              type="button"
              className="room-card"
              onClick={() => onOpenRoom(room)}
              style={{ textAlign: 'left', width: '100%' }}
              aria-label={`Open room ${getRoomNumber(room)} to update its electricity reading`}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                <h3 style={{ margin: 0, fontFamily: 'var(--font-display)', fontSize: 28, letterSpacing: '-0.02em' }}>
                  {getRoomNumber(room)}
                </h3>
                <span className="eyebrow" style={{ color: 'var(--ink)' }}>
                  {room.resident && room.resident !== 'No resident' ? room.resident : 'Vacant'}
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12, paddingTop: 16, borderTop: '2px dashed var(--ink)' }}>
                <StatRow label="Previous reading" value={room.previous_reading ?? '—'} />
                <StatRow label="Current reading" value={room.current_reading ?? '—'} />
                <StatRow label="Units used" value={room.units_used ?? '—'} />
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, marginTop: 16, paddingTop: 16, borderTop: '2px dashed var(--ink)' }}>
                <div>
                  <span className="eyebrow" style={{ display: 'block', fontSize: 10, color: '#5c564c' }}>ELECTRICITY AMOUNT</span>
                  <strong style={{ fontFamily: 'var(--font-display)', fontSize: 24, letterSpacing: '-0.02em' }}>{money(room.electricity_amount)}</strong>
                </div>
                <span style={{ padding: '8px 12px', border: '2px solid var(--ink)', background: 'var(--paper)', fontWeight: 700, fontSize: 12 }}>
                  UPDATE →
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Drop a single room's entry from a per-room state map.
 * Returns the same object when nothing changes, so React can skip the re-render.
 */
/** Payment-status filter options, matching the statuses the backend reports. */
const PAYMENT_STATUS_FILTERS = ['', 'PAID', 'PARTIAL', 'DUE']

function omitRoom(map, roomId) {
  if (!(roomId in map)) return map
  const next = { ...map }
  delete next[roomId]
  return next
}

function PaymentsView({ rooms, buildings, loading, error, onOpenRoom, onRetry, historyInvalidation }) {
  const [openRoomId, setOpenRoomId] = useState(null)
  const [history, setHistory] = useState({})
  const [historyLoading, setHistoryLoading] = useState({})
  const [historyError, setHistoryError] = useState({})
  // MainShell bumps this signal (with the affected room id) after a successful
  // collection, so only that room's history is ever invalidated or refetched.
  const [appliedInvalidation, setAppliedInvalidation] = useState(() => historyInvalidation?.token ?? 0)
  const [pendingFetch, setPendingFetch] = useState(null)
  const [selectedBuilding, setSelectedBuilding] = useState('')
  const [selectedStatus, setSelectedStatus] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  // Strict equality on purpose: building names are distinct values ("M1" is a
  // different building from "1"), so any loose or substring match would let the
  // two bleed into each other.
  const query = searchQuery.trim().toLowerCase()
  // Building options come from the backend list, which already orders M1,1..5.
  const buildingNames = buildings.map((building) => building.name)
  const visibleRooms = rooms.filter((room) => {
    if (selectedBuilding && room.building !== selectedBuilding) return false
    if (selectedStatus && normalizeRoomStatus(room) !== selectedStatus) return false
    if (!query) return true
    return `${getRoomNumber(room)} ${room.resident || ''}`.toLowerCase().includes(query)
  })

  // Summary cards follow the current selection: they always describe exactly the
  // rooms listed below, computed from the same authoritative per-room figures.
  const summary = summarizeRooms(visibleRooms)

  // Highlights fire only when the backend reports different figures.
  const flashExpected = useValueFlash(summary.expected)
  const flashCollected = useValueFlash(summary.collected)
  const flashDue = useValueFlash(summary.due)
  const filtersApplied = Boolean(selectedBuilding || selectedStatus || query)
  const scopeLabel = selectedBuilding
    ? `Building ${selectedBuilding}`
    : filtersApplied
      ? 'Filtered rooms'
      : 'Entire portfolio'

  // Ask for a fresh payment history for one room. Loading and error for that room
  // are reset here; the network request itself runs in the effect below, which
  // keeps synchronous setState out of the effect body.
  const requestHistory = (roomId) => {
    setHistoryLoading((current) => ({ ...current, [roomId]: true }))
    setHistoryError((current) => omitRoom(current, roomId))
    setPendingFetch((current) => ({ roomId, seq: (current?.seq ?? 0) + 1 }))
  }

  const toggleHistory = (roomId) => {
    if (openRoomId === roomId) {
      setOpenRoomId(null)
      return
    }
    setOpenRoomId(roomId)
    // Cached history is only reused while it is complete and clean; anything
    // loading, failed or invalidated is refetched on open.
    if (history[roomId] && !historyLoading[roomId] && !historyError[roomId]) return
    requestHistory(roomId)
  }

  // Render-phase adjustment: a payment was collected for `signalRoomId` since the
  // last render. Drop only that room's cached records and error, and refetch
  // immediately when its panel is open so the visible list never stays stale.
  const signalToken = historyInvalidation?.token ?? 0
  if (signalToken !== appliedInvalidation) {
    setAppliedInvalidation(signalToken)
    const signalRoomId = historyInvalidation?.roomId ?? null
    if (signalRoomId !== null) {
      setHistory((current) => omitRoom(current, signalRoomId))
      setHistoryError((current) => omitRoom(current, signalRoomId))
      if (openRoomId === signalRoomId) requestHistory(signalRoomId)
    }
  }

  // Single fetch path for payment history. Every setState runs after the await,
  // and a superseded request is cancelled so an older response can never win.
  useEffect(() => {
    if (!pendingFetch) return undefined
    const { roomId } = pendingFetch
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch(`/api/rooms/${roomId}/payments/`)
        if (cancelled) return
        setHistory((current) => ({ ...current, [roomId]: data.payments || [] }))
        setHistoryError((current) => omitRoom(current, roomId))
      } catch (err) {
        if (cancelled) return
        setHistoryError((current) => ({ ...current, [roomId]: err.message || 'Unable to load payment history.' }))
      } finally {
        if (!cancelled) setHistoryLoading((current) => omitRoom(current, roomId))
      }
    })()
    return () => { cancelled = true }
  }, [pendingFetch])

  if (loading) return <LoadingShell label="Loading payment ledger…" />

  if (error) {
    return (
      <div className="surface">
        <div className="section-head" style={{ marginTop: 0 }}>
          <h2>Payments unavailable</h2>
          <span>Rooms API</span>
        </div>
        <div className="error-state">
          <span>{error}</span>
          <button type="button" className="retry-button" onClick={onRetry}>Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="payments-layout">
      <div className="section-head" style={{ marginTop: 0 }}>
        <div>
          <span className="eyebrow" style={{ color: '#5c564c' }}>Current month</span>
          <h2>Collection Summary</h2>
        </div>
        <span>{scopeLabel} · {visibleRooms.length} of {rooms.length} rooms</span>
      </div>

      <div className="metrics-grid payments-metrics">
        <MetricCard label="Expected collection" value={money(summary.expected)} color="yellow" flash={flashExpected} />
        <MetricCard label="Total collected" value={money(summary.collected)} color="green" flash={flashCollected} />
        <MetricCard label="Due" value={money(summary.due)} color="red" flash={flashDue} />
        <MetricCard label="Fully paid rooms" value={summary.fullyPaid} />
      </div>

      <div className="surface" style={{ padding: '14px 16px', marginBottom: 20, display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="eyebrow" style={{ color: '#5c564c' }}>BUILDING</span>
          <div className="building-grid" style={{ gap: 8 }}>
            <button
              type="button"
              className={`building-card ${selectedBuilding === '' ? 'active' : ''}`}
              aria-pressed={selectedBuilding === ''}
              onClick={() => setSelectedBuilding('')}
              style={{ minWidth: 64, padding: '8px 12px' }}
            >
              ALL
            </button>
            {buildingNames.map((name) => (
              <button
                key={name}
                type="button"
                className={`building-card ${selectedBuilding === name ? 'active' : ''}`}
                aria-pressed={selectedBuilding === name}
                onClick={() => setSelectedBuilding(name)}
                style={{ minWidth: 64, padding: '8px 12px' }}
              >
                {name}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span className="eyebrow" style={{ color: '#5c564c' }}>PAYMENT STATUS</span>
          <div className="building-grid" style={{ gap: 8 }}>
            {PAYMENT_STATUS_FILTERS.map((status) => (
              <button
                key={status || 'all'}
                type="button"
                className={`building-card ${selectedStatus === status ? 'active' : ''}`}
                aria-pressed={selectedStatus === status}
                onClick={() => setSelectedStatus(status)}
                style={{ minWidth: 72, padding: '8px 12px' }}
              >
                {status || 'ALL'}
              </button>
            ))}
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 220, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <label className="eyebrow" htmlFor="payments-search" style={{ color: '#5c564c' }}>SEARCH</label>
          <input
            id="payments-search"
            type="search"
            className="field-input"
            placeholder="Search by room number or resident…"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            style={{ minHeight: 44 }}
          />
        </div>
      </div>

      <div className="surface payments-ledger">
        <div className="section-head" style={{ marginTop: 0 }}>
          <div>
            <span className="eyebrow" style={{ color: '#5c564c' }}>Current room bills</span>
            <h2>Payment Ledger</h2>
          </div>
          <span>{visibleRooms.length} rooms</span>
        </div>

        {visibleRooms.length === 0 ? (
          <EmptyState
            message={filtersApplied
              ? 'No rooms match the selected building, status and search.'
              : 'No room payment data is available.'}
          />
        ) : (
          <div className="payments-list">
            {visibleRooms.map(room => {
              const status = normalizeRoomStatus(room)
              const building = room.building || '—'
              const resident = room.resident && room.resident !== 'No resident' ? room.resident : 'Vacant Room'
              const roomHistory = history[room.id] || []
              const isHistoryOpen = openRoomId === room.id

              return (
                <article className="payment-row" key={room.id}>
                  <div className="payment-room-details">
                    <div>
                      <span className="eyebrow">Room ID</span>
                      <strong className="payment-room-number">{getRoomNumber(room)}</strong>
                    </div>
                    <div>
                      <span className="eyebrow">Building</span>
                      <strong>{building}</strong>
                    </div>
                    <div className="payment-resident">
                      <span className="eyebrow">Resident</span>
                      <strong>{resident}</strong>
                    </div>
                    <span className={`status-tag ${statusColors[status] || 'pending'}`}>{status}</span>
                  </div>

                  <div className="payment-financials">
                    <div><span>Agreed rent</span><strong>{money(room.agreed_rent || room.price || 0)}</strong></div>
                    <div><span>Total bill</span><strong>{money(room.total_bill || 0)}</strong></div>
                    <div><span>Amount collected</span><strong className="payment-collected">{money(room.collected_amount || 0)}</strong></div>
                    <div><span>Outstanding</span><strong className="payment-outstanding">{money(room.outstanding_amount || 0)}</strong></div>
                  </div>

                  <div className="payment-actions">
                    <button className="ghost-button" onClick={() => onOpenRoom(room)}>Open room →</button>
                    <button className="btn-primary" onClick={() => toggleHistory(room.id)}>
                      {isHistoryOpen ? 'Hide history' : 'Payment history'}
                    </button>
                  </div>

                  {isHistoryOpen && (
                    <div className="payment-history-panel">
                      <span className="eyebrow">Payment history</span>
                      {historyError[room.id] ? (
                        <div className="error-state">
                          <span>{historyError[room.id]}</span>
                          <button
                            type="button"
                            className="retry-button"
                            onClick={() => requestHistory(room.id)}
                          >
                            Retry
                          </button>
                        </div>
                      ) : historyLoading[room.id] ? (
                        <LoadingShell label="Loading payment history…" />
                      ) : roomHistory.length ? (
                        <div className="payment-history-list">
                          {roomHistory.map(record => (
                            <div className="payment-history-item" key={record.id}>
                              <div>
                                <span className="eyebrow">Payment date</span>
                                <strong>{formatDate(record.date)}</strong>
                              </div>
                              <div>
                                <span className="eyebrow">Method</span>
                                <strong>{record.method || '—'}</strong>
                              </div>
                              <strong>{money(record.amount)}</strong>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <EmptyState message="No payments have been recorded for this room." />
                      )}
                    </div>
                  )}
                </article>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

/** Expense category options, matching MaintenanceExpense.EXPENSE_CATEGORIES. */
const EXPENSE_CATEGORIES = [
  { value: 'plumbing', label: 'Plumbing' },
  { value: 'electrical', label: 'Electrical' },
  { value: 'painting', label: 'Painting' },
  { value: 'carpentry', label: 'Carpentry' },
  { value: 'cleaning', label: 'Cleaning' },
  { value: 'repairs', label: 'General Repairs' },
  { value: 'security', label: 'Security' },
  { value: 'internet', label: 'Internet/WiFi' },
  { value: 'other', label: 'Other' },
]

/**
 * Reporting period defaults are resolved once at module load, not during render,
 * so a re-render can never silently shift the period to a different month.
 */
const DEFAULT_REPORT_MONTH = (() => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`
})()

const DEFAULT_REPORT_YEAR = String(new Date().getFullYear())

/** Current month as YYYY-MM-DD, the format the reporting endpoints accept. */
function currentMonthValue() {
  return DEFAULT_REPORT_MONTH
}

/**
 * Expenses are read from /api/expenses/ and written through the existing
 * /api/maintenance/record/ endpoint — no second expense ledger is kept here and
 * no total is recomputed in the browser. Building options come straight from the
 * backend's authoritative list so 'M1' and '1' stay distinct.
 */
function ExpensesView({ onToast }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [month, setMonth] = useState(currentMonthValue)
  const [building, setBuilding] = useState('')
  const [showForm, setShowForm] = useState(false)

  // Expense totals animate only when the backend reports different figures.
  const flashTotal = useValueFlash(data?.totals?.total)
  const flashPaid = useValueFlash(data?.totals?.paid)
  const flashPending = useValueFlash(data?.totals?.pending)
  const flashCount = useValueFlash(data?.count)

  useEffect(() => {
    let cancelled = false
    const query = new URLSearchParams()
    if (month) query.set('month', month)
    if (building) query.set('building', building)
    apiFetch(`/api/expenses/?${query.toString()}`)
      .then((payload) => {
        if (cancelled) return
        setData(payload)
        setError('')
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Unable to load expenses.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [reloadKey, month, building])

  // Resets live in the click handler so the effect never sets state synchronously.
  const retry = () => {
    setLoading(true)
    setError('')
    setReloadKey((key) => key + 1)
  }

  if (loading) return <LoadingShell label="Loading expenses…" />

  if (error) {
    return (
      <div className="surface">
        <div className="section-head" style={{ marginTop: 0 }}>
          <h2>Expenses unavailable</h2>
          <span>Expenses API</span>
        </div>
        <div className="error-state">
          <span>{error}</span>
          <button type="button" className="retry-button" onClick={retry}>Retry</button>
        </div>
      </div>
    )
  }

  const expenses = data?.expenses || []
  const totals = data?.totals || { total: 0, paid: 0, pending: 0 }
  const buildingNames = data?.available_buildings || []

  return (
    <div>
      <div className="metrics-grid payments-metrics">
        <MetricCard label="Total expenses" value={money(totals.total)} color="yellow" flash={flashTotal} />
        <MetricCard label="Paid" value={money(totals.paid)} color="green" flash={flashPaid} />
        <MetricCard label="Pending" value={money(totals.pending)} color="red" flash={flashPending} />
        <MetricCard label="Recorded" value={data?.count ?? 0} flash={flashCount} />
      </div>

      <ExpenseFilters
        month={month}
        building={building}
        buildings={buildingNames}
        onMonthChange={setMonth}
        onBuildingChange={setBuilding}
        onAdd={() => setShowForm(true)}
      />

      <div className="surface payments-ledger">
        <div className="section-head" style={{ marginTop: 0 }}>
          <h2>Expense History</h2>
          <span>{expenses.length} record{expenses.length === 1 ? '' : 's'}</span>
        </div>

        {expenses.length === 0 ? (
          <EmptyState message="No expenses have been recorded for this selection." />
        ) : (
          <div className="payments-list">
            {expenses.map((expense) => (
              <article className="payment-row" key={expense.id}>
                <div className="payment-room-details">
                  <div>
                    <span className="eyebrow">Building</span>
                    <strong className="payment-room-number">{expense.building || '—'}</strong>
                  </div>
                  <div>
                    <span className="eyebrow">Category</span>
                    <strong>{expense.category_display}</strong>
                  </div>
                  <div className="payment-resident">
                    <span className="eyebrow">Date</span>
                    <strong>{formatDate(expense.date)}</strong>
                  </div>
                  {/* `pending` (grey) rather than `partial` (amber): amber already
                      means a partially-paid room elsewhere in the app. */}
                  <span className={`status-tag ${expense.is_paid ? 'paid' : 'pending'}`}>
                    {expense.is_paid ? 'PAID' : 'PENDING'}
                  </span>
                </div>

                <div className="payment-financials">
                  <div><span>Amount</span><strong className="payment-outstanding">{money(expense.amount)}</strong></div>
                  <div><span>Description</span><strong>{expense.description || '—'}</strong></div>
                </div>
              </article>
            ))}
          </div>
        )}
      </div>

      {showForm && (
        <ExpenseForm
          buildings={buildingNames}
          defaultMonth={month}
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false)
            setReloadKey((key) => key + 1)
            onToast?.({ type: 'success', message: 'Expense recorded.' })
          }}
        />
      )}
    </div>
  )
}

/** Month / building filter bar for the Expenses view. */
function ExpenseFilters({ month, building, buildings, onMonthChange, onBuildingChange, onAdd }) {
  return (
    <div className="surface" style={{ padding: '14px 16px', marginBottom: 20, display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <label className="eyebrow" htmlFor="expenses-month" style={{ color: '#5c564c' }}>MONTH</label>
        <input
          id="expenses-month"
          type="month"
          className="field-input"
          value={month.slice(0, 7)}
          onChange={(event) => onMonthChange(event.target.value ? `${event.target.value}-01` : '')}
          style={{ minHeight: 44 }}
        />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span className="eyebrow" style={{ color: '#5c564c' }}>BUILDING</span>
        <div className="building-grid" style={{ gap: 8 }}>
          <button type="button" className={`building-card ${building === '' ? 'active' : ''}`} aria-pressed={building === ''} onClick={() => onBuildingChange('')} style={{ minWidth: 64, padding: '8px 12px' }}>ALL</button>
          {buildings.map((name) => (
            <button key={name} type="button" className={`building-card ${building === name ? 'active' : ''}`} aria-pressed={building === name} onClick={() => onBuildingChange(name)} style={{ minWidth: 64, padding: '8px 12px' }}>{name}</button>
          ))}
        </div>
      </div>

      <button type="button" className="btn-primary" style={{ minHeight: 44 }} onClick={onAdd}>RECORD EXPENSE</button>
    </div>
  )
}

/** Posts to the existing /api/maintenance/record/ endpoint; no new API is added. */
function ExpenseForm({ buildings, defaultMonth, onClose, onSaved }) {
  const [form, setForm] = useState({
    building: buildings[0] || '',
    category: 'repairs',
    amount: '',
    date: defaultMonth || currentMonthValue(),
    description: '',
    is_paid: true,
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const update = (field) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value
    setForm((current) => ({ ...current, [field]: value }))
  }

  // Draft detection drives the shared modal's discard prompt: a backdrop or
  // Escape close never eats a typed-in (but unsent) expense.
  const hasUnsavedDraft = !saving && (
    form.amount.trim() !== '' || form.description.trim() !== '' || !form.is_paid
  )
  const closeMessage = hasUnsavedDraft
    ? 'You have an unsaved expense draft. Discard it and close?'
    : undefined

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (saving) return
    if (!form.building || !form.amount || !form.date) {
      setError('Building, amount and date are required.')
      return
    }
    setSaving(true)
    setError('')
    const body = new FormData()
    body.append('building_name', form.building)
    body.append('category', form.category)
    body.append('amount', form.amount)
    body.append('date', form.date)
    body.append('description', form.description)
    body.append('is_paid', form.is_paid ? 'true' : 'false')
    try {
      await apiFetch('/api/maintenance/record/', { method: 'POST', body })
      onSaved()
    } catch (err) {
      setError(err.message || 'Unable to record the expense.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal title="RECORD EXPENSE" onClose={saving ? undefined : onClose} confirmCloseMessage={closeMessage}>
      <form onSubmit={handleSubmit} aria-busy={saving} noValidate>
        {error && (
          <div className="error-state" role="alert" aria-live="assertive" style={{ marginBottom: 14 }}><span>{error}</span></div>
        )}

        <div className="expense-fields-grid">
          <FieldGroup label="Building">
            <select className="field-input" value={form.building} onChange={update('building')} disabled={saving}>
              {buildings.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </FieldGroup>
          <FieldGroup label="Category">
            <select className="field-input" value={form.category} onChange={update('category')} disabled={saving}>
              {EXPENSE_CATEGORIES.map(({ value, label }) => <option key={value} value={value}>{label}</option>)}
            </select>
          </FieldGroup>
          <FieldGroup label="Amount (₹)">
            <input type="number" min="0" step="0.01" inputMode="decimal" className="field-input" value={form.amount} onChange={update('amount')} disabled={saving} />
          </FieldGroup>
          <FieldGroup label="Date">
            <input type="date" className="field-input" value={form.date} onChange={update('date')} disabled={saving} />
          </FieldGroup>
        </div>

        <FieldGroup label="Description">
          <input type="text" className="field-input" value={form.description} onChange={update('description')} disabled={saving} placeholder="What was this expense for?" autoComplete="off" />
        </FieldGroup>

        <label className="expense-paid-row">
          <input type="checkbox" checked={form.is_paid} onChange={update('is_paid')} disabled={saving} />
          Already paid (pending expenses do not reduce net collection)
        </label>

        <div className="modal-footer">
          <button type="button" className="ghost-button" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={saving}>{saving ? 'Saving…' : 'Record expense'}</button>
        </div>
      </form>
    </Modal>
  )
}

function AnalyticsView() {
  const [metrics, setMetrics] = useState(null)
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const retry = () => {
    setLoading(true)
    setError('')
    setReloadKey((key) => key + 1)
  }

  useEffect(() => {
    let cancelled = false
    apiFetch('/api/dashboard/metrics/')
      .then((data) => {
        if (cancelled) return
        setMetrics(data.metrics || {})
        setMeta(data.meta || {})
        setError('')
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Unable to load analytics.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [reloadKey])

  if (loading) return <LoadingShell label="Loading analytics…" />

  if (error) {
    return (
      <div className="surface">
        <div className="section-head" style={{ marginTop: 0 }}>
          <h2>Analytics unavailable</h2>
          <span>Metrics API</span>
        </div>
        <div className="error-state">
          <span>{error}</span>
          <p style={{ margin: 0, fontSize: 13, color: '#5c564c' }}>
            These figures come from the backend metrics API, so nothing is displayed until it responds.
          </p>
          <button type="button" className="retry-button" onClick={retry}>Retry</button>
        </div>
      </div>
    )
  }

  const totalRooms = meta?.total_rooms ?? null
  const occupiedRooms = meta?.occupied_rooms ?? null
  const vacantRooms = totalRooms !== null && occupiedRooms !== null ? totalRooms - occupiedRooms : null
  const occupancyRate = Number(metrics?.occupancy_rate ?? 0)
  const collectionEfficiency = Number(metrics?.collection_efficiency ?? 0)

  return (
    <div>
      <div className="section-head" style={{ marginTop: 0 }}>
        <h2>Performance</h2>
        <span>Updated {formatUpdated(meta?.last_updated)}</span>
      </div>

      <div className="analytics-grid">
        <div className="analytics-card yellow">
          <span>Expected yield (month)</span>
          <strong>{money(metrics?.expected_yield ?? 0)}</strong>
        </div>
        <div className="analytics-card green">
          <span>Realized revenue</span>
          <strong>{money(metrics?.realized_revenue ?? 0)}</strong>
        </div>
        <div className="analytics-card red">
          <span>Accounts receivable</span>
          <strong>{money(metrics?.accounts_receivable ?? 0)}</strong>
        </div>
        <div className="analytics-card blue">
          <span>Collection efficiency</span>
          <strong>{collectionEfficiency.toFixed(1)}%</strong>
        </div>
        <div className="analytics-card blue">
          <span>Occupancy rate</span>
          <strong>{occupancyRate.toFixed(1)}%</strong>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="surface">
          <div className="section-head" style={{ marginTop: 0 }}>
            <h2>Occupancy Split</h2>
            <span>Live</span>
          </div>
          <div className="metrics-grid">
            <MetricCard label="Total rooms" value={totalRooms ?? '—'} />
            <MetricCard label="Occupied" value={occupiedRooms ?? '—'} color="green" />
            <MetricCard label="Vacant" value={vacantRooms ?? '—'} color="yellow" />
          </div>
        </div>

        <div className="surface">
          <div className="section-head" style={{ marginTop: 0 }}>
            <h2>Reporting Scope</h2>
            <span>Metric API</span>
          </div>
          <p style={{ margin: 0, fontSize: 13, color: '#5c564c' }}>
            Current month only. Monthly and yearly figures are in the report below.
          </p>
        </div>
      </div>

      <FinancialReport />
    </div>
  )
}

/**
 * Monthly and yearly financial reports. Every figure is aggregated by Django in
 * /api/reports/monthly/ and /api/reports/yearly/ from MonthlyPayment,
 * ElectricityBill and MaintenanceExpense — nothing is summed in the browser, so
 * this view cannot drift from the database. Settlement and previous-due have no
 * backing column and are reported as unavailable, never as zero.
 */
function FinancialReport() {
  const [monthly, setMonthly] = useState(null)
  const [yearly, setYearly] = useState(null)
  const [month, setMonth] = useState(currentMonthValue)
  const [year, setYear] = useState(DEFAULT_REPORT_YEAR)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // Report figures animate only when the backend reports different values.
  const flashGross = useValueFlash(monthly?.gross_collected)
  const flashDeductions = useValueFlash(monthly?.expenses?.paid_total)
  const flashNet = useValueFlash(monthly?.net_operating_collection)
  const flashPendingExp = useValueFlash(monthly?.expenses?.pending_total)

  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    const monthQuery = month ? `?month=${encodeURIComponent(month)}` : ''
    Promise.all([
      apiFetch(`/api/reports/monthly/${monthQuery}`),
      apiFetch(`/api/reports/yearly/?year=${encodeURIComponent(year)}`),
    ])
      .then(([monthPayload, yearPayload]) => {
        if (cancelled) return
        setMonthly(monthPayload)
        setYearly(yearPayload)
        setError('')
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Unable to load the financial report.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [reloadKey, month, year])

  const retry = () => {
    setLoading(true)
    setError('')
    setReloadKey((key) => key + 1)
  }

  return (
    <div>
      <div className="section-head">
        <h2>Financial Report</h2>
        <span>{monthly?.period?.label || '—'}</span>
      </div>

      <div className="surface" style={{ padding: '14px 16px', marginBottom: 20, display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'flex-end' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <label className="eyebrow" htmlFor="report-month" style={{ color: '#5c564c' }}>MONTH</label>
          <input id="report-month" type="month" className="field-input" value={month.slice(0, 7)} onChange={(event) => setMonth(event.target.value ? `${event.target.value}-01` : '')} style={{ minHeight: 44 }} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <label className="eyebrow" htmlFor="report-year" style={{ color: '#5c564c' }}>YEAR</label>
          <input id="report-year" type="number" min="1900" max="9999" className="field-input" value={year} onChange={(event) => setYear(event.target.value)} style={{ minHeight: 44, width: 120 }} />
        </div>
        <button type="button" className="ghost-button" style={{ minHeight: 44 }} onClick={retry}>Refresh</button>
      </div>

      {loading ? (
        <LoadingShell label="Building the financial report…" />
      ) : error ? (
        <div className="surface">
          <div className="error-state">
            <span>{error}</span>
            <button type="button" className="retry-button" onClick={retry}>Retry</button>
          </div>
        </div>
      ) : (
        <>
          <div className="metrics-grid payments-metrics">
            <MetricCard label="Gross collection" value={money(monthly?.gross_collected ?? 0)} color="green" flash={flashGross} />
            <MetricCard label="Paid deductions" value={money(monthly?.expenses?.paid_total ?? 0)} color="red" flash={flashDeductions} />
            <MetricCard label="Net operating collection" value={money(monthly?.net_operating_collection ?? 0)} color="green" flash={flashNet} />
            <MetricCard label="Pending expenses" value={money(monthly?.expenses?.pending_total ?? 0)} color="yellow" flash={flashPendingExp} />
          </div>

          <div className="surface report-section" style={{ marginBottom: 20 }}>
            <div className="section-head" style={{ marginTop: 0 }}>
              <h2>Income by Building</h2>
              <span>{monthly?.period?.label || '—'}</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {(monthly?.income || []).map((line) => (
                <StatRow
                  key={line.building}
                  label={`Building ${line.building} — expected ${money(line.gross_expected)}`}
                  value={money(line.collected)}
                  tone="var(--green)"
                />
              ))}
              <div style={{ borderTop: '3px solid var(--ink)', marginTop: 6, paddingTop: 10 }}>
                <StatRow label="TOTAL GROSS COLLECTION" value={money(monthly?.gross_collected ?? 0)} />
              </div>
              <StatRow label="Paid expenses (deductions)" value={`- ${money(monthly?.expenses?.paid_total ?? 0)}`} tone="var(--red)" />
              <div style={{ borderTop: '3px solid var(--ink)', marginTop: 6, paddingTop: 10 }}>
                <StatRow label="NET OPERATING COLLECTION" value={money(monthly?.net_operating_collection ?? 0)} tone="var(--blue)" />
              </div>
            </div>
          </div>

          <div className="surface report-section" style={{ marginBottom: 20 }}>
            <div className="section-head" style={{ marginTop: 0 }}>
              <h2>Expense Breakdown</h2>
              <span>Paid only</span>
            </div>
            {(monthly?.expenses?.paid_by_category || []).length === 0 ? (
              <EmptyState message="None recorded." />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {monthly.expenses.paid_by_category.map((entry) => (
                  <StatRow key={entry.category} label={entry.category_display} value={money(entry.amount)} tone="var(--red)" />
                ))}
              </div>
            )}
            {/* Only surfaced when there is a pending amount to act on. */}
            {(monthly?.expenses?.pending_total ?? 0) > 0 && (
              <p style={{ margin: '14px 0 0', fontSize: 13, color: '#5c564c' }}>
                {money(monthly.expenses.pending_total)} pending — excluded from net until paid.
              </p>
            )}
          </div>

          <div className="surface payments-ledger report-section" style={{ marginBottom: 20 }}>
            <div className="section-head" style={{ marginTop: 0 }}>
              <h2>Yearly Report</h2>
              <span>{yearly?.period?.label || '—'}</span>
            </div>
            <div className="payments-list">
              {(yearly?.months || []).map((row) => (
                <article className="payment-row" key={row.month}>
                  <div className="payment-room-details">
                    <div>
                      <span className="eyebrow">Month</span>
                      <strong className="payment-room-number">{row.label}</strong>
                    </div>
                  </div>
                  <div className="payment-financials">
                    <div><span>Gross collection</span><strong>{money(row.gross_collection)}</strong></div>
                    <div><span>Paid expenses</span><strong className="payment-outstanding">{money(row.paid_expenses)}</strong></div>
                    <div><span>Net operating collection</span><strong className="payment-collected">{money(row.net_operating_collection)}</strong></div>
                  </div>
                </article>
              ))}
            </div>
            <div style={{ borderTop: '3px solid var(--ink)', marginTop: 16, paddingTop: 12 }}>
              <StatRow label="YEARLY GROSS COLLECTION" value={money(yearly?.totals?.gross_collection ?? 0)} />
              <div style={{ height: 8 }} />
              <StatRow label="YEARLY PAID EXPENSES" value={money(yearly?.totals?.paid_expenses ?? 0)} tone="var(--red)" />
              <div style={{ height: 8 }} />
              <StatRow label="YEARLY NET OPERATING COLLECTION" value={money(yearly?.totals?.net_operating_collection ?? 0)} tone="var(--blue)" />
            </div>
          </div>

          <div className="surface report-section">
            <div className="section-head" style={{ marginTop: 0 }}>
              <h2>Not Available</h2>
              <span>No backing data</span>
            </div>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: '#5c564c' }}>
              {(monthly?.unavailable || []).map((item) => (
                <li key={item.field}><strong>{item.field}</strong> — {item.reason}</li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  )
}

/**
 * Public brand landing — the front door of the unauthenticated flow.
 * Presentational only: its single action hands off to the existing login
 * screen, which keeps using the project's authentication context unchanged.
 */
function LandingShell({ onEnter }) {
  return (
    <div className="panesar-landing">
      <header className="pl-topbar">
        <div className="pl-brandmark">
          <img src="/branding/panesar-logo.png" alt="" width="34" height="34" />
          <span className="pl-wordmark">Panesar <span className="gold">Living</span></span>
        </div>
        <span className="pl-topmeta">Property Operations / 2026</span>
      </header>

      <span className="pl-rail left" aria-hidden="true">Panesar Property System</span>
      <span className="pl-rail right" aria-hidden="true">Rooms · Residents · Payments</span>

      <main className="pl-hero">
        <div className="pl-monogram">
          <img src="/branding/panesar-logo.png" alt="Panesar PG and Motels emblem" />
        </div>

        <h1 className="pl-title">
          <span className="pl-word w-panesar">PANESAR</span>{' '}
          <span className="pl-word w-living">LIVING</span>
        </h1>
        <span className="pl-kicker">Property Operations</span>
        <span className="pl-rule" aria-hidden="true" />
        <p className="pl-sub">
          One focused workspace for rooms, residents, rent, electricity and property operations.
        </p>

        <button type="button" className="pl-enter" onClick={onEnter}>
          Enter workspace <span className="arrow" aria-hidden="true">→</span>
        </button>
      </main>

      <footer className="pl-caption">People · Property · Progress</footer>
    </div>
  )
}

function LoginShell() {
  const { login, authError, checkAuth } = useAuth()
  const [form, setForm] = useState({ username: '', password: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [retrying, setRetrying] = useState(false)

  const visibleError = error || authError
  // authError only appears when the session probe itself failed (backend down),
  // which is a different problem from a rejected username/password.
  const isConnectionError = !error && Boolean(authError)

  const handleChange = (field) => (event) => {
    const { value } = event.target
    setForm((current) => ({ ...current, [field]: value }))
    if (error) setError('')
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (loading) return

    if (!form.username.trim() || !form.password) {
      setError('Enter both your username and password to continue.')
      return
    }

    setLoading(true)
    setError('')
    try {
      await login({ username: form.username.trim(), password: form.password })
    } catch (err) {
      setError(err.message || 'Login failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleRetry = async () => {
    setRetrying(true)
    try {
      await checkAuth()
    } finally {
      setRetrying(false)
    }
  }

  return (
    <div className="panesar-login">
      <aside className="panesar-brand">
        <span className="plb-corner tl" aria-hidden="true" />
        <span className="plb-corner tr" aria-hidden="true" />
        <span className="plb-corner bl" aria-hidden="true" />
        <span className="plb-corner br" aria-hidden="true" />
        <div className="plb-arc" aria-hidden="true" />

        <div className="plb-content">
          <div className="plb-logo">
            <img src="/branding/panesar-logo.png" alt="" />
          </div>
          <div className="plb-title">PANESAR <span className="gold">LIVING</span></div>
          <div className="plb-kicker">Property Operations</div>
          <span className="plb-rule" aria-hidden="true" />
          <p className="plb-copy">
            A focused digital workspace for rooms, residents, rent, electricity
            and everyday property operations.
          </p>
        </div>

        <div className="plb-foot">Panesar Living · Property Operations</div>
      </aside>

      <main className="panesar-auth-side">
        <span className="pl-auth-meta" aria-hidden="true">Login / Access</span>

        <section className="panesar-login-card" aria-labelledby="login-heading">
          <h1 className="pl-heading" id="login-heading">
            <span>Welcome</span> <span className="blue">back.</span>
          </h1>
          <p className="pl-lede">Enter your property operations credentials to continue.</p>

          {visibleError && (
            <div id="login-error" className="pl-error">
              <Toast
                type="error"
                message={visibleError}
                onClose={error ? () => setError('') : undefined}
              />
            </div>
          )}

          {isConnectionError && (
            <button
              type="button"
              className="retry-button pl-retry"
              onClick={handleRetry}
              disabled={retrying}
            >
              {retrying ? 'Reconnecting…' : 'Retry connection'}
            </button>
          )}

          <form onSubmit={handleSubmit} className="pl-form" aria-busy={loading} noValidate>
            <div className="pl-field">
              <label htmlFor="login-username">Username</label>
              <input
                id="login-username"
                name="username"
                className="pl-input"
                placeholder="Enter your username"
                value={form.username}
                onChange={handleChange('username')}
                autoComplete="username"
                autoFocus
                required
                disabled={loading}
                aria-invalid={visibleError ? 'true' : undefined}
                aria-describedby={visibleError ? 'login-error' : undefined}
              />
            </div>

            <div className="pl-field">
              <label htmlFor="login-password">Password</label>
              <input
                id="login-password"
                name="password"
                type="password"
                className="pl-input"
                placeholder="Enter your password"
                value={form.password}
                onChange={handleChange('password')}
                autoComplete="current-password"
                required
                disabled={loading}
                aria-invalid={visibleError ? 'true' : undefined}
                aria-describedby={visibleError ? 'login-error' : undefined}
              />
            </div>

            <button type="submit" className="pl-submit" disabled={loading}>
              {loading ? 'Authenticating…' : 'Sign in to Panesar Living →'}
            </button>
          </form>

          <p className="pl-card-foot">Protected property management workspace</p>
        </section>
      </main>
    </div>
  )
}

function MainShell() {
  const { authState } = useAuth()
  const [currentView, setCurrentView] = useState('dashboard')
  // Which unauthenticated screen to show: the brand landing first, then the
  // login card once the visitor asks to enter. Authentication itself (login
  // call, error handling, protected views) is unchanged.
  const [authView, setAuthView] = useState('landing')
  const [rooms, setRooms] = useState([])
  const [buildings, setBuildings] = useState([])
  const [roomsLoading, setRoomsLoading] = useState(true)
  const [roomsError, setRoomsError] = useState('')
  const [selectedRoomId, setSelectedRoomId] = useState(null)
  const [toast, setToast] = useState(null)
  // { roomId, token } emitted after a successful collection, so the payments view
  // can invalidate/refetch the history of exactly the room that changed.
  const [historyInvalidation, setHistoryInvalidation] = useState(null)
  // Bumped after a successful assignment so a mounted residents register refetches.
  const [residentsSync, setResidentsSync] = useState(0)
  // Bumped after any successful financial mutation so the dashboard refetches
  // authoritative metrics from the backend rather than trusting local arithmetic.
  const [financialSync, setFinancialSync] = useState(0)
  // Building selected from the dashboard directory; consumed by RoomsView.
  const [roomsBuilding, setRoomsBuilding] = useState('')

  const handlePaymentsCollected = useCallback((roomId) => {
    setHistoryInvalidation((prev) => ({ roomId, token: (prev?.token ?? 0) + 1 }))
    setFinancialSync((value) => value + 1)
  }, [])

  const handleResidentsChanged = useCallback(() => {
    setResidentsSync((value) => value + 1)
    setFinancialSync((value) => value + 1)
  }, [])

  // Dashboard building card → Rooms, filtered to exactly that building.
  const openBuilding = useCallback((name) => {
    setRoomsBuilding(name)
    setCurrentView('rooms')
  }, [])

  // Single source of truth for room data. Every view and the drawer read from this,
  // so one refetch after a mutation refreshes cards, totals and the drawer together.
  const refreshRooms = useCallback(async () => {
    const data = await apiFetch('/api/rooms/')
    setRooms(data.rooms || [])
    setBuildings(data.buildings || [])
    setRoomsError('')
    return data
  }, [])

  useEffect(() => {
    // Only load rooms once the session is actually established. Fetching while
    // authState is 'checking'/'unauthenticated' would hit the login redirect,
    // and that rejection would otherwise persist and leave every room-backed
    // view permanently empty even after a successful login.
    if (authState !== 'authenticated') return undefined

    let cancelled = false
    // Fetched inline (rather than via refreshRooms) so that no setState runs
    // synchronously inside the effect body.
    apiFetch('/api/rooms/')
      .then((data) => {
        if (cancelled) return
        setRooms(data.rooms || [])
        setBuildings(data.buildings || [])
        setRoomsError('')
      })
      .catch((err) => {
        if (!cancelled) setRoomsError(err.message || 'Unable to load rooms.')
      })
      .finally(() => {
        if (!cancelled) setRoomsLoading(false)
      })
    return () => { cancelled = true }
  }, [authState])

  useEffect(() => {
    if (!toast) return undefined
    const timer = setTimeout(() => setToast(null), 4500)
    return () => clearTimeout(timer)
  }, [toast])

  const retryRooms = () => {
    setRoomsLoading(true)
    setRoomsError('')
    refreshRooms()
      .catch((err) => setRoomsError(err.message || 'Unable to load rooms.'))
      .finally(() => setRoomsLoading(false))
  }

  const openRoom = (room) => setSelectedRoomId(room.id)

  if (authState === 'checking') return <LoadingShell label="Checking session…" />
  // The auth state alone decides "signed in or not"; only the presentation of
  // the signed-out state is routed — Landing first, then the Login card.
  if (authState === 'unauthenticated' || authState === 'error') {
    return authView === 'login'
      ? <LoginShell />
      : <LandingShell onEnter={() => setAuthView('login')} />
  }

  const activeView = VIEW_META[currentView] || VIEW_META.dashboard
  const selectedRoom = selectedRoomId === null ? null : rooms.find((room) => room.id === selectedRoomId) || null

  return (
    <div className="page-shell">
      <TopBar currentView={currentView} onViewChange={setCurrentView} />

      <main className="content-wrap" key={currentView} aria-labelledby="page-title" data-view={currentView}>
        <div className="page-banner">
          <div>
            {activeView.eyebrow && <span className="eyebrow">{activeView.eyebrow}</span>}
            {/* The banner heading is the page identity; labelling the landmark
                with it means assistive tech announces "where am I" on entry. */}
            <h1 id="page-title">{activeView.title}</h1>
          </div>
        </div>

        {currentView === 'dashboard' ? (
          <DashboardView syncToken={financialSync} onOpenBuilding={openBuilding} />
        ) : currentView === 'rooms' ? (
          <RoomsView
            rooms={rooms}
            buildings={buildings}
            selectedBuilding={roomsBuilding}
            onBuildingChange={setRoomsBuilding}
            loading={roomsLoading}
            error={roomsError}
            onOpenRoom={openRoom}
            onRetry={retryRooms}
            onRefresh={refreshRooms}
            onToast={setToast}
            onResidentsChanged={handleResidentsChanged}
          />
        ) : currentView === 'residents' ? (
          <ResidentsView
            rooms={rooms}
            buildings={buildings}
            syncToken={residentsSync}
          />
        ) : currentView === 'electricity' ? (
          <ElectricityView
            rooms={rooms}
            buildings={buildings}
            loading={roomsLoading}
            error={roomsError}
            onOpenRoom={openRoom}
            onRetry={retryRooms}
          />
        ) : currentView === 'payments' ? (
          <PaymentsView
            rooms={rooms}
            buildings={buildings}
            loading={roomsLoading}
            error={roomsError}
            onOpenRoom={openRoom}
            onRetry={retryRooms}
            historyInvalidation={historyInvalidation}
          />
        ) : currentView === 'expenses' ? (
          <ExpensesView onToast={setToast} />
        ) : currentView === 'analytics' ? (
          <AnalyticsView />
        ) : (
          <div className="surface">
            <div className="section-head">
              <h2>{activeView.title} Module</h2>
              <span>Coming next</span>
            </div>
            <p style={{ fontSize: 14, color: '#5c564c', marginBottom: 20 }}>
              Content for <strong>{activeView.title}</strong> is scheduled for a later frontend step.
            </p>
          </div>
        )}
      </main>

      {toast && (
        <div className="toast-region">
          <Toast type={toast.type} message={toast.message} onClose={() => setToast(null)} />
        </div>
      )}

      {selectedRoom && (
        <Suspense fallback={null}>
          <RoomDrawer
            key={selectedRoom.id}
            room={selectedRoom}
            onClose={() => setSelectedRoomId(null)}
            onRefresh={refreshRooms}
            onToast={setToast}
            onPaymentsCollected={handlePaymentsCollected}
          />
        </Suspense>
      )}
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <MainShell />
    </AuthProvider>
  )
}

export default App
