import sys
import numpy as np
from scipy.io.wavfile import write
import tkinter as tk
from tkinter import ttk, messagebox
import pyaudio
import threading

def generate_fade(duration_ms, sample_rate, fade_in=True):
    fade_length = int(sample_rate * (duration_ms / 1000.0))
    if fade_in:
        return 1 - np.exp(-5 * np.linspace(0, 1, fade_length))  # Fade-in starts slow and gradually increases
    else:
        return 1 - np.exp(-5 * np.linspace(1, 0, fade_length))  # Fade-out starts strong and gradually decreases

def generate_wave(frequency, duration_ms, sample_rate, freq_width=0):
    t = np.linspace(0, duration_ms / 1000.0, int(sample_rate * (duration_ms / 1000.0)), endpoint=False)
    
    if freq_width == 0:
        signal = np.sin(2 * np.pi * frequency * t)
    else:
        # Create white noise and apply a bandpass filter centered around the desired frequency
        noise = np.random.normal(0, 1, len(t))
        freqs = np.fft.fftfreq(len(t), 1 / sample_rate)
        fft_noise = np.fft.fft(noise)
        bandpass_filter = np.exp(-0.5 * ((freqs - frequency) / (freq_width / 2)) ** 2)
        bandpass_filter += np.exp(-0.5 * ((freqs + frequency) / (freq_width / 2)) ** 2)  # Mirror for negative frequencies
        fft_filtered = fft_noise * bandpass_filter
        signal = np.fft.ifft(fft_filtered).real

    # Apply fade-in and fade-out to smooth the beginning and ending
    fade_in = generate_fade(1, sample_rate, fade_in=True)
    fade_out = generate_fade(1, sample_rate, fade_in=False)
    signal[:len(fade_in)] *= fade_in
    signal[-len(fade_out):] *= fade_out

    return normalize_signal(signal)

def normalize_signal(signal):
    max_val = np.max(np.abs(signal))
    if max_val > 0:
        signal /= max_val
    return signal

def play_audio(signal, sample_rate):
    signal = normalize_signal(signal)
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16,
                    channels=1,
                    rate=sample_rate,
                    output=True)
    audio = np.int16(signal * 32767)
    stream.write(audio.tobytes())
    stream.stop_stream()
    stream.close()
    p.terminate()

class TinnitusFrequencyGenerator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tinnitus Frequency Generator")
        self.geometry("700x800")
        
        self.frequency = tk.DoubleVar(value=1000)
        self.sample_rate = 44100
        self.duration_ms = 25
        self.freq_width = tk.DoubleVar(value=0)
        
        self.freqs = []
        self.freq_dom_sliders = []
        self.freq_width_sliders = []
        self.freq_width_entries = []
        self.freq_width_labels = []

        self.freq_width_error_shown = False
        self.play_thread = None
        self.stop_playback = threading.Event()

        self.canvas = tk.Canvas(self)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Add bindings for scroll wheel events
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

        self.create_widgets()

    def _on_mousewheel(self, event):
        if event.num == 5 or event.delta == -120:
            self.canvas.yview_scroll(1, "units")
        if event.num == 4 or event.delta == 120:
            self.canvas.yview_scroll(-1, "units")

    def create_widgets(self):
        frame_freq_test = tk.LabelFrame(self.scrollable_frame, text="Frequency Test", padx=10, pady=10)
        frame_freq_test.pack(padx=10, pady=10, fill="both", expand="yes")

        tk.Label(frame_freq_test, text="Find Your Frequency (Hz)").pack(pady=5)
        self.freq_slider = ttk.Scale(frame_freq_test, from_=100, to=20000, variable=self.frequency, length=600)
        self.freq_slider.pack(pady=5)
        self.freq_slider.bind("<B1-Motion>", self.update_freq_label)
        self.freq_slider.bind("<ButtonRelease-1>", self.update_freq_label)
        
        self.freq_label = tk.Label(frame_freq_test, text="Current Frequency: 1000 Hz")
        self.freq_label.pack(pady=5)

        self.freq_entry_frame = tk.Frame(frame_freq_test)
        self.freq_entry_frame.pack(pady=5)
        
        self.freq_entry = ttk.Entry(self.freq_entry_frame)
        self.freq_entry.pack(side=tk.LEFT)
        self.freq_entry.bind("<Return>", self.set_frequency_from_entry)
        
        tk.Label(self.freq_entry_frame, text="Enter Manually").pack(side=tk.LEFT, padx=5)

        btn_frame = tk.Frame(frame_freq_test)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Increase by 1 Octave", command=self.increase_octave).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Decrease by 1 Octave", command=self.decrease_octave).pack(side=tk.LEFT, padx=5)
        
        tk.Button(frame_freq_test, text="Play Short Sample", command=self.play_current_sample).pack(pady=5)

        tk.Label(frame_freq_test, text="VOLUME WARNING").pack(pady=5)
        self.constant_play_button = tk.Button(frame_freq_test, text="Play Constant Tone", command=lambda: self.toggle_constant_playback(self.frequency, self.freq_width))
        self.constant_play_button.pack(pady=5)

        tk.Label(frame_freq_test, text="Frequency Width").pack(pady=5)
        self.freq_width_slider = ttk.Scale(frame_freq_test, from_=0, to=20000, variable=self.freq_width, length=600)
        self.freq_width_slider.pack(pady=5)
        
        self.freq_width_label = tk.Label(frame_freq_test, text="Current Frequency Width: 0 Hz")
        self.freq_width_label.pack(pady=5)
        
        self.freq_width_entry = ttk.Entry(frame_freq_test)
        self.freq_width_entry.pack(pady=5)
        self.freq_width_entry.bind("<Return>", self.set_freq_width_from_entry)
        
        tk.Label(frame_freq_test, text="INCREASING FREQUENCY WIDTH WILL MAKE THE TONE MORE HISS-LIKE. KEEP IT AT 0 FOR A PURE TONE.")
        self.freq_width_slider.bind("<B1-Motion>", self.update_freq_width_label_refresh)
        self.freq_width_slider.bind("<ButtonRelease-1>", self.update_freq_width_label_refresh)

        frame_freq_gen = tk.LabelFrame(self.scrollable_frame, text="Frequency Generator", padx=10, pady=10)
        frame_freq_gen.pack(padx=10, pady=10, fill="both", expand="yes")

        tk.Label(frame_freq_gen, text="Frequencies (comma separated)").pack(pady=5)
        self.tonal_entry = tk.Entry(frame_freq_gen)
        self.tonal_entry.pack(pady=5)
        
        self.confirm_tones_button = tk.Button(frame_freq_gen, text="Confirm Tones", command=self.confirm_tones)
        self.confirm_tones_button.pack(pady=5)
        
        tk.Button(frame_freq_gen, text="Play Short Sample", command=self.play_sample).pack(pady=5)

        tk.Label(frame_freq_gen, text="VOLUME WARNING").pack(pady=5)
        self.constant_play_button_gen = tk.Button(frame_freq_gen, text="Play Constant Tone", command=self.play_constant_tone_gen)
        self.constant_play_button_gen.pack(pady=5)

        self.frame_tone_dom = tk.LabelFrame(self.scrollable_frame, text="Tone Dominance", padx=10, pady=10)
        self.frame_tone_dom.pack(padx=10, pady=10, fill="both", expand="yes")
        self.frame_tone_dom.pack_forget()

    def toggle_constant_playback(self, frequency, freq_width):
        if self.play_thread is None or not self.play_thread.is_alive():
            self.stop_playback.clear()
            self.constant_play_button.config(text="Stop Constant Tone")
            self.play_thread = threading.Thread(target=self.play_constant_tone, args=(frequency, freq_width))
            self.play_thread.start()
        else:
            self.stop_playback.set()
            self.constant_play_button.config(text="Play Constant Tone")

    def play_constant_tone_gen(self):
        if not self.freqs:
            messagebox.showerror("Error", "No frequencies confirmed. Please confirm tones first.")
            return
        if self.play_thread is None or not self.play_thread.is_alive():
            self.stop_playback.clear()
            self.constant_play_button_gen.config(text="Stop Constant Tone")
            self.play_thread = threading.Thread(target=self.play_constant_mixed_tone)
            self.play_thread.start()
        else:
            self.stop_playback.set()
            self.constant_play_button_gen.config(text="Play Constant Tone")

    def play_constant_mixed_tone(self):
        duration_ms = 60000  # Play for 1 minute
        dominances = [slider.get() for slider in self.freq_dom_sliders]
        widths = [slider.get() for slider in self.freq_width_sliders]
        signal = self.generate_mixed_signal(self.freqs, dominances, widths, duration_ms, self.sample_rate)
        signal = normalize_signal(signal)
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16,
                        channels=1,
                        rate=self.sample_rate,
                        output=True)
        audio = np.int16(signal * 32767)

        chunk_size = 1024
        for i in range(0, len(audio), chunk_size):
            if self.stop_playback.is_set():
                break
            stream.write(audio[i:i+chunk_size].tobytes())

        stream.stop_stream()
        stream.close()
        p.terminate()
        self.constant_play_button_gen.config(text="Play Constant Tone")
        self.play_thread = None

    def play_constant_tone(self, frequency, freq_width):
        if isinstance(frequency, tk.DoubleVar):
            frequency = frequency.get()
        if isinstance(freq_width, tk.DoubleVar):
            freq_width = freq_width.get()
        
        duration_ms = 60000  # Play for 1 minute
        signal = generate_wave(frequency, duration_ms, self.sample_rate, freq_width)
        signal = normalize_signal(signal)
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16,
                        channels=1,
                        rate=self.sample_rate,
                        output=True)
        audio = np.int16(signal * 32767)

        chunk_size = 1024
        for i in range(0, len(audio), chunk_size):
            if self.stop_playback.is_set():
                break
            stream.write(audio[i:i+chunk_size].tobytes())

        stream.stop_stream()
        stream.close()
        p.terminate()
        self.constant_play_button.config(text="Play Constant Tone")
        self.constant_play_button_gen.config(text="Play Constant Tone")
        self.play_thread = None

    def increase_octave(self):
        new_freq = self.frequency.get() * 2
        if new_freq > 20000:
            messagebox.showerror("Error", "Frequency cannot exceed 20000 Hz.")
        else:
            self.frequency.set(new_freq)
            self.update_freq_label(None)
    
    def decrease_octave(self):
        new_freq = self.frequency.get() / 2
        if new_freq < 100:
            messagebox.showerror("Error", "Frequency cannot be lower than 100 Hz.")
        else:
            self.frequency.set(new_freq)
            self.update_freq_label(None)
        
    def update_freq_label(self, event=None):
        self.freq_label.config(text=f"Current Frequency: {int(self.frequency.get())} Hz")
        self.freq_entry.delete(0, tk.END)
        self.freq_entry.insert(0, str(int(self.frequency.get())))
        self.check_frequency_width_range()

    def set_frequency_from_entry(self, event):
        try:
            new_freq = float(self.freq_entry.get())
            if new_freq < 100 or new_freq > 20000:
                messagebox.showerror("Error", "Frequency must be between 100 Hz and 20000 Hz.")
            else:
                self.frequency.set(new_freq)
                self.update_freq_label(None)
                self.check_frequency_width_range()
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid frequency.")
    
    def update_freq_width_label_refresh(self, event=None):
        self.update_freq_width_label()
    
    def update_freq_width_label(self, event=None):
        self.freq_width_label.config(text=f"Current Frequency Width: {int(self.freq_width.get())} Hz")
        self.freq_width_entry.delete(0, tk.END)
        self.freq_width_entry.insert(0, str(int(self.freq_width.get())))
        self.check_frequency_width_range()
    
    def set_freq_width_from_entry(self, event):
        try:
            new_width = float(self.freq_width_entry.get())
            freq = self.frequency.get()
            max_width = min(freq - 100, 20000 - freq)
            if new_width > max_width:
                new_width = max_width
            
            self.freq_width.set(new_width)
            self.freq_width_slider.set(new_width)
            self.freq_width_label.config(text=f"Current Frequency Width: {int(self.freq_width.get())} Hz")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid frequency width.")
    
    def check_frequency_width_range(self):
        freq = self.frequency.get()
        width = self.freq_width.get()
        max_width = min(freq - 100, 20000 - freq)
        if width > max_width:
            self.freq_width.set(max_width)
            self.freq_width_slider.set(max_width)
            self.freq_width_entry.delete(0, tk.END)
            self.freq_width_entry.insert(0, str(int(max_width)))
            self.freq_width_label.config(text=f"Current Frequency Width: {int(max_width)} Hz")
        else:
            self.freq_width_label.config(text=f"Current Frequency Width: {int(width)} Hz")

    def parse_frequencies(self, freq_string):
        freqs = [float(freq.strip()) for freq in freq_string.split(',') if freq.strip()]
        for freq in freqs:
            if freq < 100 or freq > 20000:
                messagebox.showerror("Error", "Frequencies must be between 100 Hz and 20000 Hz.")
                return []
        return freqs

    def generate_mixed_signal(self, freqs, dominances, width, duration_ms, sample_rate):
        total_len = int(sample_rate * (duration_ms / 1000.0))
        mixed_signal = np.zeros(total_len)
        
        signals = []
        for i, freq in enumerate(freqs):
            signal = generate_wave(freq, duration_ms, sample_rate, width[i])
            signal = normalize_signal(signal) * (dominances[i] / 100.0)
            signals.append(signal)
            mixed_signal += signal
        
        mixed_signal = normalize_signal(mixed_signal)
        return mixed_signal
    
    def play_current_sample(self):
        freq = self.frequency.get()
        freq_width = self.freq_width.get()
        
        signal = generate_wave(freq, self.duration_ms, self.sample_rate, freq_width)
        play_audio(signal, self.sample_rate)

    def play_sample(self):
        if not self.freqs:
            messagebox.showerror("Error", "No frequencies confirmed. Please confirm tones first.")
            return
        dominances = [slider.get() for slider in self.freq_dom_sliders]
        widths = [slider.get() for slider in self.freq_width_sliders]
        signal = self.generate_mixed_signal(self.freqs, dominances, widths, self.duration_ms, self.sample_rate)
        play_audio(signal, self.sample_rate)
    
    def confirm_tones(self):
        self.freqs = self.parse_frequencies(self.tonal_entry.get())
        
        if not self.freqs:
            return
        
        self.freq_dom_sliders = []
        self.freq_width_sliders = []
        self.freq_width_entries = []
        self.freq_width_labels = []

        total_sliders = len(self.freqs)
        new_height = 800 + (total_sliders * 100)

        self.geometry(f"850x{new_height}")
        
        for widget in self.frame_tone_dom.winfo_children():
            widget.destroy()

        tk.Label(self.frame_tone_dom, text="Adjust Tone Dominance (Volume) and Width").pack(pady=5)

        for i, freq in enumerate(self.freqs):
            frame = tk.LabelFrame(self.frame_tone_dom, text=f"Frequency {freq} Hz")
            frame.pack(padx=10, pady=5, fill='x')

            tk.Label(frame, text="Dominance:").pack(side=tk.LEFT, padx=5)
            slider = tk.Scale(frame, from_=0, to=100, orient=tk.HORIZONTAL)
            slider.set(100)
            slider.pack(side=tk.LEFT, fill='x', expand=True)
            percentage_label = tk.Label(frame, text="100%")
            percentage_label.pack(side=tk.LEFT, padx=5)
            slider.bind("<Motion>", lambda e, l=percentage_label, s=slider: l.config(text=f"{s.get()}%"))
            self.freq_dom_sliders.append(slider)
            
            width_frame = tk.Frame(frame)
            width_frame.pack(padx=10, pady=5, fill='x')
            tk.Label(width_frame, text=f"Width for {freq} Hz:").pack(side=tk.LEFT, padx=5)
            width_slider = tk.Scale(width_frame, from_=0, to=20000, orient=tk.HORIZONTAL)
            width_slider.set(0)
            width_slider.pack(side=tk.LEFT, fill='x', expand=True)
            width_slider.bind("<B1-Motion>", lambda e, i=i: self.update_freq_width_label_individual(i))
            width_slider.bind("<ButtonRelease-1>", lambda e, i=i: self.update_freq_width_label_individual(i))

            width_percentage_label = tk.Label(width_frame, text="0 Hz")
            width_percentage_label.pack(side=tk.LEFT, padx=5)
            width_slider.bind("<Motion>", lambda e, l=width_percentage_label, s=width_slider: l.config(text=f"{s.get()} Hz"))
            self.freq_width_sliders.append(width_slider)

            width_entry = ttk.Entry(width_frame)
            width_entry.pack(padx=5, pady=5)
            width_entry.bind("<Return>", lambda event, i=i: self.set_freq_width_from_entry_individual(event, i))
            self.freq_width_entries.append(width_entry)
            
            width_label = tk.Label(width_frame, text=f"Current Frequency Width: 0 Hz")
            width_label.pack(pady=5)
            self.freq_width_labels.append(width_label)
        
        self.frame_tone_dom.pack(padx=10, pady=10, fill="both", expand="yes")

    def set_freq_width_from_entry_individual(self, event, index):
        try:
            new_width = float(self.freq_width_entries[index].get())
            freq = self.freqs[index]
            max_width = min(freq - 100, 20000 - freq)
            if new_width > max_width:
                new_width = max_width
            
            self.freq_width_sliders[index].set(new_width)
            self.freq_width_labels[index].config(text=f"Current Frequency Width: {int(new_width)} Hz")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid frequency width.")

    def update_freq_width_label_individual(self, index):
        current_width = int(self.freq_width_sliders[index].get())
        self.freq_width_labels[index].config(text=f"Current Frequency Width: {current_width} Hz")
        self.freq_width_entries[index].delete(0, tk.END)
        self.freq_width_entries[index].insert(0, str(current_width))
        self.check_frequency_width_range_for_individual(index)

    def check_frequency_width_range_for_individual(self, index):
        freq = self.freqs[index]
        width = int(self.freq_width_sliders[index].get())
        max_width = min(freq - 100, 20000 - freq)
        if width > max_width:
            self.freq_width_sliders[index].set(max_width)
            self.freq_width_entries[index].delete(0, tk.END)
            self.freq_width_entries[index].insert(0, str(max_width))
            self.freq_width_labels[index].config(text=f"Current Frequency Width: {int(max_width)} Hz")
        else:
            self.freq_width_labels[index].config(text=f"Current Frequency Width: {int(width)} Hz")

if __name__ == "__main__":
    app = TinnitusFrequencyGenerator()
    app.mainloop()
