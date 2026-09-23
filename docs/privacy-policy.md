# PolarnikTTS – Privacy Policy / Polityka prywatności

Last updated: 2026-09-23 · Author: MrTip (Tipson), https://tipson.pl

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

The engine server can use third-party providers, but only those you enable yourself and only
with API keys you enter yourself: Microsoft Edge TTS, OpenAI, Google Gemini, ElevenLabs, DeepL,
Anthropic, or a local Ollama model. When enabled, subtitle sentences are sent to that provider
under its own privacy policy. Uploaded voice samples stay on your computer in the server's
`voices` folder.

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

Serwer silników może korzystać z usług zewnętrznych, ale wyłącznie tych, które sam włączysz i
z kluczami, które sam wpiszesz: Microsoft Edge TTS, OpenAI, Google Gemini, ElevenLabs, DeepL,
Anthropic albo lokalny model Ollama. Wtedy zdania napisów trafiają do tego dostawcy na zasadach
jego polityki prywatności. Przesłane próbki głosu pozostają na Twoim komputerze w katalogu
`voices` serwera.

**Kontakt**

https://tipson.pl · https://github.com/mrtipeq/PolarnikTTS/issues
