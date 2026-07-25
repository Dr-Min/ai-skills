# Min Edit Seedance 2.0

[中文](README-zh.md)

[Agent skill](https://agentskills.io) for writing effective video generation prompts for [Jimeng Seedance 2.0](https://jimeng.jianying.com/), ByteDance's multimodal AI video generation model. This edition adds Higgsfield MCP media-role and payload guidance to the original prompt-writing workflow.

Covers input constraints, @ reference syntax, camera language, prompt structure patterns, ready-to-use templates, and validated Higgsfield MCP roles such as `start_image`, `end_image`, `image_references`, `video_references`, and `audio_references`.

## Install

### Option A: Skills CLI (recommended)

```bash
npx skills add Dr-Min/min-edit-seedance-2-0
```

### Option B: Codex manual install

```bash
git clone https://github.com/Dr-Min/min-edit-seedance-2-0.git ~/.codex/skills/min-edit-seedance-2-0
```

The skill is available to Codex on the next turn.

### Option C: Claude manual install

Clone or download this repository, then copy the skill file(s) to your Claude skills directory:

```bash
mkdir -p ~/.claude/skills

# English
cp SKILL.md ~/.claude/skills/seedance-prompt-en.md

# Chinese
cp zh/SKILL.md ~/.claude/skills/seedance-prompt-zh.md
```

Then ask your AI agent to help you write a Seedance 2.0 video prompt.

## Skills

| File | Language | Description |
|---|---|---|
| [SKILL.md](SKILL.md) | English | Prompt writing guide for Seedance 2.0 |
| [zh/SKILL.md](zh/SKILL.md) | 中文 | Seedance 2.0 提示词撰写指南 |

## Sources

Based on official ByteDance documentation:

- [Seedance 2.0 User Manual](https://bytedance.larkoffice.com/wiki/A5RHwWhoBiOnjukIIw6cu5ybnXQ) — Parameters, interaction methods, multimodal capabilities, and example prompts
- [Seedance 2.0 Real-world Cases](https://bytedance.larkoffice.com/wiki/LJXzwehluiFdzKkb1recZdfonZg) — Drama production, e-commerce ads, dance imitation, science education, AI MVs, and more

## Attribution

Adapted from [dexhunter/seedance2-skill](https://github.com/dexhunter/seedance2-skill) under the MIT License. This edition adds Higgsfield MCP integration guidance and keeps the original copyright notice.

## License

[MIT](LICENSE)
