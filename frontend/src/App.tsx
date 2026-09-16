import { Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { Landing } from './pages/Landing'
import { InterviewFlow } from './pages/InterviewFlow'
import { AuthCallback } from './pages/AuthCallback'
import { LoginPage } from './pages/LoginPage'
import { EmailVerified } from './pages/EmailVerified'
import { ForgotPassword } from './pages/ForgotPassword'
import { ResetPassword } from './pages/ResetPassword'
import { MyInterviews } from './pages/MyInterviews'
import { AdminDashboard } from './pages/AdminDashboard'
import { SessionDetail } from './pages/SessionDetail'
import { CandidateSessionReport } from './pages/CandidateSessionReport'
import { ProtectedRoute } from './components/auth/ProtectedRoute'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/verified" element={<EmailVerified />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/interview" element={<ProtectedRoute><InterviewFlow /></ProtectedRoute>} />
        <Route path="/my-interviews" element={<ProtectedRoute><MyInterviews /></ProtectedRoute>} />
        <Route path="/my-interviews/:sessionId" element={<ProtectedRoute><CandidateSessionReport /></ProtectedRoute>} />
        <Route path="/admin" element={<ProtectedRoute requireAdmin><AdminDashboard /></ProtectedRoute>} />
        <Route path="/admin/session/:sessionId" element={<ProtectedRoute requireAdmin><SessionDetail /></ProtectedRoute>} />
      </Routes>
    </AuthProvider>
  )
}

export default App
