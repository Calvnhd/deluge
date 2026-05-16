# phase 1

- record data in json to track changes
- write ALL files into a json file with the following info recorded
    * full path and filename relative to zzzort
    * SHA256-hash
- create this json using a bash or python script so it can be used to generate multiple jsons

# phase 2

- reorganise all wav into new folder categories based on keywords or description in their name
- Best guess is fine -- this is just a first pass

| NEW FOLDER | DESCRIPTION |
|--|--|
| BASS | Any bass guitar or synth or other low register sounds |
| FX | Sounds effects, environmental effects, non-musical |
| KEYS | Keyboard, piano, organ etc |
| MULTI | Multiple instruments - no single dominating  |
| PERC | Drums, drumkit parts, cymbals, other percussion |
| STRINGED | Orchestral or guitar or anything |
| SYNTH | All synth sounds, leads, pads |
| VOCAL | Any voice |
| WIND | Wind instruments, sax, trumpet, brass, reed, flute |

# phase 3

- record all data again to NEW json file
- compare before and after, ensure no files are lost