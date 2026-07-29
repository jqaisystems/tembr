# Roadmap

Honest and short. No dates.

- **Fine-tuning.** Zero-shot cloning conditions on ten seconds and will
  always carry some take-to-take variance. Training a voice on 10 to 60
  minutes of speech is what permanently nails accent, similarity and proper
  names. The studio already banks full recordings with every voice for
  exactly this.
- **More languages.** Engine routing is per language; adding an engine that
  does a language better than the current pair is a small, contained change.
- **Window curation refinements.** The best-ten-seconds scan is energy and
  pitch based today; there is room for smarter scoring and for letting the
  ear pick between the top few windows.
- **REST surface for automations.** The API is already local FastAPI;
  a stable documented surface for external pipelines is the missing piece.
