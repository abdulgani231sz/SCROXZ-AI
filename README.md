<div align="center">

# SCROXZ AI

### A multilingual Windows voice assistant with streaming AI, local speech recognition and an interactive 3D interface

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows&logoColor=white)
![Tests](https://img.shields.io/badge/Automated%20tests-129%20passing-brightgreen)
![License](https://img.shields.io/badge/License-MIT-yellow)

[**Watch the demo**](https://github.com/user-attachments/assets/760b43bb-3d33-4711-8185-5fabdde666ef) · [**Quick start**](#quick-start) · [**Architecture**](#architecture) · [**Engineering decisions**](#engineering-decisions)

</div>

https://github.com/user-attachments/assets/760b43bb-3d33-4711-8185-5fabdde666ef

<!-- TODO: Add 2-3 screenshots here (main window, AI connection settings, 3D interface).
<p align="center">
  <img src="docs/main.png" width="32%" />
  <img src="docs/settings.png" width="32%" />
  <img src="docs/3d.png" width="32%" />
</p>
-->

---

## Overview

SCROXZ is a desktop assistant I built to explore how **AI, real-time voice, graphics and safe automation** fit together in one application. You can talk to it in **Hindi, Hinglish or English**, and it answers with streamed text and synchronized speech, while using your documents, saved memories and optional web search as context.

The focus of the project is not only "call an LLM", but the engineering around it: streaming pipelines, audio ordering and cancellation, permission-gated actions, encrypted credentials, graceful fallbacks and a real automated test suite.

## Highlights

| | |
| --- | --- |
| **Multilingual chat** | Hindi, Hinglish, English, or automatic language selection |
| **Voice in** | Local speech recognition with Whisper; hands-free mode is started explicitly |
| **Voice out** | Online Hindi/English voices or installed Windows voices; text is revealed using playback word timings |
| **Streaming AI** | Gemini, OpenAI-compatible chat APIs, or fully local models through Ollama |
| **Context** | Optional web search snippets with source links, text/PDF retrieval, saved memories |
| **Safe automation** | Application launches, notes, reminders and browser searches, all behind permission checks |
| **3D interface** | Rotating geometry, drag rotation, visual profiles, reduced-motion option and a lightweight fallback renderer |
| **Secure keys** | Saved Gemini keys are encrypted per Windows user with DPAPI |

## What this project demonstrates

- **Real-time systems:** streamed tokens → phrase buffer → speech worker, with bounded prefetch to reduce pauses between phrases.
- **Concurrency and state management:** speech queue ordering, cancellation and synchronized text display.
- **Security-minded design:** explicit consent for cloud calls, permission prompts for sensitive actions, no arbitrary shell execution from model output, OS-level credential encryption.
- **Provider-agnostic AI layer:** one interface over a cloud API, compatible endpoints and local Ollama.
- **Graceful degradation:** GPU renderer falls back to native canvas rendering when drivers are unsupported.
- **Testing discipline:** 129 automated tests, with manual diagnostics kept separate from the suite.
- **Honest documentation:** measurements and limitations are stated as they are, without inflated claims.

## Tech stack

| Area | Technology |
| --- | --- |
| Application | Python 3.11, Tkinter |
| AI | Gemini API, compatible chat-completions APIs, Ollama |
| Recognition | faster-whisper, sounddevice |
| Speech | edge-tts, Windows speech synthesis |
| Memory | SQLite |
| Graphics | ModernGL, Pillow, Tkinter Canvas |
| Search and documents | DDGS, pypdf |

## Quick start

**Requirements:** Windows, Python 3.11 (with the Python launcher and Tcl/Tk support).

1. Download the repository via **Code → Download ZIP** and extract it.
2. Double-click **`Setup-Extras.bat`** to create the virtual environment and install dependencies.
3. Double-click **`Start-SCROXZ.bat`**.
4. Open **Workspace → AI connection**, enter your own API key, load models, test a response and save. Or configure a local Ollama model in **AI settings**.
5. Choose a reply language, press **Test voice**, then use **Mic** or **Start hands-free**.

> No API key, personal configuration, conversation database, virtual environment or downloaded model is included. Whisper models download on first use. Cloud and online speech need internet access, and provider quotas and charges depend on your own account.

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

## Engineering decisions

- **Streaming first.** Responses are streamed and spoken phrase by phrase, so the user hears the answer while it is still being generated.
- **Bounded prefetch.** Speech for upcoming phrases is synthesized ahead of time, but only within a limit, to reduce gaps without wasting resources.
- **Text follows audio.** For online voices, words appear according to real playback timings instead of a fixed typing speed.
- **Permission-gated actions.** Every supported action goes through intent and permission checks; the model cannot run arbitrary commands.
- **Local by default where possible.** Speech recognition runs on-device; memory and notes stay in a local SQLite database.

## Privacy and permissions

- Cloud conversations need consent before prompts and relevant context are sent. Online voice has its own consent for spoken reply text.
- Live web search sends queries to public search engines. Turn it off for private or offline questions.
- Hands-free capture must be started explicitly.
- Screen capture and sensitive actions keep their approval prompts.
- Memory and notes are stored locally in SQLite and are **not encrypted**. Saved keys use Windows user encryption separately.

## Testing

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

The development version passed **129 automated tests** on Windows, covering streaming, speech ordering and cancellation, language settings, permissions, credential persistence, search handling and UI state. GUI tests need a desktop session.

`tests/check_*.py` are **manual diagnostics**. They may contact online services, use your configured account, download models, play audio or open windows, so they are kept apart from the automated suite.

## Performance and limitations

- In individual public-greeting checks, switching the chat model cut first-text latency from **6.8–9.2 s to 1.3–2.1 s**. These are small-sample observations, not a controlled benchmark.
- An end-to-end greeting test started audio after **6.06 s**; online speech startup is still a noticeable delay.
- Voice interaction is turn-based, not full-duplex. Transcription accuracy depends on language, microphone and background noise.
- Answer quality depends on the configured model. Search snippets can be incomplete and public endpoints can rate-limit.
- GPU rendering depends on driver support; unsupported setups fall back to native rendering.
- Windows only. Linux and macOS are not supported.

## Roadmap

- [ ] Add screenshots and a short architecture walkthrough
- [ ] Reduce online speech startup latency
- [ ] Add a troubleshooting guide (microphone, Tcl/Tk, GPU fallback)
- [ ] Publish minimum system requirements (RAM, model download sizes)
- [ ] Explore cross-platform support

## About the author

Built by **[YOUR NAME]**, [one line about you, e.g. "a computer science student interested in AI applications and real-time systems"].

- LinkedIn:(https://www.linkedin.com/in/abdul-gani-08sz/)
- Email:abdulgani231sz@gmail.com
- Portfolio: [your-link]

## License

Released under the [MIT License](LICENSE). Third-party services and dependencies remain subject to their own terms and licenses.

> This is a personal project focused on integrating AI, voice, graphics and controlled automation. GitHub Pages does not run the Windows application.
