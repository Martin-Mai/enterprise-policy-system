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
    <el-collapse>
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

    <el-dialog
      v-model="dialogVisible"
      :title="selectedCitation?.file_name ?? '引用详情'"
      width="640px"
      destroy-on-close
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
  margin-top: 12px;
}

.citation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  padding: 4px 0;
}

.citation-card {
  background: linear-gradient(145deg, #f8fafc 0%, #f1f5f9 100%);
  border: 1px solid var(--eps-border);
  border-radius: 10px;
  padding: 12px 14px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.citation-card:hover {
  border-color: var(--eps-primary);
  box-shadow: 0 4px 12px rgba(26, 86, 219, 0.12);
  transform: translateY(-2px);
}

.citation-card__header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  color: var(--eps-primary);
  font-weight: 600;
  font-size: 13px;
}

.citation-card__filename {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.citation-card__meta {
  font-size: 12px;
  color: var(--eps-text-muted);
  margin-bottom: 8px;
}

.citation-card__preview {
  font-size: 12px;
  color: #475569;
  line-height: 1.5;
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

.dialog-content {
  background: #f8fafc;
  border-radius: 8px;
  padding: 16px;
  line-height: 1.75;
  font-size: 14px;
  color: #334155;
  max-height: 400px;
  overflow-y: auto;
  white-space: pre-wrap;
}
</style>
