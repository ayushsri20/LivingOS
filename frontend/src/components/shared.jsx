import { cloneElement, useEffect, useId, useState } from 'react'
import '../components.css'
import { logout } from '../api/client'

export function TopBar({ showNav = true, currentView, onViewChange }) {
  async function handleLogout() {
    await logout()
    window.location.href = '/'
  }

  const navItems = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'rooms', label: 'Rooms' },
    { id: 'residents', label: 'Residents' },
    { id: 'electricity', label: 'Electricity' },
    { id: 'payments', label: 'Payments' },
    { id: 'expenses', label: 'Expenses' },
    { id: 'analytics', label: 'Analytics' },
  ]

  return (
    <header className="topbar">
      <div className="brand-wrap">
        <a href="#" onClick={(e) => { e.preventDefault(); onViewChange?.('dashboard'); }} style={{ textDecoration: 'none', color: 'inherit' }}>
          <div className="brand-mark">P</div>
        </a>
        <div>
          <div className="brand-name">Panesar / Rental OS</div>
          <div className="brand-subtitle">Room-first operations</div>
        </div>
      </div>

      {showNav && (
        <nav style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {navItems.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => onViewChange?.(id)}
              className={`nav-link ${currentView === id ? 'active' : ''}`}
            >
              {label}
            </button>
          ))}
          <button type="button" className="ghost-button btn-danger" onClick={handleLogout}>
            Logout
          </button>
        </nav>
      )}
    </header>
  )
}

export function Toast({ message, type = 'success', onClose }) {
  if (!message) return null
  return (
    <div className={`toast ${type}`} role="alert">
      {message}
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          style={{ marginLeft: 10, background: 'none', border: 'none', cursor: 'pointer', fontWeight: 700 }}
        >
          ×
        </button>
      )}
    </div>
  )
}

export function LoadingShell({ label = 'Loading…' }) {
  return <div className="loading-shell" role="status">{label}</div>
}

export function EmptyState({ message = 'No data found.' }) {
  return <div className="empty-state">{message}</div>
}

export function Modal({ title, onClose, children, footer }) {
  const [closing, setClosing] = useState(false)

  // Escape closes the dialog, matching the room drawer. Registered on the window
  // so it works no matter which element currently holds focus inside the modal.
  useEffect(() => {
    if (!onClose) return undefined
    const onKeyDown = (event) => { if (event.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  // Plays the exit transition before the parent unmounts the modal, so closing
  // does not snap away. If onClose is withheld (while submitting) nothing closes.
  const requestClose = () => {
    if (!onClose) return
    setClosing(true)
    setTimeout(onClose, 150)
  }

  return (
    <div
      className={`modal-overlay${closing ? ' closing' : ''}`}
      onClick={(e) => e.target === e.currentTarget && requestClose()}
    >
      <div
        className={`modal-box${closing ? ' closing' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-header">
          <h2>{title}</h2>
          <button type="button" className="modal-close" onClick={requestClose} aria-label="Close">×</button>
        </div>
        {children}
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  )
}

/**
 * Label + control with a real programmatic association. The generated id is
 * applied to the control so clicking the label focuses it and screen readers
 * announce the field name; a control that already declares its own id keeps it.
 */
export function FieldGroup({ label, children }) {
  const generatedId = useId()
  const child = Array.isArray(children) ? children[0] : children
  const isElement = child && typeof child === 'object' && 'props' in child
  const controlId = isElement ? child.props.id || generatedId : undefined

  return (
    <div className="field-group">
      <label htmlFor={controlId}>{label}</label>
      {isElement && controlId !== child.props.id
        ? cloneElement(child, { id: controlId })
        : children}
    </div>
  )
}

/**
 * `flash` is set by useValueFlash when the figure changes, so a refreshed total
 * is visibly updated. The value itself always comes from the caller (the
 * backend response) — this component never computes money.
 */
export function MetricCard({ label, value, color, flash }) {
  return (
    <div className={`metric-card${color ? ` ${color}` : ''}${flash ? ' flash' : ''}`}>
      <span>{label}</span>
      <strong>{value ?? '—'}</strong>
    </div>
  )
}
