<script setup lang="ts">
import { nextTick } from 'vue'
import { useTicketForm } from './context'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Textarea } from '@/components/ui/textarea'

// The ticket's title, a heading edited in place (its border shows on hover and focus), one line
// that wraps as it grows: Enter leaves it, and leaving a changed title saves it. A refusal shows
// under it and is its description.
const { id } = defineProps<{ id: string }>()

const { model, save, errors } = useTicketForm()
// shadcn-vue's controls pass a typed value on from a watcher, after the event, and a select fires
// `change` right after `input`: a change saves once that value has reached the model.
async function changed(): Promise<void> {
  await nextTick()
  await save()
}
</script>

<template>
  <Field :data-invalid="errors.title ? true : undefined">
    <FieldLabel :for="`${id}-title`" class="sr-only">Title</FieldLabel>
    <Textarea
      :id="`${id}-title`"
      :model-value="model.title"
      name="title"
      data-shortcut="title"
      required
      rows="1"
      class="cn-font-heading -ml-2 min-h-0 border-transparent bg-transparent! text-lg font-semibold hover:border-input focus-visible:border-ring md:text-lg"
      placeholder="Ticket title"
      :aria-invalid="errors.title ? true : undefined"
      :aria-describedby="errors.title ? `${id}-title-error` : undefined"
      @update:model-value="model.title = String($event)"
      @keydown.enter.prevent="($event.target as HTMLTextAreaElement).blur()"
      @change="changed()"
    />
    <FieldError v-if="errors.title" :id="`${id}-title-error`">{{ errors.title }}</FieldError>
  </Field>
</template>
