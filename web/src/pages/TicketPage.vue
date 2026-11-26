<script setup lang="ts">
import { HelpCircleIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed, ref, useTemplateRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import TicketChanges from '../components/TicketChanges.vue'
import TicketForm from '../components/TicketForm.vue'
import TicketPreview from '../components/TicketPreview.vue'
import type { TicketView } from '../lib/ticket'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'

// A ticket as a page of its own: the panel's form, editable.
const route = useRoute()
const repository = computed(() => String(route.params.repository ?? ''))
const id = computed(() => String(route.params.id ?? ''))
const missing = ref(false)
const branch = ref('')
const merged = ref(false)
const revision = ref(0)
const form = useTemplateRef<{ refresh: () => Promise<void> }>('form')

// The changes follow every reading of the ticket, reloaded on each change.
function loaded(view: TicketView): void {
  branch.value = String(view.ticket.branch ?? '')
  merged.value = view.current_stage === 'merged'
  revision.value += 1
}

watch([repository, id], () => {
  missing.value = false
  branch.value = ''
})
</script>

<template>
  <Teleport to="#header-title">
    <Breadcrumb class="min-w-0">
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink as-child><RouterLink to="/tickets">Tickets</RouterLink></BreadcrumbLink>
        </BreadcrumbItem>
        <BreadcrumbSeparator />
        <BreadcrumbItem>
          <h1>
            <BreadcrumbPage class="font-mono text-sm">{{ id }}</BreadcrumbPage>
          </h1>
        </BreadcrumbItem>
      </BreadcrumbList>
    </Breadcrumb>
  </Teleport>
  <div v-if="missing" class="page-wide">
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon"
          ><HugeiconsIcon :icon="HelpCircleIcon" aria-hidden="true"
        /></EmptyMedia>
        <EmptyTitle>No ticket {{ id }}</EmptyTitle>
        <EmptyDescription>Check the ticket ID or return to the board to find it.</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button as-child variant="secondary"><RouterLink to="/tickets">Tickets</RouterLink></Button>
      </EmptyContent>
    </Empty>
  </div>
  <div v-else id="ticket-page" class="page-wide min-h-full p-0">
    <!-- One form per ticket: a form reused across tickets would show the old one's fields while
         its changes go to the new one. -->
    <TicketForm
      :id="id"
      :key="`${repository}/${id}`"
      ref="form"
      :repository="repository"
      page
      @missing="missing = true"
      @loaded="loaded($event)"
    >
      <TicketPreview :id="id" :repository="repository" />
      <TicketChanges
        v-if="branch"
        :id="id"
        :repository="repository"
        :revision="revision"
        :merged="merged"
        @commented="void form?.refresh()"
      />
    </TicketForm>
  </div>
</template>
