<script setup lang="ts">
import { Field as VeeField } from 'vee-validate'
import { useId } from 'vue'
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from '@/components/ui/field'
import {
  NumberField,
  NumberFieldContent,
  NumberFieldDecrement,
  NumberFieldIncrement,
  NumberFieldInput,
} from '@/components/ui/number-field'

// An agent's limits, inside AgentForm's form: whole numbers from 1, or empty for no limit. The
// form holds an empty limit as '' (AgentDraft).
const uid = useId()
const LIMITS = [
  {
    name: 'tokens',
    label: 'Token limit',
    hint: "Tokens all of this agent's runs on one ticket may use together; empty: no limit",
  },
  {
    name: 'minutes',
    label: 'Run time limit (minutes)',
    hint: "Minutes all of this agent's runs on one ticket may take together; empty: no limit",
  },
] as const

const shown = (value: unknown): number | null => (typeof value === 'number' ? value : null)
const held = (value: number | undefined): number | '' =>
  value === undefined || Number.isNaN(value) ? '' : value
</script>

<template>
  <FieldGroup class="grid grid-cols-1 items-start gap-4 @lg/field-group:grid-cols-2">
    <VeeField
      v-for="limit in LIMITS"
      :key="limit.name"
      v-slot="{ value, handleChange, errors }"
      :name="limit.name"
    >
      <Field :data-invalid="errors.length ? true : undefined">
        <FieldLabel :for="`${uid}-${limit.name}`">{{ limit.label }}</FieldLabel>
        <NumberField
          :id="`${uid}-${limit.name}`"
          :model-value="shown(value)"
          :min="1"
          :step="1"
          :name="limit.name"
          @update:model-value="handleChange(held($event))"
        >
          <NumberFieldContent>
            <NumberFieldDecrement />
            <NumberFieldInput
              :aria-invalid="errors.length ? true : undefined"
              :aria-describedby="`${uid}-${limit.name}-hint`"
              placeholder="no limit"
            />
            <NumberFieldIncrement />
          </NumberFieldContent>
        </NumberField>
        <FieldDescription :id="`${uid}-${limit.name}-hint`">{{ limit.hint }}</FieldDescription>
        <FieldError v-if="errors.length" :errors="errors" />
      </Field>
    </VeeField>
  </FieldGroup>
</template>
