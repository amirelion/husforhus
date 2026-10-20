"""The City Museum's document archive in Digitala Stadsmuseet: the page addresses its sources share. A leaf module, so
pipeline/cited.py can name the pages without importing stadsmuseet's own imports (plaques, wiki, s02_attributes),
which come back round to s02_years."""
import re

SITE = "https://digitalastadsmuseet.stockholm.se"
ARCHIVE = f"{SITE}/fotoweb/archives/5004-Dokument-och-publikationer/"
# A document's own page in the archive ("…/Dokument/DOK_1/SSM_DOK_000624.pdf.info")
REPORT_RE = re.compile(re.escape(ARCHIVE) + r"[^\s\"'<>?#]+\.info")
