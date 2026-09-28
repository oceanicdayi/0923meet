"""Command-line entry point for the Drive course-recording review pipeline.

Recursively downloads every file in a Drive folder, transcribes videos with
faster-whisper, extracts scene-change frames with OCR, and (optionally)
writes 5-minute review clips -- then uploads all derived artifacts to a new
Drive output folder next to the source. See README.md for what "complete"
means here: this is machine preprocessing only, not verified content review.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

from .auth import default_credentials, drive_service
from .drive_runner import execute_drive_review


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--folder-id', required=True, help='Drive folder ID to process')
    p.add_argument('--work-dir', default='./work', help='Local working directory')
    p.add_argument('--run-tag', default='v1', help='Tag distinguishing this run/model from others sharing the output folder')
    p.add_argument('--model', default=None,
                    help='faster-whisper model name (e.g. large-v3, small). Omit to skip transcription '
                         '(download, scene scan, and OCR only).')
    p.add_argument('--device', default='auto', choices=['auto', 'cpu', 'cuda'])
    p.add_argument('--compute-type', default=None,
                    help='faster-whisper compute_type; defaults to float16 on cuda, int8 on cpu')
    p.add_argument('--frame-interval', type=int, default=15, help='Seconds between grid frame captures')
    p.add_argument('--make-clips', action='store_true', help='Write 5-minute review clips')
    p.add_argument('--initial-prompt', default='',
                    help='Domain vocabulary hint passed to faster-whisper (e.g. jargon, names) to bias ASR accuracy')
    p.add_argument('--only-ids', default=None,
                    help='Comma-separated Drive file IDs to (re)process; every other file is marked not_selected')
    return p.parse_args(argv)


def load_whisper_model(name, device, compute_type):
    from faster_whisper import WhisperModel

    has_gpu = shutil.which('nvidia-smi') is not None
    if device == 'auto':
        device = 'cuda' if has_gpu else 'cpu'
    if compute_type is None:
        compute_type = 'float16' if device == 'cuda' else 'int8'
    try:
        return WhisperModel(name, device=device, compute_type=compute_type,
                             cpu_threads=min(6, os.cpu_count() or 2)), device
    except Exception as error:
        if device != 'cuda':
            raise
        print(f'GPU model init failed, falling back to CPU: {error}', file=sys.stderr)
        return WhisperModel(name, device='cpu', compute_type='int8',
                             cpu_threads=min(6, os.cpu_count() or 2)), 'cpu'


def main(argv=None):
    args = parse_args(argv)
    credentials = default_credentials()
    service = drive_service(credentials)

    model = None
    model_name = args.model or 'none'
    if args.model:
        model, device = load_whisper_model(args.model, args.device, args.compute_type)
        print(f'Loaded ASR model {args.model} on {device}')

    only_ids = args.only_ids.split(',') if args.only_ids else None
    records, output_folder = execute_drive_review(
        service, credentials, args.folder_id, args.work_dir, model, model_name,
        run_tag=args.run_tag, make_clips=args.make_clips, frame_interval=args.frame_interval,
        only_ids=only_ids, initial_prompt=args.initial_prompt)

    for r in records:
        p = r.get('processing', {})
        print(r['label'], r['source']['name'],
              'download=', r.get('download_complete', False),
              'asr=', p.get('transcription', {}).get('asr_pass_completed', False),
              'scene_scan=', p.get('visual_index', {}).get('full_stream_scan_completed', False),
              'content_reviewed=', r.get('content_analysis_complete', False),
              'error=', r.get('error', ''))
    link = output_folder.get('webViewLink')
    if link:
        print('Output folder:', link)


if __name__ == '__main__':
    main()
