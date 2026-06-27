import { describe, it, expect } from 'vitest'
import {
  recPill,
  statusPill,
  formatDate,
  formatDateTime,
  formatDuration,
  initials,
} from '../dashboard-utils'

describe('recPill', () => {
  it('returns success class for Strong Hire', () => {
    expect(recPill('Strong Hire')).toEqual({ cls: 'pill pill-success', text: 'Strong Hire' })
  })

  it('returns success class for Hire', () => {
    expect(recPill('Hire')).toEqual({ cls: 'pill pill-success', text: 'Hire' })
  })

  it('returns warn class for Hold', () => {
    expect(recPill('Hold')).toEqual({ cls: 'pill pill-warn', text: 'Hold' })
  })

  it('returns danger class for No Hire', () => {
    expect(recPill('No Hire')).toEqual({ cls: 'pill pill-danger', text: 'No Hire' })
  })

  it('returns muted pill for null recommendation', () => {
    expect(recPill(null)).toEqual({ cls: 'pill pill-muted', text: '—' })
  })
})

describe('statusPill', () => {
  it('returns success class for completed', () => {
    expect(statusPill('completed')).toEqual({ cls: 'pill pill-success', text: 'Completed' })
  })

  it('returns accent class for in_progress', () => {
    expect(statusPill('in_progress')).toEqual({ cls: 'pill pill-accent', text: 'In Progress' })
  })

  it('returns muted class for pending', () => {
    expect(statusPill('pending')).toEqual({ cls: 'pill pill-muted', text: 'Pending' })
  })
})

describe('formatDate', () => {
  it('formats ISO date string', () => {
    const result = formatDate('2026-06-27T10:30:00Z')
    expect(result).toBeTruthy()
    // Should contain date components (locale-dependent, so just check it's not empty)
    expect(result.length).toBeGreaterThan(0)
  })

  it('handles date-only strings', () => {
    const result = formatDate('2026-01-01')
    expect(result).toBeTruthy()
  })
})

describe('formatDateTime', () => {
  it('formats ISO datetime string', () => {
    const result = formatDateTime('2026-06-27T10:30:00Z')
    expect(result).toBeTruthy()
    expect(result).not.toBe('—')
  })

  it('returns dash for null', () => {
    expect(formatDateTime(null)).toBe('—')
  })
})

describe('formatDuration', () => {
  it('formats seconds only', () => {
    expect(formatDuration(45)).toBe('45s')
  })

  it('formats minutes and seconds', () => {
    expect(formatDuration(150)).toBe('2m 30s')
  })

  it('formats hours and minutes', () => {
    expect(formatDuration(3661)).toBe('1h 1m')
  })

  it('returns dash for null', () => {
    expect(formatDuration(null)).toBe('—')
  })

  it('returns dash for undefined', () => {
    expect(formatDuration(undefined)).toBe('—')
  })

  it('handles zero seconds', () => {
    expect(formatDuration(0)).toBe('0s')
  })
})

describe('initials', () => {
  it('returns first two initials for full name', () => {
    expect(initials('John Doe')).toBe('JD')
  })

  it('returns single initial for one name', () => {
    expect(initials('Madonna')).toBe('M')
  })

  it('returns question mark for empty string', () => {
    expect(initials('')).toBe('?')
  })

  it('handles multiple word names', () => {
    expect(initials('John Michael Doe')).toBe('JM')
  })
})
