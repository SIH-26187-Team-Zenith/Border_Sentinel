// src/App.jsx
import { Navigate, Route, BrowserRouter as Router, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import { AuthProvider } from './context/AuthContext'
import Alerts from './pages/Alerts'
import Analyze from './pages/Analyze'
import AuthCallback from './pages/AuthCallback'
import CameraDetail from './pages/CameraDetail'
import Cameras from './pages/Cameras'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Register from './pages/Register'

export default function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/auth/callback" element={<AuthCallback />} />
          <Route
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/cameras" element={<Cameras />} />
            <Route path="/cameras/:id" element={<CameraDetail />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/analyze" element={<Analyze />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
  )
}
