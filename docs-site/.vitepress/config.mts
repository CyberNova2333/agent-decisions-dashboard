import { defineConfig } from 'vitepress'
import { guideLinks } from './guide-links.mts'

const repoGuideRouteMap: Record<string, string> = {
  'README.md': 'docs/architecture',
  'walkthroughs/one-real-run.md': 'docs/architecture#真实运行全链路走读',
  'code-map.md': 'docs/architecture#源码目录与模块地图',
  'glossary.md': 'docs/architecture#关键边界与决策迁移',
  'modules/save-idempotency-and-recovery.md': 'docs/architecture#持久化与恢复机制',
  'modules/states-and-agent-workflow.md': 'docs/contracts',
  'references/source-evidence.md': 'docs/architecture#源码证据与验证边界',
  'references/quality-review.md': 'docs/architecture#源码证据与验证边界',
  'change-log.md': 'docs/architecture#关键边界与决策迁移',
}

export default defineConfig({
  cleanUrls: true,
  markdown: {
    config(md) {
      md.use(guideLinks(repoGuideRouteMap))
    },
  },
  locales: {
    root: {
      label: '简体中文',
      lang: 'zh-CN',
      title: 'Agent Decisions Dashboard 官方文档',
      description: '面向个人与本机 AI 编程工具协作的 Python 标准库 + SQLite 本地决策台账与审阅工作台文档。',
      themeConfig: {
        siteTitle: 'Agent 决策面板',
        nav: [
          { text: '首页', link: '/' },
          { text: '起步与部署', link: '/docs/' },
          { text: '接口与契约', link: '/docs/contracts' },
          { text: '原理与源码', link: '/docs/architecture' },
          { text: 'GitHub', link: 'https://github.com/CyberNova2333/agent-decisions-dashboard' },
        ],
        sidebar: [
          {
            text: '文档导览',
            items: [
              { text: '起步与配置部署', link: '/docs/' },
              { text: '接口与扩展契约', link: '/docs/contracts' },
              { text: '原理与源码导览', link: '/docs/architecture' },
            ],
          },
        ],
        outline: { level: [2, 3], label: '本页目录' },
        docFooter: { prev: '上一页', next: '下一页' },
      },
    },
    en: {
      label: 'English',
      lang: 'en-US',
      link: '/en/',
      title: 'Agent Decisions Dashboard Documentation',
      description: 'Documentation for the Python standard-library and SQLite local technical decision ledger and review workbench.',
      themeConfig: {
        siteTitle: 'Agent Decisions',
        nav: [
          { text: 'Home', link: '/en/' },
          { text: 'Setup & Config', link: '/en/docs/' },
          { text: 'Contracts & Hooks', link: '/en/docs/contracts' },
          { text: 'Architecture & Code', link: '/en/docs/architecture' },
          { text: 'GitHub', link: 'https://github.com/CyberNova2333/agent-decisions-dashboard' },
        ],
        sidebar: [
          {
            text: 'Documentation Guide',
            items: [
              { text: 'Setup & Configuration', link: '/en/docs/' },
              { text: 'API Contracts & Extensions', link: '/en/docs/contracts' },
              { text: 'Architecture, Code & Migrations', link: '/en/docs/architecture' },
            ],
          },
        ],
        outline: { level: [2, 3], label: 'On this page' },
        docFooter: { prev: 'Previous page', next: 'Next page' },
      },
    },
  },
  themeConfig: {
    search: { provider: 'local' },
  },
})
