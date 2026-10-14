import { Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material'
import { api } from '../api/client'
import type { AssigneeList } from '../api/types'
import { useApi } from '../api/useApi'
import { Async } from '../components/Async'
import { dateRange, hours, money } from '../format'

/** Everyone working on any milestone of the project, with the hours and cost the calendar produces. */
export function TeamTab({ projectId }: { projectId: string }) {
  const state = useApi(() => api.get<AssigneeList>(`/projects/${projectId}/team`), [projectId])
  return (
    <Async state={state}>
      {(team) => (
        <>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Hours are not typed in. Every Monday to Friday of an assignment is an 8-hour shift, counted up to today.
          </Typography>
          <TableContainer component={Paper}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Person</TableCell>
                  <TableCell>Milestone</TableCell>
                  <TableCell>Dates</TableCell>
                  <TableCell align="right">Days</TableCell>
                  <TableCell align="right">Hours</TableCell>
                  {team.laborCost !== null && <TableCell align="right">Cost so far</TableCell>}
                </TableRow>
              </TableHead>
              <TableBody>
                {team.items.map((a) => (
                  <TableRow key={a.assignmentId}>
                    <TableCell>{a.name}<Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{a.jobTitle}</Typography></TableCell>
                    <TableCell>{a.milestoneName}</TableCell>
                    <TableCell>{dateRange(a.startDate, a.endDate)}</TableCell>
                    <TableCell align="right">{a.daysWorked}</TableCell>
                    <TableCell align="right">{hours(a.hoursWorked)}</TableCell>
                    {team.laborCost !== null && <TableCell align="right">{money(a.laborCost)}</TableCell>}
                  </TableRow>
                ))}
                {team.items.length === 0 && <TableRow><TableCell colSpan={6}><Typography color="text.secondary">Nobody is assigned to a milestone yet.</Typography></TableCell></TableRow>}
                {team.items.length > 0 && (
                  <TableRow>
                    <TableCell colSpan={4}><strong>Total</strong></TableCell>
                    <TableCell align="right"><strong>{hours(team.hoursWorked)}</strong></TableCell>
                    {team.laborCost !== null && <TableCell align="right"><strong>{money(team.laborCost)}</strong></TableCell>}
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </>
      )}
    </Async>
  )
}
