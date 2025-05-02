from faster_whisper import WhisperModel
from log import Logger
import torch
import pyaudio
import wave
import platform
import os

class voice_to_text:
    def __init__(self, model_size: str = "medium", device: str = "cuda" if torch.cuda.is_available() else "cpu"):
        """Initialize the voice_to_text class with the specified model size and device."""
        self.model = WhisperModel(model_size, device=device, compute_type="int8")
        self.device = device
        self.logger = Logger("Voice_to_text").get_logger()
        self.logger.info(f"Model loaded on {self.device} with size {model_size}.")

    def transcribe(self, audio_path: str) -> str:
        segments, info = self.model.transcribe(audio_path, beam_size=5)
        self.logger.info(f"Transcribing {audio_path}...")
        self.logger.debug(f"Language info: {info.language}")
        text = ""
        for segment in segments:
            text += segment.text + " "
        self.logger.info(f"Transcription completed for {audio_path}.")
        self.logger.debug(f"Transcription: {text}")
        return text.strip()

    def play_beep(self):
        """Riproduce un beep cross-platform."""
        system = platform.system()
        if system == "Windows":
            import winsound
            winsound.Beep(1000, 500)
        elif system == "Darwin":
            os.system('say "beep"')
        else:
            os.system('beep -f 1000 -l 500')

    def record_audio(self, output_filename="registrazione.wav", sample_rate=16000, channels=1):
        """
        Registra un audio dal microfono e lo salva come file WAV, terminando alla pressione di Invio.
        """

        chunk_size = 1024
        format = pyaudio.paInt16
        p = pyaudio.PyAudio()

        self.logger.info("Preparazione della registrazione...")
        self.play_beep()
        self.logger.info("Inizia a parlare ora (premi Invio per terminare)...")

        stream = p.open(format=format,
                        channels=channels,
                        rate=sample_rate,
                        input=True,
                        frames_per_buffer=chunk_size)

        frames = []

        try:
            while True:
                data = stream.read(chunk_size)
                frames.append(data)
                if os.name == 'nt':
                    import msvcrt
                    if msvcrt.kbhit() and msvcrt.getch() == b'\r':
                        break
                else:
                    import sys
                    import select
                    if select.select([sys.stdin], [], [], 0.01)[0]:
                        break
        except KeyboardInterrupt:
            self.logger.info("Interruzione manuale della registrazione.")

        stream.stop_stream()
        stream.close()
        p.terminate()

        with wave.open(output_filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(p.get_sample_size(format))
            wf.setframerate(sample_rate)
            wf.writeframes(b''.join(frames))

        self.logger.info(f"Registrazione completata e salvata in: {output_filename}")
        return output_filename


if __name__ == "__main__":
    transcriptor = voice_to_text()
    audio_filename = transcriptor.record_audio()
    transcription = transcriptor.transcribe(audio_filename)
    print(f"Transcription: {transcription}")
