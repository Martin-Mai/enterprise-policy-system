<script setup lang="ts">
import SessionSidebar from '@/components/SessionSidebar.vue'
import ChatView from '@/components/ChatView.vue'
</script>

<template>
  <div class="chat-layout">
    <SessionSidebar />
    <ChatView />
  </div>
</template>

<style scoped>
.chat-layout {
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
}
</style>
