"""Isolated online speech synthesis and native Windows MP3 playback.

Parent owns the temporary directory and can terminate this process to cancel both
network synthesis and playback. Never imports Tk or executes supplied text.
"""
import asyncio
import ctypes
import json
import html
from pathlib import Path
import sys
import time

VOICES = {'hi': 'hi-IN-SwaraNeural', 'en': 'en-IN-NeerjaNeural'}


async def synthesize(text, language, rate, output):
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError('Run Setup-Extras.bat to install online Hindi/English voices.') from exc
    voice = VOICES[language]
    boundaries = []
    async def collect():
        cursor = 0
        with open(output, 'wb') as audio:
            async for event in edge_tts.Communicate(text, voice, rate=f'{int(rate):+d}%', boundary='WordBoundary').stream():
                if event['type'] == 'audio':
                    audio.write(event['data'])
                elif event['type'] == 'WordBoundary':
                    word = html.unescape(event['text'])
                    start = text.find(word, cursor)
                    if start >= 0:
                        cursor = start + len(word)
                        boundaries.append((event['offset'] / 10000, cursor))
    await asyncio.wait_for(collect(), timeout=35)
    return boundaries


def play_mp3(path, boundaries=(), progress=None):
    winmm = ctypes.WinDLL('winmm')
    send = winmm.mciSendStringW
    send.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
    send.restype = ctypes.c_uint
    def command(value):
        result = ctypes.create_unicode_buffer(256)
        if send(value, result, len(result), None):
            raise RuntimeError('Windows could not play speech audio. Check your audio output device.')
        return result.value
    command(f'open "{path}" type mpegvideo alias scroxzvoice')
    try:
        command('set scroxzvoice time format milliseconds')
        command('play scroxzvoice')
        if progress:
            progress(0)
        started = time.monotonic()
        index = 0
        while command('status scroxzvoice mode') == 'playing':
            position = int(command('status scroxzvoice position'))
            revealed = None
            while index < len(boundaries) and boundaries[index][0] <= position:
                revealed = boundaries[index][1]
                index += 1
            if revealed is not None and progress:
                progress(revealed)
            if time.monotonic() - started > 150:
                raise RuntimeError('Speech playback timed out.')
            time.sleep(0.05)
    finally:
        command('close scroxzvoice')


def main(request_path):
    request_path = Path(request_path)
    try:
        data = json.loads(request_path.read_text(encoding='utf-8'))
        output = request_path.with_suffix('.mp3')
        boundaries = asyncio.run(synthesize(data['text'], data['language'], data['rate'], output))
        if data.get('deferred'):
            deadline = time.monotonic() + 180
            while not request_path.with_name('play.ready').exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError('Queued speech timed out.')
                time.sleep(0.01)
        def progress(count):
            temporary = request_path.with_name('progress.tmp')
            temporary.write_text(str(count), encoding='ascii')
            temporary.replace(request_path.with_name('progress.txt'))
        play_mp3(output, boundaries, progress)
        progress(len(data['text']))
    except Exception as exc:
        # Do not expose provider payloads or generated text in error reports.
        message = str(exc) if isinstance(exc, RuntimeError) else 'Online speech failed. Check internet access and try again, or choose Windows voice.'
        request_path.with_name('error.txt').write_text(message, encoding='utf-8')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1]))
