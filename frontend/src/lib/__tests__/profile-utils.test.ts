import { describe, it, expect } from 'vitest'
import { cleanSkills, mergeParsedIntoProfile, parsedHasContent, type ProfileFormState } from '@/lib/profile-utils'
import type { ParsedResumeProfile } from '@/api/client'

const emptyForm = (): ProfileFormState => ({
  headline: '',
  location: '',
  summary: '',
  skills: [],
  experience: [],
  education: [],
  linkedin_url: null,
  github_url: null,
  portfolio_url: null,
})

const parsed = (over: Partial<ParsedResumeProfile> = {}): ParsedResumeProfile => ({
  headline: 'Backend Engineer',
  location: 'Berlin',
  summary: 'Ships things.',
  skills: ['Python', 'Go'],
  experience: [{ title: 'SWE', company: 'Acme', start: '2020', end: '', description: '' }],
  education: [{ school: 'TU', degree: 'MSc', field: 'CS', start: '', end: '' }],
  linkedin_url: 'https://linkedin.com/in/x',
  github_url: null,
  portfolio_url: null,
  ...over,
})

describe('cleanSkills', () => {
  it('trims, dedupes case-insensitively, and drops empties', () => {
    expect(cleanSkills([' Python ', 'python', 'Go', '', 'GO', 'Rust'])).toEqual(['Python', 'Go', 'Rust'])
  })

  it('caps at 30 entries', () => {
    expect(cleanSkills(Array.from({ length: 40 }, (_, i) => `s${i}`)).length).toBe(30)
  })
})

describe('mergeParsedIntoProfile', () => {
  it('fills empty fields from the parse', () => {
    const merged = mergeParsedIntoProfile(emptyForm(), parsed())
    expect(merged.headline).toBe('Backend Engineer')
    expect(merged.skills).toEqual(['Python', 'Go'])
    expect(merged.experience[0].company).toBe('Acme')
    expect(merged.linkedin_url).toBe('https://linkedin.com/in/x')
  })

  it('never overwrites existing values', () => {
    const form: ProfileFormState = {
      ...emptyForm(),
      headline: 'My own headline',
      skills: ['Ruby'],
      linkedin_url: 'https://linkedin.com/in/mine',
    }
    const merged = mergeParsedIntoProfile(form, parsed())
    expect(merged.headline).toBe('My own headline')
    expect(merged.skills).toEqual(['Ruby'])
    expect(merged.linkedin_url).toBe('https://linkedin.com/in/mine')
    // …while still filling the untouched fields.
    expect(merged.location).toBe('Berlin')
    expect(merged.github_url).toBeNull()
  })

  it('treats whitespace-only current values as empty', () => {
    const merged = mergeParsedIntoProfile({ ...emptyForm(), headline: '   ' }, parsed())
    expect(merged.headline).toBe('Backend Engineer')
  })

  it('does not mutate the inputs', () => {
    const form = emptyForm()
    const p = parsed()
    mergeParsedIntoProfile(form, p)
    expect(form.headline).toBe('')
    expect(p.skills).toEqual(['Python', 'Go'])
  })
})

describe('parsedHasContent', () => {
  it('is false for an empty parse', () => {
    expect(parsedHasContent(parsed({
      headline: null, location: null, summary: null, skills: [],
      experience: [], education: [], linkedin_url: null,
    }))).toBe(false)
  })

  it('is true when only skills were found', () => {
    expect(parsedHasContent(parsed({
      headline: null, location: null, summary: null, skills: ['Go'],
      experience: [], education: [], linkedin_url: null,
    }))).toBe(true)
  })
})
