import subprocess
import os
import shutil
import threading
from pathlib import Path


class PiperEngine:
    def __init__(self):
        self.voice_dir = Path(__file__).parent / "voices"
        self.current_process: subprocess.Popen | None = None
        self.play_process: subprocess.Popen | None = None
        self.mute = False
        self.lock = threading.Lock()

        self.pipewire = self._is_pipewire()
        self.paplay_cmd = "pw-play" if self.pipewire else "paplay"
        self.has_sox = shutil.which("sox") is not None

    def _is_pipewire(self) -> bool:
        try:
            subprocess.check_output(["pw-cli", "info"], stderr=subprocess.DEVNULL, timeout=2)
            return True
        except Exception:
            return False

    def stop(self):
        """Force-stop all synthesis and playback processes."""
        with self.lock:
            # Kill synthesis
            if self.current_process and self.current_process.poll() is None:
                try:
                    self.current_process.terminate()
                    self.current_process.wait(timeout=0.3)
                except:
                    self.current_process.kill()
                    self.current_process.wait(timeout=0.3)
                self.current_process = None

            # Kill playback
            if self.play_process and self.play_process.poll() is None:
                try:
                    self.play_process.terminate()
                    self.play_process.wait(timeout=0.3)
                except:
                    self.play_process.kill()
                    self.play_process.wait(timeout=0.3)
                self.play_process = None

        # Last-resort: kill any lingering piper or pw-play processes by name
        try:
            subprocess.run(["pkill", "-9", "-f", "piper-tts"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-9", "-f", self.paplay_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        volume = settings.get("volume", 1.0)
        output_device = settings.get("output_device", "default")

        model_path = self.voice_dir / f"{voice}.onnx"
        tmp_wav = Path("/tmp/piper_output.wav")

        if not model_path.is_file():
            print(f"Model file not found: {model_path}")
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
            with self.lock:
                proc = subprocess.Popen(
                    piper_cmd,
                    stdin=subprocess.PIPE,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self.current_process = proc

            stdout, stderr = proc.communicate(input=text, timeout=60)

            if proc.returncode != 0:
                print(f"Piper failed (exit {proc.returncode}): {stderr.decode().strip()}")
                return

            if not tmp_wav.is_file():
                print("No WAV file created!")
                return

            # Playback
            if self.has_sox and abs(volume - 1.0) > 0.001:
                sox_cmd = ["sox", str(tmp_wav), "-t", "wav", "-", "vol", str(volume)]
                play_cmd = [self.paplay_cmd, "-"]

                if output_device != "default" and not self.pipewire:
                    play_cmd += ["--device", output_device]

                with self.lock:
                    sox = subprocess.Popen(sox_cmd, stdout=subprocess.PIPE)
                    play_proc = subprocess.Popen(play_cmd, stdin=sox.stdout)
                    sox.stdout.close()

                play_proc.wait()
                sox.wait()
            else:
                cmd = [self.paplay_cmd, str(tmp_wav)]
                if output_device != "default" and not self.pipewire:
                    cmd += ["--device", output_device]

                with self.lock:
                    play_proc = subprocess.Popen(cmd)
                play_proc.wait()

        except subprocess.TimeoutExpired:
            print("Generation or playback timed out")
            self.stop()
        except Exception as e:
            print(f"Playback error: {e}")
            self.stop()

        finally:
            with self.lock:
                self.current_process = None
                self.play_process = None

            if tmp_wav.exists():
                try:
                    tmp_wav.unlink()
                except:
                    pass
