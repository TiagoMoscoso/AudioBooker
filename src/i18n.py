"""Translation catalog for the UI language setting (English/Portuguese,
English default). Deliberately has zero imports from domain/application/
infrastructure/presentation, so every layer can call `tr(...)` — including
where the app raises its own user-facing error messages — without inverting
the project's layering. Current language is process-wide state (like Python's
own `gettext`/`logging` modules), set once at startup from `AppSettings` and
again whenever the user changes it in Settings; screens re-render their own
text by calling `tr(...)` again in a `retranslate()` method — there is no
automatic widget-level propagation, by design (§ no globals/no DI framework
convention — this is the one deliberate, minimal exception, matching how
logging already uses global state)."""
from __future__ import annotations

DEFAULT_LANGUAGE = "en"

_current_language = DEFAULT_LANGUAGE

_CATALOG: dict[str, dict[str, str]] = {
    "en": {
        # -- home / library -------------------------------------------------
        "home.file_filter": "Documents (*.pdf *.mobi *.azw *.azw3 *.docx *.txt *.md *.markdown)",
        "home.image_filter": "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        "home.drop_hint": "Drag a book here",
        "home.drop_hint_active": "Drop to import",
        "home.drop_hint_invalid": "Unsupported format",
        "home.choose_file": "Choose file",
        "home.menu_rename": "Rename",
        "home.menu_change_cover": "Change cover",
        "home.menu_delete": "Delete",
        "home.dialog_choose_cover_title": "Select cover",
        "home.empty_library": "Your library is empty — import a book to get started.",
        "home.search_placeholder": "Search by title...",
        # -- book review ------------------------------------------------------
        "book.audio_filter": "Audio (*.wav *.mp3 *.flac *.m4a *.ogg)",
        "book.chapters": "CHAPTERS",
        "book.select_all": "Select all",
        "book.narration": "NARRATION",
        "book.language": "Language",
        "book.voice_default": "Default voice",
        "book.choose_sample": "Choose sample",
        "book.remove": "Remove",
        "book.narrator_voice": "Narrator voice",
        "book.style": "Style",
        "book.advanced": "Advanced",
        "book.exaggeration": "Expressiveness (exaggeration)",
        "book.cfg_weight": "Fidelity (cfg_weight)",
        "book.generate_preview": "▶ Generate preview",
        "book.generating_preview": "Generating preview...",
        "book.generate_audiobook": "Generate audiobook",
        "book.dialog_choose_voice_title": "Select voice sample",
        "book.estimate": "{words} words · {chapters} chapters · ~{hours}h {minutes}min estimated audio",
        # -- chapter list -----------------------------------------------------
        "chapters.menu_rename": "Rename",
        "chapters.menu_exclude": "Exclude from generation",
        "chapters.menu_include": "Include in generation",
        "chapters.menu_merge_next": "Merge with next",
        "chapters.rename_dialog_title": "Rename chapter",
        "chapters.rename_dialog_label": "New title:",
        "chapters.single_chapter_title": "Single chapter",
        "document.untitled": "Untitled document",
        # -- generation progress ----------------------------------------------
        "generation.title": "Generating audiobook",
        "generation.chapter_progress": "Chapter {index} of {count}",
        "generation.chunk_progress": "Chunk {index} of {count}",
        "generation.elapsed": "Elapsed time: {time}",
        "generation.cancel": "Cancel",
        "generation_state.preparing_text": "Preparing text",
        "generation_state.generating_audio": "Generating audio",
        "generation_state.processing_chapter": "Processing chapter",
        "generation_state.finalizing": "Finalizing",
        "generation_state.compacting": "Compacting",
        "generation_state.completed": "Completed",
        "generation_state.cancelled": "Cancelled",
        "generation_state.failed": "Failed",
        # -- narration style / language names ----------------------------------
        "narration_style.natural": "Natural",
        "narration_style.calmo": "Calm",
        "narration_style.expressivo": "Expressive",
        "narration_style.dramatico": "Dramatic",
        "narration_language.pt": "Portuguese",
        "narration_language.en": "English",
        # -- player -------------------------------------------------------------
        "player.export_section": "EXPORT",
        "player.mode_separate": "Separate by chapters",
        "player.mode_single": "Single file",
        "player.export": "Export",
        "player.exporting": "Exporting...",
        "player.speed": "Speed",
        "player.volume": "Volume",
        "player.dialog_choose_folder_title": "Select destination folder",
        # -- preparing screen / model status ------------------------------------
        "preparing.title": "Preparing narration engine",
        "preparing.checking_model": "Checking model...",
        "model.downloading": "Preparing narration engine. Downloading model...",
        "model.loading": "Loading model...",
        "model.ready": "Ready",
        "model_state.not_loaded": "Not loaded",
        "model_state.downloading": "Downloading model...",
        "model_state.failed": "Failed: {detail}",
        # -- settings -------------------------------------------------------------
        "settings.title": "Settings",
        "settings.appearance": "Appearance",
        "settings.system": "System",
        "settings.light": "Light",
        "settings.dark": "Dark",
        "settings.ui_language": "Interface language",
        "settings.storage": "Storage",
        "settings.cache_calculating": "Cache: calculating...",
        "settings.cache_size": "Cache: {size}",
        "settings.open_folder": "Open folder",
        "settings.clear_cache": "Clear cache",
        "settings.hardware": "Hardware",
        "settings.detecting": "Detecting...",
        "settings.model": "Model",
        "settings.confirm_clear_cache_title": "Clear cache",
        "settings.confirm_clear_cache_text": "This will remove the audio chunks already generated and stored in cache. Continue?",
        # -- main window / dialogs ------------------------------------------------
        "main.model_prepare_failed_title": "Unable to prepare the narration engine",
        "main.model_prepare_failed_text": (
            "Unable to download or load the narration model right now.\n\n"
            "You can still import and review books; narration will be "
            "prepared again when you generate a preview or the audiobook."
        ),
        "main.retry": "Try again",
        "main.continue_without_prep": "Continue without preparing",
        "main.incomplete_generation_title": "Incomplete generation",
        "main.incomplete_generation_text": "We found an incomplete generation.\n\n{title}\n{percent}% complete",
        "main.continue_btn": "Continue",
        "main.discard_btn": "Discard",
        "main.cannot_resume_title": "Unable to continue",
        "main.cannot_resume_text": "This generation's data is incomplete and cannot be resumed.",
        "main.scanned_pdf_title": "PDF without text",
        "main.import_failed_title": "Unable to import",
        "main.import_failed_text": "Unable to import this document.\n\n{message}",
        "main.preview_failed_title": "Unable to generate this excerpt",
        "main.preview_failed_text": "Try again or check the technical details.\n\n{message}",
        "main.no_chapters_title": "No chapter selected",
        "main.no_chapters_text": "Include at least one chapter to generate the audiobook.",
        "main.try_again_details": "Try again or check the technical details.",
        "main.export_failed_title": "Unable to export",
        "main.delete_book_title": "Delete audiobook",
        "main.delete_book_text": 'Delete "{title}" from the library?\n\nThe generated audio will be permanently deleted.',
        "main.delete_confirm": "Delete",
        "main.cancel": "Cancel",
        "main.export_succeeded_title": "Export completed",
        "main.export_succeeded_text": "Audiobook exported successfully.\n\n{filename}",
        "main.open_folder": "Open destination folder",
        "main.done": "Done",
        # -- app-authored error messages ------------------------------------------
        "error.unsupported_format": "Unsupported format: {suffix}",
        "error.scanned_pdf": "This PDF appears to contain only images.\nOCR is not yet available for this document.",
        "error.sample_rate_mismatch": "Inconsistent sample rate in {path}: expected {expected}, got {actual}",
        "error.audio_encode_failed": "Failed to encode audio: {detail}",
        "error.audio_decode_failed": "Failed to decode audio: {detail}",
        "error.pauses_length_mismatch": "Pause list length mismatch: expected {expected}, got {actual}",
    },
    "pt": {
        # -- home / library -------------------------------------------------
        "home.file_filter": "Documentos (*.pdf *.mobi *.azw *.azw3 *.docx *.txt *.md *.markdown)",
        "home.image_filter": "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)",
        "home.drop_hint": "Arraste um livro aqui",
        "home.drop_hint_active": "Solte para importar",
        "home.drop_hint_invalid": "Formato não suportado",
        "home.choose_file": "Escolher arquivo",
        "home.menu_rename": "Renomear",
        "home.menu_change_cover": "Alterar capa",
        "home.menu_delete": "Excluir",
        "home.dialog_choose_cover_title": "Selecionar capa",
        "home.empty_library": "Sua biblioteca está vazia — importe um livro para começar.",
        "home.search_placeholder": "Buscar por título...",
        # -- book review ------------------------------------------------------
        "book.audio_filter": "Áudio (*.wav *.mp3 *.flac *.m4a *.ogg)",
        "book.chapters": "CAPÍTULOS",
        "book.select_all": "Selecionar todos",
        "book.narration": "NARRAÇÃO",
        "book.language": "Idioma",
        "book.voice_default": "Voz padrão",
        "book.choose_sample": "Selecionar amostra",
        "book.remove": "Remover",
        "book.narrator_voice": "Voz do narrador",
        "book.style": "Estilo",
        "book.advanced": "Avançado",
        "book.exaggeration": "Expressividade (exaggeration)",
        "book.cfg_weight": "Fidelidade (cfg_weight)",
        "book.generate_preview": "▶ Gerar prévia",
        "book.generating_preview": "Gerando prévia...",
        "book.generate_audiobook": "Gerar audiobook",
        "book.dialog_choose_voice_title": "Selecionar amostra de voz",
        "book.estimate": "{words} palavras · {chapters} capítulos · ~{hours}h {minutes}min de áudio estimado",
        # -- chapter list -----------------------------------------------------
        "chapters.menu_rename": "Renomear",
        "chapters.menu_exclude": "Excluir da geração",
        "chapters.menu_include": "Incluir na geração",
        "chapters.menu_merge_next": "Unir com o próximo",
        "chapters.rename_dialog_title": "Renomear capítulo",
        "chapters.rename_dialog_label": "Novo título:",
        "chapters.single_chapter_title": "Capítulo único",
        "document.untitled": "Documento sem título",
        # -- generation progress ----------------------------------------------
        "generation.title": "Gerando audiobook",
        "generation.chapter_progress": "Capítulo {index} de {count}",
        "generation.chunk_progress": "Trecho {index} de {count}",
        "generation.elapsed": "Tempo decorrido: {time}",
        "generation.cancel": "Cancelar",
        "generation_state.preparing_text": "Preparando texto",
        "generation_state.generating_audio": "Gerando áudio",
        "generation_state.processing_chapter": "Processando capítulo",
        "generation_state.finalizing": "Finalizando",
        "generation_state.compacting": "Compactando",
        "generation_state.completed": "Concluído",
        "generation_state.cancelled": "Cancelado",
        "generation_state.failed": "Falhou",
        # -- narration style / language names ----------------------------------
        "narration_style.natural": "Natural",
        "narration_style.calmo": "Calmo",
        "narration_style.expressivo": "Expressivo",
        "narration_style.dramatico": "Dramático",
        "narration_language.pt": "Português",
        "narration_language.en": "Inglês",
        # -- player -------------------------------------------------------------
        "player.export_section": "EXPORTAR",
        "player.mode_separate": "Separar por capítulos",
        "player.mode_single": "Arquivo único",
        "player.export": "Exportar",
        "player.exporting": "Exportando...",
        "player.speed": "Velocidade",
        "player.volume": "Volume",
        "player.dialog_choose_folder_title": "Selecionar pasta de destino",
        # -- preparing screen / model status ------------------------------------
        "preparing.title": "Preparando mecanismo de narração",
        "preparing.checking_model": "Verificando modelo...",
        "model.downloading": "Preparando mecanismo de narração. Baixando modelo...",
        "model.loading": "Carregando modelo...",
        "model.ready": "Pronto",
        "model_state.not_loaded": "Não carregado",
        "model_state.downloading": "Baixando modelo...",
        "model_state.failed": "Falhou: {detail}",
        # -- settings -------------------------------------------------------------
        "settings.title": "Configurações",
        "settings.appearance": "Aparência",
        "settings.system": "Sistema",
        "settings.light": "Claro",
        "settings.dark": "Escuro",
        "settings.ui_language": "Idioma da interface",
        "settings.storage": "Armazenamento",
        "settings.cache_calculating": "Cache: calculando...",
        "settings.cache_size": "Cache: {size}",
        "settings.open_folder": "Abrir pasta",
        "settings.clear_cache": "Limpar cache",
        "settings.hardware": "Hardware",
        "settings.detecting": "Detectando...",
        "settings.model": "Modelo",
        "settings.confirm_clear_cache_title": "Limpar cache",
        "settings.confirm_clear_cache_text": "Isso removerá os trechos de áudio já gerados e armazenados em cache. Continuar?",
        # -- main window / dialogs ------------------------------------------------
        "main.model_prepare_failed_title": "Não foi possível preparar o mecanismo de narração",
        "main.model_prepare_failed_text": (
            "Não foi possível baixar ou carregar o modelo de narração agora.\n\n"
            "Você ainda pode importar e revisar livros; a narração será "
            "preparada novamente quando você gerar uma prévia ou o audiobook."
        ),
        "main.retry": "Tentar novamente",
        "main.continue_without_prep": "Continuar sem preparar",
        "main.incomplete_generation_title": "Geração incompleta",
        "main.incomplete_generation_text": "Encontramos uma geração incompleta.\n\n{title}\n{percent}% concluído",
        "main.continue_btn": "Continuar",
        "main.discard_btn": "Descartar",
        "main.cannot_resume_title": "Não foi possível continuar",
        "main.cannot_resume_text": "Os dados desta geração estão incompletos e não podem ser retomados.",
        "main.scanned_pdf_title": "PDF sem texto",
        "main.import_failed_title": "Não foi possível importar",
        "main.import_failed_text": "Não foi possível importar este documento.\n\n{message}",
        "main.preview_failed_title": "Não foi possível gerar este trecho",
        "main.preview_failed_text": "Tente novamente ou consulte os detalhes técnicos.\n\n{message}",
        "main.no_chapters_title": "Nenhum capítulo selecionado",
        "main.no_chapters_text": "Inclua ao menos um capítulo para gerar o audiobook.",
        "main.try_again_details": "Tente novamente ou consulte os detalhes técnicos.",
        "main.export_failed_title": "Não foi possível exportar",
        "main.delete_book_title": "Excluir audiobook",
        "main.delete_book_text": 'Excluir "{title}" da biblioteca?\n\nOs áudios gerados serão apagados permanentemente.',
        "main.delete_confirm": "Excluir",
        "main.cancel": "Cancelar",
        "main.export_succeeded_title": "Exportação concluída",
        "main.export_succeeded_text": "Audiobook exportado com sucesso.\n\n{filename}",
        "main.open_folder": "Abrir pasta de destino",
        "main.done": "Concluído",
        # -- app-authored error messages ------------------------------------------
        "error.unsupported_format": "Formato não suportado: {suffix}",
        "error.scanned_pdf": "Este PDF parece conter apenas imagens.\nOCR ainda não está disponível para este documento.",
        "error.sample_rate_mismatch": "Sample rate inconsistente em {path}: esperado {expected}, obtido {actual}",
        "error.audio_encode_failed": "Falha ao codificar áudio: {detail}",
        "error.audio_decode_failed": "Falha ao decodificar áudio: {detail}",
        "error.pauses_length_mismatch": "Lista de pausas com tamanho incorreto: esperado {expected}, obtido {actual}",
    },
}


def set_language(code: str) -> None:
    global _current_language
    if code in _CATALOG:
        _current_language = code


def current_language() -> str:
    return _current_language


def tr(key: str, **params) -> str:
    catalog = _CATALOG.get(_current_language, _CATALOG[DEFAULT_LANGUAGE])
    template = catalog.get(key) or _CATALOG[DEFAULT_LANGUAGE].get(key, key)
    return template.format(**params) if params else template


def format_number(n: int) -> str:
    """Formats an integer with the thousands separator conventional for the
    current UI language (comma for English, period for Portuguese)."""
    grouped = f"{n:,}"
    return grouped.replace(",", ".") if _current_language == "pt" else grouped


def format_estimate(word_count: int, chapter_count: int, minutes: float) -> str:
    hours = int(minutes // 60)
    remaining_minutes = int(minutes % 60)
    return tr(
        "book.estimate",
        words=format_number(word_count),
        chapters=chapter_count,
        hours=hours,
        minutes=remaining_minutes,
    )
