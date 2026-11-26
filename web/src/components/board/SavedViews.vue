<script setup lang="ts">
import { Folder01Icon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { ref, useId, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useSavedViews, viewUrl } from '../../lib/savedViews'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { usePressed } from '../../lib/pressed'
import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Field, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'

// The saved views: each a link to the board's address it was saved from, and a form that saves the
// address showing. The list is read again each time the popover opens.
const route = useRoute()
const { views, refresh, save, remove } = useSavedViews()
const open = ref(false)
const name = ref('')
const busy = ref(false)
const { press, spins } = usePressed()
const uid = useId()
watch(open, (now) => {
  if (now) void refresh()
})

async function submit(): Promise<void> {
  if (busy.value || !name.value.trim()) return
  busy.value = true
  const query = route.fullPath.split('?')[1]?.split('#')[0] ?? ''
  if (await save(name.value, query)) name.value = ''
  busy.value = false
}

async function erase(name: string): Promise<void> {
  if (busy.value) return
  busy.value = true
  await remove(name)
  busy.value = false
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button variant="ghost" class="gap-1.5">
        <HugeiconsIcon :icon="Folder01Icon" data-icon="inline-start" aria-hidden="true" /><span
          class="max-sm:sr-only"
          >Views</span
        >
      </Button>
    </PopoverTrigger>
    <PopoverContent align="end" class="w-64">
      <PopoverHeader>
        <PopoverTitle>Saved views</PopoverTitle>
      </PopoverHeader>
      <ul v-if="views.length" class="flex flex-col gap-1" aria-label="Saved views">
        <li v-for="view in views" :key="view.name" class="flex items-center gap-2">
          <RouterLink :to="viewUrl(view)" class="min-w-0 flex-1 truncate" @click="open = false">{{
            view.name
          }}</RouterLink>
          <Button
            type="button"
            variant="ghost"
            size="xs"
            :aria-label="`Delete view ${view.name}`"
            :disabled="busy"
            @click="press(`delete ${view.name}`, () => erase(view.name))"
            ><Spinner
              v-if="spins(`delete ${view.name}`, busy)"
              data-icon="inline-start"
            />Delete</Button
          >
        </li>
      </ul>
      <form class="flex flex-col gap-2" @submit.prevent="press('save', submit)">
        <Field>
          <FieldLabel :for="`${uid}-name`">View name</FieldLabel>
          <Input
            :id="`${uid}-name`"
            :model-value="name"
            @update:model-value="name = String($event)"
          />
        </Field>
        <Button type="submit" :disabled="busy || !name.trim()"
          ><Spinner v-if="spins('save', busy)" data-icon="inline-start" />Save view</Button
        >
      </form>
    </PopoverContent>
  </Popover>
</template>
