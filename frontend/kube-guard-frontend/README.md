# kube-guard-frontend

This template should help get you started developing with Vue 3 in Vite.

## Recommended IDE Setup

[VS Code](https://code.visualstudio.com/) + [Vue (Official)](https://marketplace.visualstudio.com/items?itemName=Vue.volar) (and disable Vetur).

## Recommended Browser Setup

- Chromium-based browsers (Chrome, Edge, Brave, etc.):
  - [Vue.js devtools](https://chromewebstore.google.com/detail/vuejs-devtools/nhdogjmejiglipccpnnnanhbledajbpd) 
  - [Turn on Custom Object Formatter in Chrome DevTools](http://bit.ly/object-formatters)
- Firefox:
  - [Vue.js devtools](https://addons.mozilla.org/en-US/firefox/addon/vue-js-devtools/)
  - [Turn on Custom Object Formatter in Firefox DevTools](https://fxdx.dev/firefox-devtools-custom-object-formatters/)

## Type Support for `.vue` Imports in TS

TypeScript cannot handle type information for `.vue` imports by default, so we replace the `tsc` CLI with `vue-tsc` for type checking. In editors, we need [Volar](https://marketplace.visualstudio.com/items?itemName=Vue.volar) to make the TypeScript language service aware of `.vue` types.

## Customize configuration

See [Vite Configuration Reference](https://vite.dev/config/).

## Project Setup

```sh
npm install
```

### Compile and Hot-Reload for Development

```sh
npm run dev
```

### Type-Check, Compile and Minify for Production

```sh
npm run build
```

```
kube-guard-frontend
├─ 📁.vscode
│  └─ 📄extensions.json
├─ 📁public
│  └─ 📄favicon.ico
├─ 📁src
│  ├─ 📁api
│  │  ├─ 📄ai.ts
│  │  ├─ 📄auth.ts
│  │  ├─ 📄http.ts
│  │  ├─ 📄logs.ts
│  │  ├─ 📄monitor.ts
│  │  ├─ 📄namespaces.ts
│  │  ├─ 📄nodes.ts
│  │  ├─ 📄overview.ts
│  │  ├─ 📄prom.ts
│  │  ├─ 📄tenants.ts
│  │  ├─ 📄tools.ts
│  │  ├─ 📄users.ts
│  │  └─ 📄workloads.ts
│  ├─ 📁layouts
│  │  └─ 📄K8sLayout.vue
│  ├─ 📁router
│  │  └─ 📄index.ts
│  ├─ 📁stores
│  │  ├─ 📄auth.ts
│  │  └─ 📄counter.ts
│  ├─ 📁utils
│  ├─ 📁views
│  │  ├─ 📁ai
│  │  │  ├─ 📄CpuForecast.vue
│  │  │  └─ 📄ResourceForecast.vue
│  │  ├─ 📁Tenants
│  │  │  ├─ 📄NamespaceDetail.vue
│  │  │  ├─ 📄NamespaceList.vue
│  │  │  └─ 📄Namespaces.vue
│  │  ├─ 📄ChangePasswordView.vue
│  │  ├─ 📄Home.vue
│  │  ├─ 📄KubectlTerminal.vue
│  │  ├─ 📄LoginView.vue
│  │  ├─ 📄MetricsQuery.vue
│  │  ├─ 📄MonitorOverview.vue
│  │  ├─ 📄MonitorWall.vue
│  │  ├─ 📄NodeList.vue
│  │  ├─ 📄Overview.vue
│  │  ├─ 📄SystemStatus.vue
│  │  └─ 📄WorkloadsOverview.vue
│  ├─ 📄App.vue
│  └─ 📄main.ts
├─ 📄.env
├─ 📄.gitignore
├─ 📄env.d.ts
├─ 📄index.html
├─ 📄package-lock.json
├─ 📄package.json
├─ 📄README.md
├─ 📄tsconfig.app.json
├─ 📄tsconfig.json
├─ 📄tsconfig.node.json
└─ 📄vite.config.ts
```
```
kube-guard-frontend
├─ 📁.vscode
│  └─ 📄extensions.json
├─ 📁public
│  └─ 📄favicon.ico
├─ 📁src
│  ├─ 📁api
│  │  ├─ 📄ai.ts
│  │  ├─ 📄auth.ts
│  │  ├─ 📄http.ts
│  │  ├─ 📄logs.ts
│  │  ├─ 📄monitor.ts
│  │  ├─ 📄namespaces.ts
│  │  ├─ 📄nodes.ts
│  │  ├─ 📄ops.ts
│  │  ├─ 📄overview.ts
│  │  ├─ 📄prom.ts
│  │  ├─ 📄tenants.ts
│  │  ├─ 📄tools.ts
│  │  ├─ 📄users.ts
│  │  └─ 📄workloads.ts
│  ├─ 📁components
│  │  └─ 📄AiAssistantFloat.vue
│  ├─ 📁layouts
│  │  └─ 📄K8sLayout.vue
│  ├─ 📁router
│  │  └─ 📄index.ts
│  ├─ 📁stores
│  │  ├─ 📄aiSuggestions.ts
│  │  ├─ 📄assistant.ts
│  │  ├─ 📄auth.ts
│  │  └─ 📄counter.ts
│  ├─ 📁utils
│  ├─ 📁views
│  │  ├─ 📁ai
│  │  │  ├─ 📄AiHeal.vue
│  │  │  ├─ 📄AiSuggestions.vue
│  │  │  └─ 📄ResourceForecast.vue
│  │  ├─ 📁Tenants
│  │  │  ├─ 📄NamespaceDetail.vue
│  │  │  ├─ 📄NamespaceList.vue
│  │  │  └─ 📄Namespaces.vue
│  │  ├─ 📄ChangePasswordView.vue
│  │  ├─ 📄Home.vue
│  │  ├─ 📄KubectlTerminal.vue
│  │  ├─ 📄LoginView.vue
│  │  ├─ 📄MetricsQuery.vue
│  │  ├─ 📄MonitorOverview.vue
│  │  ├─ 📄MonitorWall.vue
│  │  ├─ 📄NodeList.vue
│  │  ├─ 📄Overview.vue
│  │  ├─ 📄SystemStatus.vue
│  │  └─ 📄WorkloadsOverview.vue
│  ├─ 📄App.vue
│  └─ 📄main.ts
├─ 📄.env
├─ 📄.gitignore
├─ 📄env.d.ts
├─ 📄index.html
├─ 📄package-lock.json
├─ 📄package.json
├─ 📄README.md
├─ 📄tsconfig.app.json
├─ 📄tsconfig.json
├─ 📄tsconfig.node.json
└─ 📄vite.config.ts
```