import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

const web = resolve(__dirname, '..')
const bin = (name: string) => join(web, 'node_modules', '.bin', name)
const scratchRoot = join(web, 'node_modules', '.tmp')
const plantedLine = 'const planted: number = "text"'
const planted = `${plantedLine}\nexport { planted }\n`
const folders: string[] = []

function project(files: Record<string, string>, include: string[]): string {
  mkdirSync(scratchRoot, { recursive: true })
  const dir = mkdtempSync(join(scratchRoot, 'cf-851-'))
  folders.push(dir)
  const compilerOptions = { strict: true, noEmit: true, types: [] }
  writeFileSync(join(dir, 'tsconfig.json'), JSON.stringify({ compilerOptions, include }))
  for (const [name, text] of Object.entries(files)) writeFileSync(join(dir, name), text)
  return dir
}

function run(tool: string, args: string[]) {
  const { status, stdout } = spawnSync(bin(tool), args, { encoding: 'utf8', cwd: web })
  return { status, stdout }
}

describe('the two TypeScript compilers', () => {
  afterEach(() => {
    for (const dir of folders.splice(0)) rmSync(dir, { recursive: true, force: true })
  })

  // CF-851-R1
  it('the_tsc_binary_is_typescript_7', () => {
    expect(run('tsc', ['--version']).stdout.trim()).toBe('Version 7.0.2')
  })

  // CF-851-R2
  it('the_typecheck_script_runs_both_compilers', () => {
    const { scripts } = JSON.parse(readFileSync(join(web, 'package.json'), 'utf8')) as {
      scripts: { typecheck: string }
    }
    expect(scripts.typecheck).toBe('tsc --build tsconfig.ts7.json && vue-tsc --build')
  })

  // CF-851-R2
  it('typescript_7_reports_a_type_error', () => {
    const dir = project({ 'planted.ts': planted }, ['*.ts'])
    const { status, stdout } = run('tsc', ['-p', dir])
    expect(status).not.toBe(0)
    expect(stdout).toContain('TS2322')
  })

  // CF-851-R2
  it('vue_tsc_reports_a_type_error_in_a_vue_file', () => {
    const sfc = `<script setup lang="ts">\n${plantedLine}\nvoid planted\n</script>\n`
    const dir = project({ 'Planted.vue': sfc }, ['*.vue'])
    const { status, stdout } = run('vue-tsc', ['-p', dir])
    expect(status).not.toBe(0)
    expect(stdout).toContain('Planted.vue')
    expect(stdout).toContain('TS2322')
  }, 60_000)
})
