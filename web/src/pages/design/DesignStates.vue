<script setup lang="ts">
import SectionCard from '../../components/SectionCard.vue'
import { Tick02Icon, UnavailableIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { toast } from 'vue-sonner'
import { statusWord, type BadgeTone } from '../../lib/status_tone'
import StatusBadge from '../../components/StatusBadge.vue'
import { Alert, AlertAction, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Kbd, KbdGroup } from '@/components/ui/kbd'
import { Progress } from '@/components/ui/progress'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'

// The status and feedback components of the /design page: a Badge per status tone, the loading
// states, Empty, Alert and a toast.
const TONES: BadgeTone[] = ['quiet', 'info', 'success', 'warning', 'error']
</script>

<template>
  <SectionCard
    heading="states-heading"
    title="Badges and states"
    description="Badge, Spinner, Skeleton, Progress, Kbd, Empty, Alert, Sonner"
  >
    <div class="flex flex-col gap-4">
      <div class="flex flex-wrap gap-2">
        <StatusBadge v-for="tone in TONES" :key="tone" :tone="tone">{{
          statusWord(tone)
        }}</StatusBadge>
      </div>
      <Separator />
      <p class="flex items-center gap-2 text-xs text-muted-foreground">
        <Spinner />Reading the board
      </p>
      <div class="flex flex-col gap-2">
        <Skeleton class="h-4 w-3/4" />
        <Skeleton class="h-4 w-1/2" />
      </div>
      <Progress :model-value="60" aria-label="A sample bar" />
      <p class="text-xs text-muted-foreground">
        Open the command menu with
        <KbdGroup><Kbd>⌘</Kbd><Kbd>K</Kbd></KbdGroup>
      </p>
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon"
            ><HugeiconsIcon :icon="Tick02Icon" aria-hidden="true"
          /></EmptyMedia>
          <EmptyTitle>Nothing waits on you</EmptyTitle>
          <EmptyDescription>An empty state with its icon.</EmptyDescription>
        </EmptyHeader>
      </Empty>
      <Alert>
        <AlertTitle>An alert with a heading</AlertTitle>
        <AlertDescription>Its words, and its action at the end.</AlertDescription>
        <AlertAction><Button type="button" variant="secondary" size="sm">Act</Button></AlertAction>
      </Alert>
      <Alert variant="destructive">
        <HugeiconsIcon :icon="UnavailableIcon" aria-hidden="true" />
        <AlertTitle>A destructive alert</AlertTitle>
      </Alert>
      <div>
        <Button type="button" variant="outline" @click="toast('A toast, the page notice')">
          Show a toast
        </Button>
      </div>
    </div>
  </SectionCard>
</template>
