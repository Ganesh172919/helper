# Troubleshooting

| Symptom | Practical fix |
| --- | --- |
| No module named maya / PyQt5 | Use `.venv\Scripts\python.exe`; run `pip install -e ".[dev]"` in this folder. |
| Dependency download times out | Retry installation with a larger installer timeout; for uv set `UV_HTTP_TIMEOUT=180`. |
| No module named pip | Run `.venv\Scripts\python.exe -m ensurepip --upgrade`; unseeded uv environments may omit pip. |
| No models / missing key | Add the provider's own key in Settings, Save & refresh; a ChatGPT/Gemini consumer subscription is not an API key. |
| Invalid key / access denied | Check provider API access, key restrictions, permissions and endpoint. Native keys are not interchangeable. |
| Compatible environment key disappeared after changing URL | Set `MAYA_COMPATIBLE_BASE_URL` to the selected API base URL, or save an endpoint-specific OS key. The default environment binding is the OpenAI endpoint. |
| Corporate proxy/private-CA connection fails | Provider clients ignore shell proxy/CA overrides. Explicit proxy/custom-CA configuration is unsupported; ask your network administrator for an approved setup. |
| Send is disabled | Select a model and type a question or attach a reviewed image with Screen ON. Stop an active operation or resume a paused app first. |
| Quota, credits or 429 | Check provider account/quota, wait or pick another accessible model. Free price does not mean unlimited calls. |
| Model disappeared | Refresh the catalog. Choose a current model; stale IDs are not guaranteed. |
| Vision unknown / rejected | Choose a discovered vision model, remove the image, or verify the compatible model's image capability before overriding. |
| Empty response | Try another model, raise output limit for thinking models, or simplify the question. Safety blocks are shown separately. |
| Stream cut off | Read kept partial text; More → Regenerate/Continue. Check network and model/server health. |
| Screenshot blank | Protected/locked/uniform content may be unavailable. Try another scope or paste text; access restrictions are not bypassed. |
| Active window captures another app | Restore/focus the target, remove covering windows, then use capture shortcut. Capture is the visible rectangle. |
| Region uses the wrong monitor | Move cursor onto the desired monitor before Capture. Region selection occurs on one current display. |
| Shortcut unavailable | Choose different Alt/Ctrl/Shift shortcuts in Preferences; another app may own them. |
| Main window disappears | Closing minimizes to tray. Alt+Shift+N or the tray reopens it. Quit exits. |
| Window is too large after restoring old preferences | More → Use compact window size. This saves the smaller placement. |
| Local Ollama unavailable | Start your own Ollama server and install a model yourself; Maya does not start/pull it. Check localhost URL. |
| Local model slow to answer | Cold loads can exceed read/overall timeouts; increase timeout or pre-load/use a smaller model. |
| Settings cannot be read | Quit Maya, back up and rename `%LOCALAPPDATA%\MayaHelper\settings.json`, restart with defaults. Keys remain OS-backed. |
| Database unavailable | Quit; back up the entire data folder before troubleshooting. Check permissions/disk space; choose another `MAYA_DATA_DIR` for a clean test. |
| Another instance starting/shutting down | Wait briefly and retry. Do not delete an active instance lock. Restart only after the prior process exits. |
| Unexpected operation failure | Check `diagnostics.log` for exception type and source location. It excludes prompt/key values. |

For a clean isolated startup check use `python -m maya --smoke-test`. For a persistent separate
test profile set `MAYA_DATA_DIR` to a new writable folder before launch. This does not erase your
normal history or credentials. Report reproduction steps, selected provider/model, Windows/Python
versions and safe code-location diagnostics; remove keys and private context from any shared report.
Use `--no-credentials` with a separate test profile to disable OS/environment credential reads.
