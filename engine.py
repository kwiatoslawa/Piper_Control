import subprocess
import threading
from pathlib import Path


class PiperEngine:
    def __init__(self):
        self.voice_dir = Path(__file__).parent / "voices"
        self.current_process = None
        self.play_process = None
        self.mute = False
        self.lock = threading.Lock()
        self.pipewire = self._is_pipewire()

    def _is_pipewire(self) -> bool:
        try:
            subprocess.check_output(["pw-cli", "info"], stderr=subprocess.DEVNULL, timeout=2)
            return True
        except Exception:
            return False

    def stop(self):
        with self.lock:
            if self.current_process and self.current_process.poll() is None:
                try:
                    self.current_process.terminate()
                    self.current_process.wait(timeout=0.5)
                except:
                    self.current_process.kill()

            if self.play_process and self.play_process.poll() is None:
                try:
                    self.play_process.terminate()
                    self.play_process.wait(timeout=0.5)
                except:
                    self.play_process.kill()

        try:
            subprocess.run(["pkill", "-9", "-f", "piper-tts"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-9", "-f", "pw-play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass

    def set_mute(self, state: bool):
        self.mute = state
        if state:
            self.stop()

    def _run(self, text: str, settings: dict):
        if self.mute or not text.strip():
            return

        voice = settings.get("voice", "en_GB-cori-high")
        speed = settings.get("speed", 1.0)
        noise = settings.get("noise", 0.5)
        output_device = settings.get("output_device", "default")

        model_path = self.voice_dir / f"{voice}.onnx"
        tmp_wav = Path("/tmp/piper_output.wav")

        if not model_path.is_file():
            print(f"Model not found: {model_path}")
            return

        piper_cmd = [
            "piper-tts",
            "--model", str(model_path),
            "--length_scale", str(speed),
            "--noise_scale", str(noise),
            "--noise_w", str(noise),
            "--output_file", str(tmp_wav),
        ]

        try:
            # Generate audio
            proc = subprocess.Popen(
                piper_cmd,
                stdin=subprocess.PIPE,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.current_process = proc
            stdout, stderr = proc.communicate(input=text, timeout=30)

            if proc.returncode != 0:
                print(f"Piper error: {stderr.decode().strip()}")
                return

            if not tmp_wav.is_file():
                print("WAV file not created!")
                return

            # Playback - very simple and direct
            play_cmd = ["pw-play" if self.pipewire else "paplay"]

            if output_device != "default":
                if self.pipewire:
                    play_cmd += ["--target", output_device]
                else:
                    play_cmd += ["--device", output_device]

            play_cmd.append(str(tmp_wav))

            self.play_process = subprocess.Popen(play_cmd)
            self.play_process.wait()

        except Exception as e:
            print(f"Error: {e}")
        finally:
            self.current_process = None
            self.play_process = None
            if tmp_wav.exists():
                try:
                    tmp_wav.unlink()
                except:
                    pass
