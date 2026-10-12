import { cloneElement, useCallback, useEffect, useId, useRef, useState } from 'react'
import '../components.css'
import { logout } from '../api/client'
import PanesarHeaderArt from './PanesarHeaderArt'

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'rooms', label: 'Rooms' },
  { id: 'residents', label: 'Residents' },
  { id: 'electricity', label: 'Electricity' },
  { id: 'payments', label: 'Payments' },
  { id: 'expenses', label: 'Expenses' },
  { id: 'analytics', label: 'Analytics' },
]

/**
 * The phone layout replaces the seven-item desktop strip rather than
 * squeezing it: three primary destinations on a fixed bottom bar and the
 * rest behind a MORE disclosure. Same `onViewChange` ids, same routes —
 * only the presentation differs.
 */
const MOBILE_PRIMARY = [
  { id: 'dashboard', label: 'Home' },
  { id: 'rooms', label: 'Rooms' },
  { id: 'payments', label: 'Payments' },
]

const MOBILE_MORE = [
  { id: 'residents', label: 'Residents' },
  { id: 'electricity', label: 'Electricity' },
  { id: 'expenses', label: 'Expenses' },
  { id: 'analytics', label: 'Analytics' },
]

export function TopBar({ showNav = true, currentView, onViewChange }) {
  const [loggingOut, setLoggingOut] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const activeRef = useRef(null)
  const moreRef = useRef(null)
  const moreToggleRef = useRef(null)

  async function handleLogout() {
    if (loggingOut) return
    setLoggingOut(true)
    try {
      await logout()
      window.location.href = '/'
    } catch {
      // Never strand the user on a dead button: allow another attempt.
      setLoggingOut(false)
    }
  }

  // The MORE disclosure dismisses on Escape and on an outside press, so it can
  // never cover content with no way back. The toggle itself is excluded: without
  // that, pointerdown closes the sheet and the subsequent click re-opens it,
  // making the tab look dead while the menu stayed visible. Resets live in the
  // event handlers.
  useEffect(() => {
    if (!moreOpen) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setMoreOpen(false)
    }
    const onPointerDown = (event) => {
      if (!moreRef.current) return
      const insideMenu = moreRef.current.contains(event.target)
      const onToggle = moreToggleRef.current && moreToggleRef.current.contains(event.target)
      if (!insideMenu && !onToggle) setMoreOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [moreOpen])

  // Where the desktop nav is still shown (tablet widths) it is one horizontally
  // scrollable row, so the current section can start off-screen. Bring it into
  // view after a change so "where am I?" is answered without a hunt.
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest', inline: 'center' })
  }, [currentView])

  /** Navigate and dismiss any open disclosure in the same event. */
  const go = (id) => {
    setMoreOpen(false)
    onViewChange?.(id)
  }

  const moreItemsOpen = MOBILE_MORE.some(({ id }) => id === currentView)

  return (
    <>
      <header className="topbar panesar-topbar">
        {/* Phase 1: Panesar Living banner. Mount = full reveal; currentView
            changes = short reveal. Everything below is untouched. */}
        <PanesarHeaderArt currentView={currentView} />

        <div className="panesar-bar">
          {showNav && (
            <nav className="top-nav" aria-label="Main sections">
              <ul className="top-nav-list">
                {NAV_ITEMS.map(({ id, label }) => {
                  const isCurrent = currentView === id
                  return (
                    <li key={id} className="top-nav-item">
                      <button
                        type="button"
                        ref={isCurrent ? activeRef : null}
                        className={`nav-link${isCurrent ? ' active' : ''}`}
                        aria-current={isCurrent ? 'page' : undefined}
                        onClick={() => onViewChange?.(id)}
                      >
                        {label}
                      </button>
                    </li>
                  )
                })}
              </ul>
              <button
                type="button"
                className="ghost-button btn-danger top-nav-logout"
                onClick={handleLogout}
                disabled={loggingOut}
              >
                {loggingOut ? 'Signing out…' : 'Logout'}
              </button>
            </nav>
          )}
        </div>
      </header>

      {/* Fixed bottom bar for phones and portrait tablets. Deliberately outside
          the sticky header: it keeps its own stacking level, so the room drawer
          and its backdrop still open above it. */}
      {showNav && (
        <>
          <nav className="mobile-tabbar" aria-label="Primary sections">
            {MOBILE_PRIMARY.map(({ id, label }) => {
              const isCurrent = currentView === id
              return (
                <button
                  key={id}
                  type="button"
                  className={`mobile-tab${isCurrent ? ' is-active' : ''}`}
                  aria-current={isCurrent ? 'page' : undefined}
                  onClick={() => go(id)}
                >
                  {label}
                </button>
              )
            })}
            <button
              type="button"
              ref={moreToggleRef}
              className={`mobile-tab${moreItemsOpen ? ' is-active' : ''}`}
              aria-expanded={moreOpen}
              aria-controls="more-menu"
              onClick={() => setMoreOpen((open) => !open)}
            >
              More
            </button>
          </nav>

          {moreOpen && (
            <div className="more-menu" id="more-menu" ref={moreRef}>
              {MOBILE_MORE.map(({ id, label }) => (
                <button
                  key={id}
                  type="button"
                  className={currentView === id ? 'is-active' : undefined}
                  aria-current={currentView === id ? 'page' : undefined}
                  onClick={() => go(id)}
                >
                  {label}
                </button>
              ))}
              <hr />
              <button
                type="button"
                className="more-logout"
                onClick={handleLogout}
                disabled={loggingOut}
              >
                {loggingOut ? 'Signing out…' : 'Logout'}
              </button>
            </div>
          )}
        </>
      )}
    </>
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
  const dialogRef = useRef(null)
  const closeTimer = useRef(null)
  const previousFocusRef = useRef(null)
  const hasFocusedRef = useRef(false)
  const closedRef = useRef(false)

  // Plays the exit transition before the parent unmounts the modal, so closing
  // does not snap away. Guarded so backdrop + Escape + button cannot fire the
  // parent callback twice (no double-submit, no double-toast).
  const requestClose = useCallback(() => {
    if (!onClose || closing || closedRef.current) return
    closedRef.current = true
    setClosing(true)
    closeTimer.current = setTimeout(onClose, 180)
  }, [onClose, closing])

  // Escape closes the dialog, matching the room drawer. Registered on the window
  // so it works no matter which element currently holds focus inside the modal.
  useEffect(() => {
    if (!onClose) return undefined
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !closing) {
        event.preventDefault()
        requestClose()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose, closing, requestClose])

  // Focus management: remember the previously focused element and restore it
  // after closing. Focus the dialog once on open (not on every close-flag
  // flip) so keyboard users land in a predictable place inside the panel.
  useEffect(() => {
    if (!onClose || closing || hasFocusedRef.current) return undefined
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
    previousFocusRef.current = previousFocus
    dialogRef.current?.focus()
    hasFocusedRef.current = true
    return () => {
      if (previousFocusRef.current instanceof HTMLElement) {
        previousFocusRef.current.focus()
      }
    }
  }, [onClose, closing])

  // Prevent background scrolling while the modal is open. Both axes are
  // restored (not hard-coded to ''), so a mid-scroll page does not jump.
  useEffect(() => {
    if (!onClose) return undefined
    const previousOverflow = document.body.style.overflow
    const previousOverscroll = document.documentElement.style.overscrollBehavior
    document.body.style.overflow = 'hidden'
    document.documentElement.style.overscrollBehavior = 'none'
    return () => {
      document.body.style.overflow = previousOverflow
      document.documentElement.style.overscrollBehavior = previousOverscroll
    }
  }, [onClose])

  // Clean up the close timer on unmount to prevent onClose firing twice.
  useEffect(() => () => clearTimeout(closeTimer.current), [])

  return (
    <div
      className={`modal-overlay${closing ? ' closing' : ''}`}
      onClick={(e) => {
        // Clicks inside the panel (buttons, inputs, labels) must never bubble
        // into a backdrop dismissal — only the overlay itself closes.
        if (e.target === e.currentTarget && !closing) {
          requestClose()
        }
      }}
      aria-hidden={closing}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className={`modal-box${closing ? ' closing' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="modal-header">
          <h2 id="modal-title">{title}</h2>
          <button
            type="button"
            className="modal-close"
            onClick={requestClose}
            aria-label={`Close ${title} dialog`}
          >
            ×
          </button>
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
 *
 * `className` is an optional extra modifier (e.g. `metric-card--money`) for
 * typographic hierarchy. It is appended, so it can never displace the base
 * class, the colour variant or the flash state.
 */
export function MetricCard({ label, value, color, flash, className = '' }) {
  const modifier = className ? ` ${className}` : ''
  return (
    <div className={`metric-card${modifier}${color ? ` ${color}` : ''}${flash ? ' flash' : ''}`}>
      <span>{label}</span>
      <strong>{value ?? '—'}</strong>
    </div>
  )
}
