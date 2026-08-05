# QA + promote

## Entry points

- CLI: `ae qa`, `ae promote-check`
- QA: [`src/agentic_editor/editor/qa.py`](../../src/agentic_editor/editor/qa.py)
- Skill: [`skills/agentic-editor/SKILL.md`](../../skills/agentic-editor/SKILL.md)

## Behavior

- Extracts frames around output-timeline cut boundaries into `edit/verify/`
- `edit/promotions.md` lists fixes to push into the framework
- Multi-root workspace: [`examples/episode.code-workspace`](../../examples/episode.code-workspace)

## Test

```bash
uv run ae qa /path/to/episode
uv run ae promote-check /path/to/episode
```
