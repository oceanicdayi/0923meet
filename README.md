# video_review

A pipeline that reads a Google Drive folder full of recordings (video, audio,
or chat-log text), and produces automated transcripts, scene-change frame
captures, OCR of on-screen text, and short review clips — uploaded back to a
new output folder in your own Drive. Originals are never modified.

It does **not** replace watching the recordings. `content_analysis_complete`
stays `False` for every item; a human still needs to read the transcript,
check the flagged low-confidence segments, and skim the frames/clips. The
goal is to make that review fast, not to remove it.

## What it does per file

- **Video**: split into overlapping 10-minute mono audio chunks, transcribe
  each with [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  (word-level timestamps, checkpointed to Drive so an interrupted run can
  resume), full-stream scene-change detection plus a fixed time-grid frame
  index, Traditional/Simplified Chinese + English OCR on every captured
  frame, and (optionally) 5-minute review clips split further if they exceed
  ~90 MB.
- **Text/JSON** (e.g. a meeting chat log): copied through unchanged, plus a
  decoded `.txt` view.
- **Anything else**: left alone and flagged as needing a dedicated reader —
  the pipeline never silently skips a file without saying so.

Outputs per source file: `status.json`, `transcript.md` / `.srt` / `.json`,
`frames.html` + `frames_index.json`, `ocr.md` + `ocr_index.json`,
`review_queue.json` (a per-minute audio/visual review checklist), and
optional `clips/`. Everything is also zipped into ≤~95 MB parts for easy
download.

## Setup

```bash
pip install -r requirements.txt
sudo apt-get install -y ffmpeg tesseract-ocr tesseract-ocr-chi-tra tesseract-ocr-chi-sim
```

Authenticate with Google Drive using Application Default Credentials — either:

```bash
gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/drive
```

or a service account key file:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

The account needs read access to the source folder and write access
somewhere in its own Drive for the output folder.

## Usage

```bash
python -m video_review.cli \
  --folder-id 1ai4iZFgyjom4DQ92YTkJsEUEYp9vzYYw \
  --work-dir ./work \
  --model large-v3 \
  --frame-interval 15 \
  --make-clips \
  --initial-prompt "地球物理、板塊構造、地震、震源深度、PyGMT、GitHub、Colab、Gemini、CER。"
```

`--initial-prompt` is optional and only biases ASR toward specific jargon/names; omit it for
general-purpose recordings.

Omit `--model` to only download, scan scenes, and OCR (no transcription).
Rerunning with the same `--work-dir` and `--run-tag` resumes: downloaded
originals, ASR checkpoints, extracted frames, and clips already on disk (or
already uploaded as checkpoints) are reused rather than redone. Changing the
model or frame parameters requires a new `--run-tag` — the pipeline refuses
to mix results from different settings in one output folder.

A GPU is strongly recommended for the `large-v3` model; on CPU-only
machines, pass a smaller model (e.g. `--model small`).

## Limitations

- Transcripts and OCR are machine output and will contain errors, especially
  for names, numbers, and code-switched speech.
- Scene-change detection and the 15-second grid are a sampling heuristic,
  not frame-by-frame understanding — they can miss brief or subtle on-screen
  content. Use the review clips to verify anything time-sensitive.
- A time range with no transcribed text is not confirmed silence; it may be
  missed speech.
