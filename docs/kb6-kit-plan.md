---
title: KB6 instrument kit plan
description: Approved 50-instrument roster, working collection progress and selection plan with two intentional TR-727 kit versions
ms.date: 2026-10-26
---

## Current progress as of 2026-10-26

The working destination `C:\source\deluge\DELUGE\SAMPLES\KB6-LIB` now holds
19 instrument folders containing 20 flat kit folders and 262 samples
(audio files), approximately 12.19 MiB. The TR-727 instrument folder contains
two flat version folders; the other 18 instrument folders are flat.
There are no non-audio files.
These represent 19 of the 50 planned instruments, with 31 not yet
represented locally. The two TR-727 versions count as one instrument.

| Current local kit folder           | Audio files |
|------------------------------------|-------------|
| `Acetone Rhythm-Ace`               | 16          |
| `Alesis Andromeda-A6`              | 13          |
| `Boss DR-110`                      | 8           |
| `Casio RZ1`                        | 12          |
| `Casio SK1`                        | 8           |
| `Casio VL1`                        | 4           |
| `Fricke MFB 301`                   | 10          |
| `Kawai R-100`                      | 24          |
| `Korg Minipops`                    | 13          |
| `Linn LM-1`                        | 19          |
| `Maestro Rhythm King`              | 17          |
| `Mattel Electronics Synsonics DRM` | 7           |
| `Nintendo Game-Boy-Advance-SP`     | 10          |
| `Roland CR78`                      | 13          |
| `Roland TR707`                     | 15          |
| `Roland TR727\DirtyTubeAmp`        | 15          |
| `Roland TR727\Original`            | 15          |
| `SequentialCircuits Drumtraks`     | 13          |
| `Teenage-Engineering PO-12`        | 16          |
| `Wurlitzer Sideman`                | 14          |

All 15 original sets with 16 or fewer samples have been brought over,
totalling 172 samples. Maestro (17), Linn LM-1 (19) and Kawai (24) bring
that to 18 instruments and 232 samples; the two 15-sample TR-727 versions
bring the working collection to 20 kit folders, 19 instruments and 262 samples.
Small-folder-first is an initial transfer convenience, not a selection rule.

These complete sets are present locally awaiting audition, QC and eventual
kit XML creation when requested. Bringing over raw folders is not final
curation, completion or approval of every sample. No audio audition has
been performed by the assistant, and there is no evidence that kit XMLs
have been created. The CR-78 loops and truncated file, Sideman rhythms,
SK-1 loop and CZ-bass provenance, Mattel repeated-strike screening and
Kawai float-format playback check remain unresolved.

## Selection principles

Build one manageable, playable kit per instrument by default across the
50 approved instruments. The two TR-727 versions, original and dirty
tube-amp, are an approved intentional exception: keep both as separate
flat folders and eventual kit versions. Do not merge them or choose only
one. This permits 51 eventual kits, not 51 instruments.
Use only that instrument's samples. Do not mix instruments, pad missing roles
or create other unapproved alternative kits. Missing conventional drum roles is fine.
Preserve distinctive flavour rather than trying to make every instrument
behave like a complete conventional drum machine.

Sixteen is a convenience for choosing initial transfers, not a minimum,
target, ceiling or audition/selection effort threshold. Every chosen
sample needs a useful function or unique timbral contribution. Near-identical
kicks, snares or other variants should not dominate, even when a source set
contains fewer than 16 files. Conversely, more than 16 is acceptable when
each sound earns its place.

The working collection has been brought over, but final sample selections
and kit sizes remain undecided. Assessments use historical filesystem information, filenames,
hashes, WAV headers and simple signal-activity screening, not listening
results. Proposed roles, contrasts and editing needs still require audition.
Selection starts fresh; existing usage or reference counts are not a ranking
constraint.

## Sources, counts and destination layout

The current library roles are:

* `D:\Creative\KB6-LIB`: Nominated bulk-library source after consolidation.
* `C:\source\deluge\DELUGE\SAMPLES\KB6-LIB`: Rebuilt working destination.

Roster source-folder names and raw counts refer to the original inventory,
not guaranteed current source availability. Verify each folder's current
location and source-drive availability before copying or moving. Presence
in the working destination does not prove that a second copy or backup
exists; do not infer a move solely from an unavailable source path.

Human instrument names are display labels, not replacement folder names.
Preserve spellings such as `Electron Sidstation` and
`SequentialCircuits Drumtraks` when forming destinations, with the
approved TR-727 version-folder layout below as an intentional exception.

All 50 source folder names are unique. The default destination is one
flat folder directly under `DELUGE\SAMPLES\KB6-LIB`:

```text
DELUGE\SAMPLES\KB6-LIB\<source folder>\<selected sample>.wav
```

The TR-727 keeps these two separate flat destinations, already present
with 15 samples each:

```text
DELUGE\SAMPLES\KB6-LIB\Roland TR727\Original\<sample>.wav
DELUGE\SAMPLES\KB6-LIB\Roland TR727\DirtyTubeAmp\<sample>.wav
```

## Foundational machines

IDs 1-10 provide contrasting machine voices and signature percussion.
Their 714 raw files range from short named palettes to large capture sets.

| ID  | Instrument                    | Sample transfer | Exact source folder            | Raw files | Effort | Evidence and next selection work                                                                                                                                                              |
|-----|-------------------------------|-----------------|--------------------------------|-----------|--------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1   | Roland TR-808                 | Pending         | `Roland TR808`                 | 64        | Medium | Compare 16 kicks and 16 snares for contrasting envelopes and timbres, not 32 retained variants. Preserve signature hats, toms, congas and other percussion.                                   |
| 2   | Roland TR-909                 | Pending         | `Roland TR-909`                | 474       | High   | Compare Set1 (160), Set2 (90) and Set3 (224); interpret parameter-coded names and build a cohesive cross-role palette. RIDED4/RIDED6 in Set1 are exact duplicates.                            |
| 3   | Roland TR-606                 | Pending         | `Roland TR606`                 | 48        | Medium | Each of eight filename families has five numbered versions plus an _OD version. Compare apparent overdrive captures and variants; do not keep every version per voice.                        |
| 4   | Roland TR-707                 | Done            | `Roland TR707`                 | 15        | Low    | Audition two bass drums, two snares, three toms, hats and cymbals. Retain distinct roles without an arbitrary size cut.                                                                       |
| 5   | Roland CR-78                  | Done            | `Roland CR78`                  | 13        | Medium | Map 11 SAMPLE-numbered hits by listening; assess LOOP1/LOOP2 separately from hits. LOOP2.WAV is truncated: 407286 declared data bytes, 131350 available. Do not silently select or repair it. |
| 6   | Boss DR-110                   | Done            | `Boss DR-110`                  | 8         | Low    | Check the clearly named voices and compare Chh/Cht/Ohh/Oht articulations. Keep useful hat contrasts, not an automatic keep-all.                                                               |
| 7   | Linn LM-1                     | Done            | `Linn LM-1`                    | 19        | Low    | Identify linn_bp; compare two kicks and two snares among mostly named voices. More than 16 is acceptable if every retained voice contributes.                                                 |
| 8   | LinnDrum                      | Pending         | `Linn Linndrum`                | 30        | Medium | Compare high/low conga, tom, snare, sidestick and hat variants. Identify the 4.126 s Reallinn file; reduce similar pitch versions while preserving useful register contrasts.                 |
| 9   | Oberheim DMX                  | Pending         | `Oberheim DMX`                 | 30        | Medium | Map 12 numbered files against 18 named files for possible timbral overlap, not proven duplicates. All 30 are 48 kHz/32-bit float; include playback QC.                                        |
| 10  | Sequential Circuits Drumtraks | Done            | `SequentialCircuits Drumtraks` | 13        | Low    | Quickly audition the clearly named broad role set. Remove only redundant or unusable sounds; neither force a cut nor assume every file earns a place.                                         |

## Digital drums and samplers

IDs 11-20 add sampled drum palettes and sampler character across 676 raw
files. Treat supplied sampler collections as supplied material, not proof
of a canonical factory sound set.

| ID  | Instrument        | Sample transfer | Exact source folder | Raw files | Effort | Evidence and next selection work                                                                                                                                                                                              |
|-----|-------------------|-----------------|---------------------|-----------|--------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 11  | E-mu Drumulator   | Pending         | `EMU Drumulator`    | 56        | High   | All files are numbered 00-55. Listen to and classify every file before choosing meaningful representatives.                                                                                                                   |
| 12  | E-mu SP-1200      | Pending         | `EMU SP1200`        | 41        | Medium | Compare the many named percussion roles and identify six unspecified Per files. Choose a compact, distinct palette from this supplied sampler collection, not an assumed factory sound set.                                   |
| 13  | Akai MPC3000      | Pending         | `Akai MPC3000`      | 97        | High   | Compare acoustic, synthetic, gated, FX and hand-percussion groups. Establish a coherent flavour rather than retaining every alternative for one role.                                                                         |
| 14  | Fairlight CMI IIx | Pending         | `Fairlight CMI IIx` | 69        | Medium | Balance named drums and FX signatures with a playable core. Symtom.wav/Symtomlo.wav are exact duplicates. All 69 are 48 kHz/32-bit float; include playback QC.                                                                |
| 15  | Ensoniq Mirage    | Pending         | `Ensoniq Mirage`    | 31        | Medium | Compare filtered/louder and a-e crash/hat alternatives plus five tom registers. Preserve sampler character and useful register contrast, not every recording version.                                                         |
| 16  | Yamaha RX5        | Pending         | `Yamaha RX-5`       | 63        | Medium | Compare normal, heavy and electronic tom groups, repeated kick/snare families and specialty percussion. Check the mixed mono/stereo captures for a coherent result.                                                           |
| 17  | Kawai R-100       | Done            | `Kawai R-100`       | 24        | Low    | Compare two bass drums, two snares, two closed hats and two rides while preserving distinct percussion. No forced 16 cut. Low musical selection effort has separate QC for all 24 files at 48 kHz/32-bit float.               |
| 18  | Casio RZ-1        | Done            | `Casio RZ1`         | 12        | Low    | Decode the abbreviated role names, including three toms, then audition the short set and remove only unhelpful overlap.                                                                                                       |
| 19  | Alesis HR-16B     | Pending         | `Alesis HR16B`      | 47        | Medium | Compare several kick/snare styles and quirky percussion. Choose signatures for one coherent set, not every wet/gated alternative. All 47 are 48 kHz/32-bit float; include playback QC.                                        |
| 20  | Alesis SR-16      | Pending         | `Alesis SR16`       | 236       | High   | Compare dry/room/hall/flange and high/mid/low families; settle on coherent acoustic/electronic flavour, tom family and cymbals. All 236 are 96 kHz/24-bit stereo: test playback; consider delivery conversion only if needed. |

## Dance, drum synthesis and later electronic instruments

IDs 21-30 cover synthetic voice contrasts, preset collections and distinctive
electronic accents across 1,366 raw files. Large kick families and preset
counts are comparison work, not reasons to enlarge the eventual kits.

| ID  | Instrument                           | Sample transfer | Exact source folder                    | Raw files | Effort | Evidence and next selection work                                                                                                                                                                                                            |
|-----|--------------------------------------|-----------------|----------------------------------------|-----------|--------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 21  | Elektron Machinedrum SPS-1 MKII      | Pending         | `Elektron MachineDrum SPS1 MKII`       | 424       | High   | Group 18 claps, 26 cymbals, 59 hats, 62 kicks, 122 percs, 47 snares, 35 stabs and 55 toms before contrasting voices. Hats 0057/Snares 0029 share audio payloads. Names do not identify synthesis engines.                                   |
| 22  | Korg M1                              | Pending         | `Korg M1`                              | 44        | Medium | Compare named ROM percussion with bells, plucks, scratch and other accents. Keep representative percussion and distinct extras, not all pitched variants.                                                                                   |
| 23  | Korg Electribe ER-1                  | Pending         | `Korg Electribe ER-1`                  | 172       | High   | Compare voices across 22 source kits of 6-8 hits; build ONE resulting kit. Resolve 19 case-insensitive basename collision groups with unique flat names and source mapping.                                                                 |
| 24  | Jomox XBase09                        | Pending         | `Jomox Xbase09`                        | 102       | Medium | 74 Bassdrum plus three LongBassDrum files make 77 kick-labelled files, about 75% of the set, against six snares and smaller families. Prioritize diversity, not kick count.                                                                 |
| 25  | Vermona DRM1 MkIII                   | Pending         | `Vermona DRM1-MK3`                     | 97        | Medium | Compare 33 bass drums, 20 hats, 14 toms and 10 each clap/FX/snare. Preserve distinctive synthetic percussion and FX; audition the longest hat (8.382 s) for tail context.                                                                   |
| 26  | Sonic Potions LXR                    | Pending         | `Sonic-Potions LXR`                    | 195       | High   | Compare voices across 30 presets, including DR slots, for one coherent kit with distinct digital colours. Resolve nine basename collision groups and retain source mapping in flat names.                                                   |
| 27  | Clavia Nord Drum                     | Pending         | `Clavia Nord-Drum`                     | 35        | Medium | Compare 10 kicks and 12 snares without letting variants dominate; explore seven percussion, three noise and hybrid/tom voices. Do not add hats from another instrument.                                                                     |
| 28  | Teenage Engineering PO-12            | Done            | `Teenage-Engineering PO-12`            | 16        | Low    | Map and label numbered files 001-016 (0.021-0.426 s), then prune similar voices. Sixteen files is not an automatic quota or keep-all.                                                                                                       |
| 29  | Noise Engineering Basimilus Iteritas | Pending         | `Noise-Engineering Basimilus-Iteritas` | 35        | High   | Compare 8 kicks, 8 snares, 8 claps, 4 HH and 4 OH. Perc01/02/03 are each 60.875 s with many separated active bursts: inspect hits/gestures and slicing needs. The other 32 are 0.305-3.499 s; all 35 audio payloads were verified complete. |
| 30  | E-mu Planet Phatt                    | Pending         | `EMU Planet-Phatt`                     | 246       | High   | Classify kicks, snares and hats alongside bass waves, stabs and FX. Retain distinct hip-hop flavour and signature accents; omit pitched waveforms only when unhelpful, not by assuming every file is a drum.                                |

## Early rhythm boxes

IDs 31-35 contribute compact rhythm-box voices across 70 raw files.
Numbered hits need identification, and supplied rhythm recordings need
separate assessment rather than automatic inclusion.

| ID  | Instrument          | Sample transfer | Exact source folder   | Raw files | Effort | Evidence and next selection work                                                                                                                     |
|-----|---------------------|-----------------|-----------------------|-----------|--------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| 31  | Wurlitzer Sideman   | Done            | `Wurlitzer Sideman`   | 14        | Low    | Map 12 numbered Side_Drum files. Assess Beguine (5.590 s) and Samba (4.728 s) rhythm recordings separately; neither must enter the playable hit set. |
| 32  | Ace Tone Rhythm Ace | Done            | `Acetone Rhythm-Ace`  | 16        | Low    | Compare three kicks, three snares and named HHCL/HHOP/CLAVE; identify seven PERC files. Prune near variants even with only 16 raw files.             |
| 33  | Korg Mini Pops      | Done            | `Korg Minipops`       | 13        | Low    | Compare three bass drums, three snares, two hats, two toms, two wood sounds and sdfx. The exact Mini Pops model is unverified; do not label it MP7.  |
| 34  | Maestro Rhythm King | Done            | `Maestro Rhythm King` | 17        | Low    | Listen to and label all 17 numbered files before selection. Retain all if distinct and useful, without forcing 16; preserve 32 kHz originals.        |
| 35  | Fricke MFB 301      | Done            | `Fricke MFB 301`      | 10        | Low    | Compare two bass drums, three hats, two snares, one rim and two toms for useful variant differences. A short set still needs listening and pruning.  |

## Electronic drums and dedicated percussion

IDs 36-40 add pitched drums, synthetic gestures, Latin articulations and
stroke variety across 470 raw files. Capture variants should support useful
contrasts rather than overwhelm the instrument's playable identity.

| ID  | Instrument                | Sample transfer      | Exact source folder         | Raw files | Effort | Evidence and next selection work                                                                                                                                                                                                                                              |
|-----|---------------------------|----------------------|-----------------------------|-----------|--------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 36  | Simmons SDS-V             | Pending              | `Simmons SDS5`              | 109       | High   | Compare 64 root files, 32 numbered misc files and 13 nested-kit files; retain useful pitched-tom spread and other roles. Snare19/Tom6 are exact duplicates needing role verification. Four files are 22.05 kHz, others 44.1 kHz; flat basenames currently do not collide.     |
| 37  | Pearl Syncussion SY-1     | Pending              | `Pearl SY-1`                | 74        | High   | Classify all 74 numbered files by distinct textures and gestures. Inspect 56.wav (17.188 s) for repeated events versus tail; do not assume it is a one-shot.                                                                                                                  |
| 38  | Star Instruments Synare 3 | Pending              | `Star-Instruments Synare-3` | 120       | High   | Audition and group all 120 numbered files by attack, noise, tonal and sweep character. Select meaningful contrasts instead of many minor variations.                                                                                                                          |
| 39  | Roland TR-727             | Done (both versions) | `Roland TR727`              | 86        | Medium | Source: Orig, TubeAmp-Clean, TubeAmp-Dirty and TubeEQ (15 each), plus a different 26-file set. Keep approved Original and DirtyTubeAmp kits separate (15 local files each), preserving Latin articulations and processing contrast. Variants are not proven exact duplicates. |
| 40  | Korg Wavedrum             | Pending              | `Korg Wavedrum`             | 81        | Medium | Compare 18 bass drums, 12 hats, 15 percussion and other families for stroke variety. Inspect seven Fill files for phrases versus useful gestures. Hat5/Hat7 share identical audio payloads.                                                                                   |

## Synth-derived percussion

IDs 41-45 cover analogue, FM, digital and characterful synth-derived
percussion across 273 raw files. Tonal and effects voices can be valuable
accents without being forced into conventional drum roles.

| ID  | Instrument          | Sample transfer | Exact source folder             | Raw files | Effort | Evidence and next selection work                                                                                                                                                                                        |
|-----|---------------------|-----------------|---------------------------------|-----------|--------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 41  | Moog Modular 55     | Pending         | `Moog Modular55`                | 35        | Medium | Compare 12 BD, eight SD and four HH; identify BL/PC/RM/ST abbreviations by listening. Preserve analogue contrasts rather than every kick.                                                                               |
| 42  | Alesis Andromeda A6 | Done            | `Alesis Andromeda-A6`           | 13        | Low    | Compare three bass drums, two claps, two cows, two shakes and the other percussion for near redundancy. Preserve distinct accents; do not invent missing roles or pad the set.                                          |
| 43  | Yamaha DX7          | Pending         | `Yamaha DX7`                    | 74        | Medium | Classify 20 Efx and eight Met files alongside named drum families, beep, zip and cow sounds. Keep FM-specific timbres rather than selecting generic drum roles alone.                                                   |
| 44  | Elektron SidStation | Pending         | `Electron Sidstation`           | 60        | High   | Map all 60 numbered files before selection. Contrast noise, tonal, metallic and sweep textures; filenames do not establish drum roles.                                                                                  |
| 45  | Polivoks            | Pending         | `Formanta-Radio-Plant Polivoks` | 91        | High   | Compare set1 (65 files, 24-bit mono) with set2 (26, 32-bit float stereo), both 44.1 kHz, for capture style and genuine voice contrasts. Inspect four Groove files instead of assuming loops; include float playback QC. |

## Home keyboards, games and unusual instruments

IDs 46-50 provide small character sets and unconventional sound functions
across 76 raw files. Supplied labels do not establish every sound's role,
provenance or suitability as a one-shot.

| ID  | Instrument                   | Sample transfer | Exact source folder                | Raw files | Effort | Evidence and next selection work                                                                                                                                                                                                                                     |
|-----|------------------------------|-----------------|------------------------------------|-----------|--------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 46  | Nintendo NES                 | Pending         | `Nintendo NES`                     | 47        | High   | Map all 47 game-prefix/Sound-number filenames to useful transient, noise, tonal or SFX functions. Do not force conventional drum roles from names that provide none.                                                                                                 |
| 47  | Nintendo Game Boy Advance SP | Done            | `Nintendo Game-Boy-Advance-SP`     | 10        | Low    | Compare four bass drums and two snares; map the clap and three percussion files. Prune similar kick variants and do not import hats.                                                                                                                                 |
| 48  | Casio SK-1                   | Done            | `Casio SK1`                        | 8         | Low    | Audition six named drum hits. Assess skloop and CZ-BASS1 separately for provenance and usefulness; neither automatically belongs to an SK-1 one-shot kit.                                                                                                            |
| 49  | Casio VL-1                   | Done            | `Casio VL1`                        | 4         | Low    | Confirm the Bass-labelled role and the difference between two snares plus the hat. Retain all four only if useful.                                                                                                                                                   |
| 50  | Mattel Synsonics             | Done            | `Mattel Electronics Synsonics DRM` | 7         | Low    | Compare kick, cymbal, snare, low tom and three high-tom versions for register contrast. Files span 1.398-6.479 s; each has two screened activity bursts. Audition repeated strikes/silence before choosing any trimmed hit; these are not confirmed clean one-shots. |

## Cross-library findings and quality checks

These findings come from the original 2026-10-26 analysis, not a new scan
of the working collection. Bringing over a complete folder does not
resolve its outstanding content or playback checks.

### Formats and recording structure

There are 196 float WAV files: DMX 30, Fairlight 69, Kawai 24, HR-16B 47 and
Polivoks set2 26. Check playback on the target Deluge firmware. Do not assume
float is unsupported. If compatibility requires another encoding, prepare
compatible copies later while preserving the originals. Kawai's Low musical
selection estimate does not remove this separate format check.

The SR-16 collection is entirely 96 kHz/24-bit stereo. Check chosen files on
the target playback system before deciding whether delivery conversion is
needed. Do not preemptively resample low-rate originals away: the Maestro
files are 32 kHz, and four Simmons files are 22.05 kHz. Preserve their source
character and keep any later delivery copies traceable.

The CR-78 `LOOP2.WAV` has a confirmed truncated audio payload. An independent
Python wave read found 407,286 declared data bytes but only 131,350 available.
Treat it as a known exception, not a usable candidate by default. Do not
silently repair it or include it because the source count is small.

The three Basimilus `Perc` recordings have complete audio payloads but many
separated activity bursts. Mattel's seven files each show two activity
bursts. Screening flags the need to inspect and listen; it does not establish
musical event boundaries, prove every burst is a strike or select a trim.
Long Pearl recordings, Wavedrum fills, Sideman rhythms and Polivoks grooves
also need content-specific assessment. A filename or duration alone does
not prove that a file is a loop or a clean one-shot.
