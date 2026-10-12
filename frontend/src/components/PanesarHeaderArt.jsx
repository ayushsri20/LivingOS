import { useEffect, useRef, useState } from 'react'
import '../panesar-header.css'

/* Fresh authenticated entry: full architectural construction (~2.1s, then static).
   Section change: a short settle sweep only (~650ms). */
const FULL_MS = 2100
const SHORT_MS = 650

/**
 * The Panesar Living banner inside the existing topbar.
 * Receives currentView purely to detect real section changes — re-renders,
 * API responses, drawers/modals etc. never touch it, so they never animate.
 * React owns ONLY the full | short | settled lifecycle; all drawing,
 * sliding and settling lives in CSS/SVG (viewBox 0 0 1800 360, no JS geometry).
 */
export default function PanesarHeaderArt({ currentView }) {
  const [mode, setMode] = useState('full') // 'full' | 'short' | 'settled'
  const lastView = useRef(currentView)
  const timer = useRef(null)

  // Fresh authenticated entry (mount): play the construction once.
  // Initial state is already 'full' — only schedule the settle.
  useEffect(() => {
    timer.current = setTimeout(() => setMode('settled'), FULL_MS)
    return () => clearTimeout(timer.current)
  }, [])

  // Actual section change: one short reveal, no full replay. Comparing the
  // value (not a first-run flag) keeps effect re-runs from faking a change.
  useEffect(() => {
    if (lastView.current === currentView) return undefined
    lastView.current = currentView
    clearTimeout(timer.current)
    setMode('short')
    timer.current = setTimeout(() => setMode('settled'), SHORT_MS)
    return () => clearTimeout(timer.current)
  }, [currentView])

  return (
    <div className="plh" data-mode={mode}>
      <div className="plh-canvas">
        {/* Single stage: artwork + temporary construction layer slide and
            settle together into the final position. */}
        <div className="plh-stage">
          <img
            className="plh-art"
            src="/branding/plh-final.webp"
            alt="Panesar Living — Property Operations"
          />
          {/* Temporary architectural construction layer. The viewBox IS the
              artwork coordinate system and `slice` maps it exactly like
              object-fit: cover, so the drawing registers with the artwork at
              every size. Opacity is 0 outside the full sequence, so the
              settled header is the unchanged approved artwork. */}
          <svg
            className="plh-sketch"
            viewBox="0 0 1800 360"
            preserveAspectRatio="xMidYMid slice"
            aria-hidden="true"
            focusable="false"
          >
            {/* 0.10s — faint drafting rules: blueprint atmosphere */}
            <g className="sk sk-rules">
              <path d="M 90 70 H 1710" pathLength="1" />
              <path d="M 1710 352 H 90" pathLength="1" />
            </g>
            {/* LEFT skyline: silhouette + structural verticals, drawn from
                the outer edge toward the central composition */}
            <g className="sk sk-build sk-lp">
              <path
                d="M 16 336 V 176 H 64 V 220 H 116 V 252 H 180 V 284 H 252 V 336 Z"
                pathLength="1"
              />
              <path d="M 64 176 V 336 M 116 220 V 336 M 180 252 V 336" pathLength="1" />
            </g>
            {/* RIGHT skyline: mirrored, drawn from the outer edge inward */}
            <g className="sk sk-build sk-rp">
              <path
                d="M 1784 336 V 176 H 1736 V 220 H 1684 V 252 H 1636 V 284 H 1596 V 336 Z"
                pathLength="1"
              />
              <path d="M 1736 176 V 336 M 1684 220 V 336 M 1636 252 V 336" pathLength="1" />
            </g>

            {/* LEFT detail: windows + balcony rails */}
            <g className="sk sk-build sk-ld">
              <path
                d="M 26 196 h12 v15 h-12 Z M 44 196 h12 v15 h-12 Z M 26 226 h12 v15 h-12 Z M 44 226 h12 v15 h-12 Z M 76 240 h12 v15 h-12 Z M 94 240 h12 v15 h-12 Z M 128 272 h13 v16 h-13 Z M 150 272 h13 v16 h-13 Z M 192 302 h13 v16 h-13 Z M 214 302 h13 v16 h-13 Z"
                pathLength="1"
              />
              <path d="M 70 288 H 110 M 70 296 H 110 M 124 314 H 172 M 124 322 H 172" pathLength="1" />
            </g>
            {/* RIGHT detail: windows + balcony rails */}
            <g className="sk sk-build sk-rd">
              <path
                d="M 1744 196 h12 v15 h-12 Z M 1762 196 h12 v15 h-12 Z M 1744 226 h12 v15 h-12 Z M 1762 226 h12 v15 h-12 Z M 1694 240 h12 v15 h-12 Z M 1712 240 h12 v15 h-12 Z M 1644 272 h12 v15 h-12 Z M 1662 272 h12 v15 h-12 Z M 1602 302 h11 v15 h-11 Z M 1618 302 h11 v15 h-11 Z"
                pathLength="1"
              />
              <path d="M 1690 288 H 1730 M 1690 296 H 1730 M 1642 314 H 1678 M 1642 322 H 1678" pathLength="1" />
            </g>

            {/* PENCIL P: stem → bowl → house detail → ghost line → frame.
                Occupies the same frame the artwork's P sits in (301–560). */}
            <g className="sk sk-p">
              <path className="p-stem" d="M 395 100 V 330" pathLength="1" />
              <path
                className="p-bowl"
                d="M 395 100 C 470 98 524 128 524 176 C 524 224 476 254 424 258 C 414 259 404 258 395 256"
                pathLength="1"
              />
              <path
                className="p-house"
                d="M 430 200 L 462 172 L 494 200 M 438 196 V 232 H 486 V 196 M 456 206 h12 v10 h-12 Z"
                pathLength="1"
              />
              <path className="p-ghost" d="M 397 106 C 473 104 529 132 528 179" pathLength="1" />
              <path className="p-frame" d="M 301 345 V 57 H 560 V 345 Z" pathLength="1" />
            </g>
            {/* GOLD FINISH: frame turns gold; descriptor rules light up where
                the artwork's own gold rules sit, for a seamless handoff. */}
            <g className="sk sk-gold">
              <path className="gold-frame" d="M 301 345 V 57 H 560 V 345 Z" pathLength="1" />
              <path className="gold-l" d="M 615 296 H 835" pathLength="1" />
              <path className="gold-r" d="M 1448 296 H 1588" pathLength="1" />
            </g>

          </svg>
        </div>
        <div className="plh-corners" aria-hidden="true">
          <span className="a" />
          <span className="b" />
          <span className="c" />
          <span className="d" />
        </div>
        <div className="plh-progress" aria-hidden="true" />
      </div>
    </div>
  )
}
