import os
import re
from flask import Flask, redirect, Response, request
import streamlink
import requests

# Importación protegida: si yt-dlp falla, el servidor NO se cae
try:
    import yt_dlp
except Exception:
    yt_dlp = None

app = Flask(__name__)

def parse_channel_line(line, current_group):
    try:
        line = line.strip()
        if not line or line.startswith("#"):
            return None, current_group

        if line.startswith("[") and line.endswith("]"):
            new_group = line[1:-1].strip()
            return None, new_group if new_group else "General"

        # Twitch
        twitch_match = re.search(r'twitch\.tv/([a-zA-Z0-9_-]+)', line, re.IGNORECASE)
        if twitch_match:
            cid = twitch_match.group(1)
            return {"platform": "twitch", "id": cid, "name": f"{cid} (Twitch)", "group": current_group}, current_group

        # Kick
        kick_match = re.search(r'kick\.com/([a-zA-Z0-9_-]+)', line, re.IGNORECASE)
        if kick_match:
            cid = kick_match.group(1)
            return {"platform": "kick", "id": cid, "name": f"{cid} (Kick)", "group": current_group}, current_group

        # YouTube Handle (@canal)
        yt_handle = re.search(r'youtube\.com/(@[a-zA-Z0-9._-]+)', line, re.IGNORECASE)
        if yt_handle:
            cid = yt_handle.group(1)
            return {"platform": "youtube", "id": cid, "name": f"{cid[1:]} (YouTube)", "group": current_group}, current_group

        # YouTube Video URL
        yt_video = re.search(r'(?:youtube\.com/(?:watch\?v=|live/)|youtu\.be/)([a-zA-Z0-9_-]+)', line, re.IGNORECASE)
        if yt_video:
            vid = yt_video.group(1)
            return {"platform": "youtube", "id": f"v_{vid}", "name": f"Live YT ({vid})", "group": current_group}, current_group

        return None, current_group
    except Exception as e:
        print(f"Error procesando linea '{line}': {e}")
        return None, current_group

def get_channels():
    channels = []
    current_group = "General"
    if os.path.exists("channels.txt"):
        try:
            with open("channels.txt", "r", encoding="utf-8") as f:
                for line in f:
                    ch, current_group = parse_channel_line(line, current_group)
                    if ch:
                        channels.append(ch)
        except Exception as e:
            print(f"Error leyendo channels.txt: {e}")
    
    if not channels:
        channels = [
            {"platform": "twitch", "id": "x9nium", "name": "x9nium (Twitch)", "group": "E-Sports"},
            {"platform": "kick", "id": "x9nium", "name": "x9nium (Kick)", "group": "E-Sports"},
        ]
    return channels

@app.route('/')
@app.route('/playlist.m3u')
def get_playlist():
    try:
        host = request.host
        scheme = request.headers.get('X-Forwarded-Proto', 'https')
        channels = get_channels()
        
        m3u_content = "#EXTM3U\n\n"
        for ch in channels:
            platform = ch.get("platform", "twitch")
            channel_id = ch.get("id", "")
            display_name = ch.get("name", "Canal")
            group = ch.get("group", "General")
            
            stream_url = f"{scheme}://{host}/live/{platform}/{channel_id}"
            m3u_content += f'#EXTINF:-1 tvg-group="{group}" group-title="{group}", {display_name}\n'
            m3u_content += f'{stream_url}\n\n'
            
        return Response(m3u_content, mimetype='text/plain')
    except Exception as e:
        print(f"Error generando playlist: {e}")
        return "#EXTM3U\n", 500

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

@app.route('/live/youtube/<path:channel_id>')
def stream_youtube(channel_id):
    if channel_id.startswith("@"):
        target_url = f"https://www.youtube.com/{channel_id}/live"
    elif channel_id.startswith("v_"):
        target_url = f"https://www.youtube.com/watch?v={channel_id[2:]}"
    else:
        target_url = f"https://www.youtube.com/{channel_id}"

    # Intento 1: Streamlink
    try:
        streams = streamlink.streams(target_url)
        if "best" in streams:
            return redirect(streams["best"].url, code=302)
    except Exception as e:
        print(f"Error Streamlink YouTube ({channel_id}): {e}")

    # Intento 2: yt-dlp si está disponible
    if yt_dlp is not None:
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'socket_timeout': 5,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=False)
                if info and 'entries' in info and info['entries']:
                    info = info['entries'][0]
                if info:
                    if info.get('hls_url'):
                        return redirect(info.get('hls_url'), code=302)
                    formats = info.get('formats', [])
                    hls_formats = [f for f in formats if f.get('protocol') in ['m3u8', 'm3u8_native']]
                    if hls_formats:
                        return redirect(hls_formats[-1].get('url'), code=302)
                    if info.get('url'):
                        return redirect(info.get('url'), code=302)
        except Exception as e:
            print(f"Error yt-dlp YouTube ({channel_id}): {e}")

    return "Canal o directo de YouTube no disponible", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
