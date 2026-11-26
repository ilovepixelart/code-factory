import { expect, test } from 'vitest'
import { followTemplate } from '@/lib/templates'

test('follows_template_only_while_untouched', () => {
  expect(followTemplate('## Goal\n', '## Goal\n', '## Steps\n')).toBe('## Steps\n')
  expect(followTemplate('', '', '## Steps\n')).toBe('## Steps\n')
  expect(followTemplate('## Goal\nmine', '## Goal\n', '## Steps\n')).toBe('## Goal\nmine')
  expect(followTemplate('written', '', '## Steps\n')).toBe('written')
})
