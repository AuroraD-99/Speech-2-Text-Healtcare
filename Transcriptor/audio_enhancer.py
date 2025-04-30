import numpy as np
import librosa
import soundfile as sf
import os

class AudioEnhancer:
    def __init__(self, noise_reduction_level=0.01, volume_boost=1.0):
        self.noise_reduction_level = noise_reduction_level
        self.volume_boost = volume_boost

    def load_audio(self, audio_path):
        """ Load an audio file and return the audio data and sample rate. """
        audio_data, sample_rate = librosa.load(audio_path, sr=None)
        return audio_data, sample_rate
    
    def reduce_noise(self, audio_data):
        """ Apply noise reduction to the audio data. """
        return np.clip(audio_data * (1 - self.noise_reduction_level), -1.0, 1.0)
    
    def normalize_volume(self, audio_data, target_dBFS=-20.0):
        """ Normalize the volume of the audio data. """
        rms = np.sqrt(np.mean(audio_data**2))
        current_dBFS = 20 * np.log10(rms) if rms > 0 else 0
        gain = target_dBFS - current_dBFS
        return np.clip(audio_data * (10 ** (gain / 20)), -1.0, 1.0)
    
    def bandpass_filter(self, audio, sample_rate, lowcut=300.0, highcut=3400.0):
        """ Apply a bandpass filter to the audio data. """
        # Apply a butterworth filter
        from scipy.signal import butter, lfilter
        nyquist = 0.5 * sample_rate
        low = lowcut / nyquist
        high = highcut / nyquist
        b, a = butter(1, [low, high], btype='band')
        return lfilter(b, a, audio)
    
    def run(self, audio_path):
        """ Process the audio file and replace the original file with the enhanced version. """
        audio_data, sample_rate = self.load_audio(audio_path)
        audio_data = self.reduce_noise(audio_data)
        audio_data = self.normalize_volume(audio_data)
        audio_data = self.bandpass_filter(audio_data, sample_rate=sample_rate)
        enhanced_audio_path = audio_path.replace('.wav', '_enhanced.wav')
        # Delete the original file if _enhanced.wav already exists
        if os.path.exists(enhanced_audio_path):
            os.remove(audio_path)
        sf.write(enhanced_audio_path, audio_data, sample_rate)
        return enhanced_audio_path
    
    
# Example usage
if __name__ == "__main__":
    enhancer = AudioEnhancer()
    enhanced_audio_path = enhancer.run("./example.wav")
    print(f"Enhanced audio saved to: {enhanced_audio_path}")