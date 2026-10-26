"""
格式匯出 registry（v2.0）。

本模組集中匯入所有格式輸出器，並提供給上層（server/frontend）
查詢支援格式清單與 MIME type。
"""

# 惰性匯入：避免 docx 等重依賴在未使用時觸發缺模組錯誤
def _get_exporter(name: str):
    if name == "word":
        from .word import export_score_to_word
        return ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", export_score_to_word)
    if name == "sola321":
        from .sola321 import export_score_to_sola321
        return ("sola321", "application/json", export_score_to_sola321)
    if name == "midi":
        from .midi import export_score_to_midi
        return ("midi", "audio/midi", export_score_to_midi)
    if name == "json":
        from .text_export import document_to_json
        return ("json", "application/json", document_to_json)
    if name == "tsv":
        from .text_export import document_to_tsv
        return ("tsv", "text/tab-separated-values", document_to_tsv)
    if name == "txt":
        from .text_export import document_to_plain_text
        return ("txt", "text/plain", document_to_plain_text)
    if name == "musicxml":
        from .musicxml import document_to_musicxml
        return ("musicxml", "application/vnd.recordare.musicxml+xml", document_to_musicxml)
    if name == "pdf":
        from .pdf import export_score_to_pdf
        return ("pdf", "application/pdf", export_score_to_pdf)
    raise ValueError(f"不支援的匯出格式：{name}")

EXPORTERS = {
    "musicxml": _get_exporter("musicxml"),
    "json": _get_exporter("json"),
    "tsv": _get_exporter("tsv"),
    "txt": _get_exporter("txt"),
    "sola321": _get_exporter("sola321"),
    "midi": _get_exporter("midi"),
    "word": _get_exporter("word"),
    "pdf": _get_exporter("pdf"),
}
