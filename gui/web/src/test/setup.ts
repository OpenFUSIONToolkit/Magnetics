// Vitest setup: adds jest-dom matchers (toBeInTheDocument, etc.) to expect.
import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// `globals` isn't enabled, so RTL's auto-cleanup afterEach isn't installed — register
// it here so each test starts from a clean DOM (renders don't leak between tests).
afterEach(() => cleanup())

// jsdom on newer Node (23+) can expose a `window.localStorage` whose methods
// aren't callable (getItem is not a function), which crashes any component that
// reads persisted state (e.g. store.ts's loadTheme). Install a minimal in-memory
// Storage so the suite runs identically across Node/jsdom versions.
if (typeof window !== 'undefined') {
  const backing = new Map<string, string>()
  const storage: Storage = {
    getItem: (key) => (backing.has(key) ? backing.get(key)! : null),
    setItem: (key, value) => {
      backing.set(key, String(value))
    },
    removeItem: (key) => {
      backing.delete(key)
    },
    clear: () => {
      backing.clear()
    },
    key: (index) => Array.from(backing.keys())[index] ?? null,
    get length() {
      return backing.size
    },
  }
  Object.defineProperty(window, 'localStorage', { value: storage, configurable: true })
}
