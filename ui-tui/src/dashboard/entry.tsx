#!/usr/bin/env node
import { render } from '@hermes/ink'

import { Dashboard } from './Dashboard.js'
import { setupGracefulExit } from '../lib/gracefulExit.js'
import { resetTerminalModes } from '../lib/terminalModes.js'

if (!process.stdin.isTTY) {
  console.log('hermes-dashboard: no TTY')
  process.exit(0)
}

resetTerminalModes()
process.stdout.write('\x1b[2J\x1b[H\x1b[3J')

setupGracefulExit({
  cleanups: [() => resetTerminalModes()],
  onSignal: signal => {
    resetTerminalModes()
    process.stderr.write(`hermes-dashboard: received ${signal}\n`)
  }
})

render(<Dashboard />, { exitOnCtrlC: false })
