// VitePress 官方文档配置 (Coolify 架构风格 + 中英双语支持)
import { defineConfig } from 'vitepress'

export default defineConfig({
  cleanUrls: true,
  locales: {
    root: {
      label: '简体中文',
      lang: 'zh-CN',
      title: "Agent Decisions Dashboard 官方文档",
      description: "Agent Decisions Dashboard 是针对自主 Agent 运行时的决策全景可视化与可观测性审计面板。",
      themeConfig: {
        siteTitle: "Agent 决策面板",
        nav: [
          { text: '官网首页', link: '/' },
          { text: '快速入门', link: '/docs/' },
          { text: '系统架构', link: '/docs/architecture' },
          { text: '配置指南', link: '/docs/configuration' },
          { text: '常见问题', link: '/docs/faq' },
          { text: 'GitHub', link: 'https://github.com/CyberNova2333/agent-decisions-dashboard' },
        ],
        sidebar: [
          {
            text: '快速入门',
            items: [
              { text: '项目概览与上手', link: '/docs/' },
            ]
          },
          {
            text: '系统架构',
            items: [
              { text: '架构设计与全景图', link: '/docs/architecture' },
            ]
          },
          {
            text: '配置与实践',
            items: [
              { text: '配置与使用指南', link: '/docs/configuration' },
            ]
          },
          {
            text: '运维与支持',
            items: [
              { text: '常见问题与排错', link: '/docs/faq' },
            ]
          }
        ],
        outline: { level: [2, 3], label: '本页目录' },
        docFooter: { prev: '上一页', next: '下一页' },
      }
    },
    en: {
      label: 'English',
      lang: 'en-US',
      link: '/en/',
      title: "Agent Decisions Dashboard Documentation",
      description: "Agent Decisions Dashboard is a visual decision graph and observability audit platform for autonomous AI agent runtimes.",
      themeConfig: {
        siteTitle: "Agent Decisions",
        nav: [
          { text: 'Home', link: '/en/' },
          { text: 'Quick Start', link: '/en/docs/' },
          { text: 'Architecture', link: '/en/docs/architecture' },
          { text: 'Configuration', link: '/en/docs/configuration' },
          { text: 'FAQ', link: '/en/docs/faq' },
          { text: 'GitHub', link: 'https://github.com/CyberNova2333/agent-decisions-dashboard' },
        ],
        sidebar: [
          {
            text: 'Quick Start',
            items: [
              { text: 'Overview & Getting Started', link: '/en/docs/' },
            ]
          },
          {
            text: 'Architecture',
            items: [
              { text: 'Architecture Design', link: '/en/docs/architecture' },
            ]
          },
          {
            text: 'Configuration & Practice',
            items: [
              { text: 'Configuration Guide', link: '/en/docs/configuration' },
            ]
          },
          {
            text: 'Operations & Support',
            items: [
              { text: 'FAQ & Diagnostics', link: '/en/docs/faq' },
            ]
          }
        ],
        outline: { level: [2, 3], label: 'On this page' },
        docFooter: { prev: 'Previous page', next: 'Next page' },
      }
    }
  },
  themeConfig: {
    search: { provider: 'local' },
  }
})
