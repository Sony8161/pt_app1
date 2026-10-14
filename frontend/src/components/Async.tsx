import type { ReactNode } from 'react'
import { Alert, Box, Button, CircularProgress } from '@mui/material'
import type { Loadable } from '../api/useApi'

/** Shows a spinner while loading and a readable error with a retry button; renders children once there is data. */
export function Async<T>({ state, children }: { state: Loadable<T>; children: (data: T) => ReactNode }) {
  if (state.data !== null) {
    return (
      <>
        {state.error && (
          <Alert severity="error" sx={{ mb: 2 }} action={<Button color="inherit" size="small" onClick={state.reload}>Try again</Button>}>
            {state.error}
          </Alert>
        )}
        {children(state.data)}
      </>
    )
  }
  if (state.error) {
    return (
      <Alert severity="error" action={<Button color="inherit" size="small" onClick={state.reload}>Try again</Button>}>
        {state.error}
      </Alert>
    )
  }
  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
      <CircularProgress aria-label="Loading" />
    </Box>
  )
}
