import { readFileSync } from 'node:fs'
import { join } from 'node:path'

export const KNOWN_PROJECTS: Record<string, string> = {
  P0062: 'PM Workflow',
  P0063: 'TIM',
  P0064: 'Hermes Agent',
  P0000: 'Inbox',
  P0048: 'its-over-9k',
  P9999: 'Phantom'
}

export function parseProjectLabel(cwd: string): string | null {
  try {
    const raw = readFileSync(join(cwd, '.tim-project'), 'utf-8')
    const parsed = JSON.parse(raw) as { project?: string }
    return parsed?.project || null
  } catch {
    return null
  }
}

export function formatProjectName(projectLabel: string | null): string {
  if (!projectLabel) return 'no project'
  const name = KNOWN_PROJECTS[projectLabel]
  if (!name) return 'no project'
  return name.length > 20 ? `${name.slice(0, 20)}…` : name
}
