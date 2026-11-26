<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import type { MemoryRecord } from '../lib/memory'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Field, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'

// One of an entry's review forms, in place of its actions: the source to add, the entry to merge
// it into (the first of `targets` chosen), or why it no longer applies. `submit` carries what was
// typed or chosen.
const { mode, targets } = defineProps<{
  mode: 'source' | 'merge' | 'retire'
  targets: MemoryRecord[]
  busy: boolean
  error: string
}>()
const emit = defineEmits<{ submit: [answer: string]; cancel: [] }>()

const WORK = {
  source: { label: 'Add a source', field: 'Source', submit: 'Save and mark reviewed' },
  merge: { label: 'Merge the entry', field: 'Merge into', submit: 'Merge' },
  retire: { label: 'Retire the entry', field: 'Why it no longer applies', submit: 'Retire' },
} as const
const uid = useId()
const typed = ref('')
const into = ref(targets[0]?.id ?? '')
const answer = computed(() => (mode === 'merge' ? into.value : typed.value))
const ready = computed(() => answer.value.trim() !== '')
</script>

<template>
  <form
    class="mt-1 grid gap-2"
    :aria-label="WORK[mode].label"
    @submit.prevent="ready && emit('submit', answer)"
  >
    <FieldGroup class="gap-2">
      <Field>
        <FieldLabel :for="`${uid}-${mode}`">{{ WORK[mode].field }}</FieldLabel>
        <NativeSelect
          v-if="mode === 'merge'"
          :id="`${uid}-${mode}`"
          :model-value="into"
          name="into"
          class="w-full"
          @update:model-value="into = String($event ?? '')"
        >
          <NativeSelectOption v-for="other in targets" :key="other.id" :value="other.id">
            {{ other.statement }}
          </NativeSelectOption>
        </NativeSelect>
        <Input
          v-else
          :id="`${uid}-${mode}`"
          :model-value="typed"
          :name="mode"
          @update:model-value="typed = String($event)"
        />
      </Field>
      <FieldError v-if="error">{{ error }}</FieldError>
      <Field orientation="horizontal" class="justify-end">
        <Button type="button" variant="ghost" @click="emit('cancel')">Cancel</Button>
        <Button type="submit" :disabled="busy || !ready"
          ><Spinner v-if="busy" data-icon="inline-start" />{{ WORK[mode].submit }}</Button
        >
      </Field>
    </FieldGroup>
  </form>
</template>
