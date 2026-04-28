# Extract instruments

This file contains high level information for a new script to be written.  This script will analyse all the saved songs and the kits and synths they use.  It will then extract the embedded kits and synths for each song, and store them in a new folder.  This will give the user easy access to custom presets that they are already using.  All xml edits will be made in the local repository -- the user can sync back to the SD card when they are ready.

## Notes on SONG structure and embedded instruments

- Songs are stored as xml files under `DELUGE/SONGS/`
- Songs contain instrument information embedded in their xml file. Many (but not all) of these instruments will have been loaded from a preset KIT or SYNTH but are likely to have been tweaked and customized to suit the song
- When using the Deluge, songs are organised by clips. A clip represents exactly one synth, kit, midi, or audio file, as well as instructions on how to play that instrument (e.g. note sequencing data, effects, levels). This script is only interested in synth and kit clips.
- Clips can be stored with multiple versions represented by one of 12 colours. This allows the user to sequence a different pattern of notes for different sections of a song. 
- Generally (but not always), the parameter changes for the instrument itself between colour versions are minimal (e.g. slight change in level or automation). 
- Generally (but not always), an instrument will only have one clip per colour, therefore there should be no more than 12 versions of a given instrument for a given song.  
- Songs are also organised into an arrangement (a series of clips in a specified order), which may contain custom instruments, clips, and automation. This feature should be ignored for the purpose of this script.
- The actual XML representation of all of this information is not yet understood.
- Presently, all songs use `firmwareVersion="c1.2.1"`.  We should add a safety check for this version. The script only needs to be able to handle this version.

## Clip extraction guide

- To reduce noise, we must determine a system to choose which version / colour of a clip to extract the instrument from.  Ideally, even if a song contains many clips of the same instrument, we should only take one version / colour of it from that song. This is so we do not end up with many near-identical versions of the same instrument.  
- Multiple versions of a synth or kit may be extracted if and only if they are sufficiently different from each other.
- Add a default option to take the first clip version found, or a extended option that makes the version comparison and selection.
- The default clip colour is light blue.  Creating a new clip with the same instrument sets the next colour in the following order: light blue, pink, gold, cyan?, red, yellow, dark blue, orange, purple, yellowy-green, green, lighter-purple (magenta?). The official names of these colours or how they are recorded in the xml is not yet known. 
- When selecting an instrument version, favour versions early in the colour order

### Synth selection

- `/home/caldavidson/source/deluge/DELUGE/SYNTHS/Init-Synth.XML` is a fresh initialized synth with no changes. Use this as a template.
- compare parameters to determine how different the versions are. This system will take some refining. We will need to review stats like number of different parameters, range value of differing parameters, which parameters represent big changes and which can be safely ignored. Depending on the results of this analysis, select one or more versions to save.
- Ignore master volume. All extracted synths should be saved with a standardized volume matching the init synth.
- Ignore master pan. All extracted synths and kits (and kit rows) should be saved with a standardized pan matching the init synth (should be centred)


### Kit selection

- `/home/caldavidson/source/deluge/DELUGE/KITS/Init-Kit.XML` is a fresh initialized kit with no changes. Use this as a template.
- Kits contain multiple rows, one for each sample. Settings can be applied to either an individual sample, or for the entire kit (when affect entire is selected). When extracting kits, it's important that params for individual rows and the entire kit are preserved
- Ignore master volume. All extracted kits should be saved with a standardized volume matching the init kit
- Preserve row volume. The volume for individual rows (i.e. sounds, samples) should be preserved
- Ignore master pan. All extracted synths and kits (and kit rows) should be saved with a standardized pan of 0 (centre)
- Preserve row pan. The pan for individual rows (i.e. sounds, samples) should be preserved

## Proposed execution flow

- Load .env DELUGE_ROOT
- Discover all song xmls in DELUGE_ROOT/SONGS/.
- Iterate through each song xml 
    - Check the firmware version
    - Analyse what instruments are used. Discover all synths and kits (ignore MIDI and AudioClip)
    - For each synth and kit...
        - If there exists only one version (i.e no different clip colours), select it for saving 
        - If there are multiple versions, evaluate their differences and select one or more to save
    - Song XMLs must remain unedited
- Check the destination folders for existing XMLs.  These can be sent to `.trash` -- this script will produce a fresh set of XMLs each time. 
- Save the synth(s) in an accurate, functional, standardized format for `firmwareVersion="c1.2.1"` to `DELUGE/SYNTHS/SONG-SYNTHS/<SongName>-<PresetName>-<ClipIdentifier>.XML`
- Save the kit(s) in an accurate, functional, standardized format for `firmwareVersion="c1.2.1"` to `DELUGE/KITS/SONG-KITS/<SongName>-<PresetName>-<ClipIdentifier>.XML`