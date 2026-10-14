import { createTheme } from '@mui/material/styles'

// Colour means status and nothing else: green on track, amber at risk, red overdue, grey done.
// Teal is the brand colour and is used only for navigation and the main action on a screen.
export const theme = createTheme({
  palette: {
    primary: { main: '#0f766e' },
    secondary: { main: '#334155' },
    success: { main: '#2e7d32' },
    warning: { main: '#ed8b00' },
    error: { main: '#c62828' },
    background: { default: '#f5f7f8', paper: '#ffffff' },
    text: { primary: '#1b2733', secondary: '#546374' },
  },
  shape: { borderRadius: 10 },
  typography: {
    fontFamily: '"Inter", "Segoe UI", system-ui, -apple-system, Roboto, sans-serif',
    h4: { fontWeight: 700, letterSpacing: '-0.01em' },
    h5: { fontWeight: 700, letterSpacing: '-0.01em' },
    h6: { fontWeight: 600 },
    button: { textTransform: 'none', fontWeight: 600 },
  },
  components: {
    MuiPaper: { defaultProps: { variant: 'outlined' }, styleOverrides: { root: { backgroundImage: 'none' } } },
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiChip: { styleOverrides: { root: { fontWeight: 600 } } },
  },
})
