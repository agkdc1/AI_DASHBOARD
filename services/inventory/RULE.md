## 🛡️ DEVELOPMENT PROTOCOL (CRITICAL)

### 1. CORE INTEGRITY (ISOLATION RULE)
- **STRICTLY FORBIDDEN:** Do NOT modify, delete, or rename any files inside the `inventree/` submodule directory.
- **ISOLATION:** All custom logic, plugins, and configurations MUST reside in your external `/plugins/` directory or `.env` file.
- **CONFIGURATION:** If you need to change a setting, use the `.env` file or InvenTree's dynamic settings UI. Never hardcode changes in `InvenTree/settings.py`.

### 2. RESOURCE EFFICIENCY (DOCUMENTATION FIRST RULE)
- **PRIORITIZE DOCS:** InvenTree has comprehensive documentation. Before reading any source code, you MUST reference the official documentation logic or standard Django/InvenTree plugin patterns.
- **MINIMIZE CODE READING:** Do NOT run `grep`, `find`, or read files inside `inventree/` as a first step. This consumes excessive tokens.
- **FALLBACK ONLY:** You are only allowed to inspect the core source code if:
  1. The documentation does not cover the specific hook/mixin you need.
  2. You have tried a standard implementation and it failed.
- **ASSUMPTION:** Assume standard InvenTree Plugin Mixins (`IntegrationPlugin`, `SettingsMixin`, `ScheduleMixin`, `UrlMixin`) work as documented. Do not verify their implementation details in the source code unless necessary.
