# Translation review

The 50 catalogs are **initial translations, not native-speaker-reviewed releases**. No native review is claimed for any language. The two new recovery messages currently have English and Estonian catalogs; other languages intentionally use English fallback pending review.

Native reviewers can open a Translation review issue using the repository's issue form. Review and record:

1. Language code and reviewer attribution (with consent).
2. Menu label and description: the action reboots into another operating system once.
3. Confirmation: users must save work before accepting. Confirm Yes/No have their intended meaning.
4. Picker: metadata cannot identify a unique macOS installation; the user must identify it.
5. Recovery: successful rollback means no one-time selection remains; failed rollback means the next restart may still boot macOS.
6. `%1` must remain in the confirmation and receive the unmodified volume name.
7. In Arabic, Persian, Hebrew, and Urdu, check the actual native dialog with a Latin, non-Latin, long, and markup-shaped disk name.

The native dialog uses Qt's right-to-left mirroring, text wrapping, plain-text rendering, and directional isolates around the volume name. The terminal CLI remains a fallback; terminal shaping depends on the terminal and font.

Automated checks validate catalog keys and placeholders, fallback, and literal volume names. Rendering checks establish layout behavior, not linguistic correctness. Keep review status honest: a passing test is not a native-speaker review.

## Review record

| Language | Linguistic review | Rendering check |
|---|---|---|
| All 50 | Pending native review | See VERIFY.md |

Add dated, attributed review results here when actually completed.
