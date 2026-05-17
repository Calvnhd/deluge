# Fix references

Bunch of stuff going wrong with this one.  Combing through and making fixes.

---

## Flow

fix_references.py
  - main()
    * parse `--apply` arg.  
        - Deleting this.  Will likely want to re-add in the future to chain together a bunch of stuff automatically, but I'm tired of the noise created by features that I don't yet need.
        - I think I deleted another arg here yesterday, maybe for manifest selection? Also not something we actually need rn.
    * get_deluge_root() [cli_utils.py] - all good
    * read_manifest() [syncing.py] - changed some var names for readability, consolidated `FileRecord` to include `hash`
    * compute_migration_map()
        - added warning for empty manifest, and moved manifest read `for` loop into `else`
        - altered `MigrationResult()` structure too
    * classify_ref_changes()
        - heaps of changes
        - only have planned changes and errors - don't need to think about missing or recovered
    * preview and apply
        - got rid of auto apply flag
        - heaps of changes to match classify changes
    * _update_manifest_keys
        - 
