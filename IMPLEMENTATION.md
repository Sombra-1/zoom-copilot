# Codex and intelligent overlay implementation

## Initial inspection and completed plan

The existing Tkinter app keeps setup, five AI providers, transcription, notes,
screen watch, capture exclusion, settings and the overlay in `zoom_copilot.py`.
`setup.py` and the batch launchers install optional capture/tray dependencies.
At initial inspection, 11 baseline unit tests passed. CI has since been updated
to Python 3.11/3.12/3.13. Current release results are in `RELEASE_CHECKS.md`.

Reuse ordered audio processing, generation identities, transcript-only notes,
smart transcript triggers, region selection, MSS/Pillow, atomic settings and
Windows display affinity. Preserve existing provider request formats.

Implement in these verified increments:

1. Introduce a provider registry while retaining legacy provider implementations.
2. Add an owned, hidden Codex app-server stdio process, account/model discovery,
   bounded requests, cancellation and shutdown. Reuse Codex-managed login only.
3. Connect text and image inputs with an ephemeral thread and validated schema.
4. Guard capture on the Tk thread, verify the actual capture path with synthetic
   windows, and hide private app surfaces for a frame if exclusion is unverified.
5. Add typed answer cards, local LaTeX/code rendering, disclosure and navigation.
6. Add explicit vision targets/triggers and presentation context.
7. Add opt-in, repository-scoped developer diagnostics and reviewed patch apply.
8. Run regression, UI, capture, transport, lint and security checks; document
   live account/platform limitations separately from automated test evidence.

## Architectural risks

- An accepted Windows affinity call is not evidence that a specific capturer or
  meeting recorder excludes the overlay. Local synthetic pixel tests and a safe
  fallback are needed. External recording remains a manual acceptance check.
- Codex app-server is versioned and evolving. Reject unavailable capabilities
  clearly; do not read credential files or assume model entitlement from catalogs.
- Meeting inference must have no general shell/MCP/desktop tools. Developer
  diagnostics must remain narrowly scoped and model output is untrusted.
- Tk widgets belong to the Tk thread. Old manual/notes/screen requests must be
  invalidated on clear, stop, settings changes and shutdown.
- Full LaTeX needs an offline renderer; missing rendering dependencies must leave
  the meeting UI usable and must never execute model-supplied HTML or commands.

Official references checked 2026-10-31:

- https://learn.chatgpt.com/docs/app-server
- https://learn.chatgpt.com/docs/auth
- https://learn.chatgpt.com/docs/config-file/config-reference

Validation results and operating instructions are recorded in `CODEX.md`.
