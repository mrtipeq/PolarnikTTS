# PolarnikTTS – Privacy Policy / Polityka prywatności

Last updated: 2026-10-28 · Author: MrTip (Tipson), https://tipson.pl

Published at https://tipson.pl/polarnik/privacy (the standalone page is `docs/privacy/index.html` - upload that folder as `polarnik/privacy/`).

## English

PolarnikTTS is a Chrome extension that reads YouTube subtitles aloud as a voice-over - in Polish or another language you choose. It works together
with the PolarnikTTS engine server, a program you install and run on your own computer (or on
another computer in your local network that you configure yourself).

**What the extension processes**

- The subtitle text and timing of the YouTube video you are watching, and the video id. This
  text is sent to your engine server for translation and speech synthesis.
- Your settings (server address, chosen engine and voice, volume, speed, language) stored locally in the
  browser (`chrome.storage.local`).

**What the extension does not do**

- It collects no personal data, no browsing history, no analytics and no telemetry.
- It sends nothing to the author or to any server other than the engine server you configured.
- It loads no remote code.

**Third-party services**

The engine server can use third-party services. Two of them work out of the box, without a key: **Microsoft Edge TTS** (the default voice) and **Google Translate** - the latter only when YouTube refuses its own auto-translation of the captions, or when you pick it as the translator. The others - OpenAI, Google Gemini, ElevenLabs, DeepL, Anthropic or a local Ollama model - are used only when you enable them yourself and enter your own API key. In every case the subtitle sentences go to that provider directly from your server, under its own privacy policy; the author of PolarnikTTS never sees them. Edge TTS and Google Translate can be turned off in the server's `config.yaml`. Uploaded voice samples stay on your computer in the server's `voices` folder.

**Contact**

https://tipson.pl · https://github.com/mrtipeq/PolarnikTTS/issues

## Polski

PolarnikTTS to rozszerzenie Chrome, które czyta napisy YouTube głosem lektora – po polsku lub w innym wybranym języku. Współpracuje z
serwerem PolarnikTTS – programem, który instalujesz i uruchamiasz na własnym komputerze (albo
na innym komputerze w swojej sieci lokalnej, który sam wskażesz).

**Co rozszerzenie przetwarza**

- Tekst i czas napisów oglądanego filmu oraz identyfikator filmu. Tekst trafia do Twojego
  serwera silników w celu tłumaczenia i syntezy mowy.
- Twoje ustawienia (adres serwera, silnik, głos, głośność, tempo, język), zapisane lokalnie w
  przeglądarce.

**Czego rozszerzenie nie robi**

- Nie zbiera danych osobowych, historii przeglądania, statystyk ani telemetrii.
- Nie wysyła niczego do autora ani na żaden serwer poza skonfigurowanym serwerem silników.
- Nie pobiera żadnego kodu z sieci.

**Usługi zewnętrzne**

Serwer silników może korzystać z usług zewnętrznych. Dwie z nich działają od razu, bez klucza: **Microsoft Edge TTS** (domyślny głos lektora) oraz **Google Translate** – ten drugi tylko wtedy, gdy YouTube odmówi własnego automatycznego tłumaczenia napisów albo gdy sam wybierzesz go jako tłumacza. Pozostałe – OpenAI, Google Gemini, ElevenLabs, DeepL, Anthropic albo lokalny model Ollama – działają wyłącznie wtedy, gdy sam je włączysz i wpiszesz własny klucz API. W każdym z tych przypadków zdania napisów trafiają do danego dostawcy prosto z Twojego serwera, na zasadach jego polityki prywatności; autor PolarnikTTS ich nie widzi. Edge TTS i Google Translate można wyłączyć w `config.yaml` serwera. Przesłane próbki głosu pozostają na Twoim komputerze w katalogu `voices` serwera.

**Kontakt**

https://tipson.pl · https://github.com/mrtipeq/PolarnikTTS/issues
