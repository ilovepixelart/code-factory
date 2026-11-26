<script setup lang="ts">
import { computed, nextTick } from 'vue'
import { Field, FieldContent, FieldError, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'

// A property of a ticket in its column: the label left of its input, which takes the classes
// given. A refusal of its value shows under the input and is its description (CF-1201). A decimal
// property asks for a number pad.
const {
  id,
  label,
  name,
  placeholder,
  title = '',
  decimal,
  readonly,
  error = '',
} = defineProps<{
  id: string
  label: string
  name: string
  placeholder: string
  title?: string
  decimal?: boolean
  /** Shown like the others, never typed in; a click selects all of it. */
  readonly?: boolean
  error?: string | undefined
}>()
const emit = defineEmits<{ change: [] }>()
const text = defineModel<string>({ required: true })
defineOptions({ inheritAttrs: false })

const errorId = computed(() => `${id}-error`)
// shadcn-vue's controls pass a typed value on from a watcher, after the event, and a select fires
// `change` right after `input`: a change saves once that value has reached the model.
async function changed(): Promise<void> {
  await nextTick()
  emit('change')
}
function selectAll(event: FocusEvent): void {
  if (readonly) (event.target as HTMLInputElement).select()
}
</script>

<template>
  <Field :data-invalid="error ? true : undefined">
    <FieldLabel :for="id">{{ label }}</FieldLabel>
    <FieldContent class="min-w-0">
      <Input
        :id="id"
        :model-value="text"
        :name="name"
        :inputmode="decimal ? 'decimal' : undefined"
        :readonly="readonly"
        :class="$attrs.class"
        :placeholder="placeholder"
        :title="title || text || undefined"
        :aria-describedby="error ? errorId : undefined"
        :aria-invalid="error ? true : undefined"
        @update:model-value="text = String($event)"
        @change="changed()"
        @focus="selectAll($event)"
      />
      <FieldError v-if="error" :id="errorId">{{ error }}</FieldError>
    </FieldContent>
  </Field>
</template>
