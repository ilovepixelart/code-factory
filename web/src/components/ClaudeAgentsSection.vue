<script setup lang="ts">
import SectionCard from './SectionCard.vue'
import ContentCard from './ContentCard.vue'
import { Badge } from '@/components/ui/badge'
import { BotIcon } from '@hugeicons/core-free-icons'
import { HugeiconsIcon } from '@hugeicons/vue'
import { computed } from 'vue'
import type { ClaudeAgent } from '../generated/ClaudeAgent'
import type { Unread } from '../generated/Unread'
import { overriddenBy } from '../lib/claudeAgents'
import { usePaged } from '../lib/paging'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import PageNav from './PageNav.vue'
import { Item, ItemContent, ItemDescription, ItemGroup, ItemTitle } from '@/components/ui/item'

// The agents Claude Code reads from its own folders, global and this project's: shown, never
// changed here, since the files are the owner's. A name defined twice shows which file applies.
const props = defineProps<{ agents: ClaudeAgent[]; unread: Unread[] }>()
const shadowed = computed(() => overriddenBy(props.agents))
const paged = usePaged(() => props.agents, 'claude_', 10)
</script>

<template>
  <SectionCard
    heading="claude-agents-heading"
    title="Claude Code agents"
    :count="agents.length"
    description="read only, not agents the board runs: edit them in ~/.claude/agents or this project's .claude/agents"
    :empty="!(agents.length || unread.length)"
  >
    <template #empty
      ><Empty
        ><EmptyHeader
          ><EmptyMedia variant="icon"
            ><HugeiconsIcon :icon="BotIcon" aria-hidden="true" /></EmptyMedia
          ><EmptyTitle>No Claude Code agents</EmptyTitle
          ><EmptyDescription
            >They are defined in ~/.claude/agents and this project's
            .claude/agents.</EmptyDescription
          ></EmptyHeader
        ></Empty
      ></template
    >
    <template v-if="agents.length || unread.length">
      <ItemGroup class="gap-3">
        <ContentCard v-for="agent in paged.rows.value" :key="agent.path" role="listitem">
          <Item class="py-3">
            <ItemContent class="min-w-0 gap-2">
              <ItemTitle class="max-w-full flex-wrap">
                <span class="wrap-anywhere font-mono">{{ agent.name }}</span>
                <Badge variant="outline">{{ agent.place }}</Badge>
                <span v-if="shadowed[agent.path]" class="text-muted-foreground"
                  >overridden by {{ shadowed[agent.path] }}</span
                >
              </ItemTitle>
              <ItemDescription class="line-clamp-none wrap-anywhere">
                {{ agent.description }}
              </ItemDescription>
              <p class="text-sm text-muted-foreground wrap-anywhere">
                {{ agent.model || 'inherits model' }} ·
                {{ agent.tools.length ? agent.tools.join(', ') : 'all tools' }}
              </p>
            </ItemContent>
          </Item>
        </ContentCard>
        <ContentCard v-for="file in unread" :key="file.path" role="listitem">
          <Item class="py-3">
            <ItemContent class="min-w-0">
              <ItemDescription class="line-clamp-none wrap-anywhere"
                >not read: <span class="font-mono">{{ file.path }}</span
                >&#32;<span class="text-foreground">{{ file.why }}</span></ItemDescription
              >
            </ItemContent>
          </Item>
        </ContentCard>
      </ItemGroup>
      <PageNav
        label="Claude Code agents"
        prefix="claude_"
        :fallback="10"
        :total="paged.total.value"
        :page="paged.page.value"
        :size="paged.size.value"
      />
    </template>
  </SectionCard>
</template>
