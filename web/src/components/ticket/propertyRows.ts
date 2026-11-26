// The rows of a ticket's properties in the groups both its forms list (`PropertyGroups.vue`), in
// one order and words.

export interface Row {
  key: string
  label: string
  placeholder?: string
  /** Shown on hover, while the value is empty. */
  hint?: string
  /** Likewise, in the New ticket form only. */
  newHint?: string
  /** Set in the code face, a value that ends in an ellipsis with all of it on hover. */
  code?: boolean
  date?: boolean
  /** A row of one form only. */
  only?: 'create' | 'edit'
  /** Folded under the group's "Tests and parallel", which opens while one of them is set (CF-1206). */
  fold?: boolean
}

export const GROUPS: { title: string; rows: Row[] }[] = [
  {
    title: 'Planning',
    rows: [
      { key: 'repository', label: 'Repository', only: 'create' },
      { key: 'stage', label: 'Stage', only: 'edit' },
      { key: 'type', label: 'Type' },
      { key: 'priority', label: 'Priority' },
      { key: 'due', label: 'Due', placeholder: 'none', date: true },
      { key: 'assignee', label: 'Assignee', placeholder: 'unassigned' },
      { key: 'labels', label: 'Labels', placeholder: 'none', newHint: 'Comma separated' },
      { key: 'blocked', label: 'Blocked', placeholder: 'not blocked' },
    ],
  },
  {
    title: 'Relations',
    rows: [
      { key: 'parent', label: 'Parent', placeholder: 'none', newHint: 'A ticket id', code: true },
      {
        key: 'blocked_by',
        label: 'Blocked by',
        placeholder: 'none',
        newHint: 'Ticket ids, comma separated',
        code: true,
      },
      {
        key: 'caused_by',
        label: 'Caused by',
        placeholder: 'none',
        newHint: 'The merged tickets this bug is a defect of, comma separated',
        code: true,
      },
    ],
  },
  {
    title: 'Code',
    rows: [
      { key: 'branch', label: 'Branch', code: true },
      {
        key: 'pages',
        label: 'Pages',
        placeholder: 'none',
        newHint: 'Board paths its captures show, comma separated',
        code: true,
      },
      {
        key: 'e2e',
        label: 'E2E tests',
        placeholder: 'none',
        newHint: 'File patterns, comma separated',
        code: true,
        fold: true,
      },
      {
        key: 'tests',
        label: 'Unit tests',
        placeholder: 'none',
        newHint: 'File patterns, comma separated',
        code: true,
        fold: true,
      },
      { key: 'parallel', label: 'Parallel', fold: true },
    ],
  },
  {
    title: 'Agent',
    rows: [{ key: 'budget', label: 'Budget', hint: 'Dollars agents may spend on this ticket' }],
  },
  { title: 'Origin', rows: [{ key: 'source', label: 'Source', placeholder: 'none', code: true }] },
]
