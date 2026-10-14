import { useState } from 'react'
import { Alert, Button, Paper, Stack, Tab, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Tabs, Typography } from '@mui/material'
import { api } from '../api/client'
import type { ProjectList, UserList } from '../api/types'
import { errorText, useApi } from '../api/useApi'
import { Async } from '../components/Async'
import { PageHeader } from '../components/PageHeader'
import { formatDate } from '../format'

/** Admin-only. Nothing in the system is ever deleted: removed things wait here and can be restored. */
export function ArchivePage() {
  const [tab, setTab] = useState(0)
  const [message, setMessage] = useState<string | null>(null)
  const projects = useApi(() => api.get<ProjectList>('/projects', { include_archived: 'true', page_size: 100 }), [])
  const people = useApi(() => api.get<UserList>('/users', { include_archived: 'true' }), [])

  const restore = async (path: string, reload: () => void) => {
    setMessage(null)
    try {
      await api.post(path)
      reload()
    } catch (err) {
      setMessage(errorText(err))
    }
  }

  return (
    <>
      <PageHeader title="Archive" subtitle="Archived records are visible to admins only. Restoring brings them back." />
      <Tabs value={tab} onChange={(_, v: number) => setTab(v)} sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tab label="Projects" />
        <Tab label="People" />
      </Tabs>
      {message && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setMessage(null)}>{message}</Alert>}

      {tab === 0 && (
        <Async state={projects}>
          {(list) => {
            const archived = list.items.filter((p) => p.archivedAt !== null)
            return (
              <TableContainer component={Paper}>
                <Table size="small">
                  <TableHead><TableRow><TableCell>Project</TableCell><TableCell>Manager</TableCell><TableCell>Archived</TableCell><TableCell align="right" /></TableRow></TableHead>
                  <TableBody>
                    {archived.map((p) => (
                      <TableRow key={p.id}>
                        <TableCell>{p.name}</TableCell>
                        <TableCell>{p.manager.name}</TableCell>
                        <TableCell>{formatDate(p.archivedAt!.slice(0, 10))}</TableCell>
                        <TableCell align="right"><Button size="small" onClick={() => restore(`/projects/${p.id}/unarchive`, projects.reload)}>Restore</Button></TableCell>
                      </TableRow>
                    ))}
                    {archived.length === 0 && <TableRow><TableCell colSpan={4}><Typography color="text.secondary">No archived projects.</Typography></TableCell></TableRow>}
                  </TableBody>
                </Table>
              </TableContainer>
            )
          }}
        </Async>
      )}

      {tab === 1 && (
        <Async state={people}>
          {(list) => {
            const archived = list.items.filter((u) => u.archivedAt !== null)
            return (
              <Stack spacing={2}>
                <TableContainer component={Paper}>
                  <Table size="small">
                    <TableHead><TableRow><TableCell>Person</TableCell><TableCell>Role</TableCell><TableCell>Archived</TableCell><TableCell align="right" /></TableRow></TableHead>
                    <TableBody>
                      {archived.map((u) => (
                        <TableRow key={u.id}>
                          <TableCell>{u.name}<Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>{u.email}</Typography></TableCell>
                          <TableCell sx={{ textTransform: 'capitalize' }}>{u.role}</TableCell>
                          <TableCell>{formatDate(u.archivedAt!.slice(0, 10))}</TableCell>
                          <TableCell align="right"><Button size="small" onClick={() => restore(`/users/${u.id}/unarchive`, people.reload)}>Restore</Button></TableCell>
                        </TableRow>
                      ))}
                      {archived.length === 0 && <TableRow><TableCell colSpan={4}><Typography color="text.secondary">No archived people.</Typography></TableCell></TableRow>}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Stack>
            )
          }}
        </Async>
      )}
    </>
  )
}
