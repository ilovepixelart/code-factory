<script setup lang="ts">
import SectionCard from '../components/SectionCard.vue'
import { useRoute } from 'vue-router'
import { Button } from '@/components/ui/button'

// Any address the app has no page for.
const route = useRoute()
</script>

<template>
  <div class="page-wide">
    <SectionCard heading="not-found-heading" title="Nothing at this address">
      <div class="grid justify-items-start gap-4 text-sm">
        <p class="min-w-0 wrap-anywhere text-muted-foreground">
          There is no page at <span class="font-mono text-sm">{{ route.fullPath }}</span
          >.
        </p>
        <Button as-child variant="secondary"><RouterLink to="/tickets">Tickets</RouterLink></Button>
      </div>
    </SectionCard>
  </div>
</template>
