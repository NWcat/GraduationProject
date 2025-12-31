<script setup lang="ts"></script>

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

<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router';
</script>

<style scoped></style>
