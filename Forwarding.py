import http.server
import socketserver
import httpx

REMOTE_URL = "http://192.168.1.89"
LOCAL_PORT = 9090

class ProxyHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        remote_url = f"{REMOTE_URL}{self.path}"
        try:
            response = httpx.get(remote_url)
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                if key.lower() == "transfer-encoding":
                    continue  # skip transfer-encoding headers
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(response.content)
        except Exception as e:
            self.send_error(502, f"Bad gateway: {e}")

Handler = ProxyHTTPRequestHandler
with socketserver.TCPServer(("0.0.0.0", LOCAL_PORT), Handler) as httpd:
    print(f"Reverse proxy running at http://localhost:{LOCAL_PORT}/ -> {REMOTE_URL}/")
    httpd.serve_forever()
