import { Box, Text, useApp, useInput } from '@hermes/ink'
import { useCallback, useEffect, useState } from 'react'

import { DEFAULT_THEME, type Theme } from '../theme.js'

import { CronsTab } from './crons.js'
import {
  type CronJob,
  fetchCrons,
  fetchTasks,
  fetchTmuxSessions,
  fetchUsageCards,
  type Task,
  type TmuxSession,
  type UsageCard
} from './data.js'
import { TasksTab } from './tasks.js'
import { TmuxTab } from './tmux.js'
import { UsageTab } from './usage.js'

const TABS = ['Tasks', 'Tmux', 'Crons', 'Usage'] as const

export function Dashboard() {
  const t: Theme = DEFAULT_THEME
  const { exit } = useApp()
  const [activeTab, setActiveTab] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tasks, setTasks] = useState<Task[]>([])
  const [sessions, setSessions] = useState<TmuxSession[]>([])
  const [crons, setCrons] = useState<CronJob[]>([])
  const [usage, setUsage] = useState<UsageCard[]>([])

  const refresh = useCallback(() => {
    setLoading(true)
    setError('')

    try {
      setTasks(fetchTasks())
      setSessions(fetchTmuxSessions())
      setCrons(fetchCrons())
      setUsage(fetchUsageCards())
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useInput((input, key) => {
    if (input === 'q' || (key.ctrl && input === 'c')) {
      exit()
      return
    }

    if (input === 'r') {
      refresh()
      return
    }

    if (key.tab || key.rightArrow) {
      setActiveTab(v => (v + 1) % TABS.length)
      return
    }

    if (key.leftArrow) {
      setActiveTab(v => (v - 1 + TABS.length) % TABS.length)
      return
    }

    const num = Number(input)

    if (num >= 1 && num <= 4) {
      setActiveTab(num - 1)
    }
  })

  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color={t.color.primary}>
        Hermes PM Dashboard
      </Text>
      <TabBar active={activeTab} t={t} />
      {error ? (
        <Text color={t.color.error}>Error: {error}</Text>
      ) : loading ? (
        <Text color={t.color.muted}>Loading...</Text>
      ) : (
        <Box flexDirection="column" marginTop={1}>
          {activeTab === 0 ? (
            <TasksTab tasks={tasks} onRefresh={refresh} t={t} />
          ) : null}
          {activeTab === 1 ? (
            <TmuxTab onRefresh={refresh} sessions={sessions} t={t} />
          ) : null}
          {activeTab === 2 ? (
            <CronsTab crons={crons} onRefresh={refresh} t={t} />
          ) : null}
          {activeTab === 3 ? <UsageTab cards={usage} t={t} /> : null}
        </Box>
      )}
      <StatusBar t={t} />
    </Box>
  )
}

function TabBar({ active, t }: { active: number; t: Theme }) {
  return (
    <Box marginTop={1}>
      {TABS.map((name, idx) => (
        <Text key={name} color={idx === active ? t.color.primary : t.color.muted}>
          {idx === active ? `[${name}]` : ` ${name} `}
        </Text>
      ))}
    </Box>
  )
}

function StatusBar({ t }: { t: Theme }) {
  return (
    <Box marginTop={1}>
      <Text color={t.color.muted}>
        [1]Tasks [2]Tmux [3]Crons [4]Usage | Tab/←→ switch | q quit | r refresh
      </Text>
    </Box>
  )
}
