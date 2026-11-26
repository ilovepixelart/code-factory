<script setup lang="ts">
import { CommandLineIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { Button } from '@/components/ui/button'
import { FieldError } from '@/components/ui/field'
import { Spinner } from '@/components/ui/spinner'
import { usePressed } from '../../../lib/pressed'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from '@/components/ui/item'

// AI Elements' Confirmation: a tool call waiting on a yes or no, as an Item with Deny and
// Approve. The board names the answers, decides which one carries the page's primary style and
// shows what was asked in full under the title, which clamps to one line.
const {
  busy,
  approve = 'Approve',
  deny = 'Deny',
  approveVariant = 'default',
  error = '',
} = defineProps<{
  busy?: boolean
  approve?: string
  deny?: string
  approveVariant?: 'default' | 'secondary'
  error?: string
}>()
const emit = defineEmits<{ approve: []; deny: [] }>()
// Of the two answers, only the one pressed shows a Spinner while it is sent.
const { press, spins } = usePressed()
defineSlots<{ title: () => unknown; default?: () => unknown; description?: () => unknown }>()
</script>

<template>
  <Item size="sm">
    <ItemMedia variant="icon">
      <HugeiconsIcon :icon="CommandLineIcon" />
    </ItemMedia>
    <ItemContent>
      <ItemTitle><slot name="title" /></ItemTitle>
      <slot />
      <ItemDescription v-if="$slots.description"><slot name="description" /></ItemDescription>
    </ItemContent>
    <ItemActions>
      <Button
        type="button"
        size="sm"
        variant="outline"
        :disabled="busy"
        @click="press('deny', () => emit('deny'))"
      >
        <Spinner v-if="spins('deny', busy)" data-icon="inline-start" />{{ deny }}
      </Button>
      <Button
        type="button"
        size="sm"
        :variant="approveVariant"
        :disabled="busy"
        @click="press('approve', () => emit('approve'))"
      >
        <Spinner v-if="spins('approve', busy)" data-icon="inline-start" />{{ approve }}
      </Button>
    </ItemActions>
    <FieldError v-if="error" class="basis-full">{{ error }}</FieldError>
  </Item>
</template>
