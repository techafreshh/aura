import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/contexts/AuthContext'

export function AuthCallback() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { setAuth } = useAuth()

  useEffect(() => {
    const token = searchParams.get('token')
    const userParam = searchParams.get('user')

    if (token && userParam) {
      try {
        const user = JSON.parse(decodeURIComponent(userParam))
        setAuth(token, user)
        navigate(user.role === 'admin' ? '/admin' : '/interview', { replace: true })
      } catch {
        navigate('/', { replace: true })
      }
    } else {
      // OAuth providers may return data via fragment or postMessage
      // For Authlib, the callback URL is handled server-side and redirects here
      navigate('/', { replace: true })
    }
  }, [searchParams, setAuth, navigate])

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
      <p>Signing you in...</p>
    </div>
  )
}
