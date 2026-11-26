// What a permission request would do, read from the text the board keeps of it: a shell command as
// written, any other call as its JSON, which the board cuts at 300 characters.

export type Payload =
  | { kind: 'code'; text: string }
  | {
      kind: 'call'
      /** A `content` string, Markdown in every board and file tool. */
      markdown: string
      /** A `command` string. */
      command: string
      fields: [string, string][]
      cut: boolean
    }

// The closings a call cut inside a string, after a value or inside a nested object needs.
const CLOSINGS = ['', '"}', '}', '"}}', '}}']

function parsed(text: string): { value: unknown; cut: boolean } | null {
  for (const closing of CLOSINGS) {
    try {
      return { value: JSON.parse(text + closing), cut: closing !== '' }
    } catch {
      // the next closing
    }
  }
  return null
}

export function readPayload(tool: string, summary: string): Payload {
  if (tool === 'Bash') return { kind: 'code', text: summary }
  const read = parsed(summary)
  if (!read) return { kind: 'code', text: summary }
  const { value, cut } = read
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return { kind: 'code', text: JSON.stringify(value, null, 2) }
  }
  const call: Payload = { kind: 'call', markdown: '', command: '', fields: [], cut }
  for (const [key, field] of Object.entries(value)) {
    if (key === 'content' && typeof field === 'string') call.markdown = field
    else if (key === 'command' && typeof field === 'string') call.command = field
    else call.fields.push([key, typeof field === 'string' ? field : JSON.stringify(field)])
  }
  return call
}
