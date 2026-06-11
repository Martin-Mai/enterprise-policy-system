<script setup lang="ts">
import { ref } from 'vue'
import { Document } from '@element-plus/icons-vue'
import type { Citation } from '@/types/chat'

defineProps<{
  citations: Citation[]
}>()

/** 弹窗中展示的完整 Chunk 文本 */
const dialogVisible = ref(false)
const selectedCitation = ref<Citation | null>(null)

/** 点击引用卡片，弹窗展示完整预览文本 */
function openPreview(citation: Citation): void {
  selectedCitation.value = citation
  dialogVisible.value = true
}
</script>

<template>
  <div v-if="citations.length > 0" class="citation-list">
    <el-collapse class="citation-collapse">
      <el-collapse-item title="参考来源" name="citations">
        <div class="citation-grid">
          <div
            v-for="(item, index) in citations"
            :key="`${item.chunk_id}-${index}`"
            class="citation-card"
            @click="openPreview(item)"
          >
            <div class="citation-card__header">
              <el-icon><Document /></el-icon>
              <span class="citation-card__filename">{{ item.file_name }}</span>
              <el-tag v-if="item.inferred" size="small" type="warning">推断</el-tag>
            </div>
            <div class="citation-card__meta">
              <span>第 {{ item.page_no }} 页</span>
              <span v-if="item.section_title">· {{ item.section_title }}</span>
            </div>
            <p class="citation-card__preview">{{ item.text_preview }}</p>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- 源码查阅弹窗：等宽字体 + 舒适行高 -->
    <el-dialog
      v-model="dialogVisible"
      :title="selectedCitation?.file_name ?? '引用详情'"
      width="680px"
      destroy-on-close
      class="citation-dialog"
    >
      <template v-if="selectedCitation">
        <div class="dialog-meta">
          <el-tag type="info">第 {{ selectedCitation.page_no }} 页</el-tag>
          <el-tag v-if="selectedCitation.section_title" type="success">
            {{ selectedCitation.section_title }}
          </el-tag>
        </div>
        <div class="dialog-content">
          {{ selectedCitation.text_preview }}
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.citation-list {
  margin-top: 16px;
}

/* 折叠面板标题字号放大 */
.citation-collapse :deep(.el-collapse-item__header) {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
  line-height: 1.6;
  border-bottom-color: #e2e8f0;
}

.citation-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 4px;
}

/* 网格布局排开引用卡片 */
.citation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
  padding: 8px 0 4px;
}

.citation-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 14px 16px;
  cursor: pointer;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.citation-card:hover {
  border-color: #3b82f6;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.1);
}

.citation-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  color: #3b82f6;
  font-weight: 600;
  font-size: 15px;
  line-height: 1.6;
}

.citation-card__filename {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.citation-card__meta {
  font-size: 14px;
  line-height: 1.6;
  color: #64748b;
  margin-bottom: 8px;
}

.citation-card__preview {
  font-size: 14px;
  line-height: 1.7;
  color: #475569;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.dialog-meta {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}

/* 弹窗源码区：等宽字体 14px，行高 1.6 */
.dialog-content {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 18px 20px;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.6;
  color: #334155;
  max-height: 420px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
