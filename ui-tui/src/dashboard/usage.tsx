import { Box, Text } from '@hermes/ink'

import type { Theme } from '../theme.js'

import type { UsageCard } from './data.js'

interface UsageTabProps {
  cards: UsageCard[]
  t: Theme
}

export function UsageTab({ cards, t }: UsageTabProps) {
  if (!cards.length) {
    return <Text color={t.color.muted}>No items found</Text>
  }

  const rows: UsageCard[][] = []

  for (let i = 0; i < cards.length; i += 2) {
    rows.push(cards.slice(i, i + 2))
  }

  return (
    <Box flexDirection="column">
      <Text color={t.color.muted}>Health snapshot</Text>
      {rows.map((pair, rowIdx) => (
        <Box key={rowIdx} marginTop={1}>
          {pair.map(card => (
            <Box
              key={card.label}
              borderStyle="round"
              borderColor={levelColor(card.level, t)}
              flexDirection="column"
              marginRight={2}
              paddingX={2}
              paddingY={1}
              width={34}
            >
              <Text color={t.color.label}>{card.label}</Text>
              <Text bold color={levelColor(card.level, t)}>
                {card.value}
              </Text>
            </Box>
          ))}
        </Box>
      ))}
    </Box>
  )
}

function levelColor(level: UsageCard['level'], t: Theme): string {
  if (level === 'error') {
    return t.color.error
  }

  if (level === 'warn') {
    return t.color.warn
  }

  return t.color.ok
}
