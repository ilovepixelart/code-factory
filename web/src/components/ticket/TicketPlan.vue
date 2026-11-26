<script setup lang="ts">
import type { TicketView } from '../../lib/ticket'
import Plan from '../ai/Plan/Plan.vue'

// The plan the agent wrote in plan.md before it built (CF-1219), read from the ticket's branch: its
// items, ticked as the commits that finish them land. Read only; the agent edits the file.
const { plan } = defineProps<{ plan: NonNullable<TicketView['plan']> }>()
</script>

<template>
  <section aria-labelledby="plan-heading">
    <Plan :plan="plan" heading-id="plan-heading" />
  </section>
</template>
