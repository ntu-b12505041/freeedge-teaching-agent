from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import os
import socket
import ssl
import subprocess
import tempfile
import time
import uuid
import wave
from pathlib import Path
from urllib.parse import urlparse

from app import config


TTS_INSTRUCTIONS = """Voice Affect: Natural, warm, and focused.
Tone: Friendly teacher, not announcer-like.
Pacing: Moderate with small pauses after important ideas.
Emotion: Curious and encouraging.
Delivery: Clear classroom explainer voice; avoid robotic cadence."""

EDGE_TRUSTED_CLIENT_TOKEN = "6A5AA1D4EAFF4E9FB37E23D68491D6F4"
EDGE_CHROMIUM_FULL_VERSION = "143.0.3650.75"
EDGE_CHROMIUM_MAJOR_VERSION = EDGE_CHROMIUM_FULL_VERSION.split(".", maxsplit=1)[0]
EDGE_SEC_MS_GEC_VERSION = f"1-{EDGE_CHROMIUM_FULL_VERSION}"


def synthesize_voiceover(text: str, out_path: Path) -> str:
    if config.TTS_PROVIDER == "openai" and config.OPENAI_API_KEY:
        try:
            _openai_tts(text, out_path)
            return "openai"
        except Exception:
            pass
    try:
        asyncio.run(_edge_tts(text, out_path))
        return "edge-tts"
    except Exception:
        try:
            _windows_sapi(text, out_path.with_suffix(".wav"))
            return "windows-sapi"
        except Exception:
            _silent_wav(out_path.with_suffix(".wav"), seconds=max(12, len(text.split()) / config.TARGET_WPM * 60))
            return "silent-fallback"


def _openai_tts(text: str, out_path: Path) -> None:
    from openai import OpenAI

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    chunks = _chunk_text(text, 3800)
    if len(chunks) == 1:
        with client.audio.speech.with_streaming_response.create(
            model=config.OPENAI_TTS_MODEL,
            voice=config.OPENAI_TTS_VOICE,
            input=chunks[0],
            instructions=TTS_INSTRUCTIONS,
            response_format="mp3",
        ) as response:
            response.stream_to_file(out_path)
        return
    parts: list[Path] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for idx, chunk in enumerate(chunks):
            part = tmp_dir / f"part_{idx:02d}.mp3"
            with client.audio.speech.with_streaming_response.create(
                model=config.OPENAI_TTS_MODEL,
                voice=config.OPENAI_TTS_VOICE,
                input=chunk,
                instructions=TTS_INSTRUCTIONS,
                response_format="mp3",
            ) as response:
                response.stream_to_file(part)
            parts.append(part)
        _concat_audio(parts, out_path)


async def _edge_tts(text: str, out_path: Path) -> None:
    try:
        import edge_tts

        communicate = edge_tts.Communicate(text, config.EDGE_TTS_VOICE, rate="-4%", pitch="+0Hz")
        await communicate.save(str(out_path))
    except ModuleNotFoundError:
        _edge_tts_raw(text, out_path)


def _edge_tts_raw(text: str, out_path: Path) -> None:
    chunks = _chunk_text(text, 2500)
    if len(chunks) == 1:
        _edge_tts_raw_one(chunks[0], out_path)
        return
    parts: list[Path] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for idx, chunk in enumerate(chunks):
            part = tmp_dir / f"edge_part_{idx:02d}.mp3"
            _edge_tts_raw_one(chunk, part)
            parts.append(part)
        _concat_audio(parts, out_path)


def _edge_tts_raw_one(text: str, out_path: Path) -> None:
    connection_id = uuid.uuid4().hex
    url = (
        "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1"
        f"?TrustedClientToken={EDGE_TRUSTED_CLIENT_TOKEN}"
        f"&ConnectionId={connection_id}"
        f"&Sec-MS-GEC={_edge_sec_ms_gec()}"
        f"&Sec-MS-GEC-Version={EDGE_SEC_MS_GEC_VERSION}"
    )
    parsed = urlparse(url)
    host = parsed.hostname or ""
    path = f"{parsed.path}?{parsed.query}"
    raw = socket.create_connection((host, 443), timeout=20)
    sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
    try:
        _websocket_handshake(sock, host, path)
        request_id = uuid.uuid4().hex
        _ws_send_text(sock, _edge_speech_config())
        _ws_send_text(sock, _edge_ssml(request_id, text))
        audio = bytearray()
        deadline = time.time() + 90
        while time.time() < deadline:
            opcode, payload = _ws_recv(sock)
            if opcode == 8:
                break
            if opcode == 9:
                _ws_send(sock, payload, opcode=10)
                continue
            if opcode == 1:
                message = payload.decode("utf-8", errors="ignore")
                if "Path:turn.end" in message:
                    break
            elif opcode == 2:
                chunk = _extract_edge_audio(payload)
                if chunk:
                    audio.extend(chunk)
        if not audio:
            raise RuntimeError("Edge TTS returned no audio.")
        out_path.write_bytes(audio)
    finally:
        sock.close()


def _edge_speech_config() -> str:
    return (
        "Content-Type:application/json; charset=utf-8\r\n"
        "Path:speech.config\r\n\r\n"
        '{"context":{"synthesis":{"audio":{"metadataoptions":{"sentenceBoundaryEnabled":"false",'
        '"wordBoundaryEnabled":"false"},"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}'
    )


def _edge_ssml(request_id: str, text: str) -> str:
    safe_text = html.escape(text, quote=False)
    return (
        f"X-RequestId:{request_id}\r\n"
        "Content-Type:application/ssml+xml\r\n"
        "Path:ssml\r\n\r\n"
        "<speak version='1.0' xml:lang='en-US'>"
        f"<voice name='{html.escape(config.EDGE_TTS_VOICE)}'>"
        "<prosody rate='-4%' pitch='+0Hz'>"
        f"{safe_text}"
        "</prosody></voice></speak>"
    )


def _websocket_handshake(sock: ssl.SSLSocket, host: str, path: str) -> None:
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    muid = os.urandom(16).hex().upper()
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{EDGE_CHROMIUM_MAJOR_VERSION}.0.0.0 Safari/537.36 "
        f"Edg/{EDGE_CHROMIUM_MAJOR_VERSION}.0.0.0"
    )
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Pragma: no-cache\r\n"
        "Cache-Control: no-cache\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "Origin: chrome-extension://jdiccldimpdaibmpdkjnbmckianbfold\r\n"
        f"User-Agent: {user_agent}\r\n"
        "Accept-Encoding: gzip, deflate, br, zstd\r\n"
        "Accept-Language: en-US,en;q=0.9\r\n"
        f"Cookie: muid={muid};\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))
    response = _recv_until(sock, b"\r\n\r\n")
    if b" 101 " not in response.split(b"\r\n", 1)[0]:
        raise RuntimeError("Edge TTS websocket handshake failed.")


def _edge_sec_ms_gec() -> str:
    windows_epoch_seconds = 11644473600
    ticks = time.time() + windows_epoch_seconds
    ticks -= ticks % 300
    ticks *= 10_000_000
    source = f"{ticks:.0f}{EDGE_TRUSTED_CLIENT_TOKEN}"
    return hashlib.sha256(source.encode("ascii")).hexdigest().upper()


def _ws_send_text(sock: ssl.SSLSocket, text: str) -> None:
    _ws_send(sock, text.encode("utf-8"), opcode=1)


def _ws_send(sock: ssl.SSLSocket, payload: bytes, opcode: int) -> None:
    first = 0x80 | opcode
    length = len(payload)
    if length < 126:
        header = bytes([first, 0x80 | length])
    elif length < 65536:
        header = bytes([first, 0x80 | 126]) + length.to_bytes(2, "big")
    else:
        header = bytes([first, 0x80 | 127]) + length.to_bytes(8, "big")
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
    sock.sendall(header + mask + masked)


def _ws_recv(sock: ssl.SSLSocket) -> tuple[int, bytes]:
    header = _recv_exact(sock, 2)
    first, second = header
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = int.from_bytes(_recv_exact(sock, 2), "big")
    elif length == 127:
        length = int.from_bytes(_recv_exact(sock, 8), "big")
    masked = bool(second & 0x80)
    mask = _recv_exact(sock, 4) if masked else b""
    payload = _recv_exact(sock, length) if length else b""
    if masked:
        payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
    return opcode, payload


def _extract_edge_audio(payload: bytes) -> bytes:
    if len(payload) > 2:
        header_len = int.from_bytes(payload[:2], "big")
        header_end = 2 + header_len
        if 0 < header_len < len(payload) and b"Content-Type:audio" in payload[2:header_end]:
            return payload[header_end:]
    marker = b"Path:audio"
    idx = payload.find(marker)
    if idx == -1:
        return b""
    start = payload.find(b"\r\n\r\n", idx)
    if start == -1:
        return b""
    return payload[start + 4 :]


def _recv_until(sock: ssl.SSLSocket, marker: bytes) -> bytes:
    data = bytearray()
    while marker not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def _recv_exact(sock: ssl.SSLSocket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise RuntimeError("WebSocket closed unexpectedly.")
        data.extend(chunk)
    return bytes(data)


def _concat_audio(parts: list[Path], out_path: Path) -> None:
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    list_path = out_path.parent / "audio_parts.txt"
    lines = []
    for part in parts:
        safe_path = str(part.resolve()).replace("\\", "/")
        lines.append(f"file '{safe_path}'")
    list_path.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(
        [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _silent_wav(out_path: Path, seconds: float) -> None:
    sample_rate = 22050
    frames = int(seconds * sample_rate)
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)


def _windows_sapi(text: str, out_path: Path) -> None:
    text_path = out_path.with_suffix(".txt")
    text_path.write_text(text, encoding="utf-8")
    script = f"""
Add-Type -AssemblyName System.Speech
$text = Get-Content -LiteralPath '{str(text_path).replace("'", "''")}' -Raw -Encoding UTF8
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $synth.GetInstalledVoices() | Where-Object {{ $_.VoiceInfo.Culture.Name -like 'en-*' }} | Select-Object -First 1
if ($voice) {{ $synth.SelectVoice($voice.VoiceInfo.Name) }}
$synth.Rate = -1
$synth.Volume = 100
$synth.SetOutputToWaveFile('{str(out_path).replace("'", "''")}')
$synth.Speak($text)
$synth.Dispose()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not out_path.exists():
        raise RuntimeError("Windows SAPI did not create a WAV file.")


def _chunk_text(text: str, limit: int) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = paragraph
    if current:
        chunks.append(current)
    return chunks
