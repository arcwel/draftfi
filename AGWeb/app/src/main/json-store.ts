import { app } from 'electron'
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'

/**
 * Minimal atomic JSON persistence in the app's userData directory.
 * Writes go to a temp file first so a crash mid-write can't corrupt state.
 */
export class JsonStore<T> {
  private readonly file: string

  constructor(
    name: string,
    private readonly defaults: T
  ) {
    this.file = join(app.getPath('userData'), `${name}.json`)
  }

  read(): T {
    try {
      const raw = readFileSync(this.file, 'utf8')
      return { ...this.defaults, ...(JSON.parse(raw) as T) }
    } catch {
      return this.defaults
    }
  }

  write(value: T): void {
    const tmp = `${this.file}.tmp`
    mkdirSync(dirname(this.file), { recursive: true })
    writeFileSync(tmp, JSON.stringify(value, null, 2), 'utf8')
    renameSync(tmp, this.file)
  }
}
