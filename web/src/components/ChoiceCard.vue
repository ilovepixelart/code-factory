<script setup lang="ts">
import { Field, FieldLabel } from '@/components/ui/field'

// One answer as a card: its control (a radio or a checkbox, whose id is `for`) and what it says.
// The whole card is the control's label, so a click anywhere on it picks it.
defineProps<{ for: string }>()
defineSlots<{ control: () => unknown; default: () => unknown }>()
</script>

<template>
  <FieldLabel :for="$props.for" class="font-normal">
    <Field orientation="horizontal" class="items-start">
      <slot name="control" />
      <slot />
    </Field>
  </FieldLabel>
</template>
