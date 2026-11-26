<script setup lang="ts">
import { parseDate, type DateValue } from '@internationalized/date'
import { cn } from 'cn'
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import { Field, FieldContent, FieldError, FieldLabel } from '@/components/ui/field'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

// A date property of a ticket in its column (Due): the label left of a date picker. The value is
// the ISO day (`2026-12-01`) the board stores; an empty one reads as `placeholder`. Picking a day
// or clearing it saves it, as a change of the other properties does.
const {
  id,
  label,
  placeholder,
  error = '',
} = defineProps<{
  id: string
  label: string
  placeholder: string
  error?: string | undefined
}>()
const emit = defineEmits<{ change: [] }>()
const text = defineModel<string>({ required: true })

const errorId = computed(() => `${id}-error`)
// A value the board holds that is not an ISO day still shows, as typed, and opens on today.
const day = computed(() => {
  try {
    return text.value ? parseDate(text.value) : undefined
  } catch {
    return undefined
  }
})

function set(value: DateValue | undefined, close: () => void): void {
  text.value = value ? value.toString() : ''
  emit('change')
  close()
}
</script>

<template>
  <Field :data-invalid="error ? true : undefined">
    <FieldLabel :for="id">{{ label }}</FieldLabel>
    <FieldContent class="min-w-0">
      <Popover v-slot="{ close }">
        <PopoverTrigger as-child>
          <Button
            :id="id"
            type="button"
            variant="outline"
            :class="cn('w-full justify-start font-normal', !text && 'text-muted-foreground')"
            :aria-describedby="error ? errorId : undefined"
            :aria-invalid="error ? true : undefined"
          >
            {{ text || placeholder }}
          </Button>
        </PopoverTrigger>
        <PopoverContent class="w-auto p-0" align="start">
          <Calendar
            :model-value="day ?? null"
            layout="month-and-year"
            initial-focus
            @update:model-value="set($event, close)"
          />
          <Button
            v-if="text"
            type="button"
            variant="ghost"
            class="m-2 mt-0"
            @click="set(undefined, close)"
          >
            Clear
          </Button>
        </PopoverContent>
      </Popover>
      <FieldError v-if="error" :id="errorId">{{ error }}</FieldError>
    </FieldContent>
  </Field>
</template>
