# `product_id: media`

Spoken-word audio — and, at step 6, video — for the Phase-1.5 ASR spikes.
`product_id` is derived from this folder's name.

| File | Format | Source | Notes |
|---|---|---|---|
| `hamlet-act1-librivox.mp3` | MP3 | [LibriVox — *Hamlet*, read by Sam Stinson](https://archive.org/details/hamlet2_1206_librivox) | [Public Domain Mark 1.0](http://creativecommons.org/publicdomain/mark/1.0/). 64 kbps CBR mono, 22.05 kHz. |

**Why 500 KB exactly:** the source file is a 27 MB full act. At 64 kbps constant bitrate,
a byte-range prefix is a clean time prefix — 500,000 bytes ÷ 8,000 B/s ≈ **62 seconds**,
which is the ~60s clip spec Part F asks for, without needing `ffmpeg` to trim it.
(LibriVox recordings open with a short spoken credit, so expect that before the play text.)

## Ground truth, for free

This is *Hamlet*, and `products/shakespeare/hamlet.txt` is the verbatim Project Gutenberg
text of the same play. **ASR error can be measured against it directly** — no manual
transcription needed, which is what makes the step-5 spike a real experiment rather than a
vibe check.

The reference text deliberately stays in `shakespeare` and is **not** copied here, so the
two products' chunks never overlap and the cross-tenant leak test stays unambiguous.

## Still to add

A short public-domain **video** clip for step 6. `ffmpeg` is not installed on this box yet;
step 6 extracts the audio track and reuses the audio loader, so the video itself only needs
to be a few seconds long.
