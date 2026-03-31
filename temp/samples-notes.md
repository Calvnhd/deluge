# Notes

## SAMPLES folder & scope

Presently there are several hundred samples.  The SD card is 32GB an in theory could hold several thousand samples.  In practice, I don't expect it to get much larger than 1000 in the near future.  The folder structure will likely be 3-4 levels deep, but this is subject to changing over time.  I expect I will update and iterate over the structure a few times before I settle.  As an example, my current thinking is something like `DELUGE/SAMPLES/<sample-origin>/<instrument>/<secondary-category>/some-sample.wav

All samples MUST be .wav (or .WAV for case sensitivity reasons) -- perhaps the script should flag if the incorrect format is detected

ARTISTS/ folder should be included in the manifest and may be rearranged or expanded

CLIPS/, RECORD/, RESAMPLE/ — Deluge-generated recordings should these be included in the manifest. It's highly likely I will rearrange some of these into other folders -- e.g. group recordings from a specific session into a dedicated project folder, delete old or bad takes.  However, these directories must NEVER be deleted, and must NEVER contain subdirectories.  This is so the deluge recording behaviour stays consistent.  I will only ever rearrange these directories by removing their contents (either to another directory or deleting a sample)

## Manifest (Script 1)

How much overhead will a python dependency add?  I am comfortable, provided it doesn't add much complexity or time. Also, is it possible to get the date of creation for a sample? 

File names are probably going to be the most reliable source of information.  Some samples are called things like `kick-oneshot-120bpm-techno` or something. It's very inconsistent though. The path might give some extra info like `SAMPLES/TROPICAL-HOUSE-PACK/ONE-SHOT/bassline.WAV`.  Other recordings are just called `rec-0001.WAV`.  Some samples aren't even musical, they are environmental sounds or effects.  Consistency is the goal, but that will never happen 100%.  For now, I just want ANY useful information I can get to help me understand what the file might contain before I listen to it.  This will speed up my decision-making when it comes time to rearrange. 

JSON and .csv sounds great.

Save them to `docs/manifests/sample-manifest-<date>.json`

Favour simplicity and reliability -- let's generate it from scratch each time. 

The manifest should list ALL referencing songs, as well as the synth / kit name IN THAT SONG which uses the sample. Note that synth/kit information is embedded in songs independent of synth/kit xmls. The EMBEDDED synth and kits should be listed next to the song name. Also note that a synth or kit may have multiple variations within a given song -- in this case you should treat all synths / kits with the same name as being the same.
The manifest should list should count of all songs, synths, kits that are using a sample. Be sure to not double count embedded synths / kits.  A song that uses a sample should only count as 1, even if multiple kits or synths use that sample within the song xml.
The manifest should list the first synth and kit using a sample only.  This is provided as a single reference example for the reader. If required, they can see the total count as greater than one and do another search.  Perhaps we can create another script that takes a sample name as input and lists more comprehensive use information?

## Reference fixing (Script 2)

Files will likely be renamed.  Some samples may even have the same file name e.g. `SAMPLES/TROPICAL-HOUSE-PACK/ONE-SHOT/bassline.WAV` vs `SAMPLES/70s-FUNK/ONE-SHOT/bassline.WAV` -- therefore path recognition will not work.  Will hashing solve this?  Are there other options?

Multi-step is fine.

Deleted samples — When a sample is removed entirely (not moved, just deleted), should the reference-fixing tool leave the broken reference as-is, clear it to an empty string, or flag it for manual review?

Samples should only be deleted when they are no longer in use. If a reference still exists, the user has made a mistake. Flagging this error is critical. If the reference fixing tool cannot find the sample, it MUST inform the user of their error so that they can manually resolve it. 

Yes, All XML-modifying scripts should default to dry-run mode (showing what would change) and require an explicit flag like --apply to actually write changes.  However, wherever possible, if dry-run and then applying changes is done in succession, we should not have to wait around for the script to repeat a bunch of work.  Perhaps dry-run first, then confirmation?  What kind of workflow could we use here that balances safety, speed, and ease of use?

I am relying on git for backups. The script doesn't need to worry about that.

## Architecture & tooling

I have no preference for python vs bash.  I like running things in the command line with bash though.  Mostly, whatever is easiest without sacrificing safety / accuracy / reliability.

Shared XML parsing library — The old plan mentions a deluge_sdk.py for shared XML parsing. Both the manifest and the reference-fixer need to parse fileName attributes/elements from XMLs. Should I build this shared module, and should it handle both XML formats I see (element-style <fileName>path</fileName> in kits/synths and attribute-style fileName="path" in songs)?

Reuseable code is great!  This is the first script we're writing. If there are any functions that could be useful in the future (see scripts plan and the README for potential but unconfirmed ideas), then we should begin compiliing a library.  

DELUGE/ root assumption — All sample paths in the XMLs are relative to DELUGE (e.g. SAMPLES/DRUMS/Kick/808 Kick.wav). Should scripts always operate relative to the DELUGE directory, accepting it as a required argument or inferring it from the repo root?

Scripts will be run from within this repository.  Use the scripts folder here as the base assumption.  They will act on DELUGE from within in repository.  Either we can bake that knowledge into the script, or add it to .env.  What makes the most sense there?

A verification step regarding broken references kind of feels like repeated work?  Could be useful though, yeah.  We've already mentioned multi step flow is fine, modular is good.  So maybe lets have this verification step as a normal part of the flow too.  It could inform whether we need to run the rest of the flow.  

Some kind of makefile or wrapper would be handy, yes. 

---

## Additional thoughts

- these scripts will run on the local repo copy of SAMPLES i,e NOT on the SD card and NOT on the external cloud-backed folder.
- In addition to rearranging samples, it's likely that I will rename the file itself too 
- the xml formatting is different between songs / kits / synths AND different again between versions! Take care when writing xml parsing functions. There is no universal format. Presently, all songs use the latest (community v Chopin) format but are subject to change.  Kits and synths use formats from every version from beta all the way through to latest. 

