# SCROXZ AI

**A multilingual Windows desktop assistant with synchronized speech and an interactive 3D interface.**

SCROXZ combines streaming AI conversations, local microphone transcription, document retrieval, persistent memory, and user-approved desktop actions in a Python application.

## Features

- **Multilingual conversations:** Hindi, Hinglish, English, and automatic language selection.
- **Voice interaction:** local Whisper recognition, online Hindi/English speech, and installed Windows voices. Online speech reveals text using playback word timings.
- **Streaming responses:** compatible cloud APIs and local Ollama, with bounded speech prefetch to reduce pauses between phrases.
- **Web and document context:** optional key-free search snippets with source links, text/PDF retrieval, and saved memories.
- **Controlled automation:** supported application launches, notes, reminders, and browser searches with permission checks.
- **Interactive graphics:** rotating 3D geometry, drag rotation, visual profiles, reduced motion, and a lightweight rendering fallback.
- **Credential storage:** saved Gemini keys encrypted for the current Windows user with DPAPI.

## Technology

| Area | Technology |
| --- | --- |
| Application | Python 3.11, Tkinter |
| AI | Gemini API, compatible chat-completions APIs, Ollama |
| Recognition | faster-whisper, sounddevice |
| Speech | edge-tts, Windows speech synthesis |
| Memory | SQLite |
| Graphics | ModernGL, Pillow, Tkinter Canvas |
| Search and documents | DDGS, pypdf |

## Run on Windows

1. Install **Python 3.11**, including the Python launcher and Tcl/Tk support.
2. Download this repository using **Code → Download ZIP**, then extract it.
3. Double-click **`Setup-Extras.bat`** to create the virtual environment and install dependencies.
4. Double-click **`Start-SCROXZ.bat`**.
5. Open **Workspace → AI connection** to enter your own key, load available models, test a response, and save the connection. Alternatively, configure a local Ollama model in **AI settings**.
6. Select your reply language. Use **Test voice** to check audio and **Mic** or **Start hands-free** when ready.

No API key, personal configuration, conversation database, virtual environment, or downloaded model is included. Microphone models download on first use. Cloud and online speech features require internet access. Provider quotas and charges depend on your own account; free usage is not unlimited or guaranteed.

## Architecture

```text
Typed message / microphone
            |
     Tkinter application
            |
   Permission and intent checks
            |
   +--------+--------------------+
   |                             |
AI conversation             Approved action
   |                             |
Memory / documents / web     Supported tools
   |
Streamed text → phrase buffer → speech worker
                                  |
                        Playback word timings
                                  |
                         Synchronized display
```

| File | Responsibility |
| --- | --- |
| `app.py` | Application lifecycle, conversation, permissions and UI events |
| `core.py` | AI adapters, streaming and local retrieval |
| `assistant.py` | Supported actions, notes and reminders |
| `voice.py`, `audio_gate.py` | Microphone capture and transcription |
| `speech_output.py`, `speech_worker.py` | Speech queue, synthesis, playback and text timing |
| `ui.py`, `theme.py` | Layout, settings, telemetry and assistant state |
| `hologram.py`, `gpu_scene.py`, `smooth_canvas.py` | Interactive visual renderer |
| `credentials.py`, `gemini_setup.py` | Encrypted credentials and connection setup |
| `web_context.py` | Search snippets and source handling |

## Privacy and permissions

- Cloud conversations require consent before sending prompts and relevant context. Online voice has separate consent for spoken reply text.
- Live web sends search queries to public search engines. Turn it off for private or offline questions.
- Microphone recognition runs locally after the model is downloaded. Hands-free capture must be started explicitly.
- Screen capture and sensitive supported actions retain their approval prompts.
- Memory and notes are stored locally in SQLite and are not encrypted. Saved keys use Windows user encryption separately.
- The assistant does not provide arbitrary shell execution from model-generated text.

## Tests

From the repository folder, after setup:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The development version passed **129 automated tests** on Windows. Tests cover streaming, speech ordering and cancellation, language settings, permissions, credential persistence, search handling, and UI state. Real GUI tests require a desktop session.

Files named `tests/check_*.py` are **manual diagnostics**. Depending on the script, they can contact online services, use the locally configured account, download recognition models, play audio, or open test windows. They are separate from the automated suite.

## Performance and limitations

- In individual public-greeting checks, switching the chat model reduced observed first-text latency from **6.8–9.2 seconds to 1.3–2.1 seconds**. These are small-sample observations, not a controlled benchmark or a general latency guarantee.
- An end-to-end greeting test started audio after **6.06 seconds**. Online speech startup remains a significant delay.
- Voice interaction is turn-based, not full-duplex audio conversation. Transcription accuracy varies with language, microphone and background noise.
- Answer quality depends on the configured model. Search snippets can be incomplete, and public endpoints can rate-limit requests.
- GPU rendering depends on driver support. Unsupported initialization falls back to native rendering.

## Project status

A personal desktop-assistant project focused on integrating AI, voice, graphics and controlled automation. This repository contains application code; GitHub Pages does not run the Windows application.

Third-party services and dependencies remain subject to their own terms and licenses.
