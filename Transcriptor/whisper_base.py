from faster_whisper import WhisperModel
from log import Logger
import torch
import pyaudio
import wave


class voice_to_text:
    def __init__(self, model_size: str = "medium", device: str = "cuda" if torch.cuda.is_available() else "cpu"):
        """Initialize the voice_to_text class with the specified model size and device. """
        self.model = WhisperModel(model_size, device=device, compute_type="int8")
        self.device = device
        self.logger = Logger("Voice_to_text").get_logger()
        self.logger.info(f"Model loaded on {self.device} with size {model_size}.")

    def transcribe(self, audio_path: str) -> str:
        segments, info = self.model.transcribe(audio_path, beam_size=5)
        self.logger.info(f"Transcribing {audio_path}...")
        self.logger.debug(f"Languange info: {info.language}")
        text = ""
        for segment in segments:
            text += segment.text + " "
        self.logger.info(f"Transcription completed for {audio_path}.")
        self.logger.debug(f"Transcription: {text}")
        
        return text.strip()
    
    def record_audio(self, output_filename="registrazione.wav", record_seconds=5, sample_rate=16000, channels=1):
        """
        Registra un audio dal microfono e lo salva come file WAV.

        Args:
            output_filename (str): Nome del file di output.
            record_seconds (int): Durata della registrazione in secondi.
            sample_rate (int): Frequenza di campionamento (16kHz consigliato per ASR).
            channels (int): Numero di canali (1 = mono).
        """

        chunk_size = 1024  # dimensione buffer
        format = pyaudio.paInt16  # formato audio PCM 16-bit

        p = pyaudio.PyAudio()

        self.logger.info(f"🎤 Registrazione in corso...")

        stream = p.open(format=format,
                        channels=channels,
                        rate=sample_rate,
                        input=True,
                        frames_per_buffer=chunk_size)

        frames = []

        for _ in range(0, int(sample_rate / chunk_size * record_seconds)):
            data = stream.read(chunk_size)
            frames.append(data)

        self.logger.info("✅ Registrazione terminata. Salvataggio...")

        stream.stop_stream()
        stream.close()
        p.terminate()

        with wave.open(output_filename, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(p.get_sample_size(format))
            wf.setframerate(sample_rate)
            wf.writeframes(b''.join(frames))

        self.logger.info(f"📁 Audio salvato in: {output_filename}")
        return output_filename
    
    
    
    
# Example usage
if __name__ == "__main__":
    v2t = voice_to_text()
    transcription = v2t.transcribe("registrazione.wav")