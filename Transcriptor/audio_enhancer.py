import numpy as np
import soundfile as sf
import noisereduce as nr
import os

import numpy as np
import soundfile as sf
import noisereduce as nr
from scipy.signal import butter, lfilter
import os

class AudioEnhancer:
    def __init__(self, noise_reduction_level=0.8, target_dBFS=-20.0):
        """
        Inizializza l'enhancer con livelli predefiniti.
        noise_reduction_level: tra 0 e 1. 0.8 = rimozione aggressiva del rumore.
        target_dBFS: livello di volume di destinazione.
        """
        self.noise_reduction_level = noise_reduction_level
        self.target_dBFS = target_dBFS

    def load_audio(self, audio_path):
        """ Carica l'audio in float32. """
        audio_data, sample_rate = sf.read(audio_path)
        return audio_data.astype(np.float32), sample_rate

    def bandpass_filter(self, audio, sample_rate, lowcut=300.0, highcut=3400.0, order=4):
        """ Applica un filtro passa-banda tipico per voce umana. """
        nyquist = 0.5 * sample_rate
        low = lowcut / nyquist
        high = highcut / nyquist
        b, a = butter(order, [low, high], btype='band')
        return lfilter(b, a, audio)

    def reduce_noise(self, audio_data, sample_rate):
        """ Applica una riduzione del rumore basata su un profilo dai primi 0.5s. """
        noise_clip = audio_data[:int(0.5 * sample_rate)]  # 0.5 secondi iniziali
        return nr.reduce_noise(
            y=audio_data,
            sr=sample_rate,
            y_noise=noise_clip,
            prop_decrease=self.noise_reduction_level,
            stationary=False
        )

    def normalize_volume(self, audio_data):
        """ Normalizza il volume se il segnale è sufficientemente forte. """
        rms = np.sqrt(np.mean(audio_data ** 2))
        if rms < 0.001:
            print("⚠️  RMS troppo basso, normalizzazione saltata.")
            return audio_data
        current_dBFS = 20 * np.log10(rms)
        gain = self.target_dBFS - current_dBFS
        audio_normalized = audio_data * (10 ** (gain / 20))
        return np.clip(audio_normalized, -1.0, 1.0)

    def run(self, audio_path):
        """ Esegue tutto il processo e sovrascrive il file. """
        audio_data, sample_rate = self.load_audio(audio_path)
        audio_data = self.bandpass_filter(audio_data, sample_rate)
        audio_data = self.reduce_noise(audio_data, sample_rate)
        audio_data = self.normalize_volume(audio_data)
        os.remove(audio_path)
        sf.write(audio_path, audio_data, sample_rate)
        return audio_path

    
    
# Example usage
if __name__ == "__main__":
    enhancer = AudioEnhancer()
    enhanced_audio_path = enhancer.run("./registrazione.wav")
    print(f"Enhanced audio saved to: {enhanced_audio_path}")