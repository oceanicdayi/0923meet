"""Recursive Drive folder discovery, resumable download, and result upload.

Reads a Drive folder tree read-only and writes all derived artifacts (audio
chunks, transcripts, frame index, OCR, review clips) into a fresh output
folder in the caller's own Drive. It never modifies or re-shares the
originals. Requires credentials carrying the Drive scope (see auth.py).
"""
from pathlib import Path
import re, shutil, time, zipfile
from google.auth.transport.requests import AuthorizedSession
from googleapiclient.http import MediaFileUpload

from .pipeline import digest, process_video, write_json

FOLDER_MIME = 'application/vnd.google-apps.folder'


def qliteral(value):
    return "'" + str(value).replace('\\', '\\\\').replace("'", "\\'") + "'"


def list_children(service, folder):
    files = []; token = None
    while True:
        response = service.files().list(
            q=f'{qliteral(folder)} in parents and trashed=false',
            fields='nextPageToken,files(id,name,mimeType,size,md5Checksum,modifiedTime,createdTime,webViewLink,capabilities(canDownload))',
            pageSize=1000, pageToken=token, supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute(num_retries=3)
        files.extend(response.get('files', [])); token = response.get('nextPageToken')
        if not token:
            return files


def discover(service, root):
    pending = [(root, '')]; seen = set(); records = []
    while pending:
        fid, rel = pending.pop()
        if fid in seen:
            continue
        seen.add(fid)
        for item in list_children(service, fid):
            path = rel + '/' + item['name']
            if item['mimeType'] == FOLDER_MIME:
                pending.append((item['id'], path))
            else:
                records.append(dict(item, relative_source_path=path))
    return sorted(records, key=lambda f: (f.get('createdTime', ''), f['id']))


def authenticated_download(session, meta, target):
    """32 MiB HTTP Range reads, on-disk checkpoint, provider size/MD5 validation."""
    target = Path(target); target.parent.mkdir(parents=True, exist_ok=True)
    if not meta.get('capabilities', {}).get('canDownload', False):
        raise PermissionError('This account does not have download permission.')
    expected = int(meta['size']); md5 = meta.get('md5Checksum')

    def valid(path):
        return path.exists() and path.stat().st_size == expected and (not md5 or digest(path, 'md5') == md5)

    if valid(target):
        return target
    part = target.with_suffix(target.suffix + '.part')
    if part.exists() and part.stat().st_size > expected:
        part.unlink()
    position = part.stat().st_size if part.exists() else 0
    url = f'https://www.googleapis.com/drive/v3/files/{meta["id"]}?alt=media&supportsAllDrives=true'
    while position < expected:
        end = min(expected - 1, position + 32 * 1024 * 1024 - 1)
        response = None
        for attempt in range(5):
            response = session.get(url, headers={'Range': f'bytes={position}-{end}', 'Accept-Encoding': 'identity'},
                                    stream=True, timeout=(30, 120))
            if response.status_code not in (429, 500, 502, 503, 504):
                break
            response.close(); time.sleep(min(2 ** attempt, 16))
        response.raise_for_status()
        if response.status_code == 206:
            if response.headers.get('Content-Range') != f'bytes {position}-{end}/{expected}':
                response.close(); raise RuntimeError('Unexpected Content-Range; refusing mismatched bytes.')
            mode = 'ab'; goal = end + 1
        elif response.status_code == 200 and position == 0:
            mode = 'wb'; goal = expected
        else:
            response.close(); raise RuntimeError('Server did not honor the resumed range.')
        with response, open(part, mode) as output:
            for b in response.iter_content(1024 * 1024):
                if b:
                    output.write(b)
        position = part.stat().st_size
        if position != goal:
            raise RuntimeError('Incomplete range. Rerun to resume from saved bytes.')
    if not valid(part):
        part.rename(part.with_suffix(part.suffix + '.invalid'))
        raise RuntimeError('Download checksum mismatch; invalid bytes retained separately.')
    part.replace(target)
    return target


def ensure_folder(service, name, parent=None, properties=None):
    query = f'name={qliteral(name)} and mimeType={qliteral(FOLDER_MIME)} and trashed=false'
    query += f' and {qliteral(parent or "root")} in parents'
    for k, v in (properties or {}).items():
        query += f' and appProperties has {{ key={qliteral(k)} and value={qliteral(v)} }}'
    result = service.files().list(q=query, fields='files(id,webViewLink)', pageSize=100).execute(num_retries=3).get('files', [])
    if len(result) > 1:
        raise RuntimeError('Multiple matching output folders; specify a unique run_tag.')
    if result:
        return result[0]
    body = {'name': name, 'mimeType': FOLDER_MIME, 'appProperties': properties or {}}
    if parent:
        body['parents'] = [parent]
    return service.files().create(body=body, fields='id,webViewLink').execute(num_retries=3)


def upload_output(service, path, parent):
    path = Path(path)
    existing = service.files().list(
        q=f'{qliteral(parent)} in parents and name={qliteral(path.name)} and trashed=false',
        fields='files(id)', pageSize=100,
    ).execute(num_retries=3).get('files', [])
    if len(existing) > 1:
        raise RuntimeError(f'Multiple output copies: {path.name}')
    media = MediaFileUpload(str(path), resumable=True, chunksize=8 * 1024 * 1024)
    if existing:
        request = service.files().update(fileId=existing[0]['id'], media_body=media, fields='id,webViewLink')
    else:
        request = service.files().create(body={'name': path.name, 'parents': [parent]}, media_body=media, fields='id,webViewLink')
    result = None
    while result is None:
        _, result = request.next_chunk(num_retries=3)
    return result


def zip_parts(folder, destination, prefix, target_bytes=95_000_000):
    """Each ZIP is independently readable; unzip all parts into one directory."""
    folder = Path(folder); destination = Path(destination); destination.mkdir(parents=True, exist_ok=True)
    parts = []; archive = None; size = 0
    try:
        for p in sorted(folder.rglob('*')):
            if not p.is_file():
                continue
            if p.stat().st_size > target_bytes:
                raise RuntimeError(f'Artifact too large: {p.name}')
            estimate = p.stat().st_size + len(str(p.relative_to(folder)).encode()) * 2 + 512
            if archive is None or size + estimate > target_bytes:
                if archive:
                    archive.close()
                dest = destination / f'{prefix}_part{len(parts) + 1:03}.zip'; parts.append(dest)
                archive = zipfile.ZipFile(dest, 'w', compression=zipfile.ZIP_STORED); size = 0
            archive.write(p, arcname=str(Path(prefix) / p.relative_to(folder))); size += estimate
    finally:
        if archive:
            archive.close()
    if any(p.stat().st_size >= 100_000_000 for p in parts):
        raise RuntimeError('ZIP size check failed')
    return parts


def execute_drive_review(service, credentials, folder_id, work, model, model_name,
                          run_tag='v1', make_clips=True, frame_interval=15, only_ids=None):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    session = AuthorizedSession(credentials)
    source = discover(service, folder_id); write_json(work / 'source_manifest.json', source)
    outmeta = ensure_folder(service, f'course_recording_review_{folder_id[:8]}_{run_tag}_{model_name}',
                             properties={'source_folder': folder_id, 'workflow': 'recording_review_v1', 'run_tag': run_tag, 'model': model_name})
    upload_output(service, work / 'source_manifest.json', outmeta['id'])
    print('Output folder:', outmeta.get('webViewLink', outmeta['id']))
    records = []
    for i, item in enumerate(source, 1):
        label = f'F{i:02}'; key = label + '_' + item['id']; folder = work / 'processed' / key
        folder.mkdir(parents=True, exist_ok=True)
        entry = {'label': label, 'source': item, 'content_analysis_complete': False}
        if only_ids and item['id'] not in only_ids:
            entry.update({'status': 'not_selected', 'reason': 'Run ALL files before claiming complete coverage.'}); records.append(entry); continue
        print('\nStarting', label, item['name'], flush=True)
        remote = ensure_folder(service, key, outmeta['id'])
        try:
            mime = item['mimeType']
            if not (mime.startswith('video/') or mime.startswith('audio/') or mime.startswith('text/') or mime in ['application/json', 'application/octet-stream']):
                raise RuntimeError(f'Unsupported type requires separate reader: {mime}')
            suffix = Path(item['name']).suffix or ('.mp4' if mime.startswith('video/') else '.bin')
            original = authenticated_download(session, item, work / 'originals' / (item['id'] + suffix))
            entry['download_complete'] = True; entry['sha256'] = digest(original)
            entry['md5_verified'] = bool(item.get('md5Checksum'))
            normalized = {'id': item['id'], 'title': item['name'], 'size': item.get('size'),
                          'mime_type': mime, 'url': item.get('webViewLink')}
            if mime.startswith('video/'):
                checkpoints = ensure_folder(service, 'ASR_checkpoints', remote['id'])
                td = folder / 'transcripts'; td.mkdir(exist_ok=True)
                for cf in list_children(service, checkpoints['id']):
                    if re.fullmatch(r'a\d+_\d{4}\.json', cf['name']):
                        authenticated_download(session, cf, td / cf['name'])
                entry['processing'] = process_video(original, folder, normalized, model, model_name,
                                                      clips=make_clips, interval=frame_interval, ocr=True,
                                                      checkpoint=lambda path: upload_output(service, path, checkpoints['id']))
            elif mime.startswith('text/') or mime == 'application/json':
                # Exact original bytes plus a decoded view; no guessed silent replacement.
                shutil.copy2(original, folder / 'original_text.bin')
                text = original.read_bytes().decode('utf-8-sig')
                (folder / 'text.txt').write_text(text, encoding='utf-8')
                entry.update({'text_decoded': True, 'status': 'awaiting_content_review'})
            else:
                raise RuntimeError('Stored but unsupported for semantic review; explicit reader needed.')
            for part in zip_parts(folder, work / 'packages', key):
                upload_output(service, part, remote['id'])
            # Text is also uploaded unzipped so it can be read without opening ZIPs.
            for name in ['status.json', 'transcript.md', 'transcript.srt', 'transcript.json', 'text.txt', 'review_queue.json', 'ocr.md']:
                p = folder / name
                if p.exists():
                    upload_output(service, p, remote['id'])
            entry['artifacts_saved'] = True; entry['output_url'] = remote.get('webViewLink')
        except Exception as e:
            entry.update({'status': 'failed', 'error': str(e)}); print('Needs attention:', label, str(e), flush=True)
        records.append(entry)
        write_json(work / 'processing_manifest.json', records)
        upload_output(service, work / 'processing_manifest.json', outmeta['id'])
    write_json(work / 'processing_manifest.json', records)
    upload_output(service, work / 'processing_manifest.json', outmeta['id'])
    complete = sum(bool(r.get('processing', {}).get('machine_preprocessing_complete') or r.get('text_decoded')) for r in records)
    report = (f'# Run summary\n\nSource files: {len(source)}\n\nMachine preprocessing complete: {complete}\n\n'
              'Machine preprocessing complete does NOT mean sentence-by-sentence / frame-by-frame content review is done. '
              'Bring the output folder link back and continue reading the transcripts, frames, flagged segments, and review_queue.\n\n'
              'If interrupted, rerun with the same run_tag; uploaded ASR checkpoints are read back. '
              '.part resume for large originals only survives within the same local working directory.\n')
    (work / 'run_summary.md').write_text(report, encoding='utf-8'); upload_output(service, work / 'run_summary.md', outmeta['id'])
    print(report); print('Output folder:', outmeta.get('webViewLink', outmeta['id']))
    return records, outmeta
