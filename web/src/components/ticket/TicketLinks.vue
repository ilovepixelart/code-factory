<script setup lang="ts">
import EmptyLine from '../EmptyLine.vue'
import SectionHeading from './SectionHeading.vue'
import { Cancel01Icon, PlusSignIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed, nextTick, ref, useTemplateRef, watch } from 'vue'
import { act } from '../../lib/actions'
import { STAGE_LABELS } from '../../lib/board'
import { announce, perform, refusalText } from '../../lib/notice'
import { ticketHref, type TicketView } from '../../lib/ticket'
import { useTicketForm } from './context'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Empty, EmptyDescription, EmptyHeader } from '@/components/ui/empty'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxViewport,
} from '@/components/ui/combobox'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { FieldError } from '@/components/ui/field'
import { Badge } from '@/components/ui/badge'

// The ticket's links by kind, and a combobox that finds a ticket to link.
const { repository, id, view } = defineProps<{
  repository: string
  id: string
  view: TicketView
}>()
// A link was added or removed and the views read again.
const emit = defineEmits<{ changed: [] }>()

const { busy, base, refresh, task, press, spins } = useTicketForm()

type LinkKind = 'parent' | 'child' | 'blocked_by' | 'blocks'
const LINK_KINDS: [LinkKind, string][] = [
  ['parent', 'Parent'],
  ['child', 'Child'],
  ['blocked_by', 'Blocked by'],
  ['blocks', 'Blocks'],
]
const linking = ref(false)
const linkKind = ref<LinkKind>('blocked_by')
const linkQuery = ref('')
const linkError = ref('')
const opener = useTemplateRef('opener')
const search = useTemplateRef<{ $el: HTMLElement }>('search')
const listOf = (text: unknown): string[] =>
  (typeof text === 'string' ? text : '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
// A ticket's column, '' for one the page does not know: a linked ticket's from its own
// repository, a match's from this one.
const stageOf = (other: string): string => {
  const stage = view.linked[other]?.stage ?? view.stages_by_id[other]
  return stage === undefined ? '' : STAGE_LABELS[stage]
}
// The ticket's links by kind, from the ticket and its view: what each group lists and removes.
const linked = computed<Record<LinkKind, string[]>>(() => {
  const link = view.link
  return {
    parent: link?.parent ? [link.parent] : [],
    child: link?.child_ids ?? [],
    blocked_by: listOf(view.ticket.blocked_by),
    blocks: link?.blocks ?? [],
  }
})
const linkGroups = computed(() =>
  (
    [
      ['parent', 'Parent'],
      ['child', 'Children'],
      ['blocked_by', 'Blocked by'],
      ['blocks', 'Blocks'],
    ] as [LinkKind, string][]
  ).filter(([kind]) => linked.value[kind].length),
)
// The repository's tickets a link of the chosen kind could name: not this one, not one already
// linked that way, matched by id or title.
const linkMatches = computed(() => {
  const query = linkQuery.value.trim().toLowerCase()
  const taken = new Set([id, ...linked.value[linkKind.value]])
  return Object.entries(view.titles)
    .filter(([other]) => !taken.has(other))
    .filter(
      ([other, title]) =>
        !query || other.toLowerCase().includes(query) || title.toLowerCase().includes(query),
    )
    .slice(0, 8)
})
watch([linkQuery, linkKind], () => {
  linkError.value = ''
})

// The picker takes the keyboard when it opens and gives it back to the button when it closes.
async function openLinking(): Promise<void> {
  linking.value = !linking.value
  linkQuery.value = ''
  linkError.value = ''
  if (!linking.value) return
  await nextTick()
  search.value?.$el.querySelector('input')?.focus()
}

function closeLinking(): void {
  linking.value = false
  void nextTick(() => opener.value?.$el.focus())
}

async function addLink(target: string | undefined): Promise<void> {
  if (!target || busy.value) return
  await task(async () => {
    try {
      announce(await act('POST', `${base.value}/links`, { kind: linkKind.value, target }))
      linkQuery.value = ''
      closeLinking()
      await refresh()
      emit('changed')
    } catch (error) {
      linkError.value = refusalText(error)
    }
  })
}

async function removeLink(kind: LinkKind, target: string): Promise<void> {
  await task(async () => {
    const link = `${encodeURIComponent(kind)}/${encodeURIComponent(target)}`
    await perform(() => act('DELETE', `${base.value}/links/${link}`), refresh)
    emit('changed')
  })
}

// The list is open while the picker is; a combobox closing (Escape, a click outside) closes it.
function picked(target: unknown): void {
  if (typeof target === 'string') void addLink(target)
}
</script>

<template>
  <section aria-labelledby="links-heading">
    <div class="mb-2 flex items-center justify-between gap-3">
      <SectionHeading id="links-heading"> Links </SectionHeading>
      <Button
        ref="opener"
        type="button"
        variant="secondary"
        class="gap-1.5"
        :aria-expanded="linking"
        @click="openLinking()"
      >
        <HugeiconsIcon :icon="PlusSignIcon" data-icon="inline-start" aria-hidden="true" />Link a
        ticket
      </Button>
    </div>
    <div v-if="linking" class="mb-2 flex flex-col gap-2.5">
      <ToggleGroup
        type="single"
        orientation="horizontal"
        variant="outline"
        aria-label="Link kind"
        :model-value="linkKind"
        @update:model-value="$event && (linkKind = $event as LinkKind)"
      >
        <ToggleGroupItem v-for="[value, label] in LINK_KINDS" :key="value" :value="value">{{
          label
        }}</ToggleGroupItem>
      </ToggleGroup>
      <Combobox
        ignore-filter
        :open="linking"
        :reset-search-term-on-blur="false"
        @update:open="$event || closeLinking()"
        @update:model-value="picked($event)"
      >
        <ComboboxAnchor>
          <ComboboxInput
            ref="search"
            v-model="linkQuery"
            aria-label="Find a ticket by id or title"
            placeholder="Find a ticket by id or title"
          />
        </ComboboxAnchor>
        <ComboboxList aria-label="Matching tickets">
          <ComboboxViewport>
            <ComboboxEmpty>No ticket matches.</ComboboxEmpty>
            <ComboboxItem v-for="[other, title] in linkMatches" :key="other" :value="other"
              ><span class="font-mono text-sm shrink-0 whitespace-nowrap">{{ other }}</span
              ><span class="min-w-0 truncate">{{ title }}</span
              ><Badge v-if="stageOf(other)" variant="outline" class="ml-auto shrink-0">{{
                stageOf(other)
              }}</Badge></ComboboxItem
            >
          </ComboboxViewport>
        </ComboboxList>
      </Combobox>
      <FieldError v-if="linkError">{{ linkError }}</FieldError>
    </div>
    <dl
      v-if="linkGroups.length"
      class="grid grid-cols-[88px_minmax(0,1fr)] gap-x-3 gap-y-2 text-sm"
    >
      <template v-for="[kind, label] in linkGroups" :key="kind">
        <dt class="text-muted-foreground pt-0.5">
          {{ label }}
          <span v-if="kind === 'child' && view.link" class="text-muted-foreground block text-sm"
            >{{ view.link.children_done }} of {{ view.link.children }} done</span
          >
        </dt>
        <dd class="min-w-0">
          <ul :aria-label="label" class="grid min-w-0 gap-0.5">
            <li
              v-for="other in linked[kind]"
              :key="other"
              class="group/link -mx-1.5 flex min-w-0 items-center gap-2 rounded-md px-1.5 py-0.5 hover:bg-foreground/5"
            >
              <RouterLink
                class="underline-offset-4 hover:underline flex min-w-0 items-center gap-2"
                :to="ticketHref(view.linked[other]?.repository ?? repository, other)"
                ><span class="font-mono text-sm shrink-0 whitespace-nowrap">{{ other }}</span
                ><span class="min-w-0 truncate">{{
                  view.linked[other]?.title ?? view.titles[other] ?? ''
                }}</span
                ><Badge v-if="stageOf(other)" variant="outline" class="shrink-0">{{
                  stageOf(other)
                }}</Badge></RouterLink
              >
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                class="ml-auto opacity-0 group-focus-within/link:opacity-100 group-hover/link:opacity-100"
                :aria-label="`Remove ${other} from ${label}`"
                :disabled="busy"
                @click="press(`${kind} ${other}`, () => removeLink(kind, other))"
              >
                <Spinner v-if="spins(`${kind} ${other}`, busy)" />
                <HugeiconsIcon v-else :icon="Cancel01Icon" aria-hidden="true" />
              </Button>
            </li>
          </ul>
        </dd>
      </template>
    </dl>
    <EmptyLine v-else>
      <Empty>
        <EmptyHeader>
          <EmptyDescription>No links yet.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </EmptyLine>
  </section>
</template>
