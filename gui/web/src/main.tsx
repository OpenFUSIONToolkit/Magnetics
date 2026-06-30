import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// StrictMode intentionally omitted: its dev-only double-mount races Plotly's
// imperative react/purge and causes intermittent blank plots on reload. Re-enable
// once the Plotly wrapper is fully StrictMode-safe.
createRoot(document.getElementById('root')!).render(<App />)
