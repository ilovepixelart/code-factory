<script setup lang="ts">
import { ArrowLeft02Icon, Delete02Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { usePressed } from '../lib/pressed'

// An archived ticket's actions in the Archive table: Restore while it is archived, and Delete.
const { id, archived, busy } = defineProps<{ id: string; archived: boolean; busy: boolean }>()
const emit = defineEmits<{ restore: []; remove: [] }>()
const { press, spins } = usePressed()
</script>

<template>
  <div class="inline-flex items-center gap-1">
    <Button
      v-if="archived"
      type="button"
      variant="outline"
      class="gap-1.5"
      :aria-label="`Restore ${id}`"
      :title="`Put ${id} back on the board`"
      :disabled="busy"
      @click="press('restore', () => emit('restore'))"
    >
      <Spinner v-if="spins('restore', busy)" data-icon="inline-start" />
      <HugeiconsIcon
        v-else
        :icon="ArrowLeft02Icon"
        data-icon="inline-start"
        aria-hidden="true"
      />Restore
    </Button>
    <Button
      type="button"
      variant="ghost"
      size="icon"
      :aria-label="`Delete ${id}`"
      :title="`Delete ${id}`"
      :disabled="busy"
      @click="press('remove', () => emit('remove'))"
    >
      <Spinner v-if="spins('remove', busy)" />
      <HugeiconsIcon v-else :icon="Delete02Icon" aria-hidden="true" />
    </Button>
  </div>
</template>
