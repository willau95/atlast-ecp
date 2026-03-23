import { defineConfig } from 'vitepress'

export default defineConfig({
  base: '/',
  title: 'ATLAST Protocol',
  description: 'Evidence Chain Protocol — Trust Infrastructure for the Agent Economy',
  head: [
    ['link', { rel: 'icon', href: '/favicon.ico' }],
  ],
  themeConfig: {
    logo: '/logo.svg',
    nav: [
      { text: 'Guide', link: '/guide/getting-started' },
      { text: 'SDK', items: [
        { text: 'Python', link: '/sdk/python' },
        { text: 'TypeScript', link: '/sdk/typescript' },
      ]},
      { text: 'API', link: '/api/' },
      { text: 'ECP Spec', link: '/spec/' },
      { text: 'GitHub', link: 'https://github.com/willau95/atlast-ecp' },
    ],
    sidebar: {
      '/guide/': [
        {
          text: 'Getting Started',
          items: [
            { text: 'Introduction', link: '/guide/' },
            { text: 'Quick Start', link: '/guide/getting-started' },
            { text: 'Core Concepts', link: '/guide/concepts' },
            { text: 'Architecture', link: '/guide/architecture' },
          ],
        },
        {
          text: 'Features',
          items: [
            { text: 'Content Vault', link: '/guide/content-vault' },
            { text: 'Proof Package', link: '/guide/proof-package' },
            { text: 'Chain Integrity', link: '/guide/chain-integrity' },
            { text: 'Trust Signals', link: '/guide/trust-signals' },
          ],
        },
      ],
      '/sdk/': [
        {
          text: 'Python SDK',
          items: [
            { text: 'Overview', link: '/sdk/python' },
            { text: 'wrap() — Zero-Code', link: '/sdk/python-wrap' },
            { text: 'record() — Explicit', link: '/sdk/python-record' },
            { text: 'CLI Reference', link: '/sdk/python-cli' },
            { text: 'Adapters', link: '/sdk/python-adapters' },
          ],
        },
        {
          text: 'TypeScript SDK',
          items: [
            { text: 'Overview', link: '/sdk/typescript' },
            { text: 'wrap() & track()', link: '/sdk/typescript-wrap' },
          ],
        },
      ],
      '/api/': [
        {
          text: 'Server API',
          items: [
            { text: 'Overview', link: '/api/' },
            { text: 'Authentication', link: '/api/auth' },
            { text: 'Batches', link: '/api/batches' },
            { text: 'Verification', link: '/api/verify' },
            { text: 'Attestations', link: '/api/attestations' },
          ],
        },
      ],
    },
    socialLinks: [
      { icon: 'github', link: 'https://github.com/willau95/atlast-ecp' },
    ],
    footer: {
      message: 'Released under the MIT License.',
      copyright: 'Copyright © 2026 ATLAST Protocol',
    },
    search: {
      provider: 'local',
    },
  },
})
