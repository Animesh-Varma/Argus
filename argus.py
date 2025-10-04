import socket
import cv2
import pyaudio
import struct
import time

# Client configuration
SERVER_HOST = "192.168.29.21"  # Replace with the server's IP address
STREAM_PORT = 8000

# Audio/Video configuration
FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 48000
FPS = 20.0
CHUNK = int(RATE / FPS) # Synchronize audio chunk size with video frame rate
AUDIO_DATA_SIZE = CHUNK * CHANNELS * 2

def main():
    """Connects to the server and streams audio and video at a controlled frame rate."""
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cap = None
    audio_stream = None
    try:
        client_socket.connect((SERVER_HOST, STREAM_PORT))
        print(f"Connected to server at {SERVER_HOST}:{STREAM_PORT}")

        cap = cv2.VideoCapture(0)
        audio_stream = pyaudio.PyAudio().open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

        frame_time = 1.0 / FPS

        while True:
            start_time = time.time()

            # Capture video frame
            ret, frame = cap.read()
            if not ret:
                break
            
            # Encode video frame
            result, frame_encoded = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75]) # Quality reduced to 75
            video_data = frame_encoded.tobytes()

            # Capture audio chunk
            # Note: This audio capture is not perfectly synced with the video frame capture.
            # For perfect sync, more complex threading or timestamping would be needed.
            audio_data = audio_stream.read(CHUNK)

            # Pack and send data
            payload = video_data + audio_data
            data = struct.pack(">L", len(payload)) + payload
            client_socket.sendall(data)

            # --- Frame Rate Throttling ---
            elapsed_time = time.time() - start_time
            sleep_time = frame_time - elapsed_time
            if sleep_time > 0:
                time.sleep(sleep_time)

    except (BrokenPipeError, ConnectionResetError):
        print("Server disconnected.")
    except KeyboardInterrupt:
        print("Stopping client.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if cap:
            cap.release()
        if audio_stream:
            audio_stream.stop_stream()
            audio_stream.close()
        pyaudio.PyAudio().terminate()
        client_socket.close()
        print("Client stopped.")

if __name__ == "__main__":
    main()
