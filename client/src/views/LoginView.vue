<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/authStore'

const authStore = useAuthStore()
const router = useRouter()

const isRegister = ref(false)
const username = ref('')
const password = ref('')

async function handleSubmit(): Promise<void> {
  if (!username.value.trim() || !password.value) {
    ElMessage.warning('请填写用户名和密码')
    return
  }

  try {
    if (isRegister.value) {
      await authStore.register({
        username: username.value.trim(),
        password: password.value,
      })
      ElMessage.success('注册成功，已自动登录')
    } else {
      await authStore.login({
        username: username.value.trim(),
        password: password.value,
      })
      ElMessage.success('登录成功')
    }
    router.push({ name: 'Chat' })
  } catch (err: unknown) {
    const msg =
      (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? (isRegister.value ? '注册失败' : '登录失败，请检查账号密码')
    ElMessage.error(typeof msg === 'string' ? msg : '操作失败')
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-card__brand">
        <div class="brand-icon">📚</div>
        <h1>企业知识库</h1>
        <p>智能问答 · RAG 检索 · 强引用溯源</p>
      </div>

      <el-form @submit.prevent="handleSubmit">
        <el-form-item>
          <el-input
            v-model="username"
            placeholder="用户名"
            size="large"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="password"
            type="password"
            placeholder="密码"
            size="large"
            show-password
            :prefix-icon="Lock"
            @keyup.enter="handleSubmit"
          />
        </el-form-item>

        <el-button
          type="primary"
          size="large"
          class="submit-btn"
          :loading="authStore.loading"
          native-type="submit"
        >
          {{ isRegister ? '注册并登录' : '登 录' }}
        </el-button>
      </el-form>

      <p class="toggle-mode">
        {{ isRegister ? '已有账号？' : '没有账号？' }}
        <a href="#" @click.prevent="isRegister = !isRegister">
          {{ isRegister ? '去登录' : '立即注册' }}
        </a>
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #0e7490 100%);
}

.login-card {
  width: 400px;
  padding: 40px 36px;
  background: rgba(255, 255, 255, 0.97);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.login-card__brand {
  text-align: center;
  margin-bottom: 32px;
}

.brand-icon {
  font-size: 48px;
  margin-bottom: 8px;
}

.login-card__brand h1 {
  font-size: 24px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 6px;
}

.login-card__brand p {
  font-size: 13px;
  color: #64748b;
}

.submit-btn {
  width: 100%;
  height: 44px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 10px;
  background: linear-gradient(135deg, #1a56db 0%, #0e7490 100%);
  border: none;
  margin-top: 8px;
}

.toggle-mode {
  text-align: center;
  margin-top: 20px;
  font-size: 13px;
  color: #64748b;
}

.toggle-mode a {
  color: #1a56db;
  text-decoration: none;
  font-weight: 500;
}

.toggle-mode a:hover {
  text-decoration: underline;
}
</style>
