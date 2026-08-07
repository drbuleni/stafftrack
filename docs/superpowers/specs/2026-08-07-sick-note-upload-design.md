# Sick Note Upload — Design Spec

**Date:** 2026-08-07
**Author:** Vernon Sibiya (with Claude)
**Status:** Approved, ready for implementation

## Problem

Staff apply for sick leave in StaffTrack, but the doctor's certificate lives outside the system —
on paper, in WhatsApp, or in somebody's email. The approver has no proof attached to the request,
and six months later, when a leave record is questioned, the certificate cannot be produced.

## Goal

A staff member can attach the doctor's note to a sick leave request. The approver can open it
while reviewing. The note stays attached to the leave record permanently.

## Decisions

- **Always optional.** A note may be attached to sick leave of any length, including a single day.
  Nothing is ever blocked for want of a certificate. (Considered and rejected: requiring a note for
  absences over two days, as the BCEA permits. Vernon's call — staff who have a note should be able
  to attach it, and staff who do not should not be stopped from applying.)
- **Sick leave only.** The upload field does not appear for annual, family responsibility, unpaid
  or other leave.
- **Stored in the Supabase database.** Not on the server filesystem.
- **Visible to the owner and approvers only** — the staff member who submitted the leave, plus
  Practice Manager and Super Admin.

## Why not the filesystem

The existing SOP feature saves uploads to a local folder (`app/routes/sop.py`, via
`UPLOAD_FOLDER`). Render's filesystem is ephemeral: every deploy and restart discards it, so those
files are already being lost unless a paid persistent disk is attached. A sick note is precisely
the document someone needs to produce months later, so it cannot use that pattern.

Storing bytes in Postgres keeps the note transactionally bound to its leave record — it cannot
orphan, and it survives every deploy with no new service or credentials. At this practice's volume
(roughly 20–40 notes a year at 1–2MB) this costs tens of megabytes a year, comfortable on the
current plan. If volume ever outgrows that, the migration path is Supabase Storage, which needs a
bucket and service key added to the environment.

**Out of scope:** fixing the SOP upload bug. Same class of problem, same fix, but a separate
feature. To be done as its own job.

## Data model

A **separate table**, not a column on `leave_requests`. The leave index, calendar and entitlements
pages all query leave records in bulk; a binary column on that table would pull every stored file
through memory on each of those page loads.

```
leave_documents
  id                integer, primary key
  leave_request_id  integer, FK leave_requests.id, not null, indexed
  filename          string(255)    original name, sanitised
  content_type      string(100)    e.g. application/pdf
  byte_size         integer
  data              LargeBinary    the file itself
  uploaded_by       integer, FK users.id, not null
  uploaded_at       datetime
```

Deleting a leave request deletes its documents (cascade).

## Constraints

| Rule | Value |
|---|---|
| Accepted types | PDF, JPG/JPEG, PNG, WEBP |
| Maximum size | 5MB per file |
| Files per request | One |
| Shown for | Sick leave only |
| Required | Never |

Images are first-class: a phone photograph of a paper certificate is the realistic case, more
likely than a PDF.

## Flows

**Applying.** The request form shows a file field when Leave Type is Sick, hidden otherwise
(client-side toggle, plus a server-side check so a note submitted with a non-sick type is ignored).
On submit, the file is validated and stored in the same transaction as the leave request.

**Approving.** The approval screen shows a panel with the note's filename, size and upload date,
and a button that opens it in a new tab. If no note was attached, the panel says so plainly.

**Listing.** Leave rows that carry a note show a paperclip, so an approver can see at a glance
what is documented.

**Serving.** One route, `/leave/document/<doc_id>`, streams the file. It checks on every request
that the viewer owns the leave or is a Practice Manager or Super Admin — the document ID alone is
never sufficient. Files are served with their stored content type, `Content-Disposition: inline`,
and `X-Content-Type-Options: nosniff` so a disguised file cannot execute as a web page.

## Error handling

Every failure keeps the user's typed input and explains itself:

| Case | Behaviour |
|---|---|
| Disallowed file type | Request rejected, message names the accepted types |
| File over 5MB | Request rejected, message gives the limit and the file's actual size |
| File over the 8MB request cap | Werkzeug refuses it before any view runs; a 413 handler flashes a readable message and returns the user to the form instead of showing a bare error page |
| Empty file selected | Treated as no file; request proceeds |
| Non-sick leave with a file | File ignored, leave request still created |
| Viewer not owner or approver | 404, so the response reveals nothing about whether the document exists |

`MAX_CONTENT_LENGTH` is raised from 5MB to 8MB so that an oversized sick note reaches our own
validator and receives the specific message above, rather than being truncated by Werkzeug first.
The 8MB cap remains as the outer guard, now handled gracefully.

Existing leave records, which have no documents, continue to work untouched.

## Testing

1. Attach a PDF to sick leave; retrieve it and assert the bytes match exactly.
2. Attach a JPEG; assert the correct content type is served.
3. Reject a file over 5MB, with the size in the message.
4. Reject a disallowed extension.
5. Submit sick leave with no file — succeeds, since a note is never required.
6. A different staff member requesting the document gets 403.
7. A Practice Manager can open another staff member's note.
8. Deleting the leave request removes the document row.
