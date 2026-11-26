<script setup lang="ts">
import SectionHeading from './SectionHeading.vue'
import { computed, ref } from 'vue'
import { vRendered } from '../../lib/rendered'
import { useSectionLevel } from './context'
import { DOCUMENT_LABELS, type TicketView } from '../../lib/ticket'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

// The ticket's documents as tabs in writing order (CF-846, CF-835): Requirements, Mock for a ticket
// labelled ui, Spec and UAT, a tab for each one written, the mock with the files under mock/. No
// document is required (CF-1206), so one not written is offered under Add a document.
const { repository, id, view } = defineProps<{
  repository: string
  id: string
  view: TicketView
}>()

type Document = TicketView['documents'][number]
// A document's own h1 sits one level under this section's heading.
const level = useSectionLevel()
const documentTop = computed(() => level.value + 1)

/** A document is written once it has text, or, for the mock, a file under mock/ (CF-835). */
function documentWritten(d: Document): boolean {
  return Boolean(d.html) || Boolean(d.files?.length)
}

function documentLabel(d: Document): string {
  return DOCUMENT_LABELS[d.stage] ?? d.stage
}

const written = computed(() => view.documents.filter(documentWritten))
const unwritten = computed(() => view.documents.filter((d) => !documentWritten(d)))

const IMAGE = /\.(png|jpe?g|gif|webp)$/i

/** Whether the board draws a mock file as an image: the types its mock route answers. */
function isImage(file: string): boolean {
  return IMAGE.test(file)
}

function mockHref(file: string): string {
  return `/api/tickets/${encodeURIComponent(repository)}/${encodeURIComponent(id)}/mock/${encodeURIComponent(file)}`
}

const firstDocument = computed(() => written.value[0]?.stage)
// The tab picked, while that document is still written; the first one otherwise.
const picked = ref('')
const shown = computed({
  get: () =>
    written.value.some((d) => d.stage === picked.value)
      ? picked.value
      : (firstDocument.value ?? ''),
  set: (stage: string | number) => {
    picked.value = String(stage)
  },
})
</script>

<template>
  <section v-if="view.documents.length" aria-labelledby="documents-heading">
    <SectionHeading id="documents-heading" class="mb-2"> Documents </SectionHeading>
    <Tabs v-if="written.length" v-model="shown">
      <TabsList variant="line">
        <TabsTrigger v-for="d in written" :key="d.stage" :value="d.stage">{{
          documentLabel(d)
        }}</TabsTrigger>
      </TabsList>
      <TabsContent v-for="d in written" :key="d.stage" :value="d.stage" class="mt-2">
        <div v-if="d.html" v-rendered:[documentTop]="d.html" class="typeset typeset-doc"></div>
        <ul v-if="d.files?.length" class="mt-3 grid gap-3" aria-label="Mock files">
          <li v-for="file in d.files" :key="file" class="grid gap-1">
            <span class="font-mono text-sm">{{ file }}</span>
            <img
              v-if="isImage(file)"
              :src="mockHref(file)"
              :alt="file"
              class="max-w-full rounded-xl border border-border"
            />
          </li>
        </ul>
      </TabsContent>
    </Tabs>
    <Collapsible
      v-if="unwritten.length"
      :unmount-on-hide="false"
      aria-label="Add a document"
      class="mt-2"
    >
      <CollapsibleTrigger as-child
        ><Button type="button" variant="ghost" size="xs">Add a document</Button></CollapsibleTrigger
      >
      <CollapsibleContent>
        <ul class="mt-2 grid gap-1 text-sm">
          <li v-for="d in unwritten" :key="d.stage">
            {{ documentLabel(d) }}
            <span class="font-mono text-sm text-muted-foreground"
              >.code-factory/tickets/{{ id }}/{{ d.stage }}.md</span
            >
          </li>
        </ul>
      </CollapsibleContent>
    </Collapsible>
  </section>
</template>
