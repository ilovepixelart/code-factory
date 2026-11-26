<script setup lang="ts">
import { InputGroup } from '@/components/ui/input-group'
import { computed } from 'vue'
import { Field, FieldContent, FieldError, FieldLabel } from '@/components/ui/field'
import {
  TagsInput,
  TagsInputInput,
  TagsInputItem,
  TagsInputItemDelete,
  TagsInputItemText,
} from '@/components/ui/tags-input'

// A ticket's labels in its column: the label left of a tags input. The board stores them comma
// separated (`ui, auth`); a comma, Enter or leaving the box adds what was typed, and each added or
// removed label saves, as a change of the other properties does.
const {
  id,
  label,
  placeholder,
  hint = '',
  error = '',
} = defineProps<{
  id: string
  label: string
  placeholder: string
  hint?: string
  error?: string | undefined
}>()
const emit = defineEmits<{ change: [] }>()
const text = defineModel<string>({ required: true })

const errorId = computed(() => `${id}-error`)
const tags = computed(() =>
  text.value
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean),
)

function update(next: unknown[]): void {
  text.value = next.map(String).join(', ')
  emit('change')
}
</script>

<template>
  <Field :data-invalid="error ? true : undefined">
    <FieldLabel :for="id">{{ label }}</FieldLabel>
    <FieldContent class="min-w-0">
      <!-- In an InputGroup, so it has the Input's height, fill, border and text size. -->
      <InputGroup class="h-auto min-h-9">
        <TagsInput
          class="w-full min-w-0 border-0 bg-transparent px-2 py-0.5 shadow-none focus-within:ring-0"
          :model-value="tags"
          add-on-blur
          add-on-paste
          :aria-invalid="error ? true : undefined"
          @update:model-value="update($event)"
        >
          <TagsInputItem v-for="tag in tags" :key="tag" :value="tag">
            <TagsInputItemText />
            <!-- Reka labels the button by the tag's text, which would outrank its aria-label. -->
            <TagsInputItemDelete :aria-label="`Remove ${tag}`" :aria-labelledby="undefined" />
          </TagsInputItem>
          <TagsInputInput
            :id="id"
            data-slot="input-group-control"
            :size="1"
            class="min-w-0 px-0"
            :placeholder="tags.length ? '' : placeholder"
            :title="hint || undefined"
            :aria-describedby="error ? errorId : undefined"
          />
        </TagsInput>
      </InputGroup>
      <FieldError v-if="error" :id="errorId">{{ error }}</FieldError>
    </FieldContent>
  </Field>
</template>
