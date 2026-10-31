# Error analysis

## Evidence and scope

V1 passed 49 code checks but retrieved a listed gold page for only 9 of 45
answerable public questions at six chunks. Passing code checks did not mean the
retrieval was good. V2 initially answered 43/50 public questions exactly; its
40-row candidate set covered all 45 answerable questions' gold pages. General
measure/subtotal and heading rules then improved the public development score.
The current native-report development run is 50/50 exact with valid citations.
This is in-sample: the public questions were inspected and used during development.
No hidden-report score or official evaluator result is available.

## Important remaining risks

- **Different report structure:** the solver is designed around generic table
  labels, entities, years and measures, but was developed on one report family.
  New column naming/layouts or paraphrases may cause conservative abstention.
- **Dense scanned tables:** a basic rasterized table passes, but the sampled
  complex tables showed merged numeric tokens, corrupted labels and multi-level
  header alignment problems. The scanned multi-year city table was subsequently recovered after a year-header
  fix; the denser sampled vehicle table still abstained. This two-page diagnostic
  is not a representative OCR accuracy estimate. Scanned-page searchability is
  not proof that every cell can be answered; low-resolution scans remain a risk.
- **OCR errors:** recognition can change names and digits. No unseen number is
  repaired by memorizing a public answer. Conflicting/unsupported mappings abstain.
- **Confidence:** fixed evidence-strength levels are uncalibrated. Native/OCR
  origin and ambiguity influence them, but confidence bonus eligibility is not
  claimed. A public score of 1.0 does not prove calibration or generalization.
- **Unsupported operations:** multi-year arithmetic, percentages and arbitrary
  prose questions are outside this exact-count solver. They return NOT_FOUND.
- **Runtime budget:** OCR has hard per-page subprocess timeouts. The ingestion
  deadline is checked between native pages; a pathological native table-finder
  call does not currently have its own process-level hard timeout.
- **Environment:** tests run locally on macOS/Python 3.11. The organizer's exact
  Linux 2-core/6-GB sandbox and its build-time asset placement remain unverified.
- **Presentation/metadata:** teammates' names and frontend integration are pending.
  No claim is made that the V2 scorer uses Gemma or qualifies for its prize.

## Integrity

The runtime does not load organizer gold labels, public answers, fixed page
numbers or entity-to-answer dictionaries. All cell candidates and citations come
from the supplied run PDF. Data-derived evaluation outputs are stored outside
this repository. Tests use invented numbers/entities except separate local
report benchmarks. Do not commit reports, answer files or extracted caches.

## V4 measured update

The predeclared generated benchmark contains four one-page layouts: a native dense
table, a scanned dense table, a scanned table with wrapped district labels, and a
scanned dense table with wrapped labels. Each has two answerable questions and one
absent-entity question. Seed 0 improved from 8/12 to 12/12 correct answers with
physical-page checks; answerable questions improved from 4/8 to 8/8. Seed 19, first
run after implementation, showed the same change. Incorrect non-abstaining answers
were zero in both versions on these synthetic cases. This tests the same four
layouts with different values, not unseen-layout or hidden-report performance.
The ordinary benchmark did not need crop retries; its improvement comes from
physical row grouping and header separation. A separate real OCR fault-injection
test verifies recovery of a first-pass token spanning two numeric columns.

The full native public-report output remained byte-identical to V3: 50 records,
SHA256 2cbededae25551654e337b4770383a6de6f62d5da0a47518527a2373b283ddeb.
Runtime was 64.16 seconds locally; 260/272 pages were indexed. No hidden scoring
run or organizer Linux resource verification is claimed.

For a broader diagnostic, physical pages 101 and 241 were rasterized at 144 DPI
and each evaluated as a one-page scan against the public questions listing that
source page. Page 101: 13/17 correct, three incorrect non-abstaining answers and
one abstention. Page 241: 0/12 correct, twelve abstentions. V3 and V4 produced the
same counts. These are deliberately degraded single-page tests, not the native
public-report score; other listed source pages are absent in this diagnostic.
Wrong but well-formed OCR digits remain a material risk. The conservative second
pass does not verify every complete row and does not provide independent OCR
agreement or calibrated confidence. Dense/category-heavy, faint, skewed or
irregular tables remain unresolved. No claim is made that the Gemma prize is
qualified for by this offline extraction work.
