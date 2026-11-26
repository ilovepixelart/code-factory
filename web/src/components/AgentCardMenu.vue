<script setup lang="ts">
import { MoreHorizontalIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

// An agent card's menu: Check, Test model and Remove, so one action leads the card (CF-1078).
const { name, connected, local, locked, checking } = defineProps<{
  name: string
  connected: boolean
  local: boolean
  locked: boolean
  checking: boolean
}>()
const emit = defineEmits<{ check: []; test: []; remove: [] }>()
const more = computed(() => `More actions for ${name}`)
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button variant="ghost" size="icon" data-menu :aria-label="more">
        <HugeiconsIcon :icon="MoreHorizontalIcon" aria-hidden="true" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" class="w-44">
      <DropdownMenuGroup>
        <DropdownMenuItem v-if="connected" key="check" :disabled="checking" @select="emit('check')">
          Check <span class="sr-only">{{ name }}</span>
        </DropdownMenuItem>
        <DropdownMenuItem v-if="local" key="test" :disabled="locked" @select="emit('test')">
          Test model <span class="sr-only">{{ name }}</span>
        </DropdownMenuItem>
        <DropdownMenuItem variant="destructive" :disabled="locked" @select="emit('remove')">
          Remove <span class="sr-only">{{ name }}</span>
        </DropdownMenuItem>
      </DropdownMenuGroup>
    </DropdownMenuContent>
  </DropdownMenu>
</template>
