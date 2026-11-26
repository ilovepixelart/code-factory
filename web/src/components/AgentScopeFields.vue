<script setup lang="ts">
import { sentence } from '../lib/format'
import { Field as VeeField } from 'vee-validate'
import { useId } from 'vue'
import { STAGE_LABELS, TYPES, type Stage } from '../lib/board'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from '@/components/ui/field'
import { Input } from '@/components/ui/input'

// What an agent takes, inside AgentForm's form: the columns it runs in, the ticket types and the
// ticket labels. Each list is one form value, ticked and unticked whole.
defineProps<{ roles: Stage[] }>()

const uid = useId()
const toggled = (held: unknown, item: string, on: boolean | 'indeterminate'): string[] => {
  const list = Array.isArray(held) ? held.map(String) : []
  return on === true ? [...list, item] : list.filter((kept) => kept !== item)
}
</script>

<template>
  <VeeField v-slot="{ value, handleChange }" name="roles">
    <FieldSet>
      <FieldLegend variant="label">Columns</FieldLegend>
      <FieldGroup data-slot="checkbox-group" class="flex-row flex-wrap gap-x-4">
        <Field v-for="role in roles" :key="role" orientation="horizontal" class="w-auto">
          <Checkbox
            :id="`${uid}-role-${role}`"
            :model-value="Array.isArray(value) && value.includes(role)"
            @update:model-value="handleChange(toggled(value, role, $event))"
          />
          <FieldLabel :for="`${uid}-role-${role}`" class="font-normal">{{
            STAGE_LABELS[role]
          }}</FieldLabel>
        </Field>
      </FieldGroup>
    </FieldSet>
  </VeeField>
  <VeeField v-slot="{ value, handleChange }" name="types">
    <FieldSet>
      <FieldLegend variant="label">Ticket types</FieldLegend>
      <FieldGroup data-slot="checkbox-group" class="flex-row flex-wrap gap-x-4">
        <Field v-for="type in TYPES" :key="type" orientation="horizontal" class="w-auto">
          <Checkbox
            :id="`${uid}-type-${type}`"
            :model-value="Array.isArray(value) && value.includes(type)"
            @update:model-value="handleChange(toggled(value, type, $event))"
          />
          <FieldLabel :for="`${uid}-type-${type}`" class="font-normal">{{
            sentence(type)
          }}</FieldLabel>
        </Field>
      </FieldGroup>
      <FieldDescription>None ticked: every type</FieldDescription>
    </FieldSet>
  </VeeField>
  <VeeField v-slot="{ value, handleChange }" name="labels">
    <Field>
      <FieldLabel :for="`${uid}-labels`">Ticket labels</FieldLabel>
      <Input
        :id="`${uid}-labels`"
        name="labels"
        :model-value="value"
        autocomplete="off"
        :aria-describedby="`${uid}-labels-hint`"
        @update:model-value="handleChange($event)"
      />
      <FieldDescription :id="`${uid}-labels-hint`"
        >Comma separated; a ticket needs one of them; empty: any labels</FieldDescription
      >
    </Field>
  </VeeField>
</template>
