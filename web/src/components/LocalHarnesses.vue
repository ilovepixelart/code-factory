<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import AgentForm from './AgentForm.vue'
import SectionCard from './SectionCard.vue'
import { draftOf, type AgentDraft, type AgentList } from '../lib/roster'
import { useApplied } from '../lib/queries'
import { keys } from '../lib/queryKeys'

const props = defineProps<{
  list: AgentList
  connections: { name: string; kind: string }[]
  models: Record<string, string[]>
  busy: boolean
  error: string
}>()
const emit = defineEmits<{ save: [draft: AgentDraft]; prepare: [] }>()
const adding = defineModel<boolean>('adding', { required: true })
const installed = ref<Record<string, boolean> | null>(null)
const requested = ref('')
const harnessLabels: Record<string, string> = { claude: 'Claude Code', codex: 'Codex' }

useApplied<Record<string, boolean>>(keys.harnesses, '/api/harnesses', (read) => {
  installed.value = read
})
watch(adding, (open) => {
  if (!open) requested.value = ''
})

function setup(runtime: string): void {
  requested.value = runtime
  emit('prepare')
}

const draft = computed(() => {
  const runtimes = props.list.runtimes
  const runtime =
    requested.value === ''
      ? (runtimes.find((name) => installed.value?.[name]) ?? runtimes[0])
      : requested.value
  const start = draftOf(null, runtime)
  if (requested.value === 'codex') {
    start.connection = props.connections.find((entry) => entry.kind === 'codex-login')?.name ?? ''
  }
  return start
})
</script>

<template>
  <SectionCard v-if="adding" key="new-agent" heading="agent-adding" title="New agent">
    <AgentForm
      name="New agent"
      :start="draft"
      :runtimes="list.runtimes"
      :gaps="list.gaps"
      :roles="list.roles"
      :connections="connections.map((entry) => entry.name)"
      :models="models"
      submit="Add"
      :error="error"
      :busy="busy"
      @save="emit('save', $event)"
      @cancel="adding = false"
    />
  </SectionCard>
  <SectionCard
    v-if="installed"
    key="local-harnesses"
    heading="local-harnesses"
    title="Local harnesses"
    description="Coding tools found on the machine running Factory. Connections and models are configured separately."
  >
    <div class="grid gap-4 md:grid-cols-2">
      <div
        v-for="runtime in list.runtimes"
        :key="runtime"
        class="bg-card flex flex-wrap items-center justify-between gap-3 rounded-lg p-4"
      >
        <div class="grid gap-1">
          <div class="flex flex-wrap items-center gap-2">
            <h3 class="text-sm font-medium">{{ harnessLabels[runtime] ?? runtime }}</h3>
            <Badge variant="secondary">{{
              installed[runtime] ? 'Installed' : 'Unavailable'
            }}</Badge>
          </div>
          <p
            v-if="runtime === 'codex' && installed[runtime] && !installed.srt"
            class="text-muted-foreground text-sm"
          >
            Install the sandbox runtime before starting Codex.
          </p>
        </div>
        <Button
          v-if="installed[runtime] && !adding"
          type="button"
          variant="outline"
          size="sm"
          @click="setup(runtime)"
        >
          Set up {{ harnessLabels[runtime] ?? runtime }} agent
        </Button>
      </div>
    </div>
  </SectionCard>
</template>
