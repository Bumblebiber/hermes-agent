import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { type BatchInfo, parseBatchInfo } from '../domain/marker.js'

function formatBatchSummary(info: BatchInfo | null): string | null {
  return info ? `${info.batchesSummarized}/${info.batchSize}` : null
}

describe('parseBatchInfo', () => {
  let tmpRoot: string

  beforeEach(() => {
    tmpRoot = mkdtempSync(join(tmpdir(), 'marker-batch-'))
  })

  afterEach(() => {
    rmSync(tmpRoot, { recursive: true, force: true })
  })

  it('returns {batchSize:5, batchesSummarized:0} for default with batch_size:5', () => {
    writeFileSync(join(tmpRoot, '.tim-project'), JSON.stringify({ batch_size: 5 }))
    expect(parseBatchInfo(tmpRoot)).toEqual({ batchSize: 5, batchesSummarized: 0 })
  })

  it('returns null if no .tim-project', () => {
    const bare = join(tmpRoot, 'bare')
    mkdirSync(bare, { recursive: true })
    expect(parseBatchInfo(bare)).toBe(null)
  })

  it('returns null if batch_size: 0', () => {
    writeFileSync(join(tmpRoot, '.tim-project'), JSON.stringify({ batch_size: 0 }))
    expect(parseBatchInfo(tmpRoot)).toBe(null)
  })

  it('returns null if batch_size: -1', () => {
    writeFileSync(join(tmpRoot, '.tim-project'), JSON.stringify({ batch_size: -1 }))
    expect(parseBatchInfo(tmpRoot)).toBe(null)
  })

  it('returns {batchSize:5, batchesSummarized:2} when batches_summarized:2', () => {
    writeFileSync(
      join(tmpRoot, '.tim-project'),
      JSON.stringify({ batch_size: 5, batches_summarized: 2 })
    )
    expect(parseBatchInfo(tmpRoot)).toEqual({ batchSize: 5, batchesSummarized: 2 })
  })
})

describe('batch summary display data flow', () => {
  it('formats parseBatchInfo output as statusline strings', () => {
    expect(formatBatchSummary({ batchSize: 5, batchesSummarized: 0 })).toBe('0/5')
    expect(formatBatchSummary({ batchSize: 5, batchesSummarized: 2 })).toBe('2/5')
    expect(formatBatchSummary(null)).toBe(null)
  })
})
