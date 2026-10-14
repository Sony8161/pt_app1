// The API speaks snake_case (JSON and SQL); the UI code speaks camelCase. Convert once, at the edge.

const toCamel = (key: string) => key.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase())
const toSnake = (key: string) => key.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`)

function convert(value: unknown, rename: (key: string) => string): unknown {
  if (Array.isArray(value)) return value.map((item) => convert(item, rename))
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [rename(key), convert(item, rename)]))
  }
  return value
}

export const keysToCamel = <T>(value: unknown): T => convert(value, toCamel) as T
export const keysToSnake = (value: unknown): unknown => convert(value, toSnake)
