<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import AuthLayout from '@/components/AuthLayout.vue'
import { registerUser } from '@/api/auth'

const router = useRouter()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)

async function handleSubmit(): Promise<void> {
  if (!username.value.trim() || !password.value) {
    ElMessage.warning('请填写用户名和密码')
    return
  }

  if (confirmPassword.value && confirmPassword.value !== password.value) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }

  loading.value = true
  try {
    await registerUser({
      username: username.value.trim(),
      password: password.value,
    })
    ElMessage.success('注册成功，请登录')
    router.push({ name: 'Login' })
  } catch (err: unknown) {
    const msg =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? '注册失败，请稍后重试'
    ElMessage.error(typeof msg === 'string' ? msg : '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthLayout>
    <div class="form-card">
      <header class="form-card__header">
        <h1 class="form-card__title">创建账号</h1>
        <p class="form-card__subtitle">加入企业智能知识库，畅享智能检索与问答</p>
      </header>

      <el-form class="form-card__form" @submit.prevent="handleSubmit">
        <el-form-item>
          <el-input
            v-model="username"
            class="underline-input"
            placeholder="用户名"
            size="large"
            :prefix-icon="User"
          />
        </el-form-item>

        <el-form-item>
          <el-input
            v-model="password"
            class="underline-input"
            type="password"
            placeholder="密码"
            size="large"
            show-password
            :prefix-icon="Lock"
          />
        </el-form-item>

        <el-form-item>
          <el-input
            v-model="confirmPassword"
            class="underline-input"
            type="password"
            placeholder="确认密码（可选）"
            size="large"
            show-password
            :prefix-icon="Lock"
            @keyup.enter="handleSubmit"
          />
        </el-form-item>

        <el-button
          type="primary"
          class="submit-btn"
          :loading="loading"
          native-type="submit"
        >
          注 册
        </el-button>
      </el-form>

      <p class="form-card__footer">
        已有账号？
        <router-link class="form-link" :to="{ name: 'Login' }">去登录</router-link>
      </p>
    </div>
  </AuthLayout>
</template>

<style scoped>
.form-card {
  width: 100%;
  padding: 40px 36px;
  background: #ffffff;
  border-radius: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: box-shadow 0.3s ease, transform 0.3s ease;
}

.form-card__header {
  margin-bottom: 32px;
}

.form-card__title {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.3;
  margin-bottom: 8px;
}

.form-card__subtitle {
  font-size: 14px;
  color: #94a3b8;
  line-height: 1.5;
}

.form-card__form :deep(.el-form-item) {
  margin-bottom: 24px;
}

.form-card__form :deep(.underline-input .el-input__wrapper) {
  padding: 8px 4px;
  background: transparent;
  border: none;
  border-bottom: 1px solid #e2e8f0;
  border-radius: 0;
  box-shadow: none !important;
  transition: border-color 0.3s ease;
}

.form-card__form :deep(.underline-input .el-input__wrapper:hover) {
  border-bottom-color: #cbd5e1;
}

.form-card__form :deep(.underline-input .el-input__wrapper.is-focus) {
  border-bottom: 2px solid #2563eb;
}

.form-card__form :deep(.underline-input .el-input__inner) {
  font-size: 15px;
  color: #1e293b;
}

.form-card__footer {
  text-align: center;
  margin-top: 28px;
  font-size: 14px;
  color: #94a3b8;
}

.form-link {
  color: #94a3b8;
  text-decoration: none;
  transition: color 0.3s ease;
}

.form-link:hover {
  color: #2563eb;
}

.submit-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  font-weight: 600;
  border-radius: 8px;
  background: #2563eb;
  border: none;
  box-shadow: none;
  margin-top: 8px;
  transition: background 0.3s ease;
}

.submit-btn:hover {
  background: #1d4ed8;
}
</style>
