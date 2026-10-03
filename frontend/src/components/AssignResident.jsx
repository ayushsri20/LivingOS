import { useState } from 'react'
import { apiFetch } from '../api/client'
import { getRoomNumber } from '../utils'
import { FieldGroup, Modal } from './shared'

/** Personal fields supported by POST /api/guest/add/ — nothing invented. */
function blankResident() {
  return {
    first_name: '',
    last_name: '',
    phone: '',
    email: '',
    gender: 'M',
    date_of_birth: '',
    college_id: '',
    student_college: '',
    id_type: '',
    id_number: '',
  }
}

/** One resident's personal section. Room-level tenancy fields live outside it. */
function ResidentFields({ label, resident, disabled, onChange }) {
  const field = (key) => ({
    value: resident[key],
    onChange: (event) => onChange(key, event.target.value),
    disabled,
    className: 'field-input',
  })

  return (
    <fieldset
      disabled={disabled}
      style={{ border: '2px solid var(--ink)', background: 'var(--paper)', padding: '6px 16px 16px', margin: '0 0 16px' }}
    >
      <legend style={{ fontWeight: 700, fontSize: 12, letterSpacing: '0.05em', padding: '0 8px' }}>{label}</legend>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12, paddingTop: 10 }}>
        <FieldGroup label="First name *"><input type="text" {...field('first_name')} /></FieldGroup>
        <FieldGroup label="Last name *"><input type="text" {...field('last_name')} /></FieldGroup>
        <FieldGroup label="Phone"><input type="tel" {...field('phone')} /></FieldGroup>
        <FieldGroup label="Email"><input type="email" {...field('email')} /></FieldGroup>
        <FieldGroup label="Gender">
          <select {...field('gender')}>
            <option value="M">Male</option>
            <option value="F">Female</option>
            <option value="O">Other</option>
          </select>
        </FieldGroup>
        <FieldGroup label="Date of birth"><input type="date" {...field('date_of_birth')} /></FieldGroup>
        <FieldGroup label="College / student ID"><input type="text" {...field('college_id')} /></FieldGroup>
        <FieldGroup label="College name"><input type="text" {...field('student_college')} /></FieldGroup>
        <FieldGroup label="ID type"><input type="text" {...field('id_type')} /></FieldGroup>
        <FieldGroup label="ID number"><input type="text" {...field('id_number')} /></FieldGroup>
      </div>
    </fieldset>
  )
}

/**
 * Room-scoped 1/2 resident assignment on the verified backend contract:
 * POST /api/guest/add/ (form-encoded fields). The selected room is fixed
 * context, occupancy is backend-authoritative, and the financial structure
 * stays room-level: ONE agreed rent, ONE bill, ONE payment history per room —
 * residents are only personal records pointing at the same room.
 */
export default function AssignResidentModal({ room, occupancy, onClose, onRefresh, onToast, onResidentsChanged }) {
  const roomNumber = getRoomNumber(room)
  const safeOccupancy = Number.isFinite(occupancy) ? occupancy : 0
  // "ADD RESIDENT" on a 1/2 room goes straight to the single missing resident.
  const startsWithForm = safeOccupancy === 1
  const [people, setPeople] = useState(startsWithForm ? 1 : 0) // 0 = occupancy question step
  const [residents, setResidents] = useState(() => (startsWithForm ? [blankResident()] : []))
  const [agreedRent, setAgreedRent] = useState('')
  const [checkIn, setCheckIn] = useState('')
  const [checkOut, setCheckOut] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [createdCount, setCreatedCount] = useState(0)

  const updateResident = (index, key, value) => {
    setResidents((current) => current.map((item, i) => (i === index ? { ...item, [key]: value } : item)))
  }

  const choosePeople = (count) => {
    if (safeOccupancy + count > 2) {
      setError('This room cannot hold more than 2 residents.')
      return
    }
    setError('')
    setPeople(count)
    setResidents(count === 2 ? [blankResident(), blankResident()] : [blankResident()])
  }

  const resetToQuestion = () => {
    if (createdCount > 0 || startsWithForm) return
    setPeople(0)
    setResidents([])
    setError('')
  }

  const residentLabel = (index) => {
    if (createdCount > index) return `Resident ${index + 1} — created`
    if (residents.length === 1) return startsWithForm ? 'Resident 2 (joins the existing resident)' : 'Resident 1'
    return `Resident ${index + 1}`
  }

  const pending = residents.slice(createdCount)
  const occupancyPreference = people === 2 || startsWithForm ? 'double' : 'single'

  // Only ever POSTs to the verified endpoint; agreed rent rides on Resident 1's
  // request only, because it is a single room-level value.
  async function postResident(index) {
    const form = new FormData()
    Object.entries(residents[index]).forEach(([key, value]) => {
      const trimmed = String(value ?? '').trim()
      if (trimmed) form.append(key, trimmed)
    })
    form.append('room_id', String(room.id))
    form.append('occupancy_preference', occupancyPreference)
    if (index === 0 && agreedRent.trim()) form.append('agreed_rent', agreedRent.trim())
    if (checkIn) form.append('check_in_date', checkIn)
    if (checkOut) form.append('check_out_date', checkOut)
    await apiFetch('/api/guest/add/', { method: 'POST', body: form })
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (submitting || people === 0) return
    setError('')

    if (pending.some((item) => !item.first_name.trim() || !item.last_name.trim())) {
      setError('First and last name are required for every resident.')
      return
    }
    if (safeOccupancy + pending.length > 2) {
      setError('This room is already full (capacity 2).')
      return
    }

    setSubmitting(true)
    let made = 0
    try {
      for (let index = createdCount; index < residents.length; index += 1) {
        await postResident(index)
        made += 1
        setCreatedCount(index + 1)
      }
      onResidentsChanged?.()
      try {
        await onRefresh()
      } catch {
        onToast?.({ type: 'error', message: 'Residents saved, but rooms could not be reloaded.' })
        onClose?.()
        return
      }
      onToast?.({
        type: 'success',
        message: residents.length === 2
          ? `2 residents assigned to Room ${roomNumber}.`
          : `Resident assigned to Room ${roomNumber}.`,
      })
      onClose?.()
    } catch (err) {
      const totalCreated = createdCount + made
      const partial = totalCreated > 0 && totalCreated < residents.length
      const message = err.message || 'Unable to add the resident.'
      onResidentsChanged?.()
      try {
        await onRefresh()
      } catch {
        // The room list may briefly lag; the message below is still accurate.
      }
      if (partial) {
        setError(`${message} Resident 1 is saved, but Resident 2 was NOT created — Room ${roomNumber} is ${safeOccupancy + made}/2. Retry to add only the missing resident.`)
        onToast?.({ type: 'error', message: `Room ${roomNumber} is only partially assigned (${safeOccupancy + made}/2).` })
      } else {
        setError(message)
        onToast?.({ type: 'error', message })
      }
    } finally {
      setSubmitting(false)
    }
  }

  const showBack = people > 0 && createdCount === 0 && !startsWithForm

  return (
    <Modal
      title={`ASSIGN RESIDENT · ROOM ${roomNumber}`}
      onClose={submitting ? undefined : onClose}
    >
      {/* Fixed room context — the room cannot be changed inside this flow. */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10, padding: '14px 16px', border: '3px solid var(--ink)', background: 'var(--yellow)', boxShadow: '4px 4px 0 var(--ink)', marginBottom: 18 }}>
        <div>
          <span className="eyebrow" style={{ display: 'block', color: 'var(--ink)' }}>BUILDING</span>
          <strong style={{ fontFamily: 'var(--font-display)', fontSize: 18 }}>{room.building || '—'}</strong>
        </div>
        <div>
          <span className="eyebrow" style={{ display: 'block', color: 'var(--ink)' }}>ROOM</span>
          <strong style={{ fontFamily: 'var(--font-display)', fontSize: 18 }}>{roomNumber}</strong>
        </div>
        <div>
          <span className="eyebrow" style={{ display: 'block', color: 'var(--ink)' }}>OCCUPANCY</span>
          <strong style={{ fontFamily: 'var(--font-display)', fontSize: 18 }}>{safeOccupancy}/2</strong>
        </div>
      </div>

      {people === 0 ? (
        <div>
          <h3 style={{ margin: '0 0 6px', fontFamily: 'var(--font-display)', fontSize: 20 }}>How many people will occupy this room?</h3>
          <p style={{ margin: '0 0 16px', fontSize: 13, color: '#5c564c' }}>
            Capacity 2. This room cannot be changed.
          </p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <button type="button" className="btn-primary" style={{ flex: 1, minHeight: 44, justifyContent: 'center' }} onClick={() => choosePeople(1)}>1 PERSON</button>
            <button type="button" className="btn-primary" style={{ flex: 1, minHeight: 44, justifyContent: 'center' }} onClick={() => choosePeople(2)}>2 PEOPLE</button>
          </div>
          <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
            <button type="button" className="ghost-button" onClick={() => onClose?.()}>Cancel</button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleSubmit} aria-busy={submitting}>
          {startsWithForm && (
            <p style={{ margin: '0 0 14px', fontSize: 13, color: '#5c564c' }}>
              This room already has 1 resident. This form adds <strong>Resident 2 only</strong> — the existing
              resident is never modified.
            </p>
          )}

          {residents.map((resident, index) => (
            <ResidentFields
              key={index}
              label={residentLabel(index)}
              resident={resident}
              disabled={submitting || index < createdCount}
              onChange={(key, value) => updateResident(index, key, value)}
            />
          ))}

          <fieldset style={{ border: '2px dashed var(--ink)', padding: '6px 16px 14px', margin: '0 0 16px', background: 'var(--paper)' }}>
            <legend style={{ fontWeight: 700, fontSize: 12, letterSpacing: '0.05em', padding: '0 8px' }}>
              ROOM TENANCY — applies to the whole room
            </legend>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12, paddingTop: 10 }}>
              <FieldGroup label="Agreed rent (room-level)">
                <input
                  type="number"
                  min="0"
                  className="field-input"
                  value={agreedRent}
                  placeholder="Optional"
                  disabled={submitting || createdCount > 0}
                  onChange={(event) => setAgreedRent(event.target.value)}
                />
              </FieldGroup>
              <FieldGroup label="Check-in date">
                <input type="date" className="field-input" value={checkIn} disabled={submitting} onChange={(event) => setCheckIn(event.target.value)} />
              </FieldGroup>
              <FieldGroup label="Check-out date">
                <input type="date" className="field-input" value={checkOut} disabled={submitting} onChange={(event) => setCheckOut(event.target.value)} />
              </FieldGroup>
            </div>
            <p style={{ margin: '12px 0 0', fontSize: 12, color: '#5c564c' }}>
              Rent, electricity and payment history are held once per room and shared by both residents.
            </p>
          </fieldset>

          {error && (
            <div className="error-state" role="alert" style={{ marginBottom: 14 }}>
              <span>{error}</span>
            </div>
          )}

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            {showBack && (
              <button type="button" className="ghost-button" disabled={submitting} onClick={resetToQuestion}>Back</button>
            )}
            <button type="button" className="ghost-button" disabled={submitting} onClick={() => onClose?.()}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={submitting || safeOccupancy >= 2}>
              {submitting
                ? 'Saving…'
                : createdCount > 0
                  ? 'Retry remaining resident'
                  : residents.length === 2
                    ? 'Assign 2 residents'
                    : 'Assign resident'}
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}
