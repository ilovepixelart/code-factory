<script setup lang="ts">
import { useEventListener } from '@vueuse/core'
import { nextTick, ref, useTemplateRef } from 'vue'
import { Button } from '@/components/ui/button'
import { Field, FieldLabel } from '@/components/ui/field'
import { cn } from '@/lib/utils'

// One property of a ticket being edited, quiet until it is changed: its label and its value as a
// ghost button (an empty value in muted words that say what empty means). Pressed, the row's own
// control (the slot) takes its place, opened with the focus, and goes back once the focus leaves it
// or on Escape. A refused value keeps the control open with its error; a read-only one has no button.
const { id, label, value, empty, code, readonly, invalid } = defineProps<{
  /** The id of the control the slot draws, which takes the focus. */
  id: string
  label: string
  /** The value as words. */
  value: string
  /** What an empty value says. */
  empty: string
  code?: boolean
  readonly?: boolean
  /** The board refused the value: the control stays open so its error is read. */
  invalid?: boolean
}>()
defineSlots<{ default: () => unknown }>()

const editing = ref(false)
const box = useTemplateRef<HTMLElement>('box')

async function open(): Promise<void> {
  editing.value = true
  await nextTick()
  const control = document.getElementById(id)
  control?.focus()
  // One press opens the control whole: a select its list, the date its calendar.
  if (control instanceof HTMLSelectElement) {
    try {
      control.showPicker()
    } catch {
      // A browser without showPicker leaves the select focused, one more press from its list.
    }
  } else if (control instanceof HTMLButtonElement) control.click()
}

// The control goes back once the focus leaves it, or on Escape; listened for on the box from here, as
// the box itself is no control.
useEventListener(box, 'focusout', (event: FocusEvent) => {
  const next = event.relatedTarget
  // The date's calendar opens in a popover outside the row: moving into it keeps the row open.
  const inside =
    next instanceof Element &&
    (box.value?.contains(next) === true || next.closest('[data-slot="popover-content"]') !== null)
  if (!inside) editing.value = false
})
useEventListener(box, 'keydown', (event: KeyboardEvent) => {
  if (event.key !== 'Escape') return
  event.stopPropagation()
  editing.value = false
})
</script>

<template>
  <!-- The control stays in the page while the row is quiet, hidden from sight, the tab order and the
       accessibility tree, so the row has one control whether it is open or not. -->
  <div v-show="editing || invalid" ref="box" data-property-editing>
    <slot />
  </div>
  <Field v-show="!(editing || invalid)" class="gap-1" data-property-shown>
    <FieldLabel :for="`${id}-shown`">{{ label }}</FieldLabel>
    <span
      v-if="readonly"
      :id="`${id}-shown`"
      :class="
        cn(
          'min-w-0 truncate text-sm',
          code && value && 'font-mono',
          !value && 'text-muted-foreground',
        )
      "
      :title="value || undefined"
      >{{ value || empty }}</span
    >
    <Button
      v-else
      :id="`${id}-shown`"
      type="button"
      variant="ghost"
      size="sm"
      class="min-w-0 justify-start px-2"
      :title="value || undefined"
      @click="open()"
      ><span
        :class="cn('truncate', code && value && 'font-mono', !value && 'text-muted-foreground')"
        >{{ value || empty }}</span
      ></Button
    >
  </Field>
</template>
