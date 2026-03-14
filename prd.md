# Requirements

Create a simple Python CLI tool that performs OCR on a full PDF book using a free local OCR engine (preferably Surya OCR) and processes the document page by page, converting the PDF to images and looping sequentially through every page while writing the OCR result for each page into a separate Markdown file (`page_XXXX.md`) stored inside an `output/` directory with a subfolder named after the input file; the script must accept the input PDF path as a command-line argument, continuously log progress to both the terminal and a persistent log file (including page number, processing time, character count, warnings for low text extraction, and errors), maintain a `progress.json` file tracking total pages and the last successfully processed page so the run can be safely interrupted and resumed later from the correct page without reprocessing completed pages, ensure there are no silent failures or breakages by catching and logging all exceptions while continuing to the next page, create a Markdown placeholder noting failure if a page OCR operation fails, provide clear real-time observability of execution state, and remain intentionally simple with minimal dependencies (e.g., `surya-ocr`, `pdf2image`, `pillow`, `tqdm`, `python-json-logger`, plus system dependency `poppler`) and straightforward error handling without overengineering, databases, async frameworks, or background workers.


---

# Tool Choice (Recommendation)

Primary OCR engine:

**Surya OCR**

Reason:

* Strong reading-order reconstruction
* Handles **columns and tables**
* Good for **books and PDFs**
* Runs **fully local**
* Apache-2.0 license (free)

Supporting tools:

| Tool               | Purpose              |
| ------------------ | -------------------- |
| surya-ocr          | OCR + layout parsing |
| pdf2image          | convert PDF → images |
| pillow             | image handling       |
| tqdm               | progress display     |
| python-json-logger | structured logs      |

---

# requirements.txt

```txt
surya-ocr
pdf2image
pillow
tqdm
python-json-logger
```

System dependency required:

```bash
poppler
```

Install examples:

Ubuntu

```bash
sudo apt install poppler-utils
```

Mac

```bash
brew install poppler
```

---

# Expected CLI Usage

```bash
python ocr_book.py /path/to/book.pdf
```

---

# Output Structure

Example input:

```
/data/books/book1.pdf
```

Output:

```
output/
 └── book1/
     ├── page_0001.md
     ├── page_0002.md
     ├── page_0003.md
     ├── progress.json
     └── run.log
```

---

# Required Features

## 1. Page Loop Processing

Process pages sequentially.

Flow:

```
load PDF
convert to images
for page in pages
    OCR page
    write markdown
    update progress
```

---

## 2. Resume Capability

Progress stored in:

```
progress.json
```

Example:

```json
{
  "input_file": "book.pdf",
  "total_pages": 300,
  "last_completed_page": 27
}
```

On restart:

```
resume from page 28
```

---

## 3. Observability

Three channels of visibility:

### Terminal

Show:

```
[INFO] Processing page 28/300
[INFO] OCR completed in 1.2s
[INFO] Output written: page_0028.md
```

### Log File

```
output/book1/run.log
```

Contains:

* timestamp
* page number
* OCR duration
* errors

### Progress File

```
progress.json
```

Continuously updated.

---

## 4. Page Quality Tracking

For each page record:

* processing time
* characters extracted
* empty page detection

Log example:

```
page=28
chars=1243
time=1.18s
status=ok
```

If extracted text length < threshold:

```
status=low_text_warning
```

---

## 5. Markdown Output Format

Each page stored separately.

Example:

```
page_0028.md
```

Contents:

```md
# Page 28

<extracted text>
```

Tables should be preserved as text blocks where possible.

---

## 6. Interrupt Handling

Must support safe interruption.

Handle:

```
KeyboardInterrupt
```

Behavior:

```
log interruption
save progress.json
exit cleanly
```

---

## 7. Error Handling

Rules:

No silent failures.

Every exception must:

```
log error
print to terminal
record page failure
continue processing next page
```

Example log:

```
[ERROR] Page 31 OCR failed: RuntimeError(...)
```

---

## 8. Page Failure Handling

If OCR fails:

```
create page_0031.md
```

Content:

```md
# Page 31

OCR FAILED
```

Log failure.

Continue pipeline.

---

# Runtime Observability

Terminal output example:

```
Book: book1.pdf
Total pages: 300

Processing page 1/300
Processing page 2/300
Processing page 3/300

[WARN] Page 3 low text detected

Processing page 4/300
```

---

# Simplicity Constraints

Implementation must:

* single script
* no frameworks
* no background workers
* no async complexity
* no database
* no queues

Only:

```
Python
filesystem
logging
```

---

# Performance Expectations

Typical runtime:

| Hardware   | Speed           |
| ---------- | --------------- |
| CPU laptop | ~1–3 sec/page   |
| GPU        | ~0.3–1 sec/page |

300-page book:

```
5–10 minutes CPU
```

---

# Optional (but recommended)

Add checksum validation:

```
hash(input_file)
```

Stored in `progress.json` to ensure resume matches same file.

---

# Summary

Your agent should build:

**Script**

```
ocr_book.py
```

**Capabilities**

* OCR full book
* page-by-page markdown output
* resumable execution
* terminal + log observability
* robust error handling
* no silent failures

**Dependencies**

```
surya-ocr
pdf2image
pillow
tqdm
python-json-logger
poppler
```
