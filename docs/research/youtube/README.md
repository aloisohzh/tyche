# YouTube inbox summaries

One file per video, `<video_id>.md`, written on the desk machine from the private raw transcript
(`research/youtube/raw/<video_id>.txt`, gitignored; mirrored to the Drive locker with
`--raw-dir`). The cloud researcher reads these summaries, never the transcripts, through the
`youtube-inbox` skill. Perimeter: [ADR 0015](../../adr/0015-external-research-perimeter.md).

Format (keep it short; a hypothesis, not a signal):

```markdown
# <title>
Video: <url> · Published: YYYY-MM-DD · Source: <playlist or inbox> · Summarised: YYYY-MM-DD

## Claims (one line each, attributed, no verbatim passages beyond a short phrase)
- ...

## Testable hypotheses (at most three, each labelled unvalidated)
- Instrument or setup / condition / expected behaviour / horizon / what would falsify it
```

Rules: no transcript text, no account or personal data, no trading instruction. Nothing here
enters signals, sizing, risk verdicts or the order path; a hypothesis graduates only through the
local LEAN lane, a validation label and a pre-registered rules hash.
