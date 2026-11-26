<script setup lang="ts">
import { computed } from 'vue'
import { STAGE_LABELS } from '../../lib/board'
import { money } from '../../lib/format'
import type { TicketView } from '../../lib/ticket'
import { useTicketForm } from './context'
import PropertyGroups from './PropertyGroups.vue'

// The ticket's properties, beside its content; each saves itself when changed.
const { id, view } = defineProps<{ id: string; view: TicketView }>()

const { model, save, errors } = useTicketForm()
// While its own `branch:` is empty, the branch its worktree has checked out (CF-1229).
const branch = computed(() => (view.branch ? `${view.branch} (auto)` : 'set by agents'))
const budget = computed(() =>
  view.default_budget != null ? `from config: ${money(view.default_budget)}` : 'no budget',
)
</script>

<template>
  <aside aria-label="Properties" class="bg-muted/40 px-4 py-5">
    <PropertyGroups
      :model-value="model"
      :prefix="id"
      mode="edit"
      :repository="view.repository"
      :stage-empty="`${STAGE_LABELS[view.current_stage]} (auto)`"
      :branch="branch"
      :budget="budget"
      :source="String(view.ticket.source ?? '')"
      :errors="errors"
      @change="save($event)"
    />
  </aside>
</template>
