# Publishing PolarnikTTS to the Chrome Web Store

## What the store needs

1. A developer account (one-time registration fee) at https://chrome.google.com/webstore/devconsole.
2. A zip of the extension folder. Build it with `pack_extension.cmd <path to key.pem>`:
   - `dist/PolarnikTTS-<version>-store-with-key.zip` - use for the **first** upload. It contains
     `key.pem`, so the store assigns the same id the unpacked extension already has
     (`gocceeipamkkjphdecegbhbghhogeidb`). The native messaging host registered by
     `install_host.cmd` only trusts that id, so keeping it is what makes "Uruchom serwer"
     work for store installs too.
   - `dist/PolarnikTTS-<version>-store.zip` - for every later update (no key inside).
   - The store rejects a manifest that still contains the `key` field; the script strips it.
3. Store listing: name, summary (132 chars), description, category (Accessibility or
   Productivity), language (Polish), at least one 1280x800 screenshot, a 128x128 icon
   (already in `extension/icons/icon128.png`), optionally a 440x280 promo tile.
4. Privacy: a privacy policy URL (host `docs/privacy-policy.md` on tipson.pl, e.g.
   `https://tipson.pl/polarnik/privacy`) and the "single purpose" statement plus a
   justification for each permission (below). Declare that the extension does not sell or
   transfer user data.
5. Review takes from hours to a few days. Extensions using `nativeMessaging` and
   `webRequest` are reviewed by a human more often; the justifications matter.

## Single purpose

Polish voice-over for YouTube subtitles: the extension reads the current video's captions,
translates them into Polish and plays synthesized speech in sync with the video.

## Permission justifications (paste into the developer console)

- `storage` - stores the user's settings (server address, engine, voice, volume, speed).
- `webRequest` (observing only, no blocking) - detects the caption track request YouTube's
  own player makes (`/api/timedtext`), so the extension knows which subtitles are available.
  No request is modified or blocked.
- `nativeMessaging` - lets the extension start the user's own local PolarnikTTS engine server
  (a program the user installs separately) when it is not running. Optional; without the host
  registered the button simply reports that the launcher is missing.
- Host permission `https://www.youtube.com/*` - the extension only works on YouTube watch pages
  (player-bar button, caption capture, playback synchronisation).
- Host permissions `http://127.0.0.1/*`, `http://localhost/*` - communication with the local
  engine server that synthesizes the speech.
- Optional host permissions `http://*/*`, `https://*/*` - requested at runtime only if the
  user points the extension at an engine server on another machine in their LAN.

## Remote code

None. All extension code is inside the package; nothing is loaded from the network.

## Data usage disclosure

- Subtitle text of the video being watched is sent to the user's own engine server
  (localhost or a server the user configured) for translation and speech synthesis. The server
  forwards it to third-party TTS/translation providers only when the user enables and
  configures them (OpenAI, Google, ElevenLabs, DeepL, Anthropic, Microsoft Edge TTS).
- No analytics, no telemetry, no accounts, no personal data collected by the author.

## Store listing text (Polish)

**Nazwa:** PolarnikTTS – polski lektor do YouTube

**Krótki opis (do 132 znaków):**
Polski lektor do YouTube: tłumaczy napisy i czyta je wybranym głosem – lokalnie (GPU) lub w chmurze, z klonowaniem głosu.

**Opis:**
PolarnikTTS zamienia napisy każdego filmu na YouTube w polskiego lektora – tak jak w telewizji:
oryginalna ścieżka jest ściszona, a na niej słychać polski głos, zsynchronizowany z napisami.

Co wyróżnia PolarnikTTS:
- pracuje z wyprzedzeniem: składa napisy w zdania, tłumaczy je z kontekstem i syntezuje mowę
  zanim padnie w filmie, więc lektor nie „goni” obrazu;
- wybór silnika mowy: Microsoft Edge (Zofia, Marek), OpenAI, Google Gemini, ElevenLabs – albo
  całkowicie lokalnie na własnej karcie graficznej (Chatterbox, XTTS-v2) z klonowaniem głosu
  z 10-sekundowej próbki;
- tłumaczenie przez YouTube albo przez model językowy (OpenAI, Gemini, Claude, DeepL, lokalny
  Bielik), który przywraca interpunkcję i naturalny szyk zdania;
- panel w odtwarzaczu w stylu YouTube: włącznik, silnik, głos, tempo, głośność lektora,
  ściszenie oryginału, przesunięcie, tryb „zwolnij film, gdy lektor nie nadąża”;
- wszystko zapisuje się automatycznie, a ustawienia można wyeksportować na inny komputer.

Wymaga zainstalowania darmowego serwera PolarnikTTS (Windows/Linux/macOS, Python) – instrukcja
i kod źródłowy: https://github.com/mrtipeq/PolarnikTTS. Autor: MrTip (Tipson) – https://tipson.pl.
Bez reklam, bez telemetrii, licencja MIT.

## Screenshots and promo tile

Ready to upload, in `docs/store/` (1280x800 PNG, Polish captions, in listing order):

| File | Shows |
|---|---|
| `01_player.png` | In-player panel and the toolbar popup |
| `02_engines_local.png` | "Silniki i głosy": Edge, Piper, Chatterbox, XTTS with the voice tester |
| `03_engines_cloud.png` | OpenAI / Gemini / ElevenLabs voices and the LLM translators with shared API keys |
| `04_server_voice.png` | Engine server section (start/stop from the extension) and voice selection |
| `05_playback_transfer.png` | Playback settings, export/import and the "O programie" section |
| `promo_440x280.png` | Small promo tile |

The raw UI captures live in `docs/screenshots/` (also embedded in `README.md`). After a UI
change, replace the raw capture and regenerate the store images:

```
pip install pillow
python scripts/make_store_screenshots.py
```

The script places each capture on a dark gradient with a caption, splits the tall options-page
captures into two columns so the text stays readable, and builds the promo tile from
`extension/icons/icon128.png`. The store also accepts 640x400; 1280x800 is preferred.
