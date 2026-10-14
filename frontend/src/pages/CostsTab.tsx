import { useState } from 'react'
import {
  Box, Button, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography,
} from '@mui/material'
import { api } from '../api/client'
import type { CostCategory, CostList, Project } from '../api/types'
import { useApi } from '../api/useApi'
import { Async } from '../components/Async'
import { DateField, NumberField } from '../components/fields'
import { FormDialog } from '../components/FormDialog'
import { formatDate, money, todayIso } from '../format'

const CATEGORIES: CostCategory[] = ['technology', 'license', 'vendor', 'travel', 'other']

/** Money that is not people: tools, licences, vendors. Added to labor cost for the project's total spend. */
export function CostsTab({ project, canManage, onChanged }: { project: Project; canManage: boolean; onChanged: () => void }) {
  const state = useApi(() => api.get<CostList>(`/projects/${project.id}/costs`), [project.id])
  const [adding, setAdding] = useState(false)
  const [category, setCategory] = useState<CostCategory>('technology')
  const [description, setDescription] = useState('')
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState(todayIso())

  return (
    <Async state={state}>
      {(c) => (
        <>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, mb: 3 }}>
            <Total label="People (labor)" value={money(c.laborCost)} />
            <Total label="Other costs" value={money(c.otherCost)} />
            <Total label="Total spent" value={money(c.totalCost)} />
            <Total label="Budget left" value={money(c.budgetRemaining)} />
          </Box>
          {canManage && <Button variant="contained" sx={{ mb: 2 }} onClick={() => setAdding(true)}>Add a cost</Button>}
          <TableContainer component={Paper}>
            <Table size="small">
              <TableHead>
                <TableRow><TableCell>Date</TableCell><TableCell>Category</TableCell><TableCell>What</TableCell><TableCell align="right">Amount</TableCell></TableRow>
              </TableHead>
              <TableBody>
                {c.items.map((i) => (
                  <TableRow key={i.id}>
                    <TableCell>{formatDate(i.incurredOn)}</TableCell>
                    <TableCell sx={{ textTransform: 'capitalize' }}>{i.category}</TableCell>
                    <TableCell>{i.description}</TableCell>
                    <TableCell align="right">{money(i.amount)}</TableCell>
                  </TableRow>
                ))}
                {c.items.length === 0 && <TableRow><TableCell colSpan={4}><Typography color="text.secondary">No other costs recorded.</Typography></TableCell></TableRow>}
              </TableBody>
            </Table>
          </TableContainer>

          <FormDialog
            open={adding} title="Add a cost" submitLabel="Add cost" submitDisabled={!description.trim() || amount === ''}
            onClose={() => setAdding(false)}
            onSubmit={async () => {
              await api.post(`/projects/${project.id}/costs`, { category, description, amount: Number(amount), incurredOn: date })
              setDescription('')
              setAmount('')
              state.reload()
              onChanged()
            }}
          >
            <Stack spacing={2}>
              <TextField select label="Category" value={category} onChange={(e) => setCategory(e.target.value as CostCategory)}>
                {CATEGORIES.map((k) => <MenuItem key={k} value={k} sx={{ textTransform: 'capitalize' }}>{k}</MenuItem>)}
              </TextField>
              <TextField label="What was it for?" value={description} onChange={(e) => setDescription(e.target.value)} required />
              <NumberField label="Amount ($)" value={amount} onChange={(e) => setAmount(e.target.value)} required />
              <DateField label="Date" value={date} onChange={(e) => setDate(e.target.value)} />
            </Stack>
          </FormDialog>
        </>
      )}
    </Async>
  )
}

function Total({ label, value }: { label: string; value: string }) {
  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      <Typography variant="h6" component="p">{value}</Typography>
    </Paper>
  )
}
