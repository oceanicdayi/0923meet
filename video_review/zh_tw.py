"""Traditional-Chinese normalisation of ASR output, plus optional glossary fixes.

Whisper emits Simplified Chinese for a lot of Mandarin audio regardless of the
speaker's variety, which makes a Taiwanese course transcript awkward to read
and hard to search. This module rewrites the transcript into Traditional
Chinese (OpenCC `s2twp`) as *additional* files -- the raw ASR output is left
untouched so the machine result stays auditable.

An optional glossary applies literal string substitutions for domain terms the
model reliably mis-hears (homophones like 振幅/政府). Substitutions are not
verification: every hit is logged with its timestamp in `zh_tw_report.json` so
a human can confirm it against the audio.
"""
from pathlib import Path
import json

from .pipeline import stamp, write_json

CONFIG = 's2twp'


def converter(config=CONFIG):
    from opencc import OpenCC

    return OpenCC(config)


def load_glossary(path):
    """Read {"wrong": "right", ...}; longest patterns are applied first."""
    if not path:
        return []
    mapping = json.loads(Path(path).read_text(encoding='utf-8'))
    if not all(isinstance(k, str) and isinstance(v, str) and k for k, v in mapping.items()):
        raise ValueError('Glossary must map non-empty strings to strings.')
    return sorted(mapping.items(), key=lambda kv: -len(kv[0]))


def apply_glossary(text, glossary):
    hits = []
    for wrong, right in glossary:
        if wrong in text:
            hits.append({'from': wrong, 'to': right, 'count': text.count(wrong)})
            text = text.replace(wrong, right)
    return text, hits


def normalize_transcript(folder, glossary_path=None, config=CONFIG):
    """Write transcript.zh_tw.{json,md,srt} beside the raw transcript."""
    folder = Path(folder)
    source = folder / 'transcript.json'
    if not source.exists():
        return {'complete': False, 'reason': 'no transcript.json'}
    convert = converter(config).convert
    glossary = load_glossary(glossary_path)
    segments = json.loads(source.read_text(encoding='utf-8'))
    report = []
    for segment in segments:
        raw = segment['text']
        converted = convert(raw)
        fixed, hits = apply_glossary(converted, glossary)
        segment['text_raw_asr'] = raw
        segment['text'] = fixed
        segment['zh_tw_converted'] = converted != raw
        segment['glossary_applied'] = bool(hits)
        segment['verified'] = False
        if hits:
            report.append({'start': segment['start'], 'timestamp': stamp(segment['start']),
                           'raw': raw, 'text': fixed, 'replacements': hits})
    write_json(folder / 'transcript.zh_tw.json', segments)
    lines = ['# 自動語音逐字稿 · 繁體中文正規化版（未經逐句校訂）', '',
             f'簡轉繁設定：OpenCC {config}。原始 ASR 文字保留於 transcript.md 與本檔的 text_raw_asr 欄位。',
             f'套用詞彙修正 {sum(h["count"] for r in report for h in r["replacements"])} 處，'
             f'逐筆列於 zh_tw_report.json，請回聽確認。',
             '未出現文字的區間不代表已確認靜音；中英夾雜、專名及數字仍需回聽。', '']
    srt = []
    for i, segment in enumerate(segments, 1):
        flags = ' ⚠ 待核對' if segment.get('review_required') else ''
        flags += ' ✎ 詞彙修正' if segment['glossary_applied'] else ''
        lines.append(f'[{stamp(segment["start"])}–{stamp(segment["end"])}]{flags} {segment["text"]}')
        srt.append(f'{i}\n{stamp(segment["start"], True)} --> {stamp(segment["end"], True)}\n'
                   f'{segment["text"]}\n')
    (folder / 'transcript.zh_tw.md').write_text('\n\n'.join(lines), encoding='utf-8')
    (folder / 'transcript.zh_tw.srt').write_text('\n'.join(srt), encoding='utf-8')
    write_json(folder / 'zh_tw_report.json',
               {'opencc_config': config, 'glossary_terms': len(glossary),
                'segments': len(segments),
                'converted_segments': sum(s['zh_tw_converted'] for s in segments),
                'glossary_segments': len(report), 'human_verified': False, 'details': report})
    return {'complete': True, 'opencc_config': config, 'segments': len(segments),
            'glossary_segments': len(report), 'human_verified': False}


def normalize_ocr(folder, glossary_path=None, config=CONFIG):
    """Same normalisation for the frame OCR index."""
    folder = Path(folder)
    source = folder / 'ocr_index.json'
    if not source.exists():
        return {'complete': False, 'reason': 'no ocr_index.json'}
    convert = converter(config).convert
    glossary = load_glossary(glossary_path)
    records = json.loads(source.read_text(encoding='utf-8'))
    for record in records:
        record['text_raw_ocr'] = record['text']
        record['text'], _ = apply_glossary(convert(record['text']), glossary)
    write_json(folder / 'ocr_index.zh_tw.json', records)
    (folder / 'ocr.zh_tw.md').write_text(
        '# 自動畫面 OCR · 繁體中文正規化版（未校訂）\n\n' + '\n\n'.join(
            f'## {stamp(r["time"])}\n\n{r["text"]}' for r in records), encoding='utf-8')
    return {'complete': True, 'frames': len(records), 'human_verified': False}
