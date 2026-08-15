# Higgsfield Element contract

An Element exists only when its actual saved identity is visible in the authenticated
project. Never infer a remote Element from a local filename or intended name.

## Naming

Use stable project-scoped names such as:

```text
@char_<project>_<name>_<state>_vNN
@loc_<project>_<name>_<state>_vNN
@prop_<project>_<name>_<state>_vNN
```

Store the exact provider tag or ID separately from the human asset ID. Never rewrite a
tag in prompt text for readability.

## Role and state

Record what the Element controls: identity, wardrobe, location geometry, prop shape,
mechanical state, look, or another approved role. One Element must not ambiguously
control incompatible roles. Create a new state asset rather than overwriting an
approved one.

## Proof

Record project/folder identity, Element ID/tag, source asset ID/hash, descriptor
version, state, creation time, and last verification time. An Element may be used only
when the local record and visible remote state agree.
