from app.models import Document, DocumentVersion
from app.schemas import DocumentDetail, DocumentOut, VersionOut


def version_out(v: DocumentVersion) -> VersionOut:
    out = VersionOut.model_validate(v)
    out.file_url = f"/api/v1/versions/{v.id}/file"
    return out


def document_out(d: Document, detail: bool = False) -> DocumentOut:
    data = dict(
        id=d.id,
        document_key=d.document_key,
        title=d.title,
        regulator=d.regulator,
        jurisdiction=d.jurisdiction,
        category=d.category,
        active_version_id=d.active_version_id,
        created_at=d.created_at,
        updated_at=d.updated_at,
        version_count=len(d.versions),
        active_version=version_out(d.active_version) if d.active_version else None,
    )
    if detail:
        return DocumentDetail(**data, versions=[version_out(v) for v in d.versions])
    return DocumentOut(**data)
