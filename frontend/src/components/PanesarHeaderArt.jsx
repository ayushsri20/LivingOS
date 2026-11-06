import { useEffect, useRef, useState } from 'react'
import '../panesar-header.css'

/* Baseline brand header: graphite layer, gold architectural P, one
   continuous PANESAR -> LIVING reveal plus a single liquid-gloss sweep.
   React owns ONLY the full lifecycle; CSS draws. */
const FULL_MS = 1800

const PANESAR = 'PANESAR'.split('')
const LIVING = 'LIVING'.split('')

/**
 * The Panesar Living brand lockup inside the existing topbar.
 * The full entrance animation plays once on mount; section navigation
 * never replays any logo animation.
 */
export default function PanesarHeaderArt() {
  const [mode, setMode] = useState('full') // 'full' | 'settled'
  const timer = useRef(null)

  // Fresh authenticated entry (mount): full entrance once, then settle.
  // The cleanup clears the timer on unmount so nothing fires late.
  useEffect(() => {
    timer.current = setTimeout(() => setMode('settled'), FULL_MS)
    return () => {
      if (timer.current) clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  return (
    <div className="plb" data-mode={mode}>
      <div className="plb-lockup" aria-label="Panesar Living">
        <span className="plb-mark" aria-hidden="true">
          <svg viewBox="0 0 64 64" fill="none" focusable="false">
            <defs>
              <clipPath id="plb-mark-ink-clip">
                <path d="M17 51V13H34C45 13 51 19 51 28C51 37 44 42 34 42H25Z M24 22H34C38 22 41 24 41 28C41 32 38 34 34 34H24Z" fillRule="evenodd" clipRule="evenodd" />
              </clipPath>
              <linearGradient id="plb-mark-gold" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="var(--brand-gold-bright)" />
                <stop offset="50%" stopColor="var(--brand-gold)" />
                <stop offset="100%" stopColor="var(--brand-gold-soft)" />
              </linearGradient>
            </defs>
            <path
              className="plb-liquid"
              d="M17 51V13H34C45 13 51 19 51 28C51 37 44 42 34 42H25ZM24 22H34C38 22 41 24 41 28C41 32 38 34 34 34H24Z"
              fill="url(#plb-mark-gold)"
              clipPath="url(#plb-mark-ink-clip)"
              aria-hidden="true"
            />
            <path
              className="plb-mark-stroke"
              d="M17 51V13H34C45 13 51 19 51 28C51 37 44 42 34 42H25"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              className="plb-mark-inner"
              d="M24 22H34C38 22 41 24 41 28C41 32 38 34 34 34H24"
              strokeLinecap="round"
            />
          </svg>
        </span>
        <span className="plb-wordmark" aria-hidden="true">
          <span className="plb-word plb-word--panesar">
            {PANESAR.map((letter, index) => (
              <span key={index} className="plb-letter" style={{ '--i': index }}>
                {letter}
              </span>
            ))}
          </span>
          <span className="plb-gap" />
          <span className="plb-word plb-word--living">
            {LIVING.map((letter, index) => (
              <span
                key={index}
                className="plb-letter"
                style={{ '--i': PANESAR.length + index }}
              >
                {letter}
              </span>
            ))}
          </span>
        </span>
        <span className="plb-sr">PANESAR LIVING</span>
      </div>
      <span className="plb-gloss" aria-hidden="true" />
    </div>
  )
}
