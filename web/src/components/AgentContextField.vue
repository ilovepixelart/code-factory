<script setup lang="ts">
import { computed, ref } from 'vue'
import { AGENT_CONTEXT_LIMIT } from '../generated/Limits'
import { post } from '../lib/actions'
import { vRendered } from '../lib/rendered'
import { contextCount } from '../lib/roster'
import { Empty, EmptyDescription, EmptyHeader } from '@/components/ui/empty'
import { FieldDescription, FieldError, FieldLegend, FieldSet } from '@/components/ui/field'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'

// An agent's Context: the owner's Markdown for its runs, written in a monospace area with its count
// against the limit, and previewed as the server's Markdown renderer draws a ticket's description,
// raw HTML shown as text (CF-1163). `refusedBy` names the element holding a refusal of it.
defineProps<{ id: string; refusedBy: string }>()
const text = defineModel<string>({ required: true })

const count = computed(() => contextCount(text.value, AGENT_CONTEXT_LIMIT))
const previewing = ref(false)
const preview = ref<{ html: string } | { refused: string } | null>(null)
const view = computed({
  get: () => (previewing.value ? 'preview' : 'write'),
  set: (next: string | number) => {
    if (next === 'preview') void showPreview()
    else previewing.value = false
  },
})

async function showPreview(): Promise<void> {
  previewing.value = true
  preview.value = null
  if (text.value.trim() === '') return
  try {
    preview.value = await post<{ html: string }>('/api/agent-context/preview', {
      text: text.value,
    })
  } catch (error) {
    preview.value = { refused: error instanceof Error ? error.message : String(error) }
  }
}
</script>

<template>
  <FieldSet class="gap-2">
    <FieldLegend variant="label">Context</FieldLegend>
    <Tabs v-model="view">
      <TabsList aria-label="Context view">
        <TabsTrigger value="write" data-tab="write">Write</TabsTrigger>
        <TabsTrigger value="preview" data-tab="preview">Preview</TabsTrigger>
      </TabsList>
    </Tabs>
    <Textarea
      :id="id"
      :model-value="text"
      :style="previewing ? 'display: none' : undefined"
      class="min-h-48 font-mono"
      name="context"
      aria-label="Context"
      rows="12"
      :aria-describedby="`${id}-hint ${id}-count${refusedBy ? ` ${refusedBy}` : ''}`"
      :aria-invalid="refusedBy ? true : undefined"
      placeholder="What this agent should know that the board's instructions do not say"
      @update:model-value="text = String($event)"
    />
    <div
      v-if="previewing"
      role="tabpanel"
      aria-label="Preview"
      data-preview
      class="max-h-96 min-h-24 overflow-auto rounded-xl bg-muted/50 p-4"
    >
      <Empty v-if="text.trim() === ''">
        <EmptyHeader>
          <EmptyDescription>Nothing written yet.</EmptyDescription>
        </EmptyHeader>
      </Empty>
      <p v-else-if="preview === null" class="text-muted-foreground text-sm">Rendering</p>
      <FieldError v-else-if="'refused' in preview"
        >The preview failed: {{ preview.refused }}</FieldError
      >
      <div v-else v-rendered="preview.html" class="typeset typeset-doc"></div>
    </div>
    <div class="flex flex-col gap-1 md:flex-row md:items-baseline md:justify-between md:gap-4">
      <FieldDescription :id="`${id}-hint`"
        >Markdown, given to every run of this agent after the board's instructions. Changes apply
        from its next run.</FieldDescription
      >
      <span
        :id="`${id}-count`"
        class="shrink-0 text-sm tabular-nums"
        :class="count.tone"
        data-count
        >{{ count.text }}</span
      >
    </div>
  </FieldSet>
</template>
