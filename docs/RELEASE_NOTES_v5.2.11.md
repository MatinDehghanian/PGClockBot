# PGClockBot v5.2.11 — Release Notes

**Tag:** `v5.2.11`  
**App version:** `5.2.11`

---

## Fixes & UX

- Staff note / risk save no longer redirects to a missing `/users/{id}` page (`detail: Not Found`); returns to the users list edit modal.
- Form validation shows Persian messages and red field borders instead of English HTML5 tooltips (e.g. “Fill out this field”).
- Users list: yellow risk dot beside the name when `risk_flags` is set.
- Flush search bars that are the first child of a card get full top padding (users, finance, PG users, …), matching titled cards.

## Deploy

In-panel update to `5.2.11` (or deploy this tag). Hard-refresh the panel.
