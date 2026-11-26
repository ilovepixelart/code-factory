<script setup lang="ts">
import { computed } from 'vue'
import type { Card } from '../lib/board'
import { PULL_STATES, pullState } from '../lib/pull_state'
import { Badge } from '@/components/ui/badge'

// The pull request's one state label, coloured per state (CF-1217); nothing without a pull request.
const { card } = defineProps<{ card: Pick<Card, 'pull' | 'check'> }>()
const state = computed(() => pullState(card))
</script>

<template>
  <Badge v-if="state" :variant="PULL_STATES[state].variant" :data-pull-state="state">{{
    PULL_STATES[state].words
  }}</Badge>
</template>
