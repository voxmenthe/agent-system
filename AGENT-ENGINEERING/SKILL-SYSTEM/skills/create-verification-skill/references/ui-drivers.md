# Choose and exercise the real UI surface

Use the target's existing browser or UI harness first and preserve a
user-selected transport. A driver is useful only if it reaches the actual
surface being claimed. This reference provides conditional methods; it does
not install tools or certify every platform.

| Surface | Starting point | Important limit |
| --- | --- | --- |
| Web application | Existing Playwright/browser harness or available browser tool | API requests alone do not prove the UI path |
| Electron renderer | Existing Electron/CDP driver and an identified app window | Renderer reload does not apply main-process/preload changes |
| Native window or menu | Available accessibility/input driver | Browser DOM access cannot exercise an OS-native control |
| Canvas or image-led UI | Current screenshot/image observations and actual input | DOM assertions may omit the important rendered behavior |
| Mobile/simulator | Project-supported device/simulator harness | Record the exercised platform and prerequisites; do not infer support from desktop |

## Browser path

1. **Bind the instance.** Launch the intended source/build with owned data and
   a fresh profile, or establish identity and authorized access to the supplied
   instance. An arbitrary healthy port or familiar page title is not enough.
   Prefer an assigned ephemeral port for an owned server; never kill a process
   merely because it occupies the expected port.
2. **Drive one complete journey.** Use current roles, labels, stable selectors,
   and actual input. Reinspect after navigation or structural changes rather
   than trusting stale handles. Prefer state-aware waits with deadlines over
   sleeps or generic network-idle as a proxy for completion.
3. **Observe the result.** Match the visible result to the actual created ID,
   downloaded file, API response, or persisted state required by the claim.
   Register a response/download observer before the triggering action. Keep
   console/network failures when relevant; an empty console is not acceptance.
4. **Rerun at the right boundary.** Reload for the browser changes that permit
   it; restart the owned process when server/main-process state changed. After
   surprising behavior, distinguish unhealthy environment, driver drift, and
   product failure before retrying.
5. **Retain proof and settle ownership.** Save useful observations outside
   disposable state. Close only owned pages, browser sessions, processes, and
   data handles on failed as well as successful attempts. Check that proof
   remains readable after teardown.

A focused negative can show that a rejected operation stays rejected or that
a disconnected/backend-wrong result is not mistaken for UI success. Do not
replace the app component, inject internal state, or mock the application just
to make the public-path assertion pass.

## Availability and claims

Read the installed tool's help before using unfamiliar flags. Use existing
dependencies; tool installation, personal-profile reuse, and external service
effects retain their own task authority. A missing native/mobile driver leaves
that branch unexercised, not passing and not a requirement to install a platform.
State whether evidence comes from a fixture, a real product, or an installed
host. A browser screenshot does not certify native menus, visual fidelity,
concurrency, or persistence unless those properties were actually checked.

Source ideas: Cursor's control-ui recipe and existing Playwright/Electron
interaction patterns. No upstream driver implementation is bundled here.
