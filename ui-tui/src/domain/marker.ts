import { readFileSync } from 'node:fs'
import { join } from 'node:path'

export interface BatchInfo {
  batchSize: number
  batchesSummarized: number
}

export function parseBatchInfo(cwd: string): BatchInfo | null {
  try {
    const raw = readFileSync(join(cwd, '.tim-project'), 'utf-8')
    const parsed = JSON.parse(raw) as { batch_size?: number; batches_summarized?: number }
    const batchSize = parsed?.batch_size ?? 0
    if (batchSize <= 0) return null
    return {
      batchSize,
      batchesSummarized: parsed?.batches_summarized ?? 0
    }
  } catch {
    return null
  }
}
