# System Agentic Browser Expansion

## Goals

- Deliver an on-device "agentic browser" experience that extends beyond web automation to full operating-system task execution.
- Maintain the existing local-first, privacy-preserving architecture while adding a capability-driven automation stack.
- Provide a generalized action registry that models the OS capabilities available to the planner, so the same plan machinery can orchestrate browser, shell, application, and file-automation tasks.
- Preserve safety: explicit user-managed permissions, sandboxed execution, auditable logs, and capability scopes.

## Non-Goals

- Shipping a closed-source cloud service. All components remain local and open source.
- Offering elevated/root-only operations or bypassing OS security prompts.
- Replacing focused, domain-specific integrations (calendar, mail) with uncontrolled automation routines.

## Capability Model

```
Capability        Description                              Permission flag
--------------    ---------------------------------------  ------------------
browser           Browser automation via Playwright        browser_access
shell             Command execution & scripts              shell_access
files             File system read/write operations        file_access
apps              Launching & controlling GUI apps         automation_access
calendar          Calendar actions (existing)              calendar_access
mail              Compose email drafts (existing)          mail_access
notes             Create Notes entries                     automation_access
```

The plugin manifest enumerates the capabilities that are explicitly enabled. When the runtime is packaged, the manifest shipped with the app is signed and checked before use.

## Architecture Overview

```
┌────────────────────┐      ┌────────────────────┐     ┌────────────────────┐
│ Swift UI (OnDevice │      │ REST/gRPC API      │     │ Orchestrator       │
│ AI App)            │◀────▶│ core/api.py        │◀───▶│ core/orchestrator.py│
└────────┬───────────┘      └────────┬───────────┘     └────────┬───────────┘
         │                             │                          │
         │  permissions/settings       │                          │
         ▼                             ▼                          ▼
┌────────────────────────────┐ ┌────────────────────────────┐ ┌───────────────────────┐
│ SystemAutomationRuntime    │ │ SandboxHarness              │ │ SystemActionRegistry  │
│ core/plugin_runtime.py     │ │ core/sandbox.py             │ │ core/system_agent.py │
└────────────┬───────────────┘ └────────────┬────────────────┘ └────────────┬────────┘
             │                                │                               │
             ▼                                ▼                               ▼
      Browser helpers                  OS process limits             Capability handlers
      tools/agent_browser.py           (timeouts, perms)             (shell, files, apps)
```

### Key Components

- **SystemActionRegistry** – Declarative catalog describing each automation action (name, summary, required permission scopes, handler callable).
- **SystemAutomationRuntime** – Runtime dispatcher that validates permissions, looks up handlers, executes them (with sandbox when high risk), and returns structured results. Existing `PluginRuntime` evolves into this component.
- **Plan Schema** – `core/orchestrator.Orchestrator.plan` prompt enumerates the registry actions so language models can produce JSON plans referencing them. All actions follow the same schema `{name, payload, sensitive, preview_required}`.
- **Permissions** – Extend config (`permissions.*`) and app UI models to include `automation_access`, `shell_access`, and `browser_access`. These toggle handler availability and sandbox options.
- **Sandbox Integration** – High-risk actions (shell/files) run through `SandboxHarness.execute` with gated permissions. Low-risk AppleScript actions run inline but remain guarded by capability flags.
- **Auditing** – Existing `write_event` logging records dispatch, results, and permission state for review.

## Implementation Phases

1. **Scaffolding**
   - Introduce `core/system_agent.py` with registry + handler base classes.
   - Refactor `core/plugin_runtime.py` to delegate to the new registry.
   - Update default plugin manifest to include new capability names.

2. **Permission & Config updates**
   - Extend `SandboxPermissions` and Swift `AutomationPermissions` with `browserAccess`, `automationAccess`, `shellAccess`.
   - Wire REST endpoints (`/api/permissions`) to persist the new flags.

3. **Action Handlers**
   - Implement first-class handlers: `system.shell.run`, `system.files.write`, `system.apps.launch`, `browser.navigate/click/fill/extract/screenshot`, `system.apple_script.run`.
   - Each handler validates payload schema and returns structured responses (status, stdout, result path, etc.).

4. **Planning Prompt**
   - Update orchestrator prompt with concise action catalog and examples, ensuring local models understand the new actions.
   - Provide fallback when the model outputs unrecognized actions (surface error & preview requirement).

5. **UI Enhancements**
   - Surface new permission toggles and runtime action audit output in the Swift UI, highlighting preview/sensitive actions.

6. **Testing & Docs**
   - Unit tests for registry dispatch, sandboxed shell action, permission enforcement, and API responses.
   - Update README/docs with usage guide and security considerations.

## Security Considerations

- Capabilities remain opt-in. The default configuration ships with automation, shell, and browser access disabled.
- Each handler declares the permission scope it needs; dispatcher enforces it before execution.
- Shell executions run in sandbox directories to prevent access outside allowed roots.
- Structured payload validation ensures LLM output cannot inject arbitrary keys.
- Audit log retains each execution with payload snapshot and result.

## Open Questions / Future Work

- Cross-platform support: Windows (PowerShell) and Linux (DBus/X11) adapters.
- Continuous UI automation (e.g., via Accessibility API) with human-in-the-loop preview.
- Capability discovery API so external planners can query supported actions programmatically.
- Workflow recording & replay (macro support) built on top of action registry.

## Acceptance Criteria

- New registry module provides at least five system-level actions beyond the browser helpers.
- Planner prompt enumerates actions; manual tests show the local model produces well-formed `system.*` actions.
- Permissions disabled → action invocation rejected with clear error, logged in audit trail.
- REST `/api/execute` returns structured results for the new actions, and tests cover success + permission-denied paths.
- Documentation updated to explain enabling permissions and adding custom actions.
