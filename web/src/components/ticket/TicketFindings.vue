<script setup lang="ts">
import SectionHeading from './SectionHeading.vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, reactive, watch } from 'vue'
import { ask } from '../../lib/actions'
import { readAgain } from '../../lib/queries'
import { keys } from '../../lib/queryKeys'
import { useTicketForm } from './context'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Input } from '@/components/ui/input'

// The ticket's review findings (CF-688), each open one closed as fixed or dismissed with a reason.
interface Finding {
  id: string
  severity: string
  file: string
  line: number
  text: string
  state: string
  reason: string
  by: string
}

const { repository, id } = defineProps<{ repository: string; id: string }>()
const { base, busy, send, press, spins } = useTicketForm()
const client = useQueryClient()
const key = computed(() => keys.findings(repository, id))
const read = useQuery({
  queryKey: key,
  queryFn: ({ signal }) => ask<{ findings: Finding[] }>(`${base.value}/findings`, signal),
})
const findings = computed<Finding[]>(() => {
  const listed = read.data.value?.findings
  return Array.isArray(listed) ? listed : []
})
// A review run files findings while the ticket is open: each answer of the ticket's own read (its
// poll, a change) reads them again.
const ticket = useQuery({ queryKey: computed(() => keys.ticket(repository, id)), enabled: false })
watch(ticket.dataUpdatedAt, (at, was) => {
  if (was && at !== was && !read.isFetching.value) void read.refetch()
})
const reasons = reactive<Record<string, string>>({})
// The board names findings F1, F2...; any other id read back from the activity file is shown but
// never sent, so it cannot steer the close request to another address.
const closable = (finding: Finding): boolean =>
  finding.state === 'open' && /^F\d+$/.test(finding.id)
const open = computed(() => findings.value.filter((f) => f.state === 'open').length)

async function close(finding: Finding, state: 'fixed' | 'dismissed'): Promise<void> {
  if (!closable(finding)) return
  const reason = reasons[finding.id] ?? ''
  if (await send(`findings/${encodeURIComponent(finding.id)}`, { state, reason })) {
    delete reasons[finding.id]
    await readAgain(client, key.value, read)
  }
}
</script>

<template>
  <section
    v-if="findings.length"
    aria-labelledby="findings-heading"
    class="rounded-xl bg-muted/50 p-4"
  >
    <SectionHeading id="findings-heading" class="mb-3">
      Review findings <span class="text-muted-foreground font-normal">{{ open }} open</span>
    </SectionHeading>
    <ul aria-label="Review findings" class="grid gap-4">
      <li v-for="finding in findings" :key="finding.id" class="grid gap-2 text-sm">
        <p class="flex items-baseline gap-2">
          <span class="font-mono text-sm">{{ finding.id }}</span>
          <span class="font-medium">{{ finding.severity }}</span>
          <span class="font-mono text-sm text-muted-foreground min-w-0 flex-1 truncate"
            >{{ finding.file }}:{{ finding.line }}</span
          >
          <span class="text-muted-foreground text-sm">{{ finding.state }}</span>
        </p>
        <p class="break-words">{{ finding.text }}</p>
        <div v-if="closable(finding)" class="flex gap-2">
          <Input
            :model-value="reasons[finding.id] ?? ''"
            class="flex-1"
            :aria-label="`Reason for ${finding.id}`"
            placeholder="Reason"
            @update:model-value="reasons[finding.id] = String($event)"
          />
          <Button
            type="button"
            variant="secondary"
            :disabled="busy"
            @click="press(`fixed ${finding.id}`, () => close(finding, 'fixed'))"
          >
            <Spinner v-if="spins(`fixed ${finding.id}`, busy)" data-icon="inline-start" />Fixed
          </Button>
          <Button
            type="button"
            variant="secondary"
            :disabled="busy"
            @click="press(`dismissed ${finding.id}`, () => close(finding, 'dismissed'))"
          >
            <Spinner
              v-if="spins(`dismissed ${finding.id}`, busy)"
              data-icon="inline-start"
            />Dismiss
          </Button>
        </div>
        <p v-else-if="finding.state !== 'open'" class="text-muted-foreground text-sm">
          {{ finding.state }}: {{ finding.reason }} ({{ finding.by }})
        </p>
      </li>
    </ul>
  </section>
</template>
