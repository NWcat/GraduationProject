<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router';
</script>

<template>
  <div>
    <!-- 导航栏 -->
    <!-- <nav style="padding: 20px; background: #f5f5f5;">
      <router-link to="/system" style="margin-right: 20px;">系统状态监控</router-link>
    </nav> -->
    <!-- 路由出口 -->
    <router-view />
  </div>
</template>

<style scoped>
:global(html, body, #app) {
  height: 100%;
  margin: 0;
}

/* Global scroll strategy: body locked, el-main is the only scroll container. */
:global(body) {
  overflow: hidden;
}
</style>
