import { Box, Text, useInput } from '@hermes/ink'
import { useState } from 'react'

import type { Theme } from '../theme.js'

import { captureTmuxPane, killTmuxSession, type TmuxSession } from './data.js'
import { windowItems } from '../components/overlayControls.js'

const VISIBLE = 12

interface TmuxTabProps {
  sessions: TmuxSession[]
  onRefresh: () => void
  t: Theme
}

export function TmuxTab({ sessions, onRefresh, t }: TmuxTabProps) {
  const [selected, setSelected] = useState(0)
  const [preview, setPreview] = useState('')
  const [confirmKill, setConfirmKill] = useState(false)
  const [error, setError] = useState('')

  const { items, offset } = windowItems(sessions, selected, VISIBLE)
  const current = sessions[selected]

  useInput((input, key) => {
    if (confirmKill) {
      if (input === 'y' && current) {
        try {
          killTmuxSession(current.name)
          setPreview('')
          setConfirmKill(false)
          onRefresh()
        } catch (err) {
          setError(err instanceof Error ? err.message : String(err))
          setConfirmKill(false)
        }
      } else if (input === 'n' || key.escape) {
        setConfirmKill(false)
      }

      return
    }

    if (key.upArrow) {
      setSelected(v => Math.max(0, v - 1))
      setPreview('')
      return
    }

    if (key.downArrow) {
      setSelected(v => Math.min(sessions.length - 1, v + 1))
      setPreview('')
      return
    }

    if (key.return && current) {
      try {
        setError('')
        setPreview(captureTmuxPane(current.name))
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      }

      return
    }

    if (input === 'd' && current) {
      setConfirmKill(true)
    }
  })

  if (!sessions.length) {
    return <Text color={t.color.muted}>No items found</Text>
  }

  return (
    <Box flexDirection="column">
      <Text color={t.color.muted}>Enter preview | d kill session (y/n confirm)</Text>
      {error ? <Text color={t.color.error}>Error: {error}</Text> : null}
      {confirmKill && current ? (
        <Text color={t.color.warn}>
          Kill session {current.name}? y/n
        </Text>
      ) : null}
      {items.map((session, idx) => {
        const row = offset + idx
        const active = row === selected

        return (
          <Text key={session.name} color={active ? t.color.primary : t.color.text}>
            {active ? '▸ ' : '  '}
            {session.name.padEnd(24)} {String(session.windows).padStart(2)} windows {session.created}
          </Text>
        )
      })}
      {preview ? (
        <Box flexDirection="column" marginTop={1}>
          <Text color={t.color.label}>Last 20 lines — {current?.name}</Text>
          {preview.split('\n').map((line, i) => (
            <Text key={`${i}-${line}`} color={t.color.muted}>
              {line || ' '}
            </Text>
          ))}
        </Box>
      ) : null}
    </Box>
  )
}
