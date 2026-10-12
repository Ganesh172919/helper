# Reference audit and implementation plan

The product name is **Maya the Helper**. Available source and narrative references describe a
Python desktop assistant with reviewed screenshots, live chat and reusable instructions.

## What was actually supplied

`tool_sharescreen.py` (externally supplied reference) is a 12,673-byte raw ctypes/Win32
program, not a Qt application. The pasted Python attachment implements the same overlay.
The other two attachments are specifications. The detailed build brief ends at FR-PROV-7;
later section numbers it refers to are absent. No separate second working program was found.

`StealthOverlayOS.launch()` registers a native window class and runs a Windows message loop.
The popup is layered, topmost, non-activating, 480 × 320 at (120,120), with alpha 215/255.
It subscribes to clipboard updates, draws white wrapped text with GDI, measures text height,
and scrolls through mouse wheel, arrows, Page Up/Down, Home/End, and Alt+Shift+Up/Down.
Alt+Shift+N toggles visibility. It requests Windows capture exclusion.

There is **no screenshot capture, AI request, worker thread, streaming, floating orb,
settings, credential store, history, or model discovery** in that source. Clipboard text
is the only input. We do not execute the legacy clipboard listener during installation.
The original Downloads file is preserved unchanged.

## Issues addressed in the new implementation

- Some GDI/kernel APIs in the reference lack pointer-safe signatures; partial declarations
  do not make the whole file 64-bit safe. Qt owns drawing/font resources in Maya.
- Return values for class registration, hotkeys, and capture exclusion are unchecked.
  Maya reports hotkey conflicts and uses hide/capture/restore as a capture fallback.
- `GetMessageW` can return -1, which the existing loop treats as a normal message.
  Qt owns the event loop and shutdown lifecycle instead.
- The only window cannot accept chat input because it is non-activating. Maya keeps its orb
  non-activating and lets the input panel acquire focus when deliberately opened.
- Clipboard watching can ingest private text. The latest request restores the reference viewer as
  **More / orb / tray → Floating clipboard viewer**, with an explicit Watch switch initially OFF.
  It uses native Qt notifications while visible, masks recognizable secrets, bounds text, and clears
  on hiding/pausing. Use in chat is explicit; copied content never automatically goes to a provider.
- Capture exclusion is a best-effort Windows API, not a universal guarantee against recording.

## Build sequence

1. Set up a Python 3.13 virtual environment, pinned runtime dependencies, and entry point.
2. Implement UI-free request types, validation, SQLite history/memory, and skill instructions.
3. Implement tested SSE transport and dynamic Gemini/OpenRouter catalogs, then extra adapters.
4. Build Qt chat, settings/model picker, tray, orb, and compact panel with shared conversation.
5. Add explicit monitor/window/region capture, preview/redaction, Windows shortcuts, safe shutdown.
6. Run mocked API, database, privacy, image, and Qt integration tests; launch and inspect native UI.
7. Document verified results and limitations, including live requests awaiting user-configured keys.

## Latest supplied source

The October 10 code attachment (`b277d78f-370b-4b17-a722-e8059bb8d715`) is byte-identical to
the preserved Downloads reference, SHA-256
`79985b08d3eeb6acdd07224e818658dbde2263aed7dcdead7251301944a21fd0`.
Its clipboard, opacity, scrolling, show/hide and capture-exclusion behavior is now available inside
Maya through `ui/clipboard.py`. Qt owns text/event resources; the original ctypes program is not
run as another process or allowed to compete for hotkeys. The new panel initially shows without
activating, permits deliberate focus for selection/scroll keys, and uses a native movable/resizable
tool-window frame. The latest repeated narrative (`33333c7c-04e0-4a8a-8e56-d480bbeed552`)
reinforces the Python local scope and streaming preference. Gemini classification extends the
instruction framework; see SMART_ROUTING for the data and fallback contracts.

The next attachments (`88697b9b-4d54-4892-a1dc-a17483fd5a8e` and
`cab395d9-12cd-45e3-b08b-4addaf78e063`) repeat the same Python source and narrative.
The code again matches the preserved Downloads SHA-256 above. The new request adds the sculpted
Maya identity, smaller topmost UI, more instructions and additional verification; it supplies no
additional API implementation or second independent Python program. Those additions extend the
same Qt/controller pipeline rather than launching another competing Win32 event loop.

The latest repeated source remains byte-identical to the SHA-256 above. The accompanying request
changes publication preferences: remove creator details and preloaded memories, provide an empty
environment template, keep the compact identity, expand skills and verify screen-share protection.
That request takes precedence over earlier personalized narrative. No pasted biography or filled
configuration is shipped. The capture-exclusion lifecycle guard extends the reference to Qt dialogs
and menus; [SCREEN_SHARING](SCREEN_SHARING.md) records its native checks and recorder limits.
