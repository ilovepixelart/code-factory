<script setup lang="ts">
import ContentCard from '../ContentCard.vue'
import { ItemGroup } from '@/components/ui/item'
import { PERMISSION_WAIT_SECONDS } from '../../generated/Limits'
import type { InboxItem } from '../../lib/metrics'
import Confirmation from '../ai/Confirmation/Confirmation.vue'
import { actionKeys, itemHref, useInbox, useSectionPage } from './inbox'
import InboxAge from './InboxAge.vue'
import InboxNav from './InboxNav.vue'
import InboxTicketLink from './InboxTicketLink.vue'
import RequestPayload from './RequestPayload.vue'
import SectionCard from '../SectionCard.vue'

// Requests an agent's hook waits on, allowed or denied in place.
const { items } = defineProps<{ items: InboxItem[] }>()
const { now, busy, errors, run, primary } = useInbox()
const { paged, offset } = useSectionPage('permissions', () => items)
const { rows } = paged

function answer(item: InboxItem, verdict: 'allow' | 'deny'): void {
  void run(
    actionKeys.permissions(item),
    'POST',
    `/api/permissions/${item.request?.id ?? ''}/${verdict}`,
  )
}
</script>

<template>
  <SectionCard
    v-if="items.length"
    heading="inbox-permissions"
    title="Permission requests"
    :count="items.length"
    :description="`an agent waits; unanswered requests are denied in ${PERMISSION_WAIT_SECONDS / 60} min`"
  >
    <ItemGroup class="gap-3">
      <template v-for="(item, n) in rows" :key="actionKeys.permissions(item)">
        <ContentCard :id="actionKeys.permissions(item)" role="listitem">
          <Confirmation
            :data-inbox-item="`Allow ${item.request?.tool ?? ''}?`"
            :data-href="itemHref(item)"
            data-permission
            tabindex="-1"
            approve="Allow"
            :approve-variant="primary('permissions', offset + n)"
            :busy="busy.has(actionKeys.permissions(item))"
            :error="errors[actionKeys.permissions(item)] ?? ''"
            @approve="answer(item, 'allow')"
            @deny="answer(item, 'deny')"
          >
            <template #title>Allow {{ item.request?.tool }}?</template>
            <RequestPayload
              v-if="item.request"
              :tool="item.request.tool"
              :summary="item.request.summary"
            />
            <template #description
              ><InboxTicketLink :item="item" /><template v-if="item.note">
                · {{ item.note }}</template
              >
              · <InboxAge :since="item.since" :now="now"
            /></template>
          </Confirmation>
        </ContentCard>
      </template>
    </ItemGroup>
    <InboxNav section="permissions" label="permission requests" :paged="paged" />
  </SectionCard>
</template>
