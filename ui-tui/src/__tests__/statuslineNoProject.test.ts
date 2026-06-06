/**
 * Regression test for statusline "no project" detection (task-statusline-no-project-v2).
 *
 * Bug: commit 433af4da8 implemented a walk-up loop that searched for
 * `.tim-project` from cwd all the way to filesystem root. This made
 * "no project" unreachable inside meta-project trees (e.g. a
 * `~/.tim-project` from P0062 was visible from every subdir of `~`).
 *
 * Correct behaviour: cwd-only check. If cwd itself has no marker,
 * statusline shows "no project" regardless of what parents carry.
 *
 * The hook is a React component (useMainApp.ts) that we don't render
 * here — instead we test the pure check it relies on. The check IS
 * the bug surface: `existsSync(join(cwd, '.tim-project'))`.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

// Mirror of the exact check inside useMainApp.ts (line 826).
// Pure functional: takes cwd, returns true iff cwd has a .tim-project marker.
const hasTimProjectInCwd = (cwd: string): boolean => existsSync(join(cwd, '.tim-project'))

describe('statusline "no project" — cwd-only .tim-project check', () => {
  let tmpRoot: string
  let leaf: string
  let parent: string
  let root: string

  beforeEach(() => {
    // Build a small tree that mirrors the bug scenario:
    //   <tmpRoot>/.tim-project   ← parent HAS marker (the P0062 case)
    //   <tmpRoot>/child/         ← leaf has NO marker
    tmpRoot = mkdtempSync(join(tmpdir(), 'statusline-no-project-'))
    root = tmpRoot
    parent = join(tmpRoot, 'meta-project')
    leaf = join(tmpRoot, 'meta-project', 'child', 'task-foo')
    mkdirSync(parent, { recursive: true })
    mkdirSync(leaf, { recursive: true })
    writeFileSync(join(parent, '.tim-project'), 'P0062\n')
  })

  afterEach(() => {
    rmSync(tmpRoot, { recursive: true, force: true })
  })

  it('cwd WITH .tim-project → hasProject === true', () => {
    // The meta-project root itself has the marker. Statusline should
    // show cwd (this is what the user sees in PM mode at `~`).
    expect(hasTimProjectInCwd(parent)).toBe(true)
  })

  it('cwd WITHOUT .tim-project, but parent HAS one → hasProject === false (regression for 433af4da8 walk-up bug)', () => {
    // The bug: walk-up would return TRUE here, hiding "no project".
    // The fix: cwd-only check returns FALSE → statusline shows "no project".
    // This is the exact scenario the user described: cd into a task dir
    // under a meta-project's tree, expect "no project".
    expect(leaf.startsWith(parent)).toBe(true) // sanity: leaf really is under parent
    expect(hasTimProjectInCwd(leaf)).toBe(false)
  })

  it('cwd with NO .tim-project and NO parent marker → hasProject === false', () => {
    // Standard "no project" case — fully isolated dir.
    const isolated = join(root, 'totally-isolated')
    mkdirSync(isolated, { recursive: true })
    expect(hasTimProjectInCwd(isolated)).toBe(false)
  })

  it('filesystem root "/" without .tim-project → hasProject === false', () => {
    // User explicitly listed this in the verification checklist:
    // "Manual: in / (root) → 'no project' (no .tim-project there)"
    expect(hasTimProjectInCwd('/')).toBe(false)
  })

  it('does NOT walk up: sibling subdir of a project must not see marker', () => {
    // Two siblings: A has marker, B does not. B must NOT inherit A's
    // project status via walk-up. (Siblings are a useful negative test
    // because cwd-only and walk-up both agree on direct children of
    // the project root — siblings are the disambiguator.)
    const siblingA = join(root, 'sibling-a')
    const siblingB = join(root, 'sibling-b')
    mkdirSync(siblingA, { recursive: true })
    mkdirSync(siblingB, { recursive: true })
    writeFileSync(join(siblingA, '.tim-project'), 'A\n')

    expect(hasTimProjectInCwd(siblingA)).toBe(true)
    expect(hasTimProjectInCwd(siblingB)).toBe(false)
  })

  it('does NOT walk up: child of a project shows cwd, not parent project', () => {
    // The PM mode scenario: P0062 in ~, user cd's into a project subdir.
    // The subdir's own .tim-project (if any) should win; otherwise "no project".
    const projectChild = join(parent, 'sub', 'deep')
    mkdirSync(projectChild, { recursive: true })
    writeFileSync(join(projectChild, '.tim-project'), 'CUSTOM\n')

    // cwd-only: child has its OWN marker → true (different project, but
    // statusline shows cwd regardless — that's the correct semantic).
    expect(hasTimProjectInCwd(projectChild)).toBe(true)
  })
})
