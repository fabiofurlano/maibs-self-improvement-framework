#!/bin/bash
# Serve the MAIBS dashboard locally with CORS headers
# Usage: bash serve-dashboard.sh
# Opens http://localhost:8822 in your browser

cd "$(dirname "$0")/dashboard" || exit 1

echo "MAIBS Dashboard → http://localhost:8822"
echo "Make sure the MCP server is running: python3 maibs_mcp_server.py"
echo "Press Ctrl+C to stop."

python3 -c "
from http.server import HTTPServer, SimpleHTTPRequestHandler
import webbrowser, os

class CORSHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cross-Origin-Opener-Policy', 'unsafe-none')
        SimpleHTTPRequestHandler.end_headers(self)

server = HTTPServer(('0.0.0.0', 8822), CORSHandler)
print('Serving on http://localhost:8822')
server.serve_forever()
"
