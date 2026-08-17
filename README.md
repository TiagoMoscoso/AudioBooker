# Audiobooker

Aplicativo desktop local, multiplataforma (Windows/Linux), para converter livros e documentos em audiobooks narrados com **Resemble AI Chatterbox**. Processamento 100% local — nenhum texto é enviado a serviços externos.

## Features

- Importação de PDF, MOBI/AZW/AZW3, DOCX, TXT e Markdown com extração e limpeza de texto.
- Detecção automática de capítulos (estrutura explícita → padrões textuais → heurística), com revisão manual: renomear, incluir/excluir, reordenar (arrastar) e unir capítulos.
- Narração em **Português** ou **English**, escolhidos explicitamente (sem detecção automática de idioma).
- Clonagem de voz opcional via amostra de áudio (mecanismo oficial `audio_prompt_path` do Chatterbox).
- Prévia de narração antes de gerar o livro inteiro.
- Presets de estilo (Natural, Calmo, Expressivo, Dramático) mapeados para os parâmetros reais do Chatterbox (`exaggeration`, `cfg_weight`), com seção "Avançado" para ajuste fino.
- Geração assíncrona (nunca trava a UI), com progresso real por capítulo/trecho, cancelamento seguro e **checkpoint/resume** — inclusive após reiniciar o aplicativo.
- Cache de trechos gerados por hash de conteúdo (texto + voz + modelo + idioma + parâmetros), evitando reprocessamento.
- Pós-processamento com normalização, prevenção de clipping e pausas naturais entre trechos/parágrafos/capítulos.
- Biblioteca pessoal em tela cheia (estilo pôster de filme/livro), com busca por título, capa e título personalizáveis e exclusão de audiobooks.
- Player integrado com capítulos, pular capítulo, controle de velocidade e volume, e retomada automática de onde a reprodução parou.
- Exportação sob demanda para ZIP (capítulos separados ou arquivo único), com `audiobook.json` de metadados. Escrita atômica (`.partial.zip` → `.zip`) — o ZIP só é criado quando o usuário clica em "Exportar" e escolhe a pasta de destino.
- Detecção automática de hardware (CUDA → CPU), nunca assume GPU.
- Interface minimalista (PySide6/Qt), paleta marfim/carvão, tipografia serif + sans-serif.

## Supported formats

`.pdf` `.mobi` / `.azw` / `.azw3` `.docx` `.txt` `.md` / `.markdown`

PDFs somente com imagem (sem camada de texto) são recusados com uma mensagem clara — OCR está fora do escopo desta versão.

## Supported languages

Portuguese · English

Apenas estes dois idiomas são oferecidos, sem variantes regionais (PT-BR/PT-PT, EN-US/EN-UK) e sem modo automático — o usuário escolhe explicitamente antes de gerar.

## Development setup

Requisitos: Python 3.11, GPU NVIDIA opcional (CUDA), `ffmpeg` (opcional — usado se já estiver no PATH; senão o app usa o binário empacotado via `imageio-ffmpeg`).

```bash
# Linux
./scripts/setup_linux.sh

# Windows (PowerShell)
scripts\setup_windows.ps1
```

Isso cria `.venv` com Python 3.11 e instala as dependências via `pyproject.toml` (`pip install -e .`).

## Chatterbox

- Referência: <https://huggingface.co/ResembleAI/chatterbox> / <https://github.com/resemble-ai/chatterbox>
- Pacote: `chatterbox-tts` (pinado em `pyproject.toml`).
- **Inglês**: `chatterbox.tts.ChatterboxTTS.from_pretrained(device=...)`.
- **Português**: `chatterbox.mtl_tts.ChatterboxMultilingualTTS.from_pretrained(device=...)` com `generate(..., language_id="pt")` — o mecanismo multilíngue oficial do Chatterbox. O projeto também publica finetunes dedicados por idioma no Hugging Face (incluindo `pt-br` e `pt-pt`), mas, até o momento desta implementação, eles só são demonstrados via Spaces do Gradio separados, sem um caminho documentado de `from_pretrained(...)` no pacote principal. Por isso o MVP usa o modelo multilíngue geral para português; isso é uma decisão documentada (ver `AUDIOBOOKER_SPECS.md` §53), não uma limitação técnica de arquitetura — trocar para o checkpoint dedicado depois é uma mudança isolada em `infrastructure/tts/model_manager.py`.
- Modelo carregado uma única vez por idioma e reaproveitado entre trechos (nunca recarregado por chunk). Como uma sessão de geração usa só um idioma por vez, o `ChatterboxModelManager` descarrega o modelo anterior antes de carregar outro — em GPUs com pouca VRAM (testado em uma RTX 4050 Laptop de 6 GB), manter dois modelos carregados simultaneamente causa `CUDA out of memory`.
- Voice cloning usa exclusivamente `audio_prompt_path` (mecanismo oficial), sem pipeline paralelo.
- Parâmetros `exaggeration`/`cfg_weight` são os documentados oficialmente; não há parâmetros inventados.

### Divergência de API encontrada (documentada, per §53)

O README do repositório GitHub do Chatterbox descreve `ChatterboxMultilingualTTS.from_pretrained(device=..., t3_model="v3")`, mas a versão publicada no PyPI (`chatterbox-tts==0.1.7`, a pinada neste projeto) **não aceita** esse parâmetro — `inspect.signature()` no pacote instalado mostra apenas `from_pretrained(device)`. O código usa a assinatura real instalada, não a do README (que aparentemente descreve uma versão ainda não publicada).

Também foi necessário fixar `setuptools<81` (ver `pyproject.toml`): a dependência `resemble-perth` (usada pelo Chatterbox para watermarking de áudio) ainda importa a API legada `pkg_resources` em tempo de execução; `setuptools>=81` removeu esse módulo, o que quebra silenciosamente o carregamento do watermarker (`perth.PerthImplicitWatermarker` vira `None`, e o Chatterbox falha com `TypeError: 'NoneType' object is not callable` ao instanciar o modelo). Verificado localmente contra o `chatterbox-tts==0.1.7` instalado.

### Empacotamento: metadata ausente no build PyInstaller

Um build gerado sem os flags `--copy-metadata` corretos falha ao **usar** o app (não ao abrir — o erro só aparece quando o Chatterbox é carregado pela primeira vez, porque `diffusers` só é importado nesse momento) com:

```text
No package metadata was found for The 'requests' distribution
was not found and is required by this application.
Try: pip install transformers -U or pip install -e '.[dev]' if you're
working with git main
```

Causa: `diffusers` e `transformers` (dependências do `chatterbox-tts`) checam a versão de várias dependências suas via `importlib.metadata.version(...)` assim que são importados (`diffusers/dependency_versions_check.py` checa `requests`, `filelock`, `numpy`; `transformers/dependency_versions_check.py` checa mais alguns). `--collect-all` do PyInstaller empacota código/dados/binários, mas **não** a pasta `.dist-info` de metadados de cada pacote — isso exige o flag separado `--copy-metadata`. `scripts/build_linux.sh` e `scripts/build_windows.ps1` já incluem esse flag para toda a lista de pacotes checados (`requests`, `filelock`, `numpy`, `tqdm`, `regex`, `packaging`, `tokenizers`, `huggingface-hub`, `safetensors`, `pyyaml`, além de `chatterbox-tts`, `transformers`, `diffusers`, `torch` e as demais dependências do Chatterbox). Corrigido e verificado com um build real: o executável gerado agora inicia e a pasta `_internal/` contém o `.dist-info` de todos esses pacotes.

## GPU support

Detecção automática: CUDA se disponível, senão CPU (nunca assume GPU). O modo CPU funciona, porém mais lento — a UI indica o dispositivo ativo em Configurações → Hardware.

Testado neste ambiente com uma NVIDIA GeForce RTX 4050 Laptop GPU (6 GB VRAM): geração de um trecho curto em ~3-13s (incluindo troca de idioma/modelo).

## Running from source

```bash
source .venv/bin/activate      # ou .venv\Scripts\Activate.ps1 no Windows
python src/main.py
```

## Windows build

```powershell
scripts\build_windows.ps1
```

Gera `dist\Audiobooker\Audiobooker.exe` (modo `--onedir`; ver justificativa abaixo). O script converte `logo.png` para `audiobooker.ico` automaticamente.

## Linux build

```bash
./scripts/build_linux.sh
```

Gera `dist/Audiobooker/Audiobooker` (`--onedir`) e instala automaticamente um launcher `.desktop` com ícone (`scripts/install_linux.sh`) em `~/.local/share/applications` e `~/.local/share/icons/hicolor/512x512/apps` — necessário porque, diferente do Windows, o binário Linux não carrega um ícone embutido; o ícone do menu/taskbar vem exclusivamente do `.desktop`. Rode `./scripts/install_linux.sh` isoladamente para reinstalar o launcher sem rebuildar.

**Por que `--onedir` e não `--onefile`**: PyTorch + CUDA + PySide6/Qt + Chatterbox formam uma árvore de dependências nativas grande (bibliotecas `.so`/`.dll` de CUDA, plugins Qt, checkpoints de modelo). O modelo de auto-extração para diretório temporário do `--onefile` é frágil nessa escala (primeira inicialização lenta, e descoberta de plugins Qt/CUDA pode falhar ao rodar de um caminho temporário). `--onedir` é a opção mais estável, conforme permitido pela especificação.

## Architecture

```text
src/
├── main.py                    # composition root
├── domain/                    # modelos puros (document, chapter, narration, generation)
├── application/                # casos de uso (import, analyze, preview, generate, resume)
├── infrastructure/
│   ├── parsers/                # DocumentParser + implementações por formato
│   ├── tts/                    # SpeechSynthesizer, ChatterboxModelManager, hardware
│   ├── audio/                  # AudioPostProcessor (concat, normalize, encode)
│   ├── persistence/             # checkpoint/settings/recents stores, chunk cache
│   └── packaging/              # ZipPackager
├── services/                    # TextPreprocessor, ChapterDetector, NarrationChunker, FilenameSanitizer
└── presentation/
    ├── windows/                 # MainWindow
    ├── widgets/                 # HomeScreen, BookScreen, GenerationScreen, SettingsScreen, ...
    ├── workers/                  # QThread workers (import/preview/generation)
    └── styles/                   # tema visual (QSS)
```

Fluxo: `UI → Application Service → SpeechSynthesizer → Chatterbox`. A UI nunca chama o Chatterbox diretamente nem contém regra de negócio; toda operação potencialmente bloqueante roda em `QThread` e reporta progresso só por sinais Qt.

### Checkpoint/resume

```text
sessions/
  session_xxx/
    manifest.json     # progresso, chunks, configurações de saída
    chapters.json      # capítulos exatamente como revisados pelo usuário
    chunks/
      <chapter_id>/
        0000.wav
        0001.wav
    finalized/output/  # áudio final por capítulo/arquivo único
```

`chapters.json` existe porque os IDs de capítulo são gerados na importação; sem persistir os capítulos revisados (incluindo renomeações/uniões/exclusões manuais), retomar uma geração após reiniciar o aplicativo não teria como recuperar o texto exato usado para gerar cada chunk. `manifest.json` também guarda a configuração de narração usada (idioma, estilo, voz, `exaggeration`/`cfg_weight`) para retomar com os parâmetros exatos.

## Troubleshooting

- **"Este PDF parece conter apenas imagens"**: o PDF não tem camada de texto extraível (provavelmente escaneado). OCR está fora do escopo desta versão.
- **`CUDA out of memory` ao trocar de idioma**: o `ChatterboxModelManager` já descarrega o modelo anterior antes de carregar outro; se ainda ocorrer, feche outros processos que usem a GPU ou use CPU.
- **Download do modelo lento na primeira geração**: os pesos (múltiplos GB) são baixados do Hugging Face Hub na primeira vez que um idioma é usado; usos seguintes reaproveitam o cache local do `huggingface_hub`.
- **Erros de geração**: a tela de erro nunca mostra um traceback como mensagem principal; use "Ver detalhes" para informações técnicas, e consulte `logs/audiobooker.log` (com rotação).

## Known limitations

- Sem OCR para PDFs escaneados (fora do escopo do MVP, conforme especificação).
- Divisão manual de capítulos ("split") não foi implementada nesta versão — apenas unir, renomear, incluir/excluir e reordenar, para não transformar o app em um editor de texto completo (a especificação permite isso como "quando viável").
- Português usa o modelo multilíngue geral do Chatterbox, não os finetunes dedicados `pt-br`/`pt-pt` (ver seção Chatterbox acima).
- "Limpar cache" em Configurações limpa apenas o cache de trechos gerados por este app (`platformdirs` cache dir), não o cache de pesos de modelo do Hugging Face Hub (`~/.cache/huggingface`), para não forçar um novo download de vários GB inadvertidamente.
- Sem testes automatizados nesta versão, por decisão explícita da especificação — validação feita via smoke tests manuais (abaixo) e scripts de verificação ad-hoc durante o desenvolvimento.
- Botão "Abrir pasta" em Configurações/geração usa `xdg-open`/`explorer`/`open` via `subprocess`; não testado no Windows/macOS neste ambiente (apenas Linux).
- `scripts/build_windows.ps1` não pôde ser executado neste ambiente Linux (script escrito e alinhado ao `build_linux.sh` que foi testado, incluindo os mesmos flags `--copy-metadata`, mas não rodado de fato). `scripts/build_linux.sh` **foi** executado de verdade: gerou `dist/Audiobooker/` (~6 GB, esperado dado PyTorch+CUDA+Qt) e o executável inicia corretamente em modo offscreen.

## Smoke tests realizados durante o desenvolvimento

- Importação real de TXT, Markdown, DOCX e PDF (PDF sintético com cabeçalho/rodapé repetido, numeração de página e hifenização — todos corretamente removidos/corrigidos).
- Detecção de capítulos nos três níveis de prioridade (estrutura explícita, padrão textual, heurística).
- Chunking com abreviações (`Dr.`, `Sra.`) sem quebra indevida.
- Pipeline completo de geração (chunking → síntese real via Chatterbox em PT e EN → concatenação → normalização → encoding MP3/FLAC → cópia para a biblioteca permanente) rodando através da UI real (`MainWindow`), incluindo troca de idioma sem vazamento de VRAM.
- Cancelamento a meio da geração e retomada — inclusive simulando um reinício completo do processo (novas instâncias de `CheckpointStore`/`ChunkCache`, sem estado em memória) — preservando capítulos editados manualmente e as configurações exatas de narração.
- Cache de chunks: uma segunda geração idêntica não chama o sintetizador (reaproveita os `.wav` em cache).
- Telas de Configurações (aparência, tamanho de cache, limpar cache) através da `MainWindow` real.
- MOBI não foi testado por falta de um arquivo de exemplo disponível neste ambiente (a especificação permite isso — "MOBI, caso haja arquivo disponível").
- Biblioteca/player (redesenho): `LibraryStore` (round-trip JSON, renomear, trocar capa, salvar posição de reprodução, excluir com remoção do diretório em disco), grade de capas na `HomeScreen` (renderização de `BookCard` com título customizado, filtro de busca ao vivo), `PlayerScreen.load_book` (lista de capítulos, capa custom, retomada de posição) e `ExportBookService` (ZIP sob demanda nos dois modos — capítulos separados e arquivo único, este último decodificando/recodificando via ffmpeg) — todos validados via scripts ad-hoc com `QApplication` real em modo offscreen, incluindo instanciação completa da `MainWindow` com o novo parâmetro `library_dir`.
