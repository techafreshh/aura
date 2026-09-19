import type { CandidateProfile, ParsedResumeProfile } from '@/api/client'

export type ProfileFormState = Omit<CandidateProfile, 'resume_stored' | 'resume_uploaded_at'>

const MAX_SKILLS = 30

/** Case-insensitive dedupe + hard cap for parsed skill lists. */
export function cleanSkills(skills: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of skills) {
    const skill = raw.trim().slice(0, 60)
    if (!skill) continue
    const key = skill.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(skill)
    if (out.length >= MAX_SKILLS) break
  }
  return out
}

/**
 * Fill the profile form's EMPTY fields with parsed resume values.
 *
 * Never overwrites data the candidate already has: a field keeps its existing
 * value whether or not the parser produced one, so re-uploading a resume can
 * never silently destroy saved profile data. The caller shows a toast and the
 * user saves explicitly.
 */
export function mergeParsedIntoProfile(form: ProfileFormState, parsed: ParsedResumeProfile): ProfileFormState {
  const keep = (current: string, parsedValue: string | null) =>
    current.trim() ? current : (parsedValue ?? '')

  const keepLink = (current: string | null, parsedValue: string | null) =>
    current && current.trim() ? current : parsedValue

  return {
    headline: keep(form.headline, parsed.headline),
    location: keep(form.location, parsed.location),
    summary: keep(form.summary, parsed.summary),
    skills: form.skills.length ? form.skills : cleanSkills(parsed.skills),
    experience: form.experience.length ? form.experience : parsed.experience,
    education: form.education.length ? form.education : parsed.education,
    linkedin_url: keepLink(form.linkedin_url, parsed.linkedin_url),
    github_url: keepLink(form.github_url, parsed.github_url),
    portfolio_url: keepLink(form.portfolio_url, parsed.portfolio_url),
  }
}

/** Did the parser find anything worth telling the user about? */
export function parsedHasContent(parsed: ParsedResumeProfile): boolean {
  return !!(
    parsed.headline?.trim() ||
    parsed.location?.trim() ||
    parsed.summary?.trim() ||
    parsed.skills.length ||
    parsed.experience.length ||
    parsed.education.length ||
    parsed.linkedin_url ||
    parsed.github_url ||
    parsed.portfolio_url
  )
}
