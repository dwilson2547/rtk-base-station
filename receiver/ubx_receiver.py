#!/usr/bin/env python3
"""
RTK Base Station — Phase 1 UBX Receiver (reconnect-resilient)

Listens on TCP port 5555 and writes all incoming bytes from the ESP32
logger to a single timestamped .ubx file for the whole session.

Unlike the original single-accept version, this loops on accept(): if the
ESP32 drops WiFi or reboots and reconnects, the receiver picks the new
connection up and keeps appending to the same file. TCP keepalive is
enabled so a powered-off client is detected instead of blocking forever.

Usage:
    python3 ubx_receiver.py

Stop with Ctrl+C. On exit, prints the convbin command and OPUS link.
"""

import socket
import time
import datetime
import signal
import sys

HOST = "0.0.0.0"
PORT = 5555
STATUS_INTERVAL = 60        # seconds between progress prints
WRITE_CHUNK = 4096          # recv/flush size


def format_bytes(n):
    if n < 1024:
        return f"{n} B"
    elif n < 1048576:
        return f"{n/1024:.2f} KB"
    else:
        return f"{n/1048576:.2f} MB"


def format_elapsed(seconds):
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"raw_obs_{timestamp}.ubx"

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"Listening on {HOST}:{PORT}...", flush=True)
    print(f"Output file: {filename}", flush=True)

    outfile = open(filename, "ab")
    total_bytes = 0
    start_time = time.time()
    last_status = start_time
    conn = None

    def shutdown(signum=None, frame=None):
        print("\nShutting down...", flush=True)
        try:
            outfile.flush()
            outfile.close()
        except Exception:
            pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        try:
            server.close()
        except Exception:
            pass

        if total_bytes > 0:
            elapsed = time.time() - start_time
            print(f"\nSession complete.")
            print(f"  File:     {filename}")
            print(f"  Size:     {format_bytes(total_bytes)}")
            print(f"  Duration: {format_elapsed(elapsed)}")
            print(f"\nConvert to RINEX:")
            print(f"  convbin {filename} -o observation.obs -r ubx")
            print(f"\nSubmit to OPUS:")
            print(f"  https://www.ngs.noaa.gov/OPUS/")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Accept loop: survive client reconnects, keep appending to the same file.
    while True:
        conn, addr = server.accept()
        print(f"Client connected from {addr[0]}:{addr[1]}", flush=True)

        # Detect a silently-dead peer instead of blocking in recv() forever.
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        except (AttributeError, OSError):
            pass

        try:
            while True:
                try:
                    data = conn.recv(WRITE_CHUNK)
                except (ConnectionResetError, TimeoutError, OSError):
                    print("Client connection lost; waiting for reconnect...", flush=True)
                    break

                if not data:
                    print("Client closed connection; waiting for reconnect...", flush=True)
                    break

                outfile.write(data)
                outfile.flush()
                total_bytes += len(data)

                now = time.time()
                if now - last_status >= STATUS_INTERVAL:
                    elapsed = now - start_time
                    print(f"[{format_elapsed(elapsed)}] {format_bytes(total_bytes)} received", flush=True)
                    last_status = now
        finally:
            try:
                conn.close()
            except Exception:
                pass
            conn = None


if __name__ == "__main__":
    main()
