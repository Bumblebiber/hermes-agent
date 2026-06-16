import { Box, Text, useInput } from '@hermes/ink'
import { useMemo, useState } from 'react'

import type { Theme } from '../theme.js'

import { type Task, toggleTaskStatus } from './data.js'
import { windowItems } from '../components/overlayControls.js'

const VISIBLE = 14
const COLS = {
  id: 28,
  project: 8,
  status: 12,
  priority: 8,
  description: 40
} as const

interface TasksTabProps {
  tasks: Task[]
  onRefresh: () => void
  t: Theme
}

export function TasksTab({ tasks, onRefresh, t }: TasksTabProps) {
  const [selected, setSelected] = useState(0)
  const [filterMode, setFilterMode] = useState(false)
  const [filterText, setFilterText] = useState('')
  const [statusPending, setStatusPending] = useState(false)

  const filtered = useMemo(() => {
    if (!filterText.trim()) {
      return tasks
    }

    const prefix = filterText.trim().toUpperCase()

    return tasks.filter(task => task.project.toUpperCase().startsWith(prefix))
  }, [filterText, tasks])

  const { items, offset } = windowItems(filtered, selected, VISIBLE)

  useInput((input, key) => {
    if (filterMode) {
      if (key.escape) {
        setFilterMode(false)
        setFilterText('')
        setSelected(0)
        return
      }

      if (key.return) {
        setFilterMode(false)
        return
      }

      if (key.backspace || key.delete) {
        setFilterText(v => v.slice(0, -1))
        setSelected(0)
        return
      }

      if (input && input.length === 1 && !key.ctrl && !key.meta) {
        setFilterText(v => v + input)
        setSelected(0)
      }

      return
    }

    if (input === 'f') {
      setFilterMode(true)
      return
    }

    if (key.upArrow) {
      setSelected(v => Math.max(0, v - 1))
      return
    }

    if (key.downArrow) {
      setSelected(v => Math.min(filtered.length - 1, v + 1))
      return
    }

    if (input === 's') {
      setStatusPending(true)
      return
    }

    if (key.return && statusPending && filtered[selected]) {
      const task = filtered[selected]!

      toggleTaskStatus(task.id, task.status)
      setStatusPending(false)
      onRefresh()
      return
    }

    if (statusPending && !key.return) {
      setStatusPending(false)
    }
  })

  if (!tasks.length) {
    return <Text color={t.color.muted}>No items found</Text>
  }

  return (
    <Box flexDirection="column">
      {filterMode ? (
        <Text color={t.color.warn}>
          Filter project prefix: {filterText || '_'} (Enter apply, Esc clear)
        </Text>
      ) : (
        <Text color={t.color.muted}>
          f filter | s then Enter toggle done/todo{statusPending ? ' (confirm Enter)' : ''}
        </Text>
      )}
      <Header t={t} />
      <Text color={t.color.border}>{'─'.repeat(96)}</Text>
      {items.map((task, idx) => {
        const row = offset + idx
        const active = row === selected

        return (
          <Text key={task.id} color={active ? t.color.primary : t.color.text}>
            {pad(task.id.slice(0, 26), COLS.id)}
            {pad(task.project, COLS.project)}
            {pad(task.status, COLS.status)}
            {pad(task.priority, COLS.priority)}
            {task.description.slice(0, COLS.description)}
          </Text>
        )
      })}
      {filtered.length > VISIBLE ? (
        <Text color={t.color.muted}>
          {selected + 1}/{filtered.length}
        </Text>
      ) : null}
      {!filtered.length ? <Text color={t.color.muted}>No items found</Text> : null}
    </Box>
  )
}

function Header({ t }: { t: Theme }) {
  return (
    <Text bold color={t.color.label}>
      {pad('ID', COLS.id)}
      {pad('Project', COLS.project)}
      {pad('Status', COLS.status)}
      {pad('Priority', COLS.priority)}
      Description
    </Text>
  )
}

function pad(text: string, width: number): string {
  return text.padEnd(width, ' ').slice(0, width)
}
