import { Suspense, lazy } from 'react'
import { Box, CircularProgress } from '@mui/material'
import { Navigate, Route, Routes } from 'react-router-dom'
import { homeFor, useAuth } from './auth/context'
import { RequireAuth, RequireRole } from './auth/guards'
import { AppShell } from './layout/AppShell'
import { ChangePasswordPage } from './pages/ChangePasswordPage'
import { LoginPage } from './pages/LoginPage'

// The signed-in pages load on demand, so the sign-in screen does not wait for the whole app.
const ArchivePage = lazy(() => import('./pages/ArchivePage').then((m) => ({ default: m.ArchivePage })))
const DashboardPage = lazy(() => import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })))
const MyWorkPage = lazy(() => import('./pages/MyWorkPage').then((m) => ({ default: m.MyWorkPage })))
const PeoplePage = lazy(() => import('./pages/PeoplePage').then((m) => ({ default: m.PeoplePage })))
const ProjectDetailPage = lazy(() => import('./pages/ProjectDetailPage').then((m) => ({ default: m.ProjectDetailPage })))
const ProjectsPage = lazy(() => import('./pages/ProjectsPage').then((m) => ({ default: m.ProjectsPage })))

const loading = (
  <Box sx={{ display: 'flex', justifyContent: 'center', py: 10 }}>
    <CircularProgress aria-label="Loading page" />
  </Box>
)

export function App() {
  const { user } = useAuth()
  return (
    <Suspense fallback={loading}>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/change-password" element={<ChangePasswordPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="/my-work" element={<RequireRole roles={['employee']}><MyWorkPage /></RequireRole>} />
          <Route path="/dashboard" element={<RequireRole roles={['admin', 'manager']}><DashboardPage /></RequireRole>} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="/people" element={<RequireRole roles={['admin', 'manager']}><PeoplePage /></RequireRole>} />
          <Route path="/archive" element={<RequireRole roles={['admin']}><ArchivePage /></RequireRole>} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to={user ? homeFor(user.role) : '/login'} replace />} />
    </Routes>
    </Suspense>
  )
}
