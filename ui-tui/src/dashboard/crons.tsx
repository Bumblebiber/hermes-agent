import { Box, Text, useInput } from '@hermes/ink'
import { useState } from 'react'

import type { Theme } from '../theme.js'

import { type CronJob, runCronNow, toggleCronPause } from './data.js'
import { windowItems } from '../components/overlayControls.js'

const VISIBLE = 12

interface CronsTabProps {
  crons: CronJob[]
  onRefresh: () => void
  t: Theme
}

export function CronsTab({ crons, onRefresh, t }: CronsTabProps) {
  const [selected, setSelected] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const { items, offset } = windowItems(crons, selected, VISIBLE)
  const current = crons[selected]

  useInput((input, key) => {
    if (busy || !current) {
      return
    }

    if (key.upArrow) {
      setSelected(v => Math.max(0, v - 1))
      return
    }

    if (key.downArrow) {
      setSelected(v => Math.min(crons.length - 1, v + 1))
      return
    }

    if (input === 'r') {
      setBusy(true)
      setError('')

      try {
        runCronNow(current.id)
        onRefresh()
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy(false)
      }

      return
    }

    if (input === 'p') {
      setBusy(true)
      setError('')

      try {
        toggleCronPause(current.id, current.status === 'paused')
        onRefresh()
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setBusy(false)
      }
    }
  })

  if (!crons.length) {
    return <Text color={t.color.muted}>No items found</Text>
  }

  return (
    <Box flexDirection="column">
      <Text color={t.color.muted}>r run now | p pause/resume</Text>
      {busy ? <Text color={t.color.warn}>Working...</Text> : null}
      {error ? <Text color={t.color.error}>Error: {error}</Text> : null}
      <Text bold color={t.color.label}>
        {'Name'.padEnd(28)} {'Schedule'.padEnd(16)} {'Status'.padEnd(12)} Last Run
      </Text>
      <Text color={t.color.border}>{'─'.repeat(80)}</Text>
      {items.map((job, idx) => {
        const row = offset + idx
        const active = row === selected

        return (
          <Text key={job.id} color={active ? t.color.primary : t.color.text}>
            {active ? '▸ ' : '  '}
            {job.name.slice(0, 26).padEnd(26)} {job.schedule.slice(0, 14).padEnd(14)}{' '}
            {job.status.padEnd(10)} {job.lastRun.slice(0, 24)}
          </Text>
        )
      })}
    </Box>
  )
}
