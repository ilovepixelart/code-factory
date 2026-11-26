<script setup lang="ts">
import { sentence } from '../../lib/format'
import { createReusableTemplate } from '@vueuse/core'
import { computed, type FunctionalComponent } from 'vue'
import { EVIDENCE_STAGE_HINT, PRIORITIES, STAGE_LABELS, STAGES, TYPES } from '../../lib/board'
import { ticketHref } from '../../lib/ticket'
import PropertyDate from './PropertyDate.vue'
import PropertyFold from './PropertyFold.vue'
import PropertyInput from './PropertyInput.vue'
import PropertyLabels from './PropertyLabels.vue'
import PropertySelect from './PropertySelect.vue'
import PropertyShown from './PropertyShown.vue'
import { GROUPS, type Row } from './propertyRows'
import { FieldGroup, FieldLegend, FieldSet } from '@/components/ui/field'

// The properties of a ticket in the groups both its forms list, in one order and words: the New
// ticket form (`create`) and the ticket's edit form (`edit`), where Stage replaces Repository and
// Source is read only (CF-1201), on one line and selected whole by one click (CF-1293).
const {
  prefix,
  mode,
  repositories = [],
  repository = '',
  stageEmpty = 'auto',
  branch = 'set by agents',
  budget = 'no budget',
  source = '',
  errors = {},
  folded,
} = defineProps<{
  /** The fields' ids start with it. */
  prefix: string
  mode: 'create' | 'edit'
  repositories?: string[]
  /** The repository the ticket is in, which its Caused by links are in. */
  repository?: string
  stageEmpty?: string
  /** What an empty Branch and Budget say. */
  branch?: string
  budget?: string
  source?: string
  /** The board's reason for each refused field, by field. */
  errors?: Partial<Record<string, string>>
  /** Repository, Type, Priority and Labels out front and the rest folded under "More
   *  properties" (New ticket). */
  folded?: boolean
}>()
const emit = defineEmits<{ change: [field: string] }>()
// The fields as typed, changed in place; given as `:model-value`.
const model = defineModel<Record<string, string | undefined>>({ required: true })
const bind = (key: string) => ({
  modelValue: model.value[key] ?? '',
  'onUpdate:modelValue': (value: string) => (model.value[key] = value),
})

// More than one starts that many Build runs, each by another agent (CF-1106).
const PARALLEL = ['2', '3', '4'] as const

// Types and priorities read in sentence case; what is saved stays as it is.
const TYPE_NAMES = Object.fromEntries(TYPES.map((t) => [t, sentence(t)])) as Record<
  (typeof TYPES)[number],
  string
>
const PRIORITY_NAMES = Object.fromEntries(PRIORITIES.map((p) => [p, sentence(p)])) as Record<
  (typeof PRIORITIES)[number],
  string
>

// What a new ticket needs, drawn out front of the fold: where it goes and what it is.
const FRONT = ['repository', 'type', 'priority', 'labels']
// One row, drawn the same out front and in its group.
const [DefineRow, PropertyRow] = createReusableTemplate<{ row: Row }>()

// Caused by is a bug's property; Source is typed in a new ticket and only read after. Folded, the
// front rows are drawn out front instead.
const groups = computed(() =>
  GROUPS.map(({ title, rows }) => {
    const shown = rows.filter(
      (row) =>
        (!row.only || row.only === mode) &&
        (row.key !== 'caused_by' || model.value.type === 'bug') &&
        !(folded && FRONT.includes(row.key)),
    )
    const tucked = shown.filter((row) => row.fold)
    return {
      title,
      chunks: [
        { fold: false, open: false, rows: shown.filter((row) => !row.fold) },
        { fold: true, open: tucked.some((row) => model.value[row.key]), rows: tucked },
      ].filter((chunk) => chunk.rows.length),
    }
  }),
)
// Out front, in FRONT's order, the rows a folded form draws before its fold.
const front = computed(() =>
  folded
    ? FRONT.map((key) => GROUPS.flatMap(({ rows }) => rows).find((row) => row.key === key)).filter(
        (row): row is Row => row !== undefined,
      )
    : [],
)
// Like every fold, "More properties" does not hide a value set: it opens while one is, the type a
// new ticket starts with aside.
const foldOpen = computed(() =>
  groups.value.some(({ chunks }) =>
    chunks.some(({ rows }) =>
      rows.some((row) =>
        row.key === 'type' ? model.value.type !== 'feature' : model.value[row.key],
      ),
    ),
  ),
)

const placeholderOf = (row: Row): string =>
  row.key === 'branch' ? branch : row.key === 'budget' ? budget : (row.placeholder ?? '')
// A written code value carries all of it as its tooltip; an empty one says what it takes.
const titleOf = (row: Row): string => {
  const value = model.value[row.key] ?? ''
  return row.code && value ? value : (row.hint ?? (mode === 'create' ? row.newHint : '') ?? '')
}
// Being edited, a row is quiet until it is changed (PropertyShown); a new ticket shows its controls.
const Bare: FunctionalComponent = (_, { slots }) => slots.default?.()
const EMPTY: Partial<Record<string, string>> = { priority: 'none', parallel: '1' }
function shownOf(row: Row): Record<string, unknown> {
  if (mode !== 'edit') return {}
  const raw = row.key === 'source' ? source : (model.value[row.key] ?? '')
  const value =
    row.key === 'stage' && raw
      ? STAGE_LABELS[raw as keyof typeof STAGE_LABELS]
      : row.key === 'type' || row.key === 'priority'
        ? sentence(raw)
        : raw
  return {
    id: `${prefix}-${row.key}`,
    label: row.label,
    value,
    empty: row.key === 'stage' ? stageEmpty : (EMPTY[row.key] ?? (placeholderOf(row) || 'none')),
    code: Boolean(row.code) || row.key === 'source',
    readonly: row.key === 'source',
    invalid: Boolean(errors[row.key]),
  }
}
const listOf = (text: string | undefined): string[] =>
  (text ?? '')
    .split(',')
    .map((id) => id.trim())
    .filter(Boolean)
const linked = computed(() => listOf(mode === 'edit' ? model.value.caused_by : ''))
</script>

<template>
  <DefineRow v-slot="{ row }">
    <component :is="mode === 'edit' ? PropertyShown : Bare" v-bind="shownOf(row)">
      <PropertySelect
        v-if="row.key === 'repository'"
        :id="`${prefix}-repository`"
        key="repository"
        v-bind="bind('repository')"
        label="Repository"
        :error="errors[row.key]"
        :options="repositories"
        name="repository"
        required
      />
      <PropertySelect
        v-else-if="row.key === 'stage'"
        :id="`${prefix}-stage`"
        key="stage"
        v-bind="bind('stage')"
        label="Stage"
        :error="errors[row.key]"
        :options="STAGES"
        :empty="stageEmpty"
        :hint="EVIDENCE_STAGE_HINT"
        :names="STAGE_LABELS"
        name="stage"
        @change="emit('change', 'stage')"
      />
      <PropertySelect
        v-else-if="row.key === 'type'"
        :id="`${prefix}-type`"
        key="type"
        v-bind="bind('type')"
        label="Type"
        :error="errors[row.key]"
        :options="TYPES"
        :names="TYPE_NAMES"
        name="type"
        @change="emit('change', 'type')"
      />
      <PropertySelect
        v-else-if="row.key === 'priority'"
        :id="`${prefix}-priority`"
        key="priority"
        v-bind="bind('priority')"
        label="Priority"
        :error="errors[row.key]"
        :options="PRIORITIES"
        :names="PRIORITY_NAMES"
        empty="none"
        name="priority"
        @change="emit('change', 'priority')"
      />
      <PropertySelect
        v-else-if="row.key === 'parallel'"
        :id="`${prefix}-parallel`"
        key="parallel"
        v-bind="bind('parallel')"
        label="Parallel"
        :error="errors[row.key]"
        :options="PARALLEL"
        empty="1"
        hint="One Build run; 2 to 4 start that many, each by another agent"
        name="parallel"
        @change="emit('change', 'parallel')"
      />
      <PropertyInput
        v-else-if="row.key === 'source' && mode === 'edit'"
        :id="`${prefix}-source`"
        key="source"
        :model-value="source"
        label="Source"
        name="source"
        class="font-mono placeholder:font-sans"
        placeholder="none"
        readonly
      />
      <PropertyDate
        v-else-if="row.date"
        :id="`${prefix}-${row.key}`"
        v-bind="bind(row.key)"
        :label="row.label"
        :error="errors[row.key]"
        :placeholder="placeholderOf(row)"
        @change="emit('change', row.key)"
      />
      <PropertyLabels
        v-else-if="row.key === 'labels'"
        :id="`${prefix}-${row.key}`"
        v-bind="bind(row.key)"
        :label="row.label"
        :error="errors[row.key]"
        :placeholder="placeholderOf(row)"
        :hint="titleOf(row)"
        @change="emit('change', row.key)"
      />
      <PropertyInput
        v-else
        :id="`${prefix}-${row.key}`"
        key="input"
        v-bind="bind(row.key)"
        :label="row.label"
        :error="errors[row.key]"
        :name="row.key"
        :class="[
          row.code ? 'font-mono placeholder:font-sans' : '',
          row.key === 'budget' ? 'tabular-nums' : '',
        ]"
        :decimal="row.key === 'budget'"
        :placeholder="placeholderOf(row)"
        :title="titleOf(row)"
        @change="emit('change', row.key)"
      />
    </component>
    <p v-if="row.key === 'caused_by' && linked.length" class="flex flex-wrap gap-x-2 pb-1 text-sm">
      <RouterLink
        v-for="other in linked"
        :key="other"
        :to="ticketHref(repository, other)"
        class="underline-offset-4 hover:underline font-mono text-sm"
        >{{ other }}</RouterLink
      >
    </p>
  </DefineRow>
  <FieldGroup class="gap-5">
    <div
      v-if="front.length"
      class="grid grid-cols-1 gap-4 @md/field-group:grid-cols-2"
      data-properties-front
    >
      <PropertyRow v-for="row in front" :key="row.key" :row="row" />
    </div>
    <PropertyFold
      :fold="folded"
      :open="foldOpen"
      label="More properties"
      name="More properties"
      spacing="mt-3 gap-5"
    >
      <FieldSet v-for="group in groups" :key="group.title" class="min-w-0 gap-3">
        <FieldLegend variant="label">{{ group.title }}</FieldLegend>
        <PropertyFold
          v-for="chunk in group.chunks"
          :key="chunk.fold ? 'fold' : 'rows'"
          :fold="chunk.fold"
          :open="chunk.open"
        >
          <template v-for="row in chunk.rows" :key="row.key">
            <PropertyRow :row="row" />
          </template>
        </PropertyFold>
      </FieldSet>
    </PropertyFold>
  </FieldGroup>
</template>
