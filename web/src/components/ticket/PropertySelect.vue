<script setup lang="ts" generic="T extends string">
import { computed, nextTick } from 'vue'
import { Field, FieldContent, FieldError, FieldLabel } from '@/components/ui/field'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'

// A property of a ticket in its column chosen from a list: the label left of its select. `empty`
// names the choice of no value; `names` shows each choice by another name; `hint` shows on hover.
// A refusal of its value shows under the select and is its description (CF-1201).
const {
  id,
  label,
  options,
  name = '',
  required,
  empty = null,
  names = null,
  hint = null,
  error = '',
} = defineProps<{
  id: string
  label: string
  options: readonly T[]
  name?: string
  required?: boolean
  empty?: string | null
  names?: Record<T, string> | null
  hint?: string | null
  error?: string | undefined
}>()
const emit = defineEmits<{ change: [] }>()
const choice = defineModel<string>({ required: true })

const errorId = computed(() => `${id}-error`)
// shadcn-vue's controls pass a typed value on from a watcher, after the event, and a select fires
// `change` right after `input`: a change saves once that value has reached the model.
async function changed(): Promise<void> {
  await nextTick()
  emit('change')
}
const choices = computed(() => [
  ...(empty === null ? [] : [{ value: '', text: empty }]),
  ...options.map((option) => ({ value: option, text: names?.[option] ?? option })),
])
</script>

<template>
  <Field :data-invalid="error ? true : undefined">
    <FieldLabel :for="id">{{ label }}</FieldLabel>
    <FieldContent class="min-w-0">
      <NativeSelect
        :id="id"
        :model-value="choice"
        class="w-full"
        :name="name || undefined"
        :required="required"
        :title="hint ?? undefined"
        :aria-describedby="error ? errorId : undefined"
        :aria-invalid="error ? true : undefined"
        @update:model-value="choice = String($event ?? '')"
        @change="changed()"
      >
        <NativeSelectOption v-for="c in choices" :key="c.value" :value="c.value">{{
          c.text
        }}</NativeSelectOption>
      </NativeSelect>
      <FieldError v-if="error" :id="errorId">{{ error }}</FieldError>
    </FieldContent>
  </Field>
</template>
