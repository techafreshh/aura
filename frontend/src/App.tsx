import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { Landing } from './pages/Landing'
import { InterviewFlow } from './pages/InterviewFlow'
import { AuthCallback } from './pages/AuthCallback'
import { ProtectedRoute } from './components/auth/ProtectedRoute'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/interview" element={<ProtectedRoute><InterviewFlow /></ProtectedRoute>} />
      </Routes>
    </AuthProvider>
  )
}

export default App
