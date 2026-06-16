import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { KNOWN_PROJECTS, formatProjectName, parseProjectLabel } from '../domain/projectName.js'

describe('statusline project name', () => {
  describe('KNOWN_PROJECTS map', () => {
    it('P0063 → TIM', () => {
      expect(KNOWN_PROJECTS.P0063).toBe('TIM')
    })

    it('P0064 → Hermes Agent', () => {
      expect(KNOWN_PROJECTS.P0064).toBe('Hermes Agent')
    })

    it('P0000 → Inbox', () => {
      expect(KNOWN_PROJECTS.P0000).toBe('Inbox')
    })

    it('P0048 → its-over-9k', () => {
      expect(KNOWN_PROJECTS.P0048).toBe('its-over-9k')
    })

    it('P0062 → PM Workflow', () => {
      expect(KNOWN_PROJECTS.P0062).toBe('PM Workflow')
    })
  })

  describe('formatProjectName truncation', () => {
    it('name exactly 20 chars → no ellipsis', () => {
      expect(formatProjectName('P9999')).toBe('Phantom')
      const twenty = 'a'.repeat(20)
      expect(formatProjectName(`__${twenty}`)).toBe('no project')
      expect(formatProjectName('P0064')).toBe('Hermes Agent')
      expect('Hermes Agent'.length).toBeLessThanOrEqual(20)
    })

    it('name 21 chars+ → truncate with …', () => {
      const long = 'x'.repeat(21)
      KNOWN_PROJECTS.__TEST_LONG__ = long
      expect(formatProjectName('__TEST_LONG__')).toBe(`${'x'.repeat(20)}…`)
      delete KNOWN_PROJECTS.__TEST_LONG__
    })

    it('"no project" fallback stays "no project"', () => {
      expect(formatProjectName(null)).toBe('no project')
      expect(formatProjectName('P9999')).not.toBe('no project')
    })
  })

  describe('fallbacks', () => {
    let tmpRoot: string

    beforeEach(() => {
      tmpRoot = mkdtempSync(join(tmpdir(), 'statusline-project-name-'))
    })

    afterEach(() => {
      rmSync(tmpRoot, { recursive: true, force: true })
    })

    it('unknown label → "no project"', () => {
      writeFileSync(join(tmpRoot, '.tim-project'), JSON.stringify({ project: 'P9998' }))
      expect(parseProjectLabel(tmpRoot)).toBe('P9998')
      expect(formatProjectName('P9998')).toBe('no project')
    })

    it('no .tim-project → null label → "no project"', () => {
      const bare = join(tmpRoot, 'bare')
      mkdirSync(bare, { recursive: true })
      expect(parseProjectLabel(bare)).toBe(null)
      expect(formatProjectName(null)).toBe('no project')
    })

    it('parses JSON .tim-project project field', () => {
      writeFileSync(join(tmpRoot, '.tim-project'), JSON.stringify({ project: 'P0063' }))
      expect(parseProjectLabel(tmpRoot)).toBe('P0063')
      expect(formatProjectName('P0063')).toBe('TIM')
    })
  })
})
