# Testing notes

Deleted manifest.  Fresh start!

## SD->Repo

    Scanning source... 7553 files found
    Scanning destination... 7553 files found
      update  SAMPLES/CLIPS/Terst/IntMic_000.wav
      update  SAMPLES/CLIPS/Terst/IntMic_002.wav
      update  SAMPLES/CLIPS/Terst/IntMic_004.wav
      update  SAMPLES/CLIPS/Terst/output_000.wav
      update  SAMPLES/CLIPS/Terst/output_002.wav
      update  SAMPLES/RESAMPLE/Terst/output_000.wav
      update  SAMPLES/RESAMPLE/Terst/output_002.wav
      update  SYNTHS/KERERU/Newtest-Symth.XML
      update  SONGS/Terst.XML
      update  SONGS/Terst 2.XML

      10 to copy, 0 to trash, 7543 unchanged

Looks good to me.  They exist on repo, but recopying cos no manifest

re-run: Already up to date
running repo->SD straight away: Already up to date
RepoSamples->CloudBackup: Copies expected files. Nothing on re-run
Snapshot: All good!

---

Make some minor changes to Repo side
    - move a WAV & XML
    - rename a WAV & XML
    - delete a WAV & XML

SD->Repo picks up the expected file changes
λ uv run sync_from_sd.py --dry-run
Source:      G:\
Destination: C:\source\deluge\DELUGE

Scanning source... 7553 files found
Scanning destination... 7552 files found
  copy    SAMPLES/FOUND/Tui/TuiWeo.wav
  copy    SAMPLES/RECORD/Noize/IntMic_000.wav
  copy    SAMPLES/RECORD/Dim/IntMic_002.wav
  copy    SAMPLES/RECORD/Dim/IntMic_004.wav
  trash   SAMPLES/FOUND/TuiWeo.wav
  trash   SAMPLES/RECORD/Dim/IntMic_002-RENAME.wav
  trash   SAMPLES/RECORD/NoizeRENAME/IntMic_000.wav

  4 to copy, 3 to trash, 7549 unchanged

  ## Repo->SD

λ uv run sync_to_sd.py --dry-run
Source:      C:\source\deluge\DELUGE
Destination: G:\

Scanning source... 7552 files found
Scanning destination... 7553 files found
  copy    SAMPLES/FOUND/TuiWeo.wav
  copy    SAMPLES/RECORD/Dim/IntMic_002-RENAME.wav
  copy    SAMPLES/RECORD/NoizeRENAME/IntMic_000.wav
  delete  SAMPLES/FOUND/Tui/TuiWeo.wav
  delete  SAMPLES/RECORD/Noize/IntMic_000.wav
  delete  SAMPLES/RECORD/Dim/IntMic_002.wav
  delete  SAMPLES/RECORD/Dim/IntMic_004.wav

  3 to copy, 4 to delete, 7549 unchanged

Dry run complete.

The inverse of sync_from!  So I think we good??

Re-run in both directions -- already up to date.  Looking good!

---

Going nuclear... deleting everything!! Let's gooo

---

Need to think about snapshots  
What happens when we move samples in between snapshot taking without fixing refs?
Are we overwriting same day snapshots? Is that okay?
Can we do any search to suggest where the new file might be?
The ambiguous mapping thing should be able to be resolved easy with the information we have

---

should probably have it remove empty directories?

---