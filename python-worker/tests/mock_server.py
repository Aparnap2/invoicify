#!/usr/bin/env python3
"""
Simple HTTP mock server for Vision API testing.
Replaces Mockoon for integration tests.
"""

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time


class VisionMockHandler(BaseHTTPRequestHandler):
    """Handler for Vision API mock endpoints."""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def do_POST(self):
        """Handle POST requests."""
        if self.path == "/extract":
            self._handle_extract()
        else:
            self._send_error(404, "Not Found")

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/health":
            self._send_json({"status": "ok"})
        else:
            self._send_error(404, "Not Found")

    def _handle_extract(self):
        """Handle invoice extraction request."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)

            # Parse request (optional validation)
            request = json.loads(post_data.decode("utf-8"))

            # Return mock response
            response = {
                "vendor_name": "Acme Corporation",
                "total_amount": 1500.00,
                "invoice_number": "INV-2025-001",
                "due_date": "2025-02-08",
                "currency": "USD",
                "confidence": 0.98,
            }

            # Simulate processing delay
            time.sleep(0.1)

            self._send_json(response)

        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
        except Exception as e:
            self._send_error(500, str(e))

    def _send_json(self, data, status=200):
        """Send JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _send_error(self, status, message):
        """Send error response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode("utf-8"))


def start_mock_server(port=3000):
    """Start the mock server in a background thread."""
    server = HTTPServer(("localhost", port), VisionMockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"✅ Mock server started on port {port}")
    return server


if __name__ == "__main__":
    server = start_mock_server()
    print("Press Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.shutdown()
