import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

/**
 * 配置 Markdown 渲染器，代码块启用 highlight.js 高亮
 */
const md: MarkdownIt = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight(str: string, lang: string): string {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang, ignoreIllegals: true }).value}</code></pre>`
      } catch {
        // 降级为普通转义
      }
    }
    const escaped = md.utils.escapeHtml(str)
    return `<pre class="hljs"><code>${escaped}</code></pre>`
  },
})

/** 将 Markdown 文本渲染为 HTML */
export function renderMarkdown(content: string): string {
  return md.render(content)
}
