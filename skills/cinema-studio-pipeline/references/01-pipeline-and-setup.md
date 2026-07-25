# 01 — Pipeline, workspace & asset naming

Covers: the four handoffs in detail, why work happens in Claude Cowork, the file
types you'll meet, the one-handoff shot-record workflow, and the `@type_project_name`
naming contract.

## The handoffs, in detail

Each receiving stage must get something more useful than an idea:

| Handoff | What crosses it | Why the next stage needs it |
| --- | --- | --- |
| **Brief → Setup** | An agreed brief shaped with Claude: the shot, world, cast, props, constraints | Setup can create the right homes instead of guessing. |
| **Setup → Generation** | A project, useful folders, one naming contract | Every candidate has an address; approved work becomes a reusable `@loc_`, `@char_`, `@prop_` Element instead of an orphaned file. |
| **Generation → Seedance** | Proofed, named location, character, and prop Elements | Seedance combines the actual source pixels. A defect here is multiplied in motion. |
| **Seedance → Review** | A motion test **and a diagnosis** | Review can approve, or send one specific source back for correction. |

**Setup defines the address; generation earns it.** A file does not become production
input merely because it exists. First inspect it, then approve it, name it, save it as
an Element.

## Why Claude Cowork, not a plain chat

Almost everything starts as a conversation with Claude — but not a throwaway chat.
Work in **Cowork mode** (the Chat/Cowork selector in the message box on the Home tab),
because a project needs a memory and a place for its files.

- **Memory across chats** — inside a Cowork project, context carries over: the story,
  the characters, the look you've agreed on. You stop re-explaining the project every
  morning. **Turn Memory on in settings before you start a real project** and turn on
  *Generate memory from chat history* — the whole value of Cowork only works when
  memory is enabled.
- **Local files** — assets live in the project folder on your machine, where Claude
  can read and reuse them. This requires the **desktop app** (Cowork is also on web and
  mobile in beta, but local file access is desktop-only).

Approved assets get saved in **two places**: the local Claude folder for the project,
and your normal project folder where you keep every related file. Asset names start
with `@` — that's the hook that pulls them straight into a prompt later.

## The three file types

- **`.md`** — plain-text Markdown. Used for notes, instructions, and skills.
- **Skill** — a folder of `.md` instructions (a `SKILL.md`) holding the rules for one
  topic; Claude opens it when a task fits and works to that standard. A skill isn't
  magic — it's a pre-written handbook that keeps Claude on one standard instead of
  improvising. Not every `.md` is a skill; sometimes it's just a system prompt.
- **`.jsx`** — technically a code file, used here as a **shotlist**: a structured
  container for shot data (shot numbers, descriptions, timings, prompts) whose fields
  Claude reads and pulls from.

## The one-handoff workflow (project files → one shot record → Cinema Studio)

Don't ask Claude to "make the prompt" in isolation. Give it the production record
first: the **scene brief `.md`** (story beat, approved references, exact `@` Element
names, identity), the **relevant `SKILL.md`** (rules for this kind of prompt), and the
**current `.jsx` shotlist** (shot number, timing, continuity). Tell Claude which files
are authoritative — memory helps it recall the project but does not choose the latest
brief for you.

Example request (replace the bracketed values with the real shot):

```
Use the scene brief, approved reference images, relevant SKILL.md, and current
.jsx shotlist in this Cowork project.

Prepare shot [number] only. Preserve the story beat, continuity, and approved Element
names. If a missing decision would change the shot, ask before writing. Do not invent
an Element.

Return one record with exactly this structure and no preamble:
{
  shot: "[number]",
  description: "[one-sentence action and framing]",
  duration: "[seconds]",
  elements: ["[@name]", "[@name]"],
  prompt: "[one complete, standalone Cinema Studio prompt]"
}
```

Then: review the record in Claude, save it into the `.jsx` shotlist. Cinema Studio
does **not** ingest that whole file — open the right project and folder, paste the
`prompt` value into the Prompt Box, and select every `elements` entry through the `@`
picker. For a video shot, carry over `duration`. Before generating, the visible `@`
tags should match the record exactly.

## Project structure

Three moves take an empty workspace to a first shot: **create and name a project**
(its workspace opens), **add a folder** (name and confirm), **generate**. For a real
production, spin up one project named for your scene holding three folders:
`locations`, `characters`, `props`.

## The asset naming contract

An approved asset only pays off if you can retrieve it. Uploading a file from the
Cowork project folder creates a reusable **Element** on Higgsfield — the local file and
the Element are different; a later prompt calls the Element by its saved `@` name.

Pattern: **`@type_project_name`** — three type prefixes, one shared project tag, then a
descriptive name.

| Prefix | Names | Example |
| --- | --- | --- |
| `@loc_` | Locations | `@loc_HG_museum_front` |
| `@char_` | Characters | `@char_HG_jaxx` |
| `@prop_` | Props | `@prop_HG_phone` |

- The middle tag is the **project prefix** (e.g. `HG` for Hell's Grind). Agree on a
  short team code at kickoff so names stay collision-free across films.
- Join multiword descriptions with **underscores** (`museum_front`), never spaces or
  hyphens.
- Cinema Studio adds the leading `@` when the Element is created; use the full address
  to refer to or select it later.

Skip the standard and Claude can reference the wrong asset while you hunt through the
picker. The type and project segments are what make retrieval reliable.
