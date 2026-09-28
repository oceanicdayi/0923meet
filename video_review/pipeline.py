"""Local preprocessing for a single downloaded recording. Originals are read-only.

Machine processing is NOT equivalent to verified human review. Every output
keeps these statuses separate: a video is "machine_preprocessing_complete"
once ASR/scan/OCR finish, but "content_analysis_complete" stays False until
a person has actually read the transcript, checked the flagged segments, and
looked at the review clips/frames. See drive_runner.py for Drive I/O.
"""
from pathlib import Path
import hashlib, html, json, math, os, re, shutil, subprocess

VERSION = '2026-09-27.2'
ASR_CONFIG = {'language': None, 'task': 'transcribe', 'multilingual': True, 'word_timestamps': True}


def write_json(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def digest(path, algorithm='sha256'):
    h = hashlib.new(algorithm)
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def run(args):
    p = subprocess.run([str(x) for x in args], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-4000:])
    return p


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', path]).stdout)


def stamp(seconds, srt=False):
    ms = round(float(seconds) * 1000)
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02}{"," if srt else "."}{ms:03}'


def windows(duration, core=600.0, overlap=5.0):
    for i in range(math.ceil(duration / core)):
        a = i * core; b = min(duration, a + core)
        yield {'index': i, 'core_start': a, 'core_end': b,
               'start': max(0.0, a - overlap), 'end': min(duration, b + overlap)}


def covers(intervals, duration, tolerance=0.15):
    end = 0.0; gaps = []
    for a, b in sorted(intervals):
        if a > end + tolerance:
            gaps.append([end, a])
        end = max(end, b)
    if end < duration - tolerance:
        gaps.append([end, duration])
    return not gaps, gaps


def audio_chunks(source, folder, info):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    chunks = []
    base = float(info['format'].get('start_time', 0) or 0)
    total = float(info['format']['duration'])
    for stream in info['streams']:
        if stream.get('codec_type') != 'audio':
            continue
        ix = stream['index']; offset = float(stream.get('start_time', base) or base) - base
        duration = float(stream.get('duration', max(0, total - offset)))
        for w in windows(duration):
            p = folder / f'a{ix}_{w["index"]:04}.flac'
            if not p.exists():
                run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', max(0, w['start'] + offset),
                     '-i', source, '-map', f'0:{ix}', '-t', w['end'] - w['start'],
                     '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'flac', '-y', p])
            actual = float(probe(p)['format']['duration'])
            if abs(actual - (w['end'] - w['start'])) > 0.20:
                raise RuntimeError(f'Audio length mismatch: {p.name} {actual}')
            chunks.append(dict(w, file=str(p.relative_to(folder.parent)), stream_index=ix,
                                stream_offset=offset, stream_duration=duration,
                                source_channels=stream.get('channels'), duration=actual,
                                byte_size=p.stat().st_size, sha256=digest(p),
                                note='ASR downmix is mono; original audio remains in source video.'))
    write_json(folder.parent / 'audio_index.json', chunks)
    return chunks


def extract_frames(source, folder, duration, interval=15, scene_threshold=0.09):
    """Full video decode for scene detection plus a time-grid index; not semantic review."""
    folder = Path(folder); frames = folder / 'frames'; frames.mkdir(parents=True, exist_ok=True)
    scan = folder / 'scene_scan.json'
    if scan.exists():
        event = json.loads(scan.read_text())
        if event.get('interval') != interval or event.get('scene_threshold') != scene_threshold:
            raise RuntimeError('Frame parameters changed: use a new output directory.')
    else:
        # Only a small frame is used for change detection; selected stills retain full resolution.
        filt = f'scale=640:-2,select=gt(scene\\,{scene_threshold}),showinfo'
        p = run(['ffmpeg', '-nostdin', '-hide_banner', '-i', source, '-an', '-vf', filt,
                 '-fps_mode', 'vfr', '-f', 'null', '-'])
        times = [float(x) for x in re.findall(r'pts_time:([0-9.]+)', p.stderr)]
        event = {'decoder_exit': 0, 'full_stream_scan_completed': True,
                 'scene_times': times, 'interval': interval, 'scene_threshold': scene_threshold,
                 'semantic_review_completed': False,
                 'limitation': 'Change thresholds and temporal samples may miss subtle or brief details; use review clips to verify.'}
        write_json(scan, event)
    candidates = [(float(t), 'time_grid') for t in range(0, math.ceil(duration), interval)]
    candidates += [(max(0, duration - 0.15), 'end')]
    candidates += [(max(0, min(duration - 0.1, t + 0.10)), 'scene_change') for t in event['scene_times']]
    selected = {}
    for t, why in sorted(candidates):
        k = round(t * 1000); selected.setdefault(k, {'time': t, 'reasons': []})['reasons'].append(why)
    records = []
    for k, r in selected.items():
        p = frames / f'{k:010d}.jpg'
        if not p.exists():
            run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', r['time'], '-i', source,
                 '-frames:v', '1', '-q:v', '3', '-y', p])
        if not p.exists():
            raise RuntimeError(f'Frame missing at {r["time"]}')
        records.append(dict(r, file=str(p.relative_to(folder)), reviewed=False))
    write_json(folder / 'frames_index.json', records)
    # Every timeline interval is present in the queue, regardless of change detection.
    queue = [{'start': w['core_start'], 'end': w['core_end'], 'visual_review': 'pending',
              'audio_review': 'pending', 'notes': ''} for w in windows(duration, 60, 0)]
    if not (folder / 'review_queue.json').exists():
        write_json(folder / 'review_queue.json', queue)
    body = ['<!doctype html><meta charset="utf-8"><title>影片畫面索引</title>',
            '<style>body{font-family:sans-serif;background:#eee}article{display:inline-block;width:48%;vertical-align:top;margin:0.5%}img{width:100%}p{margin:4px}</style>',
            '<h1>畫面索引｜尚未等同全程人工審閱</h1><p>時間為原影片相對時間。請搭配逐字稿及 review_queue.json 核對。</p>']
    for r in records:
        body.append(f'<article><p>{stamp(r["time"])} · {html.escape(", ".join(r["reasons"]))}</p><a href="{r["file"]}"><img loading="lazy" src="{r["file"]}"></a></article>')
    (folder / 'frames.html').write_text('\n'.join(body), encoding='utf-8')
    return {'frames': len(records), 'scanned_video_seconds': duration,
            'full_stream_scan_completed': True, 'visual_review': 'pending'}


def transcribe_chunks(folder, chunks, model, model_name, checkpoint=None, initial_prompt=''):
    folder = Path(folder); td = folder / 'transcripts'; td.mkdir(exist_ok=True)
    accepted = []
    for c in chunks:
        stem = Path(c['file']).stem; target = td / f'{stem}.json'
        if target.exists():
            data = json.loads(target.read_text())
            if data.get('model') != model_name:
                raise RuntimeError('Model changed; use a new output directory.')
            if data.get('chunk', {}).get('sha256') != c['sha256']:
                raise RuntimeError('Checkpoint audio differs from current source; use a new output directory.')
            if data.get('asr_config') != ASR_CONFIG:
                raise RuntimeError('ASR language settings changed; use a new RUN_TAG/output directory.')
        else:
            print('ASR', folder.name, stem, flush=True)
            segments, info = model.transcribe(
                str(folder / c['file']), **ASR_CONFIG,
                beam_size=5, vad_filter=True,
                vad_parameters={'min_silence_duration_ms': 800}, condition_on_previous_text=False,
                initial_prompt=initial_prompt)
            segs = []
            for s in segments:
                d = s._asdict(); d['words'] = [w._asdict() for w in (s.words or [])]; segs.append(d)
            data = {'model': model_name, 'language': info.language, 'chunk': c, 'segments': segs,
                    'asr_config': ASR_CONFIG,
                    'asr_pass_completed': True, 'verified': False,
                    'vad_enabled': True, 'untranscribed_intervals': 'May include silence OR missed speech; not verified silence.'}
            write_json(target, data)
            if checkpoint is not None:
                checkpoint(target)
        for s in data['segments']:
            words = [w for w in s['words'] if c['core_start'] <= c['start'] + (w['start'] + w['end']) / 2 < c['core_end']]
            if not words:
                continue
            start = c['stream_offset'] + c['start'] + words[0]['start']
            end = c['stream_offset'] + c['start'] + words[-1]['end']
            txt = ''.join(w['word'] for w in words).strip()
            if not txt:
                continue
            mean_word_probability = sum(w.get('probability', 0.0) for w in words) / len(words)
            accepted.append({'start': start, 'end': end, 'text': txt, 'stream_index': c['stream_index'],
                              'avg_logprob': s['avg_logprob'], 'no_speech_prob': s['no_speech_prob'],
                              'mean_word_probability': mean_word_probability,
                              'review_required': bool(s['avg_logprob'] < -0.8 or mean_word_probability < 0.65 or
                                                       (s['no_speech_prob'] > 0.6 and s['avg_logprob'] < -0.5)),
                              'source_chunk': stem, 'verified': False})
    accepted.sort(key=lambda x: (x['start'], x['stream_index']))
    write_json(folder / 'transcript.json', accepted)
    lines = ['# 自動語音逐字稿（未經逐句校訂）', '', f'模型：{model_name}。時間對應原始影片。',
             '未出現文字的區間不代表已確認靜音；中英夾雜、專名及數字需回聽。', '']
    srt = []
    for i, s in enumerate(accepted, 1):
        tag = ' ⚠ 待核對' if s['review_required'] else ''
        lines.append(f'[{stamp(s["start"])}–{stamp(s["end"])}]{tag} {s["text"]}')
        srt.append(f'{i}\n{stamp(s["start"], True)} --> {stamp(s["end"], True)}\n{s["text"]}\n')
    (folder / 'transcript.md').write_text('\n\n'.join(lines), encoding='utf-8')
    (folder / 'transcript.srt').write_text('\n'.join(srt), encoding='utf-8')
    return {'asr_pass_completed': True, 'model': model_name, 'segments': len(accepted),
            'flagged_segments': sum(s['review_required'] for s in accepted), 'human_verified': False}


def ocr_frames(folder):
    """Searchable machine OCR of indexed stills, not a verified slide transcript."""
    folder = Path(folder)
    if not shutil.which('tesseract'):
        return {'complete': False, 'reason': 'tesseract unavailable'}
    available = run(['tesseract', '--list-langs']).stdout.splitlines()
    langs = [x for x in ['eng', 'chi_tra', 'chi_sim'] if x in available]
    if not langs:
        return {'complete': False, 'reason': 'OCR language data unavailable'}
    language = '+'.join(langs); records = json.loads((folder / 'frames_index.json').read_text())
    od = folder / 'ocr'; od.mkdir(exist_ok=True); results = []
    for r in records:
        p = folder / r['file']; target = od / (p.stem + '.txt')
        if not target.exists():
            env = dict(os.environ, OMP_THREAD_LIMIT='1')
            proc = subprocess.run(['tesseract', str(p), 'stdout', '-l', language, '--psm', '11'],
                                   env=env, capture_output=True, text=True)
            if proc.returncode:
                raise RuntimeError(proc.stderr[-2000:])
            target.write_text(proc.stdout, encoding='utf-8')
        results.append({'time': r['time'], 'frame': r['file'], 'text': target.read_text(), 'verified': False})
    write_json(folder / 'ocr_index.json', results)
    (folder / 'ocr.md').write_text('# 自動畫面 OCR（未校訂）\n\n' + '\n\n'.join(
        f'## {stamp(r["time"])}\n\n{r["text"]}' for r in results), encoding='utf-8')
    return {'complete': True, 'languages': langs, 'frames': len(results), 'verified': False}


def make_review_clips(source, folder, duration, max_bytes=90_000_000):
    folder = Path(folder); cd = folder / 'clips'; cd.mkdir(parents=True, exist_ok=True)
    records = []

    def one(start, end):
        p = cd / f'{round(start * 1000):010d}_{round(end * 1000):010d}.mp4'
        if not p.exists():
            run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', start, '-i', source, '-t', end - start,
                 '-map', '0:v:0', '-map', '0:a?', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                 '-c:a', 'aac', '-b:a', '96k', '-movflags', '+faststart', '-y', p])
        if p.stat().st_size > max_bytes:
            p.unlink(); mid = (start + end) / 2
            if end - start < 2:
                raise RuntimeError('Clip remains too large.')
            one(start, mid); one(mid, end); return
        d = float(probe(p)['format']['duration'])
        if abs(d - (end - start)) > 0.25:
            raise RuntimeError('Clip duration mismatch')
        records.append({'start': start, 'end': end, 'duration': d, 'file': str(p.relative_to(folder)),
                         'bytes': p.stat().st_size, 'reviewed': False})

    for w in windows(duration, 300, 0):
        one(w['start'], w['end'])
    ok, gaps = covers([(r['start'], r['end']) for r in records], duration)
    if not ok:
        raise RuntimeError(f'Clip coverage gaps: {gaps}')
    write_json(folder / 'clips_index.json', records)
    return records


def process_video(source, folder, meta, model=None, model_name=None, clips=False, interval=15, checkpoint=None, ocr=False, initial_prompt=''):
    source = Path(source); folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    old = folder / 'status.json'
    status = json.loads(old.read_text()) if old.exists() else {}
    sha = digest(source)
    if status.get('sha256') and status['sha256'] != sha:
        raise RuntimeError('Source changed; use a new output directory.')
    expected = int(meta.get('size') or 0)
    if expected and source.stat().st_size != expected:
        raise RuntimeError('Source byte-size mismatch')
    status.update({'pipeline_version': VERSION, 'source': meta, 'sha256': sha,
                   'byte_size': source.stat().st_size, 'download_verified_by_size': bool(expected),
                   'content_analysis_complete': False, 'visual_review': 'pending', 'audio_review': 'pending'})
    write_json(old, status)
    try:
        info = probe(source); write_json(folder / 'media_info.json', info)
        duration = float(info['format']['duration']); status['duration_seconds'] = duration
        chunks = audio_chunks(source, folder / 'audio', info)
        status['audio_chunks'] = len(chunks); status['audio_extraction_complete'] = True; write_json(old, status)
        status['visual_index'] = extract_frames(source, folder, duration, interval)
        write_json(old, status)
        if ocr:
            status['ocr'] = ocr_frames(folder); write_json(old, status)
        if model is not None:
            status['transcription'] = transcribe_chunks(folder, chunks, model, model_name, checkpoint, initial_prompt)
        else:
            status.setdefault('transcription', {'asr_pass_completed': False, 'reason': 'ASR not run'})
        if clips:
            status['review_clip_count'] = len(make_review_clips(source, folder, duration))
        status['machine_preprocessing_complete'] = bool(status['transcription'].get('asr_pass_completed'))
        status.pop('error', None)
    except Exception as e:
        status['error'] = str(e); status['machine_preprocessing_complete'] = False
        write_json(old, status); raise
    write_json(old, status)
    return status
