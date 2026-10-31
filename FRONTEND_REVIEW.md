# Streamlit frontend implementation and review

The user directly authorized implementing the Streamlit interface with a subtle
landing page while the backend V4 publication was in progress. No teammate UI
files were present in this workspace; preserve their local work before pulling
or copying this implementation.

## Files and implementation

- app.py composes the page, native upload control, explicit offline/hosted mode,
  ingestion spinner and workspace. Offline is the initial UI choice.
- ui/session.py owns document identity, one load attempt per content/mode, explicit
  retries, stale-state clearing, question validation and safe error messages.
  Navigators live only in st.session_state; there is no global navigator cache.
- ui/views.py renders the landing, workflow explanation, answer form, citation
  excerpts and physical PDF page viewer. Questions run only on form submission;
  page navigation preserves the answer and does not call the model again.
- ui/styles.css defines a white/navy/teal editorial design with serif headings,
  responsive spacing and native widget styling. Only static trusted design
  markup uses st.html; report text, filenames and model answers use safe text.
- .streamlit/config.toml sets the light theme, 50 MB upload cap and disables usage
  telemetry. It contains no credentials. The local .env remains private.
- tests/test_frontend.py tests document/mode/removal lifecycles, explicit retry,
  blank questions, missing-key/provider-error behavior, landing rendering and
  workspace reruns using mocked API behavior. No cloud call is made in tests.

Run from the project directory with Python 3.11 and installed requirements:
`python -m streamlit run app.py`.

## Validation and fidelity ledger

122 backend/frontend tests passed (112 backend tests plus ten frontend cases).
The ten frontend cases were rechecked after the static icon fix.
Ruff basic/import checks and formatting passed after fixing import order.
The IAB API failed with an unavailable-browser-interface error, so visual and
functional checks used local Playwright Chromium with an existing browser binary.
Native Safari was used separately for GitHub publishing.

The generated visual concept and rendered screenshots were inspected with
view_image. Desktop viewport: 1505x1045, matching concept dimensions. Mobile:
390x844; no horizontal document overflow. The comparison checked:

1. Palette: true white background, navy ink and muted teal matched the concept.
2. Layout: full-width upload, vertical mode choice, three text-only workflow
   columns, thin dividers and quiet footer preserve the concept structure.
3. Typography: large serif two-line heading, serif brand and sans native controls.
   Font rendering differs slightly from the generated reference.
4. Spacing: corrected the maximum content width to align the left/right gutters;
   hid Streamlit's developer toolbar where it overlapped the team label.
5. Copy: headline/intro/header/step titles/footer preserved. Intentional functional
   copy changes clarify exact-count offline questions, source verification and
   that offline mode avoids cloud models. We do not promise uploads stay on a
   user's computer when the app is eventually hosted on a remote server.
6. Native controls: the installed Streamlit version renders an Upload button
   rather than the concept's Browse files arrangement. Keeping the native control
   preserves keyboard access, file selection and upload validation.
7. Responsive layout: workflow columns stack on narrow screens; native workspace
   columns adapt to available width. Main text and controls remain readable.

The interface was verified against the generated design with these explicit
native-widget, font-rendering and functional-copy deviations; no raster mockup is
used as UI. Concept and QA screenshots are saved outside the source package.

A browser test uploaded only an invented PDF, obtained 83 [E1] with a real source
page, checked an absent entity's abstention and switched to hosted mode to verify
its disclosure. It did not submit a hosted model question. Earlier backend V3
live tests established configured Gemma access using synthetic evidence.

## Critical review and limits

- Actual OCR digit errors remain the backend V4 limitation. The interface exposes
  source evidence and warnings; it does not present confidence as a probability.
- Hosted mode requires internet and sends the question/retrieved evidence to
  Google. It is explicitly labelled as separate from offline scoring. There is
  no automatic fallback and no claim of Gemma prize eligibility.
- The app is deployed at https://sloths-report-navigator.streamlit.app on
  Python 3.11. Anonymous access, native offline answers, Linux OCR and hosted
  Gemma passed synthetic end-to-end checks. Full-report concurrent workloads
  and organizer sandbox resource limits have not been verified. Public hosted usage could consume the account quota;
  access/usage policy should be decided before a broad public launch.
- Unexpected errors show generic safe messages. For deliberate BackendError,
  only its safe message is displayed; raw exceptions/credentials are not shown.
- The first report load remains synchronous and can take about a minute for the
  full supplied report. The spinner is honest; no fake progress is displayed.
- Each upload/mode change resets answer/page state. A failed load waits for an
  explicit Retry opening report action instead of retrying on every rerun.
- The V4 cache fingerprint changes require a fresh load after a backend update.
  Restart the app and re-upload when updating an already-running process.


## Refinement after deployment

The user requested a more appealing but simple interface. app.py now arranges
upload and mode selection in one setup area. An initial presentation-only rerun
collapses report settings after successful ingestion, bringing answers and the
PDF into view; the existing load-attempt guard prevents re-ingestion. Removing
an upload restores the landing. A new AppTest covers that transition and a real
browser test verifies uploader persistence, reopening settings and removal.

ui/views.py adds a small document mark and a centered headline with a teal source
accent. Streamlit sanitizes inline SVG, so ui/document.svg is rendered through a
static image data URI, preserving the sanitizer. ui/styles.css was consolidated
into one token-based stylesheet, with a pale setup surface, two desktop columns,
three workflow columns and stacked mobile controls. No backend behavior changed.

A fresh development process was used to avoid cached imported UI modules. Browser
checks confirmed the icon loads, the accent is rgb(39,108,100), no horizontal
mobile overflow, collapsed setup, correct answer 83 with page 1, and restored
landing after removal. Desktop 1505x1045 and mobile 390x844 screenshots were
compared with the revised generated concept using view_image. Header/icon,
headline hierarchy, white/navy/teal palette, setup grouping, workflow dividers,
spacing, native controls and mobile stacking were inspected. The installed
Streamlit uploader and font rendering remain explicit native-widget deviations.
The visible headline, intro and workflow titles match; safety/disclosure copy
explains actual supported behavior. No fake charts, metrics or report data were
added to the product.

Accuracy was rechecked on the 50 supplied development questions: exact match,
citation accuracy and composite score 1.00, hallucination rate 0/5 on absent
questions. Runtime 64.89 seconds, 260/272 pages indexed. These are in-sample
results, not hidden-report accuracy. Dense scanned reports still have documented
failures, including misread digits. Generated QA PDFs and outputs are excluded
from source releases. Deployment secrets remain outside GitHub.
