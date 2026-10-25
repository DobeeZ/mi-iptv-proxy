import os
import re
from flask import Flask, redirect, Response, request
import streamlink
import requests

app = Flask(__name__)

def parse_channel_line(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Detecta enlace de Twitch
    twitch_match = re.search(r'twitch\.tv/([a-zA-Z0-9_]+)', line, re.IGNORECASE)
    if twitch_match:
        cid = twitch_match.group(1)
        return {"platform": "twitch", "id": cid, "name": f"{cid} (Twitch)"}

    # Detecta enlace de Kick
    kick_match = re.search(r'kick\.com/([a-zA-Z0-9_]+)', line, re.IGNORECASE)
    if kick_match:
        cid = kick_match.group(1)
        return {"platform": "kick", "id": cid, "name": f"{cid} (Kick)"}

    return None

def get_channels():
    channels = []
    if os.path.exists("channels.txt"):
        with open("channels.txt", "r", encoding="utf-8") as f:
            for line in f:
                ch = parse_channel_line(line)
                if ch:
                    channels.append(ch)
    
    # Canales por defecto si no hay nada en channels.txt
    if not channels:
        channels = [
            {"platform": "twitch", "id": "x9nium", "name": "x9nium (Twitch)"},
            {"platform": "kick", "id": "x9nium", "name": "x9nium (Kick)"},
        ]
    return channels

@app.route('/')
@app.route('/playlist.m3u')
def get_playlist():
    host = request.host
    scheme = request.headers.get('X-Forwarded-Proto', 'https')
    channels = get_channels()
    
    m3u_content = "#EXTM3U\n\n"
    for ch in channels:
        platform = ch["platform"]
        channel_id = ch["id"]
        display_name = ch["name"]
        
        stream_url = f"{scheme}://{host}/live/{platform}/{channel_id}"
        m3u_content += f'#EXTINF:-1 group-title="{platform.capitalize()}", {display_name}\n'
        m3u_content += f'{stream_url}\n\n'
        
    return Response(m3u_content, mimetype='text/plain')

@app.route('/live/twitch/<channel_id>')
def stream_twitch(channel_id):
    target_url = f"https://www.twitch.tv/{channel_id}"
    try:
        streams = streamlink.streams(target_url)
        if "best" in streams:
            return redirect(streams["best"].url, code=302)
    except Exception as e:
        print(f"Error en Twitch ({channel_id}): {e}")
    return "Canal de Twitch no disponible o sin emisión", 404

@app.route('/live/kick/<channel_id>')
def stream_kick(channel_id):
    try:
        streams = streamlink.streams(f"https://kick.com/{channel_id}")
        if "best" in streams:
            return redirect(streams["best"].url, code=302)
    except Exception:
        pass
        
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(f"https://kick.com/api/v2/channels/{channel_id}", headers=headers, timeout=5).json()
        playback_url = res.get("playback_url")
        if playback_url:
            return redirect(playback_url, code=302)
    except Exception as e:
        print(f"Error en Kick ({channel_id}): {e}")
        
    return "Canal de Kick no disponible o sin emisión", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
