import type { ReactNode } from 'react'
import { Box, Typography } from '@mui/material'

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', justifyContent: 'space-between', gap: 2, mb: 3 }}>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="h5" component="h1">{title}</Typography>
        {subtitle && <Typography color="text.secondary" component="div">{subtitle}</Typography>}
      </Box>
      {actions && <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>{actions}</Box>}
    </Box>
  )
}
