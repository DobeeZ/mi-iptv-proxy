import os
import re
from flask import Flask, redirect, Response, request
import streamlink
import requests

app = Flask(__name__)

def parse_channel_line(line, current_group):
    line = line.strip()
    if not line or line.startswith("#"):
        return None, current_group

    # Si detecta un nombre entre corchetes [Ejemplo], cambia la categoría actual
    if line.startswith("[") and line.endswith("]"):
        new_group = line[1:-1].strip()
        return None, new_group if new_group else "General"

    # Detecta enlace de Twitch (permite letras, números, guiones y guiones bajos)
    twitch_match = re.search(r'twitch\.tv/([a-zA-Z0-9_-]+)', line, re.IGNORECASE)
    if twitch_match:
        cid = twitch_match.group(1)
        return {"platform": "twitch", "id": cid, "name": f"{cid} (Twitch)", "group": current_group}, current_group

    # Detecta enlace de Kick (permite letras, números, guiones y guiones bajos)
    kick_match = re.search(r'kick\.com/([a-zA-Z0-9_-]+)', line, re.IGNORECASE)
    if kick_match:
        cid = kick_match.group(1)
        return {"platform": "kick", "id": cid, "name": f"{cid} (Kick)", "group": current_group}, current_group

    return None, current_group

def get_channels():
    channels = []
    current_group = "General"
    if os.path.exists("channels.txt"):
        with open("channels.txt", "r", encoding="utf-8") as f:
            for line in f:
                ch, current_group = parse_channel_line(line, current_group)
                if ch:
                    channels.append(ch)
    
    if not channels:
        channels = [
            {"platform": "twitch", "id": "x9nium", "name": "x9nium (Twitch)", "group": "E-Sports"},
            {"platform": "kick", "id": "x9nium", "name": "x9nium (Kick)", "group": "E-Sports"},
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
        group = ch.get("group", "General")
        
        stream_url = f"{scheme}://{host}/live/{platform}/{channel_id}"
        # Se añade tvg-group para forzar la compatibilidad con OTT Navigator y TiviMate
        m3u_content += f'#EXTINF:-1 tvg-group="{group}" group-title="{group}", {display_name}\n'
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
