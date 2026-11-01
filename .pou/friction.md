# Friction log

- 2026-10-12T12:30:17.427Z The existing Python test suite stops during collection on stale imports in test_deluge_sdk.py and test_fix_references.py; a pou test command must expose this baseline failure rather than skip those tests.
- 2026-10-26T05:14:18.236Z The full Python test suite cannot collect test_deluge_sdk.py and test_fix_references.py because they import update_sample_refs, which fix_references.py does not export; unrelated catalogue tests must run with those files excluded.
- 2026-10-26T05:14:54.967Z After excluding the two uncollectable reference-repair test files, two existing sync_to_sd tests still fail because they patch sync_to_sd.shutil.copy2 but that module has no shutil attribute.
