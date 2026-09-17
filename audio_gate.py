"""Small energy gate for 100 ms audio frames. This detects energy, not words."""
class SpeechGate:
    def __init__(self, calibration=3, wait_frames=70, silence_frames=8, max_frames=200, floor=.008, ceiling=.04):
        self.calibration=calibration
        self.wait_frames=wait_frames
        self.silence_frames=silence_frames
        self.max_frames=max_frames
        self.frames=0
        self.floor=floor
        self.ceiling=ceiling
        self.noise=[]
        self.threshold=.008
        self.speech_frames=0
        self.quiet=0
        self.started=False
    def feed(self,rms):
        self.frames+=1
        if self.frames<=self.calibration:
            self.noise.append(max(0,float(rms)))
            # Lower quartile resists a click or speech during initial calibration.
            noise=sorted(self.noise)[(len(self.noise)-1)//4]
            self.threshold=max(self.floor,min(self.ceiling,noise*2.5))
            return False
        if rms>=self.threshold:
            self.speech_frames+=1
            self.quiet=0
            if self.speech_frames>=3: self.started=True
        else:
            self.quiet+=1
            if not self.started: self.speech_frames=0
        return (self.frames>=self.max_frames or
                (self.started and self.quiet>=self.silence_frames) or
                (not self.started and self.frames>=self.wait_frames))
