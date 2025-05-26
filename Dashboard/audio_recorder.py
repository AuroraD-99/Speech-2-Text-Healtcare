import pyaudio
import wave
import threading
import os 
import sys
import dotenv
from datetime import datetime
from log import Logger

dotenv.load_dotenv("key.env")


class AudioRecorder:
    def __init__(self, sample_rate=16000, channels=1, chunk_size=1024, logger=None):
        self.logger = Logger(self.__class__.__name__).get_logger() if logger is None else logger
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.format = pyaudio.paInt16

        self.p = pyaudio.PyAudio()
        self.stream = None

        self.frames = []
        self.is_recording = False
        self.thread = None
        self.logger = logger
        self.audio_path = os.getenv("AUDIO_PATH", "assets/audios")

    def _record(self):
        if self.logger:
            self.logger.info("Registrazione avviata.")
        while self.is_recording:
            try:
                data = self.stream.read(self.chunk_size)
                self.frames.append(data)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"Errore durante la registrazione: {e}")
                break

    def start_recording(self):
        if self.is_recording:
            if self.logger:
                self.logger.warning("La registrazione è già in corso.")
            return

        self.frames = []
        self.stream = self.p.open(format=self.format,
                                  channels=self.channels,
                                  rate=self.sample_rate,
                                  input=True,
                                  frames_per_buffer=self.chunk_size)

        self.is_recording = True
        self.thread = threading.Thread(target=self._record)
        self.thread.start()

        if self.logger:
            self.logger.info("Inizio registrazione...")

    def stop_recording(self):
        if not self.is_recording:
            if self.logger:
                self.logger.warning("La registrazione non è stata avviata.")
            return None

        self.is_recording = False
        self.thread.join()
        self.stream.stop_stream()
        self.stream.close()

        output_filename = os.path.join(self.audio_path, f"referto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav")
        # salva file
        with wave.open(output_filename, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.p.get_sample_size(self.format))
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(self.frames))

        if self.logger:
            self.logger.info(f"Registrazione salvata in: {output_filename}")

        return output_filename
    
    
    
if __name__ == "__main__":
    recorder = AudioRecorder()
    try:
        recorder.start_recording()
        input("Premi Invio per fermare la registrazione...")
    finally:
        filename = recorder.stop_recording()
        if filename:
            print(f"Registrazione salvata in: {filename}")
        else:
            print("Registrazione non salvata.")