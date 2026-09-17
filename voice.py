"""Optional local microphone transcription, Windows installed voices."""
import threading
import os
import re
from audio_gate import SpeechGate
from speech_output import Speaker
from languages import microphone_language

_model = None
_model_name = None
_lock = threading.Lock()

def input_devices():
    import sounddevice as sd
    return [(str(i),item['name']) for i,item in enumerate(sd.query_devices()) if item['max_input_channels']>0]


def prepare_audio(recording,sample_rate):
    import numpy as np
    audio=np.asarray(recording,dtype=np.float32).reshape(-1)
    if sample_rate!=16000:
        import av
        frame=av.AudioFrame.from_ndarray(audio.reshape(1,-1),format='flt',layout='mono')
        frame.sample_rate=sample_rate
        resampler=av.AudioResampler(format='fltp',layout='mono',rate=16000)
        frames=resampler.resample(frame)+resampler.resample(None)
        audio=np.concatenate([f.to_ndarray().reshape(-1) for f in frames]).astype(np.float32)
    audio=audio-audio.mean()
    peak=float(np.max(np.abs(audio)))
    if peak>.0005:
        audio*=min(6.,.85/peak)
    return np.clip(audio,-1,1)


def transcription_options(language='auto',fast=True):
    return dict(language=None if language=='auto' else language,
                vad_filter=True,vad_parameters={'min_silence_duration_ms':500,'speech_pad_ms':250},
                beam_size=3 if fast else 5,condition_on_previous_text=False,
                temperature=(0.0,0.2,0.4),compression_ratio_threshold=2.4,
                repetition_penalty=1.12,no_repeat_ngram_size=3,max_new_tokens=192)


def validate_transcript(text):
    if not text:
        raise RuntimeError('No speech detected. Check microphone access and try again.')
    if re.search(r'(\S)\1{5,}',text):
        raise RuntimeError('Recognition produced an unreliable repeated sound. Please repeat clearly or choose your microphone/language in AI settings.')
    return text


def listen(language='auto', progress=lambda text: None, cancel=None, fast=True,model_name='small',device='default'):
    global _model,_model_name
    language = microphone_language(language)
    try:
        import sounddevice as sd
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError('Run Setup-Extras.bat for microphone support. You can also use Windows Win+H in the input box.') from exc
    with _lock:
        if cancel is not None and cancel.is_set():
            return ''
        # Keep recognition on CPU so chat can use the GPU.
        if model_name not in ('base','small'):
            raise ValueError('Choose the base or small recognition model.')
        if _model is None or _model_name!=model_name:
            progress(f'Loading Whisper {model_name} • first use may download the model')
            _model=None
            _model = WhisperModel(model_name, device='cpu', compute_type='int8',cpu_threads=min(4,os.cpu_count() or 2))
            _model_name=model_name
        import numpy as np
        if cancel is not None and cancel.is_set():
            return ''
        selected=None if device=='default' else int(device)
        sample_rate=16000
        try:
            sd.check_input_settings(device=selected,channels=1,dtype='float32',samplerate=sample_rate)
        except sd.PortAudioError:
            sample_rate=int(sd.query_devices(selected,'input')['default_samplerate'])
        frame_size=sample_rate//10
        gate=SpeechGate(silence_frames=10 if fast else 14,wait_frames=120,max_frames=400,floor=.0025,ceiling=.012)
        blocks=[]
        with sd.InputStream(device=selected,samplerate=sample_rate, channels=1, dtype='float32', blocksize=frame_size) as stream:
            progress('Listening now • speak after a brief moment')
            while True:
                if cancel is not None and cancel.is_set():
                    return ''
                block,overflow=stream.read(frame_size)
                if overflow:
                    raise RuntimeError('Microphone audio overflow. Close heavy apps and try again.')
                blocks.append(block.copy())
                rms=float(np.sqrt(np.mean(block**2)))
                progress(('level',rms))
                if gate.feed(rms):
                    break
        if not gate.started:
            return ''
        recording=prepare_audio(np.concatenate(blocks,axis=0),sample_rate)
        progress('Transcribing your recording…')
        segments, _ = _model.transcribe(recording,**transcription_options(language,fast))
        pieces=[]
        for segment in segments:
            if cancel is not None and cancel.is_set():
                return ''
            pieces.append(segment.text.strip())
        text=' '.join(pieces).strip()
        if cancel is not None and cancel.is_set():
            return ''
        return validate_transcript(text)
