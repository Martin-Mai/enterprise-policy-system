<script setup lang="ts">
import loginBg from '@/assets/images/login-bg.jpg'
</script>

<template>
  <div class="auth-page">
    <aside class="auth-brand" :style="{ backgroundImage: `url(${loginBg})` }">
      <div class="auth-brand__overlay">
        <div class="auth-brand__content">
          <h2 class="auth-brand__title">企业智能知识库</h2>
          <p class="auth-brand__tagline">让知识有序流动</p>
        </div>
      </div>
    </aside>

    <main class="auth-form-area">
      <div class="auth-form-wrapper">
        <slot />
      </div>
    </main>
  </div>
</template>

<style scoped>
.auth-page {
  display: flex;
  width: 100%;
  height: 100vh;
  min-height: 100vh;
  overflow: hidden;
}

.auth-brand {
  flex: 0 0 50%;
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
  position: relative;
  transition: opacity 0.3s ease;
}

.auth-brand__overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    135deg,
    rgba(0, 0, 0, 0.55) 0%,
    rgba(0, 0, 0, 0.35) 50%,
    rgba(0, 0, 0, 0.45) 100%
  );
  display: flex;
  align-items: flex-start;
  padding: 64px 48px;
}

.auth-brand__content {
  max-width: 420px;
}

.auth-brand__title {
  font-size: 32px;
  font-weight: 700;
  color: #ffffff;
  line-height: 1.35;
  letter-spacing: 0.02em;
  margin-bottom: 12px;
}

.auth-brand__tagline {
  font-size: 18px;
  color: rgba(255, 255, 255, 0.85);
  line-height: 1.6;
  font-weight: 400;
}

.auth-form-area {
  flex: 0 0 50%;
  background: #f8fafc;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  transition: background 0.3s ease;
}

.auth-form-wrapper {
  width: 100%;
  max-width: 400px;
  margin: 0 auto;
}

@media (max-width: 767px) {
  .auth-brand {
    display: none;
  }

  .auth-form-area {
    flex: 1;
    padding: 24px;
  }
}
</style>
