<script setup lang="ts">
import { Field as VeeField, useForm } from 'vee-validate'
import { computed, onMounted, ref, useId, useTemplateRef } from 'vue'
import type { ContextVersion } from '../generated/ContextVersion'
import { CONTEXT_VERSIONS } from '../generated/Limits'
import type { Stage } from '../lib/board'
import { dayClock, thousands } from '../lib/format'
import { useReturnFocus } from '../lib/returnFocus'
import { NAME_LIMIT, characters, type AgentDraft, type Gap } from '../lib/roster'
import AgentContextField from './AgentContextField.vue'
import AgentLimitFields from './AgentLimitFields.vue'
import AgentScopeFields from './AgentScopeFields.vue'
import ModelSelector from './ai/ModelSelector/ModelSelector.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'

// The fields of an agent, for adding one or changing it. While a connection is chosen, the models
// it answered with are offered in the Model field's menu; the picked harness's gaps are listed below its
// row. Context, the owner's text for its runs, follows them (AgentContextField) and, for an agent
// that has them, its earlier versions, each restored by `restore` (CF-1163). The form's state and
// its checks are VeeValidate's, from field validation rules; the board refuses what they let through.
const props = withDefaults(
  defineProps<{
    name: string
    start: AgentDraft
    runtimes: string[]
    gaps: Record<string, Gap[]>
    roles: Stage[]
    connections: string[]
    models: Record<string, string[]>
    submit: string
    error: string
    busy: boolean
    history?: ContextVersion[]
    now?: number
    restore?: ((at: number) => Promise<boolean>) | undefined
  }>(),
  { history: () => [], now: () => Date.now() / 1000, restore: undefined },
)
const emit = defineEmits<{ save: [draft: AgentDraft]; cancel: [] }>()

const limit = (value: unknown) =>
  value === '' ||
  (typeof value === 'number' && Number.isInteger(value) && value >= 1) ||
  'A limit is a whole number from 1'
const { handleSubmit, setFieldValue, values } = useForm<AgentDraft>({
  validationSchema: {
    name: (value: unknown) =>
      (typeof value === 'string' && value.trim() !== '') || 'Give the agent a name',
    tokens: limit,
    minutes: limit,
  },
  initialValues: { ...props.start },
})
const nameField = useTemplateRef<InstanceType<typeof Input>>('nameField')
// A form that opens takes the keyboard to its first field, so no one loses their place.
onMounted(() => (nameField.value?.$el as HTMLInputElement | undefined)?.focus())
useReturnFocus()
const contextRefused = computed(() => props.error.startsWith('context '))
const historyTitle = computed(() => {
  const n = props.history.length
  const versions = `${String(n)} earlier version${n === 1 ? '' : 's'}`
  return n >= CONTEXT_VERSIONS
    ? `History (${versions}, the oldest dropped first)`
    : `History (${versions})`
})
const viewing = ref<number | null>(null)
const restoring = ref<number | null>(null)
const when = (at: number) => dayClock(at, props.now)

async function restoreVersion(version: ContextVersion): Promise<void> {
  if (!props.restore) return
  restoring.value = version.at
  if (await props.restore(version.at)) {
    setFieldValue('context', version.context)
    viewing.value = null
  }
  restoring.value = null
}
const ready = computed(() => values.name.trim() !== '')
const offered = computed(() => props.models[values.connection] ?? [])
const lacks = computed(() => props.gaps[values.runtime] ?? [])
// The harnesses a connection runs on are the ones the Harness field offers.
const harnesses = computed(() =>
  new Intl.ListFormat('en', { type: 'disjunction' }).format(props.runtimes),
)
const uid = useId()
const save = handleSubmit(() => {
  if (!props.busy) emit('save', { ...values })
})
</script>

<template>
  <form :aria-label="name" @submit="save($event)">
    <FieldGroup class="gap-4">
      <VeeField v-slot="{ value, handleChange, errors }" name="name">
        <Field :data-invalid="errors.length ? true : undefined">
          <FieldLabel :for="`${uid}-name`">Name</FieldLabel>
          <Input
            :id="`${uid}-name`"
            ref="nameField"
            name="name"
            :model-value="value"
            class="font-mono"
            :maxlength="NAME_LIMIT"
            autocomplete="off"
            :aria-invalid="errors.length ? true : undefined"
            @update:model-value="handleChange($event)"
          />
          <FieldError v-if="errors.length" :errors="errors" />
        </Field>
      </VeeField>
      <FieldGroup class="grid grid-cols-1 items-start gap-4 @lg/field-group:grid-cols-2">
        <VeeField v-slot="{ value, handleChange }" name="runtime">
          <Field>
            <FieldLabel :for="`${uid}-runtime`">Harness</FieldLabel>
            <NativeSelect
              :id="`${uid}-runtime`"
              name="runtime"
              :model-value="value"
              class="w-full"
              :aria-describedby="lacks.length ? `${uid}-lacks` : undefined"
              @update:model-value="handleChange($event)"
            >
              <NativeSelectOption v-for="runtime in runtimes" :key="runtime" :value="runtime">
                {{ runtime }}
              </NativeSelectOption>
            </NativeSelect>
          </Field>
        </VeeField>
        <VeeField v-slot="{ value, handleChange }" name="model">
          <Field>
            <FieldLabel :for="`${uid}-model`">Model</FieldLabel>
            <ModelSelector
              :id="`${uid}-model`"
              :model-value="String(value ?? '')"
              :connection="values.connection"
              :models="offered"
              :describedby="`${uid}-model-hint`"
              @update:model-value="handleChange($event)"
            />
            <FieldDescription :id="`${uid}-model-hint`"
              >Empty: the harness's default model</FieldDescription
            >
          </Field>
        </VeeField>
      </FieldGroup>
      <div v-if="lacks.length" :id="`${uid}-lacks`" class="text-sm text-muted-foreground">
        <p>This harness lacks:</p>
        <ul class="list-disc pl-4">
          <li v-for="gap in lacks" :key="gap.guarantee">{{ gap.guarantee }}: {{ gap.why }}</li>
        </ul>
      </div>
      <AgentScopeFields :roles="roles" />
      <VeeField v-slot="{ value, handleChange }" name="connection">
        <Field>
          <FieldLabel :for="`${uid}-connection`">Connection</FieldLabel>
          <NativeSelect
            :id="`${uid}-connection`"
            name="connection"
            :model-value="value"
            class="w-full"
            :aria-describedby="`${uid}-connection-hint`"
            @update:model-value="handleChange($event)"
          >
            <NativeSelectOption value="">None</NativeSelectOption>
            <NativeSelectOption
              v-for="connection in connections"
              :key="connection"
              :value="connection"
            >
              {{ connection }}
            </NativeSelectOption>
          </NativeSelect>
          <FieldDescription :id="`${uid}-connection-hint`"
            >None: the harness's own login; a connection runs on the
            {{ harnesses }} harness</FieldDescription
          >
        </Field>
      </VeeField>
      <AgentLimitFields />
      <VeeField v-slot="{ value, handleChange }" name="context">
        <AgentContextField
          :id="`${uid}-context`"
          :model-value="String(value ?? '')"
          :refused-by="contextRefused ? `${uid}-error` : ''"
          @update:model-value="handleChange($event)"
        />
      </VeeField>
      <Collapsible
        v-if="history.length"
        :unmount-on-hide="false"
        class="flex flex-col items-start gap-2 text-sm"
        data-history
      >
        <CollapsibleTrigger as-child
          ><Button type="button" variant="ghost" size="sm">{{
            historyTitle
          }}</Button></CollapsibleTrigger
        >
        <CollapsibleContent class="self-stretch">
          <ul class="mt-2 grid gap-3">
            <li v-for="version in history" :key="version.at" class="grid gap-2 px-3 py-2">
              <div class="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                <span class="text-muted-foreground"
                  >{{ when(version.at) }} ·
                  {{ thousands(characters(version.context)) }} characters</span
                >
                <span class="flex gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    :aria-expanded="viewing === version.at"
                    @click="viewing = viewing === version.at ? null : version.at"
                  >
                    {{ viewing === version.at ? 'Hide' : 'View' }}
                    <span class="sr-only">the version of {{ when(version.at) }}</span>
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    :disabled="restoring !== null || busy"
                    @click="restoreVersion(version)"
                  >
                    <Spinner v-if="restoring === version.at" data-icon="inline-start" />Restore
                    <span class="sr-only">the version of {{ when(version.at) }}</span>
                  </Button>
                </span>
              </div>
              <pre
                v-if="viewing === version.at"
                class="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed"
                >{{ version.context }}</pre>
            </li>
          </ul>
        </CollapsibleContent>
      </Collapsible>
      <FieldError v-if="error" :id="`${uid}-error`">{{ error }}</FieldError>
      <Field orientation="horizontal" class="justify-end">
        <Button type="button" variant="ghost" @click="emit('cancel')">Cancel</Button>
        <Button type="submit" :disabled="!ready || busy"
          ><Spinner v-if="busy" data-icon="inline-start" />{{ submit }}</Button
        >
      </Field>
    </FieldGroup>
  </form>
</template>
