import { Routes, Route } from 'react-router-dom'
import { Landing } from './pages/Landing'
import { InterviewFlow } from './pages/InterviewFlow'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/interview" element={<InterviewFlow />} />
    </Routes>
  )
}

export default App
