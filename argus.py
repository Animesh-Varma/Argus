import socket
import cv2
import pyaudio
import struct

# Client configuration
SERVER_HOST = "192.168.29.21"  # Replace with the server's IP address
STREAM_PORT = 8000

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024

def main():
    """Connects to the server and streams audio and video."""
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cap = None
    audio_stream = None
    try:
        client_socket.connect((SERVER_HOST, STREAM_PORT))
        print(f"Connected to server at {SERVER_HOST}:{STREAM_PORT}")

        cap = cv2.VideoCapture(0)
        audio_stream = pyaudio.PyAudio().open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

        while True:
            # Capture video frame
            ret, frame = cap.read()
            if not ret:
                break
            
            # Encode video frame
            result, frame = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            video_data = frame.tobytes()

            # Capture audio chunk
            audio_data = audio_stream.read(CHUNK)

            # Pack and send data
            data = struct.pack(">L", len(video_data)) + video_data + audio_data
            client_socket.sendall(data)

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