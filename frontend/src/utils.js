/** Format a number as Indian Rupee currency */
export function money(value) {
  const amount = Number(value ?? 0)
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(amount)
}

/**
 * The room-centric APIs (`_get_room_billing_snapshot` in rental/views.py) return the
 * room number under the `room` key, not `number`. Older/nested payloads may still use
 * `number`, so prefer the authoritative key and fall back. Single source of truth for
 * room-number mapping — do not duplicate this logic at call sites.
 */
export function getRoomNumber(room) {
  if (!room) return '—'
  return room.room ?? room.number ?? '—'
}

/** Normalize room payment/occupancy status */
export function normalizeRoomStatus(room) {
  if (!room) return 'VACANT'
  if (!room.resident || room.resident === 'No resident') return 'VACANT'
  const status = (room.payment_status || room.status || '').toString().toUpperCase()
  if (['PAID', 'PARTIAL', 'DUE', 'VACANT'].includes(status)) return status
  return 'DUE'
}

/** Map status string to CSS class name */
export const statusColors = {
  PAID: 'paid',
  PARTIAL: 'partial',
  DUE: 'due',
  VACANT: 'vacant',
}

/** Format a date string for display */
export function formatDate(dateStr) {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  if (isNaN(d)) return dateStr
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

/** Today's date formatted */
export function todayFormatted() {
  return new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}
