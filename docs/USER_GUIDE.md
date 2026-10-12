# Using Maya

Start with text chat. Configure your provider key and choose a discovered model. Type a question
and press Enter or Send. Shift+Enter inserts a newline. The selected task profile can stay Auto,
or you can choose Excel, commands/AI agents, code, Python/notebooks, research, writing, data/SQL,
web development, study, slides, or application troubleshooting. Quick prompts adapt to the selected
profile through **More → Quick prompts**. The profile is instruction text, not an autonomous tool or hidden application plugin.
There are 34 built-in skills, including Git, defensive security, APIs, testing, career guidance,
English, design/accessibility, systems and project planning. The new profiles cover algorithms,
statistics, engineering, business literacy, meeting notes and health terminology.
Preview them in **Settings → Smart routing**.

On a fresh cloud-provider setup, **Set up model** opens Providers directly. Once a catalog is
available, that control opens model selection. Compatible/local providers keep manual model
selection accessible. Send becomes available with a selected model and a question or reviewed image; your draft remains editable
during setup. The input well groups Paste, New, More and Send, with a clear keyboard focus border.

Providers now shows three setup steps and reports key availability for the base URL currently
displayed. **Show** temporarily reveals only a key you typed; it is masked on blur/hide/provider
change or after 30 seconds. **Clear input** keeps the stored key; Cancel discards typed input.
Changing the endpoint clears an unsaved key to avoid sending it to a different destination.

The model picker shows local match counts and explains empty catalogs or searches. **Reset filters**
affects the active tab only. Manual IDs are available for compatible/local providers. Image-input
confirmation belongs to the chosen unknown/manual model and resets when that choice changes.

In Preferences, **Reduced motion** keeps the activity icon static while preserving status updates.
The usual idle and hidden animations remain stopped regardless of that preference.

## Choose instructions with Gemini

Add a Gemini key in Providers, refresh its catalog, then enable **Settings → Smart routing → Use Gemini**.
Leave the task profile on Auto. Send first validates the answer, then Gemini chooses one existing skill.
Your answer can still use OpenRouter or another provider. The routing call has its own model/deadline
and may consume quota or money. The tab explains its redacted excerpt/title/profile-description payload;
no screenshot/history/memory is included in classification. An unavailable key/model, timeout or invalid/
uncertain result falls back locally. Choose a profile directly to bypass classification.
**More → Why this skill?** explains the last choice. Stop during routing keeps your draft without adding
a saved chat turn. Editing the draft, changing settings/profile, removing an image or turning Screen OFF
invalidates any pending decision. See [Smart routing](SMART_ROUTING.md) for details.

The normal window starts at 480 × 560 pixels; the floating panel is 360 × 440. Small displays
clamp the height to their available work area. Use the small navigation icon on the left to reveal
navigation; closing it returns to the smaller width. The sliders icon on the right opens Settings.
Both have tooltips and keyboard-accessible names. **More → Use compact window size**
resets a manually enlarged window. Navigation scrolls at small heights.

## Keep Maya beside your work

Press **Float** to collapse to the flower orb. Drag it to a screen edge. Click to open a compact
panel, or right-click for ask/model/profile/pause/settings controls. The orb does not take keyboard
focus. Click the panel's input when you want to type. Escape collapses the panel; Full window
opens the same conversation. Model choice, draft and screenshot remain shared.

**Pin** in the main header keeps Maya above ordinary desktop windows; it starts ON and remembers
your choice. The orb and quick panel remain topmost. Drag the flower/title space in the quick panel
to reposition it without changing your draft. **Settings → Preferences → Floating panel opacity**
controls translucency from 65% to 100%. The icon has shaped ceramic petals, a beveled jade base
and a soft gold glow, painted with vectors for a 3D appearance. It rests without a running timer;
its glow gently breathes during visible capture, classification or streaming. Hover brightens it.
The floating reader has transparent rounded corners and an opaque backing behind the text.

In both windows, **Screen OFF/ON** opens the capture controls. Opening this drawer only shows
controls. Use the inner **Screen: OFF/ON** switch to grant screen context, then Capture and review
the result. The status bar also shows screen permission. **Notice · Read details** opens the full
notice as plain text in either mode. Long statuses use an ellipsis while their full tooltips and
accessibility descriptions keep the small reader usable
without letting long errors/statuses enlarge it during a stream.
Minimum sizes are 400 × 450 for the main window and 320 × 360 for the quick panel.
The welcome chips fill a draft; **More → Quick prompts** offers the selected skill's suggestions.

The idle orb can be resized/dimmed in Settings. Its bloom/ring and tooltip show idle, capturing,
thinking, streaming, error or paused. A screen badge makes capture state visible. A disconnected
monitor's old placement is moved to a visible work area on restart. Exclusive full-screen apps,
protected windows and elevated apps may behave differently; use the tray or normal mode.

## Use the reference clipboard overlay

Choose **More → Floating clipboard viewer**, or the same item in the orb/tray menu. It opens a
480 × 320 translucent topmost panel. Turn **Watch copied text** ON to display newly copied text.
Wheel, arrows, Page Up/Down and Home/End scroll the viewer; Alt+Shift+Up/Down scroll it while you
keep focus in another application. Alt+Shift+N hides it and clears the preview; showing it again
leaves Watch OFF. Close/Escape and Pause also disable watching. It never automatically saves or
sends clipboard text. **Use in chat** puts the reviewed text into Maya's draft; press Send separately.
Recognizable secrets are masked and very large copied text is shortened. The viewer can be moved
and resized with its native frame. Capture exclusion is best effort, as with Maya's other windows.

## Help with your screen

1. Open the Screen drawer, then turn its inner Screen switch ON. This enables capture; it does not continuously record or automatically send images.
2. Choose Current monitor, All monitors, Active window, Select region, or Last capture.
3. Focus your work and use Alt+Shift+S, or click Capture.
4. For region mode, drag on the current monitor. Escape cancels.
5. Review the screenshot. Drag black boxes over private content if needed.
6. Attach screenshot. Enter a question; an empty question with an attached image uses a useful default.
7. Send explicitly transmits the reviewed image and question to your selected provider.

Active window means the last external foreground window's **visible screen rectangle**. Occluded
parts may show the covering application. Move/restore the target first. This version does not read
Excel cells, PDF files or editor buffers directly; it reasons from supplied pixels/text. You can
manually paste selected text for more accurate explanations.

The attached image remains visible for follow-ups until removed. An HTTP request is stateless,
so the latest image must be included again for image-grounded follow-ups; Maya avoids putting
multiple old image copies in history. Screen OFF immediately removes pending/reusable images and
all later requests are text-only. It cannot retract a request already submitted. No screenshot
survives an application restart or history reload.

## Work with responses

Open **More → Review request context** in either chat mode before sending. The local preview shows
the destination/model, current question, history actually included after trimming, approved memories,
system instructions and the already reviewed screenshot. Opening it does not read credentials,
discover models, capture pixels, save a turn or contact a provider. **Keep editing** preserves the draft.

With Gemini routing OFF or a directly selected skill, **Send this context** submits the prepared
request you inspected. With Auto and Gemini routing enabled, the first action is **Route with Gemini
& review**. It may make a separate paid/quota-consuming Gemini call, including discovery when needed.
Its tab shows the bounded excerpt/title and profile descriptions; it excludes answer history, memories,
images and name/language/style settings. After routing, a second review shows the final selected skill
and memories. Only **Send this context** starts the answer. A missing key/service error uses local
fallback and still waits for final approval.

Changing relevant inputs during review/routing invalidates the approval and keeps the draft. Reopen
review to inspect the updated context. Enter while reading cannot send; focus the action button for
keyboard approval. Ordinary Send remains available without this optional review workflow.

When typed-secret redaction is enabled, included history and raw preferences are also sanitized in
the outgoing copy. Saved originals are retained. Review refuses recognizable raw credentials when
redaction is disabled. Screenshot privacy still requires your manual review/redaction; this is not OCR.

Stop keeps partial text. More → Regenerate replaces the last question/answer pair after validating
the next request. Edit last question loads it into the shared draft; replacement happens when you
submit successfully. Continue quotes the previous answer excerpt as context. Copy answer and
**Copy code** menu entries change the clipboard only when clicked. The first 50 code blocks have
individual copy entries; whole-answer Copy retains every block. Maya never auto-pastes into other apps.

Scroll upward to stop following a long response. Jump to latest resumes automatic scrolling.
HTTP(S) links open only when clicked; embedded images and local file links are blocked. Export
chat saves Markdown text and image-presence notes, not screenshot bytes or credentials.

## Personalize locally

Settings → Preferences controls your name, language, style, history and use of approved memory.
Settings → Memory lets you save a fact/preference with a task scope, inspect it, or forget it.
Select an entry to load its text and scope, then press **Update selected** to correct it.
**Save new** adds a separate memory. Duplicate edits are rejected. Memory changes take effect
immediately; Cancel in the settings footer only discards staged preferences/profiles.
The summary shows how many memories are displayed, or explains the empty starting state. Delete
actions stay disabled until a saved entry is available; a loading error is shown as an error.
More → Remember this draft provides a second explicit memory path. Recognizable secrets are
rejected as memories. **Rate → Helpful / Needs work** stores feedback locally; adding a clear preference is
what changes future instructions. Nothing automatically trains a model or records your screen.

Every installation starts with an empty profile and no memories. **Forget all** clears approved
memories after confirmation; it leaves saved chats and provider credentials intact. A request
already sent to a provider cannot be recalled by forgetting a memory.

## Save your own task instructions

Open **Settings → Task profiles**. Choose New, enter a name and reusable instructions, and
press Save profile. Save the settings dialog to apply the collection. The main Save also keeps
a valid profile draft currently in the editor. Select your profile from the chat toolbar or orb
menu. Up to 20 custom profiles can be saved, each with 4,000 characters of instructions.
Shared grounding and safety rules retain priority. Deleted profiles fall back to Auto;
their memories remain inspectable and can be reassigned to an available scope.

## Find saved conversations

Open **More → History** or the navigation drawer. Search titles and message text. Percent and
underscore characters are literal search text. The newest 200 matches are shown; refine the
query to find older chats. Select a result to open, rename, or delete it. Deletion requires a
confirmation. Opened history contains text only; attach a fresh screenshot for visual follow-ups.
Stop generation or finish a capture before switching conversations.
