import socket
import cv2
import numpy as np
import pyaudio
import struct
import os
import sys
import wave
import subprocess
from datetime import datetime
from contextlib import contextmanager

# Streaming server configuration
STREAM_HOST = "0.0.0.0"
STREAM_PORT = 8000

# Audio/Video configuration
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 48000
VIDEO_FPS = 20.0
CHUNK = int(RATE / VIDEO_FPS) # Synchronize audio chunk size with video frame rate
AUDIO_DATA_SIZE = CHUNK * CHANNELS * 2

@contextmanager
def ignore_stderr():
    """A context manager to temporarily redirect stderr to dev/null."""
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    sys.stderr.flush()
    os.dup2(devnull, 2)
    os.close(devnull)
    try:
        yield
    finally:
        os.dup2(old_stderr, 2)
        os.close(old_stderr)

def get_default_output_device_index(p):
    """Tries to find the default system output device."""
    try:
        with ignore_stderr():
            device_info = p.get_default_output_device_info()
        return device_info['index']
    except IOError:
        print("Could not find default output device. Using fallback.")
        return 0

def main():
    """Starts the streaming server in either stream or record mode."""
    mode = ''''''
    while mode not in ['stream', 'record']:
        mode = input("Enter mode ('stream' or 'record'): ").lower()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((STREAM_HOST, STREAM_PORT))
    server_socket.listen(1)
    print(f"Streaming server listening on {STREAM_HOST}:{STREAM_PORT}...")

    conn, addr = server_socket.accept()
    print(f"Streaming client connected from {addr}")

    p = None
    audio_stream = None
    wave_file = None
    video_writer = None
    output_folder = ""
    video_path = ""
    audio_path = ""

    if mode == 'stream':
        print("Attempting to start audio stream...")
        with ignore_stderr():
            p = pyaudio.PyAudio()
            try:
                device_index = get_default_output_device_index(p)
                audio_stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True,
                                      frames_per_buffer=CHUNK, output_device_index=device_index)
                print("Audio stream opened successfully.")
            except Exception as e:
                print(f"Failed to open audio stream: {e}")
    else: # record mode
        p = pyaudio.PyAudio()
        timestamp = datetime.now().strftime("recording_%Y-%m-%d_%H-%M-%S")
        output_folder = os.path.join("output", timestamp)
        os.makedirs(output_folder, exist_ok=True)
        print(f"Recording to folder: {output_folder}")
        
        audio_path = os.path.join(output_folder, "audio.wav")
        video_path = os.path.join(output_folder, "video.mp4") # Temp video file
        wave_file = wave.open(audio_path, 'wb')
        wave_file.setnchannels(CHANNELS)
        wave_file.setsampwidth(p.get_sample_size(FORMAT))
        wave_file.setframerate(RATE)

    data = b""
    payload_size = struct.calcsize(">L")

    try:
        while True:
            while len(data) < payload_size:
                packet = conn.recv(4 * 1024)
                if not packet: break
                data += packet
            if not packet: break

            packed_msg_size = data[:payload_size]
            data = data[payload_size:]
            msg_size = struct.unpack(">L", packed_msg_size)[0]

            while len(data) < msg_size:
                data += conn.recv(4 * 1024)

            frame_data = data[:msg_size]
            data = data[msg_size:]

            video_data = frame_data[:-AUDIO_DATA_SIZE]
            audio_frame_data = frame_data[-AUDIO_DATA_SIZE:]

            if mode == 'stream':
                nparr = np.frombuffer(video_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if frame is not None: cv2.imshow('Video', frame)
                if cv2.waitKey(1) & 0xFF == ord('q'): break
                if audio_stream: audio_stream.write(audio_frame_data)
            
            else: # record mode
                if video_writer is None:
                    nparr = np.frombuffer(video_data, np.uint8)
                    first_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if first_frame is not None:
                        height, width, _ = first_frame.shape
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        video_writer = cv2.VideoWriter(video_path, fourcc, VIDEO_FPS, (width, height))
                        video_writer.write(first_frame)
                else:
                    nparr = np.frombuffer(video_data, np.uint8)
                    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if frame is not None: video_writer.write(frame)
                
                wave_file.writeframes(audio_frame_data)

    except (BrokenPipeError, ConnectionResetError): print("Client disconnected.")
    except KeyboardInterrupt: print("Stopping server.")
    except Exception as e: print(f"Streaming error: {e}")
    finally:
        # Close all streams and files
        if audio_stream: audio_stream.close()
        if wave_file: wave_file.close()
        if video_writer: video_writer.release()
        if p: p.terminate()
        conn.close()
        server_socket.close()
        cv2.destroyAllWindows()
        print("Streaming stopped.")

        # --- Automated Merging --- 
        if mode == 'record' and video_path and audio_path:
            print("Recording finished. Merging video and audio...")
            final_video_path = os.path.join(output_folder, "final_video.mp4")
            command = [
                'ffmpeg',
                '-y', # Overwrite output file if it exists
                '-i', video_path,
                '-i', audio_path,
                '-c:v', 'copy',
                '-c:a', 'aac',
                final_video_path
            ]
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
                print(f"Successfully merged video and audio to: {final_video_path}")
                # Clean up temporary files
                os.remove(video_path)
                os.remove(audio_path)
                print("Temporary files removed.")
            except FileNotFoundError:
                print("ERROR: ffmpeg command not found. Please install FFmpeg.")
            except subprocess.CalledProcessError as e:
                print("Error during ffmpeg merging process:")
                print(e.stderr)

if __name__ == "__main__":
    main()
