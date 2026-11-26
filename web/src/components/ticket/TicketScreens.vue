<script setup lang="ts">
import EmptyLine from '../EmptyLine.vue'
import SectionHeading from './SectionHeading.vue'
import { KanbanIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import { AspectRatio } from '@/components/ui/aspect-ratio'
import {
  Attachment,
  AttachmentContent,
  AttachmentDescription,
  AttachmentGroup,
  AttachmentMedia,
  AttachmentTitle,
  AttachmentTrigger,
} from '@/components/ui/attachment'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { SCREEN_RATIO } from '../../lib/screens'
import type { TicketView } from '../../lib/ticket'

// A ui ticket's screens (CF-1200): the pages its captures show, the latest capture's tree and
// state, and each image as an Attachment whose card opens the full image.
const { view, repository, id } = defineProps<{ view: TicketView; repository: string; id: string }>()

const capture = computed(() => view.status?.capture ?? null)
const pages = computed(() =>
  String(view.ticket.pages ?? '')
    .split(',')
    .map((p) => p.trim())
    .filter(Boolean),
)
const state = computed(() => {
  const c = capture.value
  if (!c) return ''
  if (c.state === 'approved') return `approved by ${c.by ?? 'the owner'}`
  if (c.state === 'sent_back') return `sent back: ${c.reason ?? ''}`
  return 'waits for approval'
})
const imageHref = (image: string) =>
  `/api/captures/${encodeURIComponent(repository)}/${id}/${capture.value?.tree ?? ''}/${image}`
</script>

<template>
  <section aria-labelledby="screens-heading">
    <SectionHeading id="screens-heading" class="mb-2"> Screens </SectionHeading>
    <p v-if="pages.length" class="text-muted-foreground mb-2 text-sm">
      Pages: <span class="font-mono text-sm">{{ pages.join(', ') }}</span>
    </p>
    <template v-if="capture">
      <p class="text-sm" data-capture>
        Tree <span class="font-mono text-sm">{{ capture.tree }}</span>
        <span :class="{ 'text-destructive': capture.state === 'sent_back' }"> · {{ state }}</span>
      </p>
      <AttachmentGroup v-if="capture.images.length" class="mt-2">
        <Attachment
          v-for="image in capture.images"
          :key="image"
          orientation="vertical"
          :state="capture.state === 'sent_back' ? 'error' : 'done'"
          class="has-data-[slot=attachment-content]:w-56"
        >
          <AttachmentMedia variant="image" class="aspect-auto">
            <AspectRatio :ratio="SCREEN_RATIO">
              <img
                :src="imageHref(image)"
                :alt="image"
                loading="lazy"
                class="size-full object-cover"
              />
            </AspectRatio>
          </AttachmentMedia>
          <AttachmentContent>
            <AttachmentTitle>{{ image }}</AttachmentTitle>
            <AttachmentDescription>{{ state }}</AttachmentDescription>
          </AttachmentContent>
          <AttachmentTrigger as-child>
            <a
              :href="imageHref(image)"
              target="_blank"
              rel="noopener noreferrer"
              :aria-label="`Open ${image}`"
            ></a>
          </AttachmentTrigger>
        </Attachment>
      </AttachmentGroup>
    </template>
    <EmptyLine v-else>
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon"
            ><HugeiconsIcon :icon="KanbanIcon" aria-hidden="true"
          /></EmptyMedia>
          <EmptyTitle>No capture yet</EmptyTitle>
          <EmptyDescription
            >Screenshots appear here after a capture is recorded for this ticket.</EmptyDescription
          >
        </EmptyHeader>
      </Empty>
    </EmptyLine>
  </section>
</template>
