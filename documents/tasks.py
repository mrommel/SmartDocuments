import logging

from django_tasks import task
from django.db import transaction

from .extraction import extract_metadata
from .geocoding import geocode_address
from .models import Document, DocumentAddress

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
        metadata = extract_metadata(document).copy()
        addresses = metadata.pop("addresses", []) if document.find_addresses else []
        saved_addresses = []
        for item in addresses:
            match, error = geocode_address(item["address"])
            saved_addresses.append(DocumentAddress(
                document=document, address=item["address"], category=item["category"],
                geocode_result=match, geocode_error=error,
            ))
        with transaction.atomic():
            document.metadata = metadata
            document.addresses.all().delete()
            DocumentAddress.objects.bulk_create(saved_addresses)
            document.status = Document.Status.COMPLETE
            document.extraction_error = ""
            document.save(update_fields=["metadata", "status", "extraction_error"])
    except Exception as exc:
        logger.exception("Document metadata extraction failed for document %s", document_id)
        document.status = Document.Status.FAILED
        document.extraction_error = (
            str(exc)[:1000] if isinstance(exc, (ValueError, OSError))
            else "Could not read document or contact local LLM."
        )
        document.save(update_fields=["status", "extraction_error"])
        raise


@task
def retry_address_geocoding(document_id):
    try:
        document = Document.objects.get(pk=document_id)
    except Document.DoesNotExist:
        return
    if document.status != Document.Status.COMPLETE:
        return  # Never race with an in-progress analysis that replaces the addresses.
    for address in document.addresses.filter(geocode_result__isnull=True):
        match, error = geocode_address(address.address)
        DocumentAddress.objects.filter(pk=address.pk, document__status=Document.Status.COMPLETE).update(
            geocode_result=match, geocode_error=error,
        )
