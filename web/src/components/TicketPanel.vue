<script setup lang="ts">
import { ArrowExpand01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { ref, useTemplateRef, watch } from 'vue'
import { panelTicket } from '../lib/openTicket'
import { useOverlay } from '../lib/overlayHistory'
import { ticketHref } from '../lib/ticket'
import TicketForm from './TicketForm.vue'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'

// A ticket's panel: the ticket form in a right-hand sheet. It focuses its title as it opens, never
// a field (docs/ui.md).
const open = useOverlay()
const title = useTemplateRef<{ $el: HTMLElement }>('title')
const shown = ref<{ repository: string; id: string } | null>(null)

function show(repository: string, id: string): void {
  shown.value = { repository, id }
  panelTicket.value = shown.value
  open.value = true
}

function focusTitle(event: Event): void {
  event.preventDefault()
  title.value?.$el.focus()
}

watch(open, (now) => {
  if (now) return
  shown.value = null
  panelTicket.value = null
})

defineExpose({ open: show })
</script>

<template>
  <Sheet v-model:open="open">
    <SheetContent
      class="gap-0 data-[side=right]:w-full data-[side=right]:sm:max-w-none data-[side=right]:xl:w-1/2"
      aria-describedby=""
      @open-auto-focus="focusTitle($event)"
    >
      <template v-if="shown">
        <SheetHeader class="flex-row items-center pr-14">
          <SheetTitle ref="title" tabindex="-1" class="flex min-w-0 items-center gap-1">
            <span class="text-muted-foreground">{{ shown.repository }}</span
            ><span class="text-muted-foreground">/</span
            ><span class="font-mono text-sm">{{ shown.id }}</span>
          </SheetTitle>
          <Button
            as-child
            variant="ghost"
            size="icon-sm"
            class="ml-auto"
            aria-label="Open as page"
            title="Open as page"
            ><RouterLink :to="ticketHref(shown.repository, shown.id)"
              ><HugeiconsIcon :icon="ArrowExpand01Icon" aria-hidden="true" /></RouterLink
          ></Button>
        </SheetHeader>
        <TicketForm
          :id="shown.id"
          :key="`${shown.repository}/${shown.id}`"
          :repository="shown.repository"
          @close="open = false"
          @missing="open = false"
        />
      </template>
    </SheetContent>
  </Sheet>
</template>
