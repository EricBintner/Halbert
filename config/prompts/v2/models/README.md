# Model Notes

Halbert does not recommend or list specific models. Configure whichever models
your endpoint serves in Settings → AI Models; the prompt system adapts to the
configured model's size and behaviour through the override files in this
directory.

## Override Files

- `small-model-overrides.xml` - Stronger, more repetitive constraints for
  smaller models (roughly 7B-14B parameters) that need extra reinforcement.
- `reasoning-model-overrides.xml` - Handling for models that emit
  `<think>...</think>` reasoning blocks before their answer. The reasoning is
  captured separately and shown to the user as a collapsible "Reasoning"
  section.

Only `.xml` files in this directory are loaded by `PromptLoader`; this README
is documentation only.

## Sizing Guidance

Choose a model by memory budget rather than by name. As a rough rule, a
~14B-parameter model at 4-bit quantization fits in ~10 GB, and a ~32B model at
4-bit needs ~20 GB. Pull a model of your choice with `ollama pull <model>` and
select it in Settings → AI Models.
