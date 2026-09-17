"""Non-blocking, ordered speech playback and incremental sentence buffering."""
from collections import deque
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

from languages import speech_language


class SpeechBuffer:
    """Emit sentences promptly, with bounded phrases for unpunctuated output."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.text = ''
        self.since = clock()
        self.first = True

    def feed(self, text='', final=False):
        if not self.text:
            self.since = self.clock()
        self.text += text
        result = []
        while self.text:
            match = re.search(r'[।!?\n]|\.(?=\s|$)', self.text)
            cut = match.end() if match else 0
            limit = 90 if self.first else 180
            delay = 0.35 if self.first else 1.2
            if (not cut or cut > limit) and (len(self.text) >= limit or self.clock() - self.since >= delay):
                # Keep the incomplete last word until more text arrives.
                if len(self.text) >= 35:
                    boundary = self.text.rfind(' ', 0, limit+1)
                    if boundary > 0:
                        cut = boundary
            if not cut and final:
                cut = len(self.text)
            if cut <= 0:
                break
            part = self.text[:cut].strip()
            self.text = self.text[cut:].lstrip()
            self.since = self.clock()
            if part:
                result.append(part)
                self.first = False
        return result


class Speaker:
    """Call poll from Tk's timer. Child processes do synthesis/playback work."""
    def __init__(self, deferred=False):
        self.process = None
        self.path = None
        self.directory = None
        self.queue = deque()
        self.started = 0
        self.engine = 'windows'
        self.on_progress = None
        self.current_text = ''
        self.reported = 0
        self.deferred = deferred
        self.prefetched = None

    @property
    def busy(self):
        return self.process is not None or bool(self.queue)

    @property
    def playing(self):
        """Playback lifecycle, separate from waiting on network synthesis."""
        if self.process is None or self.process.poll() is not None or not self.directory:
            return False
        name='progress.txt' if self.engine=='edge' else 'playing.txt'
        return Path(self.directory.name,name).exists()

    def _cleanup(self):
        if self.directory:
            self.directory.cleanup()
            self.directory = None
        self.path = None

    def stop(self):
        self.queue.clear()
        if self.prefetched:
            self.prefetched.stop()
            self.prefetched = None
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            self.process = None
        self._cleanup()

    def speak(self, text, language='auto', engine='windows', rate='0'):
        self.stop()
        self.enqueue(text, language, engine, rate)

    def enqueue(self, text, language='auto', engine='windows', rate='0'):
        text = text.strip()
        if not text:
            return
        if os.name != 'nt':
            raise RuntimeError('Speech playback requires Windows.')
        if engine not in ('edge', 'windows') or rate not in ('-20','-10','0','10','20'):
            raise ValueError('Invalid speech settings.')
        if len(self.queue) >= 100:
            raise RuntimeError('Speech queue is full. Press Stop voice to clear it.')
        self.queue.append((text, speech_language(language, text), engine, rate))
        if self.process is None:
            self._start_next()
        self._prefetch()

    def _prefetch(self):
        # One bounded lookahead: synthesize concurrently, but never play ahead.
        if (not self.deferred and self.engine == 'edge' and self.process
                and not self.prefetched and self.queue and self.queue[0][2] == 'edge'):
            upcoming = Speaker(deferred=True)
            try:
                upcoming.enqueue(*self.queue.popleft())
            except Exception:
                upcoming.stop()
                self.stop()
                raise
            self.prefetched = upcoming

    def _start_next(self):
        if self.prefetched:
            upcoming = self.prefetched
            self.prefetched = None
            for name in ('process', 'path', 'directory', 'engine', 'current_text', 'reported'):
                setattr(self, name, getattr(upcoming, name))
            upcoming.process = upcoming.directory = upcoming.path = None
            self.started = time.monotonic()
            try:
                Path(self.directory.name, 'play.ready').touch()
                self._prefetch()
            except Exception:
                self.stop()
                raise
            return
        if not self.queue:
            return
        text, language, self.engine, rate = self.queue.popleft()
        self.current_text = text
        self.reported = 0
        self.directory = tempfile.TemporaryDirectory(prefix='scroxz-speech-')
        folder = Path(self.directory.name)
        self.path = str(folder / 'request.json')
        Path(self.path).write_text(json.dumps({'text':text, 'language':language, 'rate':rate,
                                             'deferred':self.deferred}), encoding='utf-8')
        env = dict(os.environ, SCROXZ_SPEECH_FILE=self.path)
        try:
            if self.engine == 'edge':
                command = [sys.executable, str(Path(__file__).with_name('speech_worker.py')), self.path]
            else:
                # No user text is embedded into executable PowerShell input.
                script = "$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; try {$d=Get-Content -LiteralPath $env:SCROXZ_SPEECH_FILE -Raw -Encoding UTF8 | ConvertFrom-Json; $v=$s.GetInstalledVoices() | Where-Object {$_.Enabled -and $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq $d.language} | Select-Object -First 1; if (!$v) {exit 3}; $s.SelectVoice($v.VoiceInfo.Name); $s.Rate=[int]$d.rate / 10; [IO.File]::WriteAllText([IO.Path]::Combine([IO.Path]::GetDirectoryName($env:SCROXZ_SPEECH_FILE),'playing.txt'),'1'); $s.Speak($d.text)} finally {$s.Dispose()}"
                exe = Path(os.environ.get('SystemRoot', 'C:\\Windows'))/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
                command = [str(exe), '-NoProfile', '-NonInteractive', '-Command', script]
            self.process = subprocess.Popen(command, env=env, shell=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            self.started = time.monotonic()
        except Exception:
            self.stop()
            raise

    def poll(self):
        if self.process is None:
            return
        code = self.process.poll()
        if self.engine == 'edge' and self.on_progress:
            try:
                count = int(Path(self.directory.name, 'progress.txt').read_text(encoding='ascii'))
            except (OSError, ValueError):
                count = 0
            if code == 0:
                count = len(self.current_text)
            count = min(len(self.current_text), max(0, count))
            if count > self.reported:
                self.reported = count
                self.on_progress(self.current_text, count)
        if code is None:
            if time.monotonic() - self.started > 180:
                self.stop()
                raise RuntimeError('Speech timed out. Check your connection or voice settings.')
            return
        self.process = None
        engine = self.engine
        error = None
        if code:
            error_file = Path(self.directory.name) / 'error.txt'
            if error_file.exists():
                error = error_file.read_text(encoding='utf-8')[:500]
            elif engine == 'windows' and code == 3:
                error = 'No Windows voice for this language. Choose Online voice in AI settings, or install a Hindi Windows speech voice.'
            else:
                error = 'Speech playback failed. Check voice settings and audio output.'
        self._cleanup()
        if error:
            self.stop()
            raise RuntimeError(error)
        self._start_next()
        self._prefetch()
