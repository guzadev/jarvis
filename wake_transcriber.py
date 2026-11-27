"""Private Spanish wake recognizer. WAV clips and transcripts are never written to disk."""
import base64
import io
import json
import re
import socket
import sys
from pathlib import Path

# Whisper Small transcribed this invocation as “Gervis, estás ahí” on the
# capture-gated clip and “¿Garvis? ¿Estás ahí?” with longer trailing silence.
KEYWORD = re.compile(r'\bjarvis\b|\bg[ae]rvis\b[\s¿?¡!,.:;-]{1,12}est[aá]s\s+ah[ií]\b', re.IGNORECASE)


def main(folder):
    # This process communicates exclusively over its stdin/stdout pipes.
    def deny_network(*args, **kwargs):raise OSError('El detector de voz usa únicamente archivos locales.')
    socket.socket.connect=deny_network
    socket.socket.connect_ex=deny_network
    socket.getaddrinfo=deny_network
    from faster_whisper import WhisperModel
    model = WhisperModel(str(folder), device='cpu', compute_type='int8', cpu_threads=6,
                         local_files_only=True, num_workers=1)
    print('{"ready":true}', flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        wav = io.BytesIO(base64.b64decode(message['wav'], validate=True))
        segments, _ = model.transcribe(wav, language='es', beam_size=1, temperature=0,
            condition_on_previous_text=False, vad_filter=False, without_timestamps=True)
        hit = bool(KEYWORD.search(" ".join(segment.text for segment in segments)))
        print(json.dumps({'id':message['id'],'hit':hit}),flush=True)


if __name__ == '__main__':
    try:main(Path(sys.argv[1]))
    except Exception:
        print('{"error":true}', flush=True)
        sys.exit(1)
