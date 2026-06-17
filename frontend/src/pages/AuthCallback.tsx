import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'

export function AuthCallback() {
  const navigate = useNavigate()
  const { setAuth } = useAuth()

  useEffect(() => {
    // Token is delivered in URL fragment (#) so it never appears in
    // Referer headers or server access logs. Clear it immediately after reading.
    const hash = window.location.hash.startsWith('#')
      ? window.location.hash.slice(1)
      : window.location.hash
    const params = new URLSearchParams(hash)
    const token = params.get('token')
    const userParam = params.get('user')

    if (token && userParam) {
      try {
        const user = JSON.parse(decodeURIComponent(userParam))
        setAuth(token, user)
        window.history.replaceState(null, '', window.location.pathname + window.location.search)
        navigate(user.role === 'admin' ? '/admin' : '/interview', { replace: true })
      } catch {
        window.history.replaceState(null, '', window.location.pathname + window.location.search)
        navigate('/', { replace: true })
      }
    } else {
      navigate('/', { replace: true })
    }
  }, [setAuth, navigate])

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
      <p>Signing you in...</p>
    </div>
  )
}
