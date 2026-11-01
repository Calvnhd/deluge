export default {
  verbs: {
    test: 'uv run --directory scripts --locked --extra dev python -m pytest',
  },
  doctor: [
    {
      name: 'uv',
      run: 'uv --version',
      fix: 'Install uv and ensure it is available on PATH.',
    },
  ],
  briefings: {
    test: {
      summary: 'Run the Python test suite',
      purpose: 'Validate the Deluge management scripts with pytest.',
      inputs: 'No arguments; runs the full configured test suite.',
      prerequisites:
        'uv on PATH; access to Python 3.12 and locked development dependencies, locally or through downloads.',
      sideEffects:
        'May create or update scripts/.venv, download Python or dependencies, and write test caches.',
      outputs: 'pou result envelope containing pytest output and command outcome.',
      recovery:
        'Resolve environment, lockfile, collection, or test failures, then rerun pou test.',
      proofBoundary:
        'Runs pytest using scripts/pyproject.toml; does not run lint, type checks, or validate a real SD card or cloud backup. Readiness checks only establish uv availability, not Python or dependency readiness.',
    },
  },
};
