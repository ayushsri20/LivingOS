import { useCallback, useEffect, useRef, useState } from 'react'
import './components.css'
import './App.css'
import { apiFetch } from './api/client'
import { formatDate, getRoomNumber, money, normalizeRoomStatus, statusColors } from './utils'
import { TopBar, LoadingShell, Toast, MetricCard, EmptyState, Modal, FieldGroup } from './components/shared'
import { AuthProvider, useAuth } from './context/AuthContext'
import RoomDrawer from './components/RoomDrawer'
import AssignResidentModal from './components/AssignResident'

/**
 * Single source of truth for each authenticated page's banner copy.
 * The H1 names the page; the eyebrow groups it in the product. No descriptive
 * paragraph is rendered — every page's real state is stated by its own figures,
 * and prose that restated the title added no information.
 */
const VIEW_META = {
  dashboard: {
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
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13 }}>
      <span style={{ color: '#5c564c', fontWeight: 700 }}>{label}</span>
      <strong style={{ fontFamily: 'var(--font-display)', fontSize: 15, color: tone }}>{value}</strong>
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
        <AssignResidentModal
          room={assignRoom}
          occupancy={occupancyMap[assignRoom.id]}
          onClose={() => setAssignRoom(null)}
          onRefresh={onRefresh}
          onToast={onToast}
          onResidentsChanged={onResidentsChanged}
        />
      )}
    </div>
  )
}

/**
 * Residents register backed by /api/guests/. The guests payload carries the room
 * it is attached to but not the building, so the room inventory snapshot (already
 * loaded by MainShell) supplies building and billing context per resident.
 */
function ResidentsView({ rooms, buildings, onOpenRoom, syncToken = 0 }) {
  const [guests, setGuests] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [selectedBuilding, setSelectedBuilding] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

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

                <span style={{ display: 'inline-flex', width: '100%', justifyContent: 'center', marginTop: 14, padding: '8px 14px', border: '2px solid var(--ink)', background: 'var(--paper)', fontWeight: 700, fontSize: 12, letterSpacing: '0.04em' }}>
                  {snapshot ? 'OPEN ROOM →' : 'NO ROOM ASSIGNED'}
                </span>
              </>
            )

            return snapshot ? (
              <button
                key={guest.id}
                type="button"
                className="room-card"
                onClick={() => onOpenRoom(snapshot)}
                style={{ textAlign: 'left', width: '100%' }}
                aria-label={`Open room ${getRoomNumber(snapshot)} for ${guest.full_name || 'resident'}`}
              >
                {card}
              </button>
            ) : (
              <article key={guest.id} className="room-card" style={{ cursor: 'default' }}>
                {card}
              </article>
            )
          })}
        </div>
      )}
    </div>
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
  const barWidth = (value) => `${Math.min(100, Math.max(0, value))}%`

  // Portfolio totals come straight from the metrics endpoint (authoritative);
  // fully-paid rooms is derived from the authoritative per-room snapshot.
  const fullyPaidRooms = summarizeRooms(rooms).fullyPaid

  return (
    <div className="dashboard-layout">
      <section>
        <div className="section-head" style={{ marginTop: 0 }}>
          <h2>Property Overview</h2>
          <span>Updated {formatUpdated(meta?.last_updated)}</span>
        </div>
        {/* Inventory only. The money figures live once, in Live Financial
            Summary below, so the same rupee is never shown under two names. */}
        <div className="metrics-grid">
          <MetricCard label="Buildings" value={roomsError ? '—' : buildings.length} />
          <MetricCard label="Total rooms" value={totalRooms ?? '—'} />
          <MetricCard label="Occupied" value={occupiedRooms ?? '—'} color="green" flash={flashOccupied} />
          <MetricCard label="Vacant" value={vacantRooms ?? '—'} color="yellow" flash={flashVacant} />
          <MetricCard label="Occupancy" value={`${occupancyRate.toFixed(1)}%`} flash={flashOccupancyRate} />
        </div>

        <div className="section-head">
          <h2>Live Financial Summary</h2>
          <span>Entire portfolio</span>
        </div>
        <div className="metrics-grid">
          <MetricCard label="Expected collection" value={money(metrics?.expected_yield ?? 0)} color="yellow" flash={flashExpected} />
          <MetricCard label="Total collected" value={money(metrics?.realized_revenue ?? 0)} color="green" flash={flashCollected} />
          <MetricCard label="Due" value={money(metrics?.accounts_receivable ?? 0)} color="red" flash={flashDue} />
          <MetricCard label="Fully paid rooms" value={roomsError ? '—' : fullyPaidRooms} />
        </div>
      </section>

      <div className="dashboard-grid">
        <div className="surface">
          <div className="section-head" style={{ marginTop: 0 }}>
            <h2>Collection Efficiency</h2>
            <span>Current month</span>
          </div>
          <div style={{ marginTop: 14, marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontWeight: 700, fontSize: 14, fontFamily: 'var(--font-display)' }}>
              <span>TARGET REALIZATION</span>
              <span>{collectionEfficiency.toFixed(1)}%</span>
            </div>
            <div className="progress-track">
              <div
                className="progress-fill green"
                style={{ '--bar-width': barWidth(collectionEfficiency) }}
              />
            </div>
          </div>
          {/* Expected yield and realized revenue are stated in Live Financial
              Summary above; repeating them here added nothing. */}
          <p style={{ margin: '14px 0 0', fontSize: 13, color: '#5c564c' }}>
            Collected against expected for the month.
          </p>
        </div>

        <div className="surface">
          <div className="section-head" style={{ marginTop: 0 }}>
            <h2>Occupancy</h2>
            <span>Live</span>
          </div>
          <div style={{ marginTop: 14, marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, fontWeight: 700, fontSize: 14, fontFamily: 'var(--font-display)' }}>
              <span>OCCUPANCY RATE</span>
              <span>{occupancyRate.toFixed(1)}%</span>
            </div>
            <div className="progress-track">
              <div
                className="progress-fill blue"
                style={{ '--bar-width': barWidth(occupancyRate) }}
              />
            </div>
          </div>
          {/* Room counts are stated in Property Overview above. */}
          <p style={{ margin: '14px 0 0', fontSize: 13, color: '#5c564c' }}>
            {occupiedRooms ?? '—'} of {totalRooms ?? '—'} rooms occupied.
          </p>
        </div>

        <div className="surface" style={{ gridColumn: '1 / -1' }}>
          <div className="section-head" style={{ marginTop: 0 }}>
            <h2>Building Directory</h2>
            <span>{roomsError ? 'Unavailable' : `${buildings.length} buildings`}</span>
          </div>
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
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12 }}>
              {buildings.map((building) => {
                // Per-building figures are aggregated from the same authoritative
                // per-room snapshot the metrics endpoint is built from, so no
                // building-level value is invented here.
                const summary = summarizeRooms(rooms.filter((room) => room.building === building.name))
                const totalRoomsInBuilding = building.rooms?.length ?? 0
                const vacant = totalRoomsInBuilding - summary.occupied

                return (
                  <button
                    key={building.name}
                    type="button"
                    className="building-card"
                    style={{ textAlign: 'left' }}
                    onClick={() => onOpenBuilding?.(building.name)}
                    aria-label={`Open rooms in building ${building.name}`}
                  >
                    <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', marginBottom: 4 }}>BUILDING</div>
                    <div style={{ fontSize: 24, fontFamily: 'var(--font-display)', fontWeight: 700 }}>{building.name}</div>
                    <div style={{ fontSize: 11, fontWeight: 700, marginTop: 4 }}>
                      {totalRoomsInBuilding} rooms · {summary.occupied} occupied · {vacant} vacant
                    </div>
                    <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 5, fontSize: 12 }}>
                      <StatRow label="Fully paid" value={summary.fullyPaid} />
                      <StatRow label="Expected" value={money(summary.expected)} />
                      <StatRow label="Collected" value={money(summary.collected)} tone="var(--green)" />
                      <StatRow label="Due" value={money(summary.due)} tone="var(--red)" />
                    </div>
                    <div style={{ marginTop: 10, fontSize: 11, fontWeight: 700, letterSpacing: '0.04em' }}>
                      VIEW ROOMS →
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        </div>
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
    <Modal title="RECORD EXPENSE" onClose={saving ? undefined : onClose}>
      <form onSubmit={handleSubmit} aria-busy={saving} noValidate>
        {error && (
          <div className="error-state" style={{ marginBottom: 14 }}><span>{error}</span></div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
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
            <input type="number" min="0" step="0.01" className="field-input" value={form.amount} onChange={update('amount')} disabled={saving} />
          </FieldGroup>
          <FieldGroup label="Date">
            <input type="date" className="field-input" value={form.date} onChange={update('date')} disabled={saving} />
          </FieldGroup>
        </div>

        <FieldGroup label="Description">
          <input type="text" className="field-input" value={form.description} onChange={update('description')} disabled={saving} placeholder="What was this expense for?" />
        </FieldGroup>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 700, marginTop: 4 }}>
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
    <div className="login-shell">
      <div className="login-panel">
          <div className="eyebrow">Panesar Living OS</div>
          <h1>SECURE<br />ACCESS.</h1>

          {visibleError && (
            <div id="login-error">
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
              className="retry-button"
              onClick={handleRetry}
              disabled={retrying}
              style={{ width: '100%', marginBottom: 14 }}
            >
              {retrying ? 'Reconnecting…' : 'Retry connection'}
            </button>
          )}

          <form onSubmit={handleSubmit} className="login-form" aria-busy={loading} noValidate>
            <div className="field-group">
              <label htmlFor="login-username">Username</label>
              <input
                id="login-username"
                name="username"
                className="field-input"
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

            <div className="field-group">
              <label htmlFor="login-password">Password</label>
              <input
                id="login-password"
                name="password"
                type="password"
                className="field-input"
                value={form.password}
                onChange={handleChange('password')}
                autoComplete="current-password"
                required
                disabled={loading}
                aria-invalid={visibleError ? 'true' : undefined}
                aria-describedby={visibleError ? 'login-error' : undefined}
              />
            </div>

            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? 'Authenticating…' : 'Sign In'}
            </button>
        </form>
      </div>
    </div>
  )
}

function MainShell() {
  const { authState } = useAuth()
  const [currentView, setCurrentView] = useState('dashboard')
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
  if (authState === 'unauthenticated' || authState === 'error') return <LoginShell />

  const activeView = VIEW_META[currentView] || VIEW_META.dashboard
  const selectedRoom = selectedRoomId === null ? null : rooms.find((room) => room.id === selectedRoomId) || null

  return (
    <div className="page-shell">
      <TopBar currentView={currentView} onViewChange={setCurrentView} />

      <main className="content-wrap" key={currentView}>
        <div className="page-banner">
          <div>
            {activeView.eyebrow && <span className="eyebrow">{activeView.eyebrow}</span>}
            <h1>{activeView.title}</h1>
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
            onOpenRoom={openRoom}
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
        <div style={{ position: 'fixed', left: 24, bottom: 24, zIndex: 200, maxWidth: 380 }}>
          <Toast type={toast.type} message={toast.message} onClose={() => setToast(null)} />
        </div>
      )}

      {selectedRoom && (
        <RoomDrawer
          key={selectedRoom.id}
          room={selectedRoom}
          onClose={() => setSelectedRoomId(null)}
          onRefresh={refreshRooms}
          onToast={setToast}
          onPaymentsCollected={handlePaymentsCollected}
        />
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
