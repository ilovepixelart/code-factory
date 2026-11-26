<script setup lang="ts">
import { Search01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group'

// A page's search in the header: the words typed, sent as `q`, with the search glyph before them.
// `class` sizes the box.
const { id, label, placeholder } = defineProps<{
  id: string
  label: string
  placeholder: string
}>()
const text = defineModel<string>({ required: true })
</script>

<template>
  <InputGroup>
    <InputGroupInput
      :id="id"
      :model-value="text"
      type="search"
      name="q"
      :aria-label="label"
      :placeholder="placeholder"
      @update:model-value="text = String($event)"
    />
    <InputGroupAddon>
      <HugeiconsIcon :icon="Search01Icon" aria-hidden="true" />
    </InputGroupAddon>
  </InputGroup>
</template>
