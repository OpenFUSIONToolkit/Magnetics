import { describe, it, expect } from 'vitest'
import { qualityForK } from './contract'

// SLCONTOUR condition-number thresholds: warn > 10, error > 20.
describe('qualityForK', () => {
  it('classifies K by the SLCONTOUR thresholds', () => {
    expect(qualityForK(5)).toBe('good')
    expect(qualityForK(10)).toBe('good')
    expect(qualityForK(15)).toBe('warn')
    expect(qualityForK(20)).toBe('warn')
    expect(qualityForK(25)).toBe('bad')
    expect(qualityForK(Infinity)).toBe('bad')
  })
})
