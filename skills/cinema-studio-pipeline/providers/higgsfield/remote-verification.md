# Higgsfield remote verification

Use read-only checks before claiming any remote state.

## Verify and record

- authenticated account or workspace context;
- project URL and ID;
- folder name and ID when present;
- exact Element ID/tag and visible source;
- generation job ID, status, model, and UI settings;
- output identity and local downloaded file hash;
- timestamp of the last successful check.

Do not print or store passwords, cookies, API tokens, or other credentials. Do not
inspect browser credential storage.

## Status rules

- Set `remote.verified: true` only while the record matches visible state.
- Mark the verification stale when the configured capability window expires or the
  provider model/UI changes.
- Do not equate a completed job with an approved creative result.
- Do not equate a local folder with a Higgsfield project folder.
- If authentication or access prevents verification, report the boundary and keep the
  artifact local and unverified.

## Offline validator boundary

Local validation can prove that the recorded job ID, evidence file, settings, and
hashes are internally consistent. It cannot authenticate Higgsfield's current server
state by itself. Only an authenticated live UI or API observation can establish that a
remote item really exists and still matches the record. Record the observation time;
do not describe a merely consistent local record as fresh remote verification.

For an offline consistency check, save a hashed JSON evidence package that binds the
provider, project ID, Element/asset ID when relevant, job ID, actual model ID, output
SHA-256, observation time, and evidence paths. The local tools report
`verification_scope: OFFLINE_RECORD_CONSISTENCY` and `remote_truth_verified: false`.
A changed ID or output hash invalidates the package; an internally consistent package
still does not replace a fresh authenticated observation.
