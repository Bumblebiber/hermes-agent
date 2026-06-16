import { execSync } from 'node:child_process'
import { existsSync, readFileSync, statSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

export interface Task {
  id: string
  project: string
  status: string
  priority: string
  description: string
}

export interface TmuxSession {
  name: string
  windows: number
  created: string
}

export interface CronJob {
  id: string
  name: string
  schedule: string
  status: string
  lastRun: string
}

export interface UsageCard {
  label: string
  value: string
  level: 'ok' | 'warn' | 'error'
}

const TIM_CLI = join(homedir(), 'projects/tim/packages/tim-cli/dist/cli.js')
const TIM_DB = process.env.TIM_DB_PATH ?? join(homedir(), '.tim/tim.db')
const CRON_JOBS = join(process.env.HERMES_HOME ?? join(homedir(), '.hermes'), 'cron/jobs.json')
const TASK_PROJECTS = ['P0062', 'P0063', 'P0000', 'P0064']

function execText(cmd: string, timeout = 10000): string {
  return execSync(cmd, { timeout, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
}

function firstLine(text: string): string {
  return text.split('\n').find(l => l.trim())?.trim() ?? text.trim()
}

function truncate(text: string, max = 40): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  return clean.length <= max ? clean : `${clean.slice(0, max - 1)}…`
}

function parseMetadata(raw: string): Record<string, unknown> {
  try {
    return JSON.parse(raw || '{}') as Record<string, unknown>
  } catch {
    return {}
  }
}

function taskStatus(meta: Record<string, unknown>): string {
  const task = meta.task as Record<string, unknown> | undefined
  const status = task?.status ?? meta.status
  return typeof status === 'string' && status ? status : 'todo'
}

function taskPriority(meta: Record<string, unknown>): string {
  const task = meta.task as Record<string, unknown> | undefined
  const priority = task?.priority ?? meta.priority
  return typeof priority === 'string' && priority ? priority : 'medium'
}

export function parseTimOutput(out: string): Task[] {
  const tasks: Task[] = []
  let project = ''

  for (const line of out.split('\n')) {
    const header = /^([P]\d{4})\s*[—-]/.exec(line)
    if (header) {
      project = header[1]!
      continue
    }
    const row = /^\s*[\[\]?!\-xX]\]\s+(.+)$/.exec(line)
    if (!row) continue
    const body = row[1]!.trim()
    const idMatch = /\b(ubun-[a-z0-9-]+|01[A-Z0-9]{24,})\b/i.exec(body)
    const id = idMatch?.[1] ?? body.slice(0, 12)
    const statusChar = line.trimStart()[0]
    const status = statusChar === '!' ? 'in_progress' : statusChar === 'x' || statusChar === 'X' ? 'done' : 'todo'

    tasks.push({
      id,
      project: project || '?',
      status,
      priority: 'medium',
      description: truncate(body.replace(idMatch?.[0] ?? '', '').trim() || body)
    })
  }

  return tasks.filter(t => !['done', 'cancelled', 'closed'].includes(t.status))
}

function fetchTasksFromSqlite(): Task[] {
  if (!existsSync(TIM_DB)) return []

  const projects = TASK_PROJECTS.map(p => `'${p}'`).join(', ')
  const query = `
    WITH RECURSIVE up(id, parent_id, project, title, content, metadata) AS (
      SELECT e.id, e.parent_id, NULL, e.title, e.content, e.metadata
      FROM entries e
      WHERE json_extract(e.metadata, '$.task') = 1
        AND COALESCE(json_extract(e.metadata, '$.status'), 'todo')
          NOT IN ('done', 'cancelled', 'closed')
        AND e.irrelevant = 0
      UNION ALL
      SELECT up.id, p.parent_id,
        COALESCE(up.project, json_extract(p.metadata, '$.label')),
        up.title, up.content, up.metadata
      FROM up
      JOIN entries p ON p.id = up.parent_id
      WHERE up.project IS NULL
    )
    SELECT id, project, title, content, metadata
    FROM up
    WHERE project IN (${projects})
    GROUP BY id
  `.replace(/\s+/g, ' ')

  const out = execText(`sqlite3 -json ${JSON.stringify(TIM_DB)} ${JSON.stringify(query)}`, 15000)
  const rows = JSON.parse(out || '[]') as Array<{
    id: string
    project: string
    title: string
    content: string
    metadata: string
  }>

  return rows.map(row => {
    const meta = parseMetadata(row.metadata)
    const description = truncate(row.title || firstLine(row.content) || row.id)
    return {
      id: row.id,
      project: row.project,
      status: taskStatus(meta),
      priority: taskPriority(meta),
      description
    }
  })
}

export function fetchTasks(): Task[] {
  try {
    if (existsSync(TIM_CLI)) {
      const chunks: Task[] = []
      for (const project of TASK_PROJECTS) {
        try {
          const out = execText(
            `node ${JSON.stringify(TIM_CLI)} show --project ${project} --only-open`, 10000
          )
          chunks.push(...parseTimOutput(out))
        } catch { /* tim show unavailable - fall through */ }
      }
      if (chunks.length > 0) return chunks
    }
  } catch { /* fall through */ }

  try { return fetchTasksFromSqlite() }
  catch { return [] }
}

export function toggleTaskStatus(taskId: string, current: string): void {
  const next = current === 'done' ? 'todo' : 'done'
  const query = `
    UPDATE entries
    SET metadata = json_set(
      metadata,
      '$.status', '${next}',
      '$.task.status', '${next}'
    )
    WHERE id = ${JSON.stringify(taskId)}
  `.replace(/\s+/g, ' ')

  execText(`sqlite3 ${JSON.stringify(TIM_DB)} ${JSON.stringify(query)}`, 5000)
}

export function parseTmuxOutput(out: string): TmuxSession[] {
  if (!out.trim()) return []
  return out
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => {
      const m = /^([^:]+):\s*(\d+)\s+windows\s+\(created .+\)/.exec(line)
      if (!m) {
        const name = line.split(':')[0]?.trim() ?? line
        return { name, windows: 0, created: '' }
      }
      return { name: m[1]!, windows: Number(m[2]), created: m[3]! }
    })
}

export function fetchTmuxSessions(): TmuxSession[] {
  try {
    const out = execText('tmux ls 2>/dev/null || echo ""', 5000)
    return parseTmuxOutput(out)
  } catch { return [] }
}

export function captureTmuxPane(session: string): string {
  return execText(`tmux capture-pane -t ${JSON.stringify(session)} -p -S -20`, 5000)
}

export function killTmuxSession(session: string): void {
  execText(`tmux kill-session -t ${JSON.stringify(session)}`, 5000)
}

export function parseCronJobs(raw: unknown): CronJob[] {
  const list = Array.isArray(raw)
    ? raw
    : typeof raw === 'object' && raw && Array.isArray((raw as { jobs?: unknown }).jobs)
      ? (raw as { jobs: unknown[] }).jobs
      : []

  return list.map(job => {
    const j = job as Record<string, unknown>
    return {
      id: String(j.id ?? '?'),
      name: String(j.name ?? '(unnamed)'),
      schedule: String(j.schedule_display ?? (j.schedule as { display?: string })?.display ?? '?'),
      status: String(j.state ?? (j.enabled === false ? 'paused' : 'scheduled')),
      lastRun: String(j.last_run_at ?? '—')
    }
  })
}

export function fetchCrons(): CronJob[] {
  try {
    if (existsSync(CRON_JOBS)) {
      const raw = JSON.parse(readFileSync(CRON_JOBS, 'utf-8')) as unknown
      return parseCronJobs(raw)
    }
  } catch { /* fall through */ }

  try {
    const out = execText('hermes cron list --json 2>/dev/null || echo "[]"', 10000)
    return parseCronJobs(JSON.parse(out || '[]'))
  } catch {
    try {
      const out = execText('hermes cron list 2>/dev/null || echo ""', 10000)
      if (!out || out.includes('No scheduled jobs')) return []
      const jobs: CronJob[] = []
      for (const block of out.split(/\n\s*\n/)) {
        const id = /^\s*([a-f0-9]{8,})\s/m.exec(block)?.[1]
        const name = /Name:\s+(.+)/.exec(block)?.[1]
        const schedule = /Schedule:\s+(.+)/.exec(block)?.[1]
        const status = block.includes('[paused]') ? 'paused'
          : block.includes('[completed]') ? 'completed'
          : 'scheduled'
        const lastRun = /Last run:\s+(.+)/.exec(block)?.[1]
        if (id) {
          jobs.push({
            id,
            name: name ?? '(unnamed)',
            schedule: schedule ?? '?',
            status,
            lastRun: lastRun ?? '—'
          })
        }
      }
      return jobs
    } catch { return [] }
  }
}

export function runCronNow(jobId: string): void {
  execText(`hermes cron run ${JSON.stringify(jobId)}`, 15000)
}

export function toggleCronPause(jobId: string, paused: boolean): void {
  const action = paused ? 'resume' : 'pause'
  execText(`hermes cron ${action} ${JSON.stringify(jobId)}`, 10000)
}

export function fetchUsageCards(): UsageCard[] {
  const cards: UsageCard[] = []

  // TIM DB health
  try {
    if (existsSync(TIM_DB)) {
      const bytes = statSync(TIM_DB).size
      const mb = (bytes / (1024 * 1024)).toFixed(1)
      cards.push({ label: 'TIM DB', value: `${mb} MB`, level: bytes < 500 * 1024 * 1024 ? 'ok' : 'warn' })
    } else {
      cards.push({ label: 'TIM DB', value: 'missing', level: 'error' })
    }
  } catch (err) {
    cards.push({ label: 'TIM DB', value: err instanceof Error ? err.message : 'error', level: 'error' })
  }

  // OpenRouter credits
  try {
    const key = process.env.OPENROUTER_API_KEY ?? ''
    if (!key) {
      cards.push({ label: 'OpenRouter', value: 'no API key', level: 'warn' })
    } else {
      const out = execText(
        `curl -sS https://openrouter.ai/api/v1/auth/key -H 'Authorization: Bearer ${key}'`, 10000
      )
      const data = JSON.parse(out) as { data?: { limit_remaining?: number; usage?: number } }
      const remaining = data.data?.limit_remaining
      const usage = data.data?.usage
      if (typeof remaining === 'number') {
        cards.push({
          label: 'OpenRouter credits',
          value: `${remaining.toFixed(2)} left`,
          level: remaining > 5 ? 'ok' : remaining > 1 ? 'warn' : 'error'
        })
      } else if (typeof usage === 'number') {
        cards.push({ label: 'OpenRouter usage', value: `${usage.toFixed(2)}`, level: 'ok' })
      } else {
        cards.push({ label: 'OpenRouter', value: 'connected', level: 'ok' })
      }
    }
  } catch (err) {
    cards.push({
      label: 'OpenRouter',
      value: err instanceof Error ? err.message.slice(0, 40) : 'error',
      level: 'error'
    })
  }

  // Tmux sessions
  try {
    const sessions = fetchTmuxSessions().length
    cards.push({ label: 'Tmux sessions', value: String(sessions), level: sessions < 10 ? 'ok' : 'warn' })
  } catch {
    cards.push({ label: 'Tmux sessions', value: '?', level: 'warn' })
  }

  // Active crons
  try {
    const crons = fetchCrons().filter(c => c.status === 'scheduled' || c.status === 'active').length
    cards.push({ label: 'Active crons', value: String(crons), level: 'ok' })
  } catch {
    cards.push({ label: 'Active crons', value: '?', level: 'warn' })
  }

  return cards
}
