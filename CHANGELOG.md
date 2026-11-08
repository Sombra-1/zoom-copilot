# Changelog

## 2.0.1 — 2026-11-08

- Separated spoken AI replies from transcription. The workspace shows queued
  audio and marks detected gaps in the transcript and Markdown export.
- Tested proposed developer edits in a temporary copy before applying them.
  Failed tests discard the candidate, and a concurrent edit is preserved.
- Generated meeting notes from the available transcript in batches, carrying
  forward earlier decisions, action items and open questions.
- Shortened Groq transcription timeouts and limited transient failures to one
  retry. Stopped sessions cancel pending retries.
- Corrected Local Whisper model discovery for custom Hugging Face caches.

## 2.0.0 — 2026-11-05

- Redesigned the provider setup, meeting workspace, answer panel and compact layout.
- Added official Codex CLI integration with account/model discovery, structured
  answers, cancellable requests and explicit image context.
- Added one-click whole-screen watching and fresh images on questions while
  vision is enabled; each workspace starts with vision Off.
- Added formatted math/code answers, history, pinning, meeting notes and Markdown export.
- Added a branded windowless Windows launcher, native icon, tray and shortcut.
- Connected Patreon support and GitHub star buttons, with one support invitation
  after three accumulated hours of use.
- Added cached background update checks, installed/latest version notices,
  manual checks, and per-release dismissal.
- Fixed lifecycle, audio ordering, capture, setup, windowless error handling,
  and shutdown issues; refreshed dependency requirements and Windows CI.
- Kept the native PNG logo within its size budget when optional Pillow is absent,
  preserving answer space in small windows at standard display scaling.
- Published actual app screenshots, a short synthetic-content demo and logo sources.
