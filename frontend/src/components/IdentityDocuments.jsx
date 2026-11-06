import { useEffect, useRef, useState } from 'react'
import { apiFetch, fetchCsrfToken } from '../api/client'
import { FieldGroup, LoadingShell, Modal } from './shared'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

export const IDENTITY_DOCUMENT_DEFS = [
  { key: 'aadhar_front', label: 'Aadhaar card — Front image' },
  { key: 'aadhar_back', label: 'Aadhaar card — Back image' },
  { key: 'college_id_photo', label: 'College ID card — Image' },
]

export function identityLabelFor(docKey) {
  return IDENTITY_DOCUMENT_DEFS.find((def) => def.key === docKey)?.label || docKey
}

export default function IdentityDocuments({ guestId, initialStatus, initialUrls }) {
  const [status, setStatus] = useState(initialStatus || {})
  const [urls, setUrls] = useState(initialUrls || {})
  const [selected, setSelected] = useState(IDENTITY_DOCUMENT_DEFS[0].key)
  const [busy, setBusy] = useState('')
  const [feedback, setFeedback] = useState({ kind: '', text: '' })
  const [preview, setPreview] = useState(null)
  const [confirmRemove, setConfirmRemove] = useState(null)
  const fileInputs = useRef({})
  const previewRequestId = useRef(0)
  const guestIdRef = useRef(guestId)
  guestIdRef.current = guestId

  useEffect(() => {
    setStatus(initialStatus || {})
    setUrls(initialUrls || {})
  }, [guestId, initialStatus, initialUrls])

  useEffect(() => () => {
    if (preview?.objectUrl) URL.revokeObjectURL(preview.objectUrl)
  }, [preview?.objectUrl])

  // Clear sensitive preview bytes whenever the tenant changes, and whenever
  // the app broadcasts a logout/session-expiry event (see handleLogout in
  // shared.jsx which fires `panesar:logout`). Blob URLs live only in memory
  // and are revoked here — never localStorage/sessionStorage/caches.
  function clearPreview() {
    previewRequestId.current += 1
    setPreview(null)
  }

  useEffect(() => {
    clearPreview()
  }, [guestId])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const onLogout = () => {
      clearPreview()
      setUrls({})
      setFeedback({ kind: '', text: '' })
    }
    window.addEventListener('panesar:logout', onLogout)
    return () => window.removeEventListener('panesar:logout', onLogout)
  }, [])

  useEffect(() => () => {
    previewRequestId.current += 1
  }, [])

  function applyServerState(data) {
    if (data?.identity_documents) setStatus(data.identity_documents)
    if (data?.identity_document_urls) setUrls(data.identity_document_urls)
  }

  async function handleFileChange(docKey, event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setBusy(docKey)
    setFeedback({ kind: 'loading', text: `Uploading ${identityLabelFor(docKey)}…` })
    try {
      const form = new FormData()
      form.append('file', file)
      const data = await apiFetch(`/api/guest/${guestId}/identity/${docKey}/upload/`, {
        method: 'POST',
        body: form,
      })
      if (preview?.key === docKey) clearPreview()
      applyServerState(data)
      setFeedback({ kind: 'success', text: data.message || `${identityLabelFor(docKey)} saved.` })
    } catch (err) {
      setFeedback({ kind: 'error', text: err.message || `Unable to upload ${identityLabelFor(docKey)}.` })
    } finally {
      setBusy('')
    }
  }

  async function openPreview(docKey) {
    const url = urls[docKey]
    if (!url) {
      setFeedback({ kind: 'error', text: `${identityLabelFor(docKey)} is not uploaded yet.` })
      return
    }
    const requestId = ++previewRequestId.current
    const requestGuestId = guestId
    setPreview({ key: docKey, loading: true, error: '', objectUrl: '' })
    try {
      let token = ''
      try { token = await fetchCsrfToken() } catch { token = '' }
      if (requestId !== previewRequestId.current || guestIdRef.current !== requestGuestId) return
      const response = await fetch(`${API_BASE}${url}`, {
        credentials: 'include',
        cache: 'no-store',
        headers: token ? { 'X-CSRFToken': token } : {},
      })
      if (response.status === 0 || response.status === 401 || response.status === 302 || response.type === 'opaqueredirect') {
        clearPreview()
        try { window.dispatchEvent(new Event('panesar:logout')) } catch { /* noop */ }
        throw new Error('Authentication required. Please log in again.')
      }
      if (response.status === 403) throw new Error('Access denied. Check staff permissions.')
      if (!response.ok) throw new Error('Unable to load the document preview.')
      const blob = await response.blob()
      if (!blob.type.startsWith('image/')) throw new Error('The stored file is not a viewable image.')
      if (requestId !== previewRequestId.current || guestIdRef.current !== requestGuestId) return
      setPreview({ key: docKey, loading: false, error: '', objectUrl: URL.createObjectURL(blob) })
    } catch (err) {
      if (requestId !== previewRequestId.current || guestIdRef.current !== requestGuestId) return
      setPreview({ key: docKey, loading: false, error: err.message || 'Unable to load preview.', objectUrl: '' })
    }
  }

  function closePreview() {
    clearPreview()
  }

  async function confirmDeletion(docKey) {
    setBusy(docKey)
    setFeedback({ kind: 'loading', text: `Removing ${identityLabelFor(docKey)}…` })
    try {
      const data = await apiFetch(`/api/guest/${guestId}/identity/${docKey}/delete/`, { method: 'POST' })
      applyServerState(data)
      setConfirmRemove(null)
      if (preview?.key === docKey) closePreview()
      setFeedback({ kind: 'success', text: data.message || `${identityLabelFor(docKey)} removed.` })
    } catch (err) {
      setFeedback({ kind: 'error', text: err.message || `Unable to remove ${identityLabelFor(docKey)}.` })
    } finally {
      setBusy('')
    }
  }



  return (
    <div className="identity-docs" aria-live="polite">
      <FieldGroup label="Select document to view">
        <select className="field-input" value={selected} onChange={(event) => setSelected(event.target.value)}>
          {IDENTITY_DOCUMENT_DEFS.map((def) => (
            <option key={def.key} value={def.key}>
              {def.label} — {status[def.key] ? 'Uploaded' : 'Not uploaded'}
            </option>
          ))}
        </select>
      </FieldGroup>
      {IDENTITY_DOCUMENT_DEFS.map((def) => (
        <IdentityDocRow
          key={def.key}
          def={def}
          uploaded={Boolean(status[def.key])}
          loading={busy === def.key}
          inputRef={(node) => { fileInputs.current[def.key] = node }}
          onPickFile={() => fileInputs.current[def.key]?.click()}
          onFileChange={(event) => handleFileChange(def.key, event)}
          onView={() => { setSelected(def.key); openPreview(def.key) }}
          onRemove={() => setConfirmRemove(def.key)}
        />
      ))}
      {feedback.text && (
        <div className={`identity-doc-feedback identity-doc-feedback--${feedback.kind}`} role={feedback.kind === 'error' ? 'alert' : 'status'}>
          {feedback.text}
        </div>
      )}
      {confirmRemove && (
        <Modal
          title={`Remove ${identityLabelFor(confirmRemove)}?`}
          onClose={() => { if (!busy) setConfirmRemove(null) }}
          footer={(
            <>
              <button type="button" className="ghost-button" disabled={Boolean(busy)} onClick={() => setConfirmRemove(null)}>
                Keep document
              </button>
              <button type="button" className="danger-button" disabled={Boolean(busy)} onClick={() => confirmDeletion(confirmRemove)}>
                {busy ? 'Removing…' : 'Yes, remove'}
              </button>
            </>
          )}
        >
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6 }}>
            This permanently deletes the stored image. The tenant record stays unchanged.
          </p>
        </Modal>
      )}
      {preview && (
        <Modal title={identityLabelFor(preview.key)} onClose={closePreview}>
          {preview.loading ? (
            <LoadingShell label="Loading document preview…" />
          ) : preview.error ? (
            <div className="error-state">
              <span>{preview.error}</span>
              <button type="button" className="retry-button" onClick={() => openPreview(preview.key)}>Retry</button>
            </div>
          ) : (
            <img className="identity-preview-img" src={preview.objectUrl} alt={`${identityLabelFor(preview.key)} preview`} />
          )}
          <p className="tenant-profile-note">Preview is streamed over an authenticated session and is never cached.</p>
        </Modal>
      )}
    </div>
  )
}

function IdentityDocRow({ def, uploaded, loading, inputRef, onPickFile, onFileChange, onView, onRemove }) {
  return (
    <div className="identity-doc-row">
      <div className="identity-doc-meta">
        <span className="identity-doc-title">{def.label}</span>
        <span className={`identity-doc-status ${uploaded ? 'identity-doc-status--uploaded' : 'identity-doc-status--missing'}`}>
          {uploaded ? 'Uploaded' : 'Not uploaded'}
        </span>
      </div>
      <div className="identity-doc-actions">
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
          hidden
          aria-hidden="true"
          tabIndex={-1}
          onChange={onFileChange}
        />
        <button type="button" className="btn-primary" disabled={loading} onClick={onPickFile}>
          {loading ? 'Uploading…' : uploaded ? 'Replace' : 'Upload'}
        </button>
        {uploaded && (
          <button
            type="button"
            className="ghost-button"
            disabled={loading}
            onClick={onView}
            aria-label={`View ${def.label}`}
            title={`View ${def.label}`}
          >
            <span aria-hidden="true">👁</span> View Image
          </button>
        )}
        <button type="button" className="danger-button" disabled={loading || !uploaded} onClick={onRemove}>
          Remove
        </button>
      </div>
    </div>
  )
}
