# Tembr studio, web

The local interface for Tembr: record and manage voices, generate speech, run
outreach batches, and set up the profile that brands the pages your leads
receive. Next.js, App Router, all screens client components.

## It needs the API running

This is a front end only. Every screen talks to the FastAPI server on
`http://127.0.0.1:8100`, which owns the database, the audio files and the TTS
engines. Start that first, or the app loads and shows nothing but errors.

From the project root:

    powershell -File server\start.ps1     # API on :8100, loads the engine
    cd web && npm run dev                 # this app on :3000

Or `start-studio.ps1` at the root, which does both and opens the browser.

## Layout

    app/page.tsx            Generate: text to speech, plus the take history
    app/voices/             Voices: record, clone, organise, clean up
    app/outreach/           Outreach: leads in, one voice note per lead out
    app/settings/           Business profile, AI drafting, engine and disk
    components/RecordFlow   The record → check → name → save flow
    components/Waveform     Canvas player used everywhere audio appears
    lib/api.ts              Every call to the API, and the shared types

## Notes for anyone changing this

- `lib/api.ts` is the only place that knows the API's address. Nothing else
  should build a URL.
- Fonts are Archivo, Instrument Sans and IBM Plex Mono, loaded through
  `next/font` in `app/layout.tsx`.
- The design vocabulary lives in `app/globals.css`. Reuse the existing classes
  (`.chip`, `.icon-btn`, `.panel`, `.field`) rather than adding new ones; the
  screens are meant to look like one program.
- Read `AGENTS.md` in this folder before touching framework code. This is not
  the Next.js version most references describe.

## Deployment

There isn't any. Tembr runs on your own machine, which is the whole point: your
voice is biometric data and it never leaves the building. Nothing here is built
for or deployed to a hosting platform.
