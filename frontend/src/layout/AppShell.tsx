import type { ReactElement } from 'react'
import {
  AppBar, BottomNavigation, BottomNavigationAction, Box, Chip, Drawer, IconButton, List, ListItemButton,
  ListItemIcon, ListItemText, Paper, Toolbar, Tooltip, Typography,
} from '@mui/material'
import DashboardIcon from '@mui/icons-material/SpaceDashboardOutlined'
import FolderIcon from '@mui/icons-material/FolderOpenOutlined'
import PeopleIcon from '@mui/icons-material/PeopleAltOutlined'
import ArchiveIcon from '@mui/icons-material/Inventory2Outlined'
import WorkIcon from '@mui/icons-material/AssignmentTurnedInOutlined'
import LogoutIcon from '@mui/icons-material/LogoutOutlined'
import { useMediaQuery } from 'react-responsive'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/context'
import { navFor, type NavItem } from './nav'

const ICONS: Record<NavItem['icon'], ReactElement> = {
  dashboard: <DashboardIcon />,
  projects: <FolderIcon />,
  people: <PeopleIcon />,
  archive: <ArchiveIcon />,
  work: <WorkIcon />,
}

const DRAWER_WIDTH = 224

/** Frame around every signed-in page: a side menu on a laptop, a bottom tab bar on a phone. */
export function AppShell() {
  const { user, logout } = useAuth()
  const isDesktop = useMediaQuery({ minWidth: 900 })
  const { pathname } = useLocation()
  if (!user) return null
  const items = navFor(user.role)
  const current = items.find((item) => pathname.startsWith(item.to))?.to ?? false

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="fixed" color="inherit" elevation={0} sx={{ borderBottom: 1, borderColor: 'divider', zIndex: (t) => t.zIndex.drawer + 1 }}>
        <Toolbar sx={{ gap: 1.5 }}>
          <Box sx={{ width: 28, height: 28, borderRadius: 1.5, bgcolor: 'primary.main', position: 'relative', flexShrink: 0 }} aria-hidden>
            <Box sx={{ position: 'absolute', left: 6, right: 6, bottom: 8, height: 3, borderRadius: 2, bgcolor: 'rgba(255,255,255,.5)' }} />
            <Box sx={{ position: 'absolute', left: 6, width: 10, bottom: 8, height: 3, borderRadius: 2, bgcolor: '#fff' }} />
            <Box sx={{ position: 'absolute', right: 6, top: 6, width: 6, height: 6, borderRadius: '50%', bgcolor: '#fbbf24' }} />
          </Box>
          <Typography variant="h6" sx={{ flexGrow: 1 }} noWrap>ACME Projects</Typography>
          {isDesktop && <Typography variant="body2" color="text.secondary">{user.name}</Typography>}
          <Chip size="small" label={user.role} sx={{ textTransform: 'capitalize' }} />
          <Tooltip title="Sign out">
            <IconButton aria-label="Sign out" onClick={logout}><LogoutIcon /></IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>

      {isDesktop && (
        <Drawer
          variant="permanent"
          sx={{ width: DRAWER_WIDTH, '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box', borderRight: 1, borderColor: 'divider' } }}
        >
          <Toolbar />
          <List component="nav" aria-label="Main" sx={{ p: 1.5 }}>
            {items.map((item) => (
              <ListItemButton key={item.to} component={NavLink} to={item.to} selected={current === item.to} sx={{ borderRadius: 2, mb: 0.5 }}>
                <ListItemIcon sx={{ minWidth: 40 }}>{ICONS[item.icon]}</ListItemIcon>
                <ListItemText primary={item.label} />
              </ListItemButton>
            ))}
          </List>
        </Drawer>
      )}

      <Box component="main" sx={{ pt: 11, pb: isDesktop ? 6 : 12, px: { xs: 2, md: 4 }, ml: isDesktop ? `${DRAWER_WIDTH}px` : 0 }}>
        <Box sx={{ maxWidth: 1100, mx: 'auto' }}>
          <Outlet />
        </Box>
      </Box>

      {!isDesktop && items.length > 1 && (
        <Paper sx={{ position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: (t) => t.zIndex.appBar }} elevation={3}>
          <BottomNavigation showLabels value={current}>
            {items.map((item) => (
              <BottomNavigationAction key={item.to} component={NavLink} to={item.to} value={item.to} label={item.label} icon={ICONS[item.icon]} />
            ))}
          </BottomNavigation>
        </Paper>
      )}
    </Box>
  )
}
