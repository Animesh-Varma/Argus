import socket
import cv2
import pyaudio
import struct
import time

# Client configuration
SERVER_HOST = "211.ip.gl.ply.gg"
STREAM_PORT = 40815

# Audio/Video configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
FPS = 20.0
CHUNK = int(RATE / FPS)

def main():
    while True:  # Main loop for reconnection
        client_socket = None
        cap = None
        audio_stream = None
        p = None

        try:
            print(f"Attempting to connect to {SERVER_HOST}:{STREAM_PORT}...")
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((SERVER_HOST, STREAM_PORT))
            print("Connection successful. Starting stream.")

            cap = cv2.VideoCapture(0)
            p = pyaudio.PyAudio()
            audio_stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

            frame_time = 1.0 / FPS

            while True:  # Inner loop for streaming
                start_time = time.time()

                ret, frame = cap.read()
                if not ret:
                    print("Failed to grab frame from camera.")
                    break

                result, frame_encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                video_data = frame_encoded.tobytes()

                try:
                    audio_data = audio_stream.read(CHUNK, exception_on_overflow=False)
                except IOError as e:
                    print(f"Audio input overflow, skipping frame: {e}")
                    continue

                video_len = len(video_data)
                audio_len = len(audio_data)
                header = struct.pack(">LL", video_len, audio_len)
                client_socket.sendall(header + video_data + audio_data)

                elapsed_time = time.time() - start_time
                sleep_time = frame_time - elapsed_time
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except (BrokenPipeError, ConnectionResetError):
            print("Server connection lost.")
        except ConnectionRefusedError:
            print("Connection refused. Server may be down or busy.")
        except KeyboardInterrupt:
            print("\nStopping client.")
            break  # Exit the main loop on Ctrl+C
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        finally:
            # Gracefully close all resources
            if cap:
                cap.release()
            if audio_stream:
                audio_stream.stop_stream()
                audio_stream.close()
            if p:
                p.terminate()
            if client_socket:
                client_socket.close()
            
            print("Client resources released. Reconnecting in 5 minutes...")
            try:
                time.sleep(300)  # Wait 5 minutes
            except KeyboardInterrupt:
                print("\nStopping client during wait.")
                break

if __name__ == "__main__":
    main()
