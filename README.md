# Audiobooker

Narração local de frases e audiobooks inteiros, no Windows, com vozes de IA que rodam no seu computador (nada vai para a nuvem).
Importa EPUB, PDF, DOCX, MOBI, Markdown e TXT; gera M4B com capítulos, ou MP3/FLAC/WAV por capítulo.

*Local text-to-speech for Windows: short phrases or full audiobooks (EPUB/PDF/DOCX/MOBI/MD/TXT to M4B with chapters), voice cloning,
per-passage intonation, characters, pronunciation dictionary. Everything runs on your machine. The interface is in Brazilian Portuguese.*

## Requisitos

- Windows 10 ou 11 (64 bits); testado no Windows 11. Não testado em Linux nem macOS.
- [`uv`](https://docs.astral.sh/uv/) (`winget install astral-sh.uv`): ele baixa o Python 3.11 sozinho.
- Cerca de 8 GB livres (Python, PyTorch e o modelo do Chatterbox, ~3 GB, baixado na primeira geração).
- Placa NVIDIA com CUDA é fortemente recomendada para o Chatterbox. Sem ela tudo roda na CPU, mas muito mais devagar.

## Instalação e uso

```powershell
git clone <endereço do repositório>
cd Audiobooker
fonte\instalar-audiobooker.ps1          # ou duplo clique em fonte\instalar.cmd
fonte\abrir-audiobooker.ps1             # abre o programa
```

O instalador é idempotente (pode rodar de novo para consertar) e detecta a placa de vídeo sozinho.

| Opção do instalador | O que faz |
|---|---|
| `-Simular` | só mostra o que faria |
| `-SemChatterbox` | não instala o Chatterbox (então só funcionam os motores opcionais) |
| `-ComKokoro` | instala também o Kokoro: leve e rápido, vozes prontas em inglês e português |
| `-ComPiper` | instala também o Piper: vozes pequenas que rodam na CPU |

## Motores de voz

| Motor | Para que serve | Roda em |
|---|---|---|
| **Chatterbox** (padrão) | clonagem de voz a partir de um áudio de referência, emoção e CFG; variante multilíngue (23 idiomas, incluindo português) | CUDA ou CPU |
| **Kokoro** (opcional) | vozes prontas, mistura de vozes, pronúncia por IPA | CPU, DirectML ou CUDA |
| **Piper** (opcional) | vozes externas pequenas | CPU |
| Motores de terceiros | qualquer serviço compatível com a API de fala da OpenAI, ou o seu próprio | veja `fonte\motores_extras_exemplo\` |

Cada motor declara o que sabe fazer (emoção, tags, clonagem, fonemas, instrução, palavra por palavra). O que o motor escolhido
**não** executa é ignorado e listado na tela; o programa nunca imita um efeito que o motor não faz. Trocar de motor ou de placa liga
os controles que antes ficavam sem efeito.

Velocidade de referência do Chatterbox original numa GPU NVIDIA de entrada (4 GB): cerca de 2,5 h de geração por hora de áudio.
Na CPU é bem mais lento; o Kokoro na CPU gera várias vezes mais rápido que o tempo real.

## O que o programa faz

- **Frases:** gera uma frase com qualquer voz, com intonação geral, por trecho ou por palavra, e exporta.
- **Livros:** importa o texto, separa capítulos (editáveis), detecta falas e personagens, deixa revisar o roteiro (`@Papel: fala`) e gera com
  retomada: se parar, continua do capítulo e do trecho onde parou. Trechos já gerados ficam em cache.
- **Intonação:** marcação no texto (`[estilo triste]…[/estilo]`, `[emoção 0.8]`, `[velocidade 0.9]`, `[tom -2]`, `[volume -6]`,
  `[pausa 1s]`) e sugestão automática pelo contexto ("she whispered"). Velocidade, tom e volume são pós-processamento real.
- **Vozes:** clonagem a partir de amostra, vozes salvas, misturas (Kokoro) e presets de efeito (robô clássico, exterminador, IA de nave,
  rádio militar, telefone antigo) sobre qualquer voz.
- **Dicionário de pronúncias:** global e por livro; respelling, IPA, expressões regulares, importação e exportação de léxicos PLS.
- **Qualidade:** masterização por loudness (perfil audiobook ou ACX), relatório por capítulo, M4B com capítulos e capa.

## Onde ficam os dados

| O quê | Onde | Muda com |
|---|---|---|
| Vozes salvas e dicionários | pastas `vozes\` e `dicionarios\` ao lado de `fonte\` (ignoradas pelo git) | `AUDIOBOOKER_DADOS` |
| Ambiente Python, modelos, projetos, cache, biblioteca, configuração | `%LOCALAPPDATA%\AUDIOBOOKER` | `AUDIOBOOKER_LOCAL` |

## Linha de comando

Use o Python do ambiente criado pelo instalador (`%LOCALAPPDATA%\AUDIOBOOKER\venv\Scripts\python.exe`):

```powershell
$env:PYTHONPATH = "fonte"
python -m audiobooker dispositivos                       # o que foi detectado (CPU/GPU)
python -m audiobooker frase "Texto curto" --voz chatterbox-padrao --saida frase.wav
python -m audiobooker livro livro.epub --listar          # capítulos detectados
python -m audiobooker livro livro.epub --capitulos 4-7 --formato m4b
python -m audiobooker autoteste                          # verificações internas
```

## Licenças

Apache-2.0 (veja `LICENSE` e `NOTICE`). Derivado de [TiagoMoscoso/AudioBooker](https://github.com/TiagoMoscoso/AudioBooker).
Os modelos e pacotes de terceiros (Chatterbox, Kokoro, Piper e suas vozes) são baixados pelo instalador e seguem as licenças
próprias, listadas em `NOTICE`. O Piper é GPL-3.0 e é opcional: instale só se a licença servir para o seu uso.
