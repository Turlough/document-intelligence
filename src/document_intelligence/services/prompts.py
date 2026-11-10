DEFAULT_EXTRACTION_PROMPT = (
    "Read this document image. Extract every visible labeled form field. "
    "Reply with JSON only — no markdown. Use this shape:\n"
    '{"fields": [{"name": "<label text>", "value": "<value text>", '
    '"label_bbox": [x1, y1, x2, y2], "value_bbox": [x1, y1, x2, y2]}]}\n'
    "Coordinates are Qwen-style integers from 0 to 999 (relative to image width and height). "
    "Use null for a missing box when text is inferred but not visible.\n\n"
    "Also add optional entries to the same fields array (only when true; omit when false; "
    "never output No):\n"
    "1) Garda Signature — value Yes if the Garda Signature area contains a handwritten "
    "signature (not printed empty lines). Include value_bbox around the signature when Yes.\n"
    "2) Photograph attached — value Yes if the page contains a photograph of a person's "
    "face or ID-style portrait (not an empty photo box). Include value_bbox around the photo "
    "when Yes.\n"
    "3) Cheque attached — value Yes if the page contains a bank cheque (MICR line or cheque "
    "layout; not a checkbox or the word cheque alone). Include value_bbox around the cheque "
    "when Yes.\n"
    "Use exactly these names: Garda Signature, Photograph attached, Cheque attached."
)
