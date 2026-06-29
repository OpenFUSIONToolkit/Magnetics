import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import SensorsTab from './SensorsTab'

// Example component test — renders a view and checks it shows the selected shot.
describe('SensorsTab', () => {
  it('renders the selected machine id', () => {
    render(<SensorsTab machine="MOCK-A" />)
    expect(screen.getByText(/MOCK-A/)).toBeInTheDocument()
  })
})
