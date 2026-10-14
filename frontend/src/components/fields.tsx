import { TextField, type TextFieldProps } from '@mui/material'

/** A date input whose label always stays above the box (browsers draw their own placeholder inside). */
export function DateField(props: TextFieldProps) {
  return <TextField type="date" required slotProps={{ inputLabel: { shrink: true } }} {...props} />
}

export function NumberField(props: TextFieldProps) {
  return <TextField type="number" slotProps={{ htmlInput: { min: 0, step: 'any' } }} {...props} />
}
