import logging

from django_tasks import task

from .extraction import extract_metadata
from .models import Document

logger = logging.getLogger(__name__)


@task
def analyze_document(document_id):
    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        return  # The document was deleted while queued.
    if document.status != Document.Status.PENDING:
        return

    document.status = Document.Status.PROCESSING
    document.save(update_fields=["status"])
    try:
        document.metadata = extract_metadata(document)
        document.status = Document.Status.COMPLETE
        document.extraction_error = ""
    except Exception as exc:
        logger.exception("Document metadata extraction failed for document %s", document_id)
        document.status = Document.Status.FAILED
        document.extraction_error = (
            str(exc)[:1000] if isinstance(exc, (ValueError, OSError))
            else "Could not read document or contact local LLM."
        )
        document.save(update_fields=["status", "extraction_error"])
        raise
    document.save(update_fields=["metadata", "status", "extraction_error"])
