<script setup lang="ts">
import ContentCard from '../ContentCard.vue'
import SectionCard from '../SectionCard.vue'
import type { InboxItem } from '../../lib/metrics'
import { actionKeys, useInbox, useSectionPage } from './inbox'
import InboxNav from './InboxNav.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { FieldError } from '@/components/ui/field'
import {
  Item,
  ItemActions,
  ItemContent,
  ItemFooter,
  ItemTitle,
  ItemGroup,
} from '@/components/ui/item'

// Kinds of request always allowed, offered as standing rules.
const { items } = defineProps<{ items: InboxItem[] }>()
const { busy, errors, run } = useInbox()
const { paged } = useSectionPage('rules', () => items)
const { rows } = paged
</script>

<template>
  <SectionCard
    v-if="items.length"
    heading="inbox-rules"
    title="Rules to adopt"
    :count="items.length"
    description="agents stop asking once you adopt a rule"
  >
    <ItemGroup class="gap-3">
      <template v-for="item in rows" :key="item.reason">
        <ContentCard role="listitem">
          <Item class="py-3">
            <ItemContent>
              <ItemTitle class="line-clamp-none wrap-anywhere">
                You allowed <span class="font-mono">{{ item.reason }}</span> all
                {{ item.count }} times
              </ItemTitle>
            </ItemContent>
            <ItemActions>
              <Button
                type="button"
                variant="secondary"
                :disabled="busy.has(actionKeys.rules(item))"
                @click="
                  run(actionKeys.rules(item), 'POST', '/api/permissions/rules', {
                    kind: item.reason,
                  })
                "
              >
                <Spinner v-if="busy.has(actionKeys.rules(item))" data-icon="inline-start" />Always
                allow
              </Button>
            </ItemActions>
            <ItemFooter v-if="errors[actionKeys.rules(item)]">
              <FieldError>{{ errors[actionKeys.rules(item)] }}</FieldError>
            </ItemFooter>
          </Item>
        </ContentCard>
      </template>
    </ItemGroup>
    <InboxNav section="rules" label="rules" :paged="paged" />
  </SectionCard>
</template>
