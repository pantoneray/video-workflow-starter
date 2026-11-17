"""Serve only the MP4 explicitly bound to the current T4 round, with byte ranges."""
import hashlib
from pathlib import Path
import re


def serve(request, current, index, *, head=False):
    if current.get('stage') != 'T4' or not 0 <= index < len(current['items']):
        return request.reply(404, {'error': 'unknown_media'})
    video = current['items'][index]['content'].get('video')
    if not isinstance(video, dict) or not video.get('path') or not re.fullmatch(r'[a-f0-9]{64}', video.get('sha256', '')):
        return request.reply(404, {'error': 'unbound_media'})
    path = Path(video['path'])
    if path.suffix.lower() != '.mp4':
        return request.reply(415, {'error': 'only_bound_mp4_supported'})
    try:
        stream = path.open('rb')
    except OSError:
        return request.reply(503, {'error': 'media_unavailable'})
    with stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
        size = stream.tell()
        if digest.hexdigest() != video['sha256'] or size == 0:
            return request.reply(409, {'error': 'media_hash_mismatch'})
        start, end, status = 0, size-1, 200
        header = request.headers.get('Range')
        if header:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', header)
            if not match or not any(match.groups()):
                return request.reply(416, {'error': 'unsupported_range'})
            a, b = match.groups()
            if a:
                start = int(a); end = min(int(b),size-1) if b else size-1
            else:
                start = max(0, size-int(b))
            if start >= size or end < start:
                return request.reply(416, {'error': 'range_outside_media'})
            status = 206
        request.send_response(status)
        request.send_header('Content-Type', 'video/mp4')
        request.send_header('Content-Length', str(end-start+1))
        request.send_header('Accept-Ranges', 'bytes')
        request.send_header('Cache-Control', 'no-store')
        request.send_header('Referrer-Policy', 'no-referrer')
        request.send_header('X-Content-Type-Options', 'nosniff')
        if status == 206:
            request.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        request.end_headers()
        if head:
            return
        stream.seek(start)
        left = end-start+1
        try:
            while left:
                block = stream.read(min(left, 256*1024))
                if not block:
                    break
                request.wfile.write(block);left -= len(block)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass  # A browser may cancel a seek; no production operation ran.
