<script setup lang="ts">
import { computed } from 'vue'
import { HugeiconsIcon } from '@hugeicons/vue'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { ACTOR_ICONS, ACTOR_ROLES, type ActorKind } from '../../lib/teamNow'

const { kind, name } = defineProps<{ kind: ActorKind; name: string }>()
const initials = computed(() => {
  const label = name.trim()
  if (kind !== 'owner' || label.toLowerCase() === 'you') return ''
  const [first, second] = label.match(/\p{L}[\p{L}\p{M}]*/gu) ?? []
  if (!first) return ''
  const letters = Array.from(first)
  if (!second) return letters.slice(0, 2).join('').toUpperCase()
  return [...letters.slice(0, 1), ...Array.from(second).slice(0, 1)].join('').toUpperCase()
})
const role = computed(() => ACTOR_ROLES[kind])
</script>

<template>
  <span class="flex min-w-0 items-center gap-2 text-muted-foreground">
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger as-child>
          <span class="inline-flex shrink-0">
            <Avatar size="sm" role="img" :aria-label="role" class="after:border-0">
              <AvatarFallback
                :class="kind === 'owner' ? 'font-semibold' : 'rounded-md'"
                class="text-foreground/75"
              >
                <template v-if="initials">{{ initials }}</template>
                <HugeiconsIcon
                  v-else
                  :icon="ACTOR_ICONS[kind]"
                  class="size-3.5"
                  aria-hidden="true"
                />
              </AvatarFallback>
            </Avatar>
          </span>
        </TooltipTrigger>
        <TooltipContent>{{ role }}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
    <span class="min-w-0 wrap-anywhere">{{ name }}</span>
  </span>
</template>
