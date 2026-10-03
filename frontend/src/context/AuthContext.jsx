import { createContext, useContext, useEffect, useState } from 'react'
import { apiFetch, login as apiLogin, logout as apiLogout } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [authState, setAuthState] = useState('checking') // 'checking' | 'authenticated' | 'unauthenticated' | 'error'
  const [authError, setAuthError] = useState('')

  async function checkAuth() {
    setAuthState('checking')
    setAuthError('')
    try {
      await apiFetch('/api/rooms/')
      setAuthState('authenticated')
    } catch (err) {
      if (err.message?.includes('Authentication required')) {
        setAuthState('unauthenticated')
      } else {
        setAuthState('error')
        setAuthError(err.message || 'Unable to connect to the rental service.')
      }
    }
  }

  async function login(credentials) {
    await apiLogin(credentials)
    setAuthState('authenticated')
  }

  async function logout() {
    await apiLogout()
    setAuthState('unauthenticated')
  }

  useEffect(() => {
    checkAuth()
  }, [])

  return (
    <AuthContext.Provider value={{ authState, authError, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
