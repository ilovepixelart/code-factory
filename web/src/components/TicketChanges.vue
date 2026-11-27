<script setup lang="ts">
import EmptyLine from './EmptyLine.vue'
import SectionCard from './SectionCard.vue'
import { computed, reactive, ref, useId, watch } from 'vue'
import { act } from '../lib/actions'
import { latest } from '../lib/latest'
import { perform } from '../lib/notice'
import { loadChanges, type DiffLine, type TicketChanges } from '../lib/ticket'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Empty, EmptyDescription, EmptyHeader } from '@/components/ui/empty'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Textarea } from '@/components/ui/textarea'
import { CommentAdd01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import FileTreeNode from './ai/FileTree/FileTreeNode.vue'
import { fileTree } from './ai/FileTree/tree'

// A ticket branch's changes on its page, inside the ticket's form above its footer: the changed
// files as a tree that leads to each file's diff, and each numbered line has a comment form of its own,
// opened from an icon in its gutter shown on hover or focus.
const { repository, id, revision, merged } = defineProps<{
  repository: string
  id: string
  revision: number
  /** The ticket is merged: a branch without changes is in its default branch, not waiting. */
  merged?: boolean
}>()
const emit = defineEmits<{ commented: [] }>()

const KIND_CLASS: Record<DiffLine['kind'], string> = {
  added: 'bg-primary/10',
  removed: 'bg-destructive/10 text-muted-foreground',
  kept: 'text-muted-foreground',
}
const MARK: Record<DiffLine['kind'], string> = { added: '+', removed: '-', kept: ' ' }

const changes = ref<TicketChanges | null>(null)
const reads = latest()
const texts = reactive<Record<string, string>>({})
// The open comment forms by file and line: a form sent closes.
const opened = reactive<Record<string, boolean>>({})
const busy = ref('')
const count = computed(() => changes.value?.files.length ?? 0)
const REMOVED = 'a removed file'
const tree = computed(() => fileTree(changes.value?.files.map((file) => file.path) ?? [], REMOVED))
const fileId = useId()

// A file chosen in the tree takes the keyboard to its diff, which scrolls into view.
function show(path: string): void {
  const at = changes.value?.files.findIndex((file) => file.path === path) ?? -1
  document.getElementById(`${fileId}-${String(at)}`)?.focus()
}

// A row's key survives a reload that inserts lines above it: a numbered line by its kind and
// number, a removed line (no number) by its place among the removed lines of its file.
function lineKeys(lines: DiffLine[]): string[] {
  let removed = 0
  return lines.map((line) =>
    line.number === null ? `removed:${String(removed++)}` : `${line.kind}:${String(line.number)}`,
  )
}
const keys = computed(() => changes.value?.files.map((file) => lineKeys(file.lines)) ?? [])

watch(
  () => [repository, id, revision],
  async () => {
    const current = reads.take()
    try {
      const found = await loadChanges(repository, id)
      if (current()) changes.value = found
    } catch {
      // A read the board does not answer keeps the rows shown until the next change reads again.
    }
  },
  { immediate: true },
)

async function send(path: string, line: number): Promise<void> {
  const key = `${path}:${String(line)}`
  busy.value = key
  const comments = `/api/tickets/${encodeURIComponent(repository)}/${encodeURIComponent(id)}/comments`
  const done = await perform(
    () => act('POST', comments, { text: texts[key] ?? '', path, line }),
    () => {
      emit('commented')
      return Promise.resolve()
    },
  )
  busy.value = ''
  if (!done) return
  texts[key] = ''
  opened[key] = false
}
</script>

<template>
  <SectionCard
    v-if="changes"
    id="changes"
    class="px-6 py-6"
    heading="changes-heading"
    title="Changes"
    :count="count"
    :description="`${count === 1 ? 'file' : 'files'}, ${changes.branch} against ${changes.default_branch}${changes.cut ? `, cut at ${changes.limit} lines` : ''}`"
  >
    <nav v-if="count" aria-label="Changed files" class="mb-3 flex flex-col">
      <FileTreeNode v-for="node in tree" :key="node.path" :node="node" @select="show($event)" />
    </nav>
    <div
      v-for="(file, f) in changes.files"
      :id="`${fileId}-${String(f)}`"
      :key="file.path || `\0${f}`"
      tabindex="-1"
      class="mb-3 overflow-x-auto outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
    >
      <h3 class="font-mono text-xs wrap-anywhere border-b border-border px-3 py-2">
        {{ file.path || REMOVED }}
      </h3>
      <table class="w-full font-mono text-sm" :aria-label="file.path">
        <thead class="sr-only">
          <tr>
            <th scope="col">Line</th>
            <th scope="col">Change</th>
            <th scope="col">Text</th>
          </tr>
        </thead>
        <tbody>
          <Collapsible
            v-for="(line, l) in file.lines"
            :key="keys[f]?.[l] ?? l"
            as-child
            :open="opened[`${file.path}:${line.number}`] ?? false"
            :unmount-on-hide="false"
            @update:open="opened[`${file.path}:${line.number}`] = $event"
          >
            <tr :class="KIND_CLASS[line.kind]" class="group/line align-top">
              <td class="w-16 select-none pr-2 text-muted-foreground tabular-nums">
                <div class="flex items-center justify-end gap-1">
                  <CollapsibleTrigger v-if="line.number" as-child
                    ><Button
                      type="button"
                      variant="ghost"
                      size="icon-xs"
                      class="opacity-0 pointer-coarse:opacity-100 group-hover/line:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100"
                      :aria-label="`Comment on ${file.path} line ${line.number}`"
                      ><HugeiconsIcon :icon="CommentAdd01Icon" aria-hidden="true" /></Button
                  ></CollapsibleTrigger>
                  {{ line.number || '' }}
                </div>
              </td>
              <td class="w-4 select-none" :aria-label="line.kind">{{ MARK[line.kind] }}</td>
              <td class="wrap-anywhere pr-2">
                <span class="whitespace-pre-wrap">{{ line.text }}</span>
                <CollapsibleContent v-if="line.number" class="font-sans">
                  <form
                    class="my-1 flex items-start gap-2"
                    @submit.prevent="send(file.path, line.number)"
                  >
                    <Textarea
                      :model-value="texts[`${file.path}:${line.number}`] ?? ''"
                      class="flex-1"
                      name="text"
                      rows="2"
                      :aria-label="`Comment on ${file.path} line ${line.number}`"
                      required
                      @update:model-value="texts[`${file.path}:${line.number}`] = String($event)"
                    />
                    <Button
                      variant="secondary"
                      type="submit"
                      :disabled="busy === `${file.path}:${line.number}`"
                      :aria-label="`Send comment on ${file.path} line ${line.number}`"
                    >
                      <Spinner
                        v-if="busy === `${file.path}:${line.number}`"
                        data-icon="inline-start"
                      />Send
                    </Button>
                  </form>
                </CollapsibleContent>
              </td>
            </tr>
          </Collapsible>
        </tbody>
      </table>
    </div>
    <EmptyLine v-if="!count">
      <Empty>
        <EmptyHeader>
          <EmptyDescription>{{
            merged
              ? `${changes.branch} is merged into ${changes.default_branch}.`
              : `No changes on ${changes.branch} yet.`
          }}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </EmptyLine>
  </SectionCard>
</template>
