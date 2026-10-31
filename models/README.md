# Offline OCR asset

`tessdata/eng.traineddata` is the unmodified official Tesseract fast English model
from revision `87416418657359cb625c412a48b6e1d6d41c29bd` of
https://github.com/tesseract-ocr/tessdata_fast.

SHA-256: `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.
Size: 4,113,088 bytes. This is a public pretrained OCR asset, not report-derived
content or a memorized challenge model. Its URL/hash are declared in
`submission.yaml`. Keep it at `models/tessdata/eng.traineddata`, or point
`TESSDATA_PREFIX` at its containing directory in the demo environment.

The PyMuPDF wheel's Tesseract integration runs this asset locally. No Tesseract
CLI, cloud OCR, GPU or inference download is required by the scoring command.
The model is distributed under the Tesseract model repository's Apache-2.0
license; see `tessdata/LICENSE` for the original license text.

`train.py` can reproduce `pipeline.json`, containing only generic configuration
and the OCR asset hash. Never add pre-extracted report text, table records,
challenge answers or public-question lookups to this directory.
