# Ref script improvements

extract_sample_refs
    - there's a bit of trust here that we've caught all possible cases for xml files. Give it a more thorough look against the actual xml files
    - preset_name is always gonna be the name of an xml file.  It's only useful in a song where the embedded preset name differs from the xml.
    - consider renaming some of these variables?
parse_xml
    - the xml fallback feels weird. Look into how this is treated. Add logs or something. Maybe do something about the error catch
    - returning tree and recovered only actually matters for write, whihc needs redoing entirely
check_references
    - Is that except block necessary?  Might be better to just crash so I notice it lol. Or throw a proper error. I think this might be dead anyway cos it's caught in the called function??
update_xml
    - this does a bunch of dumb stuff. Get to it later. Look at how it treats tree and recovered (from parse, which needs reviewing itself!)
    - Also should update path only, not entire xml
