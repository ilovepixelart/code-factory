<script setup lang="ts">
import { ItemGroup } from '@/components/ui/item'
import { nextTick, reactive } from 'vue'
import type { InboxItem } from '../../lib/metrics'
import { actionKeys, itemHref as page, rowId, ticketApi, useInbox, useSectionPage } from './inbox'
import { usePressed } from '../../lib/pressed'
import InboxNav from './InboxNav.vue'
import InboxRow from './InboxRow.vue'
import SectionCard from '../SectionCard.vue'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Field, FieldLabel } from '@/components/ui/field'
import { Textarea } from '@/components/ui/textarea'
import { AspectRatio } from '@/components/ui/aspect-ratio'
import {
  Attachment,
  AttachmentContent,
  AttachmentDescription,
  AttachmentGroup,
  AttachmentMedia,
  AttachmentTitle,
  AttachmentTrigger,
} from '@/components/ui/attachment'
import { SCREEN_RATIO } from '../../lib/screens'

// Captures waiting for approval, approved or sent back with a reason in place.
const { items } = defineProps<{ items: InboxItem[] }>()
const { now, busy, errors, run, primary } = useInbox()
const { press, spins } = usePressed()
const { paged, offset } = useSectionPage('screens', () => items)
const { rows } = paged
// A capture's reason being typed, by its ticket's page; an open form with nothing typed is ''.
const changes = reactive<Record<string, string | undefined>>({})
const changesId = (item: InboxItem): string =>
  `changes-${String(item.ticket?.repository)}-${String(item.ticket?.id)}`
const imageHref = (item: InboxItem, image: string): string =>
  `/api/captures/${encodeURIComponent(item.ticket?.repository ?? '')}/${String(item.ticket?.id)}/${item.reason}/${image}`
const imageName = (image: string): string => image.replace('.png', '').replaceAll('-', ' ')

// The reason takes the keyboard when its form opens, and Cancel gives it back to the button.
const focusId = (id: string): void => void nextTick(() => document.getElementById(id)?.focus())
function openChanges(item: InboxItem): void {
  changes[page(item)] ??= ''
  focusId(changesId(item))
}
function closeChanges(item: InboxItem): void {
  delete changes[page(item)]
  focusId(`${changesId(item)}-open`)
}

// Approve or Send back: only the one pressed shows its Spinner while the capture is sent.
const approve = (item: InboxItem) =>
  press(`approve ${page(item)}`, () =>
    run(actionKeys.screens(item), 'POST', `${ticketApi(item)}/screens-approval`),
  )
const sending = (item: InboxItem, which: string): boolean =>
  spins(`${which} ${page(item)}`, busy.value.has(actionKeys.screens(item)))

async function sendBack(item: InboxItem): Promise<void> {
  const key = page(item)
  const body = { reason: changes[key] }
  const sent = () =>
    run(actionKeys.screens(item), 'POST', `${ticketApi(item)}/screens-changes`, body)
  if (await press(`send back ${key}`, sent)) {
    delete changes[key]
  }
}
</script>

<template>
  <SectionCard
    v-if="items.length"
    heading="inbox-screens"
    title="Screens to approve"
    :count="items.length"
    description="captured on the current tree; Review waits for you"
  >
    <ItemGroup class="gap-3">
      <template v-for="(item, n) in rows" :key="page(item)">
        <InboxRow
          :id="rowId('screens', item)"
          :item="item"
          :now="now"
          :error="errors[actionKeys.screens(item)] ?? ''"
          wrap
        >
          <template #actions>
            <Button
              :id="`${changesId(item)}-open`"
              type="button"
              variant="ghost"
              :aria-expanded="changes[page(item)] !== undefined"
              @click="openChanges(item)"
            >
              Request changes
            </Button>
            <Button
              type="button"
              :variant="primary('screens', offset + n)"
              :disabled="busy.has(actionKeys.screens(item))"
              @click="approve(item)"
            >
              <Spinner v-if="sending(item, 'approve')" data-icon="inline-start" />Approve
            </Button>
          </template>
          <AttachmentGroup v-if="item.images.length">
            <Attachment
              v-for="image in item.images"
              :key="image"
              orientation="vertical"
              class="has-data-[slot=attachment-content]:w-48"
            >
              <AttachmentMedia variant="image" class="aspect-auto">
                <AspectRatio :ratio="SCREEN_RATIO">
                  <img
                    :src="imageHref(item, image)"
                    :alt="imageName(image)"
                    loading="lazy"
                    class="size-full object-cover"
                  />
                </AspectRatio>
              </AttachmentMedia>
              <AttachmentContent>
                <AttachmentTitle>{{ imageName(image) }}</AttachmentTitle>
                <AttachmentDescription
                  >tree <span class="font-mono">{{ item.reason }}</span></AttachmentDescription
                >
              </AttachmentContent>
              <AttachmentTrigger as-child>
                <a
                  :href="imageHref(item, image)"
                  target="_blank"
                  rel="noopener noreferrer"
                  :aria-label="`Open ${imageName(image)}`"
                ></a>
              </AttachmentTrigger>
            </Attachment>
          </AttachmentGroup>
          <form
            v-if="changes[page(item)] !== undefined"
            class="grid gap-2 pt-1"
            :aria-label="`Request changes to ${item.ticket?.id}`"
            @submit.prevent="sendBack(item)"
          >
            <Field>
              <FieldLabel :for="changesId(item)">What should change?</FieldLabel>
              <Textarea
                :id="changesId(item)"
                :model-value="changes[page(item)] ?? ''"
                name="reason"
                rows="2"
                @update:model-value="changes[page(item)] = String($event)"
              />
            </Field>
            <div class="flex justify-end gap-2">
              <Button type="button" variant="ghost" @click="closeChanges(item)"> Cancel </Button>
              <Button
                variant="secondary"
                type="submit"
                :disabled="!changes[page(item)]?.trim() || busy.has(actionKeys.screens(item))"
              >
                <Spinner v-if="sending(item, 'send back')" data-icon="inline-start" />Send back
              </Button>
            </div>
          </form>
        </InboxRow>
      </template>
    </ItemGroup>
    <InboxNav section="screens" label="screens" :paged="paged" />
  </SectionCard>
</template>
