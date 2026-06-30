from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Document, Matter, User
from app.routes.helpers import can_see_document, get_form_context, int_or_none, none_if_empty, save_upload
from app.services.audit import log_action
from app.services.auth import ensure_role, get_current_user
from app.templating import templates

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
def documents_index(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    docs = db.scalars(select(Document).options(selectinload(Document.client), selectinload(Document.matter), selectinload(Document.uploaded_by)).order_by(Document.created_at.desc())).all()
    docs = [doc for doc in docs if can_see_document(user, doc)]
    return templates.TemplateResponse("documents/index.html", {"request": request, "user": user, "documents": docs, **get_form_context(db)})


@router.post("")
async def document_upload(request: Request, title: str = Form(...), document_type: str = Form(""), client_id: str = Form(""), matter_id: str = Form(""), notes: str = Form(""), is_confidential: str | None = Form(None), file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_role(user, {"lawyer", "secretary", "data_entry"})
    file_url, file_name, file_size, mime_type = await save_upload(file)
    parsed_client_id = int_or_none(client_id)
    parsed_matter_id = int_or_none(matter_id)
    if parsed_matter_id:
        matter = db.get(Matter, parsed_matter_id)
        if matter:
            parsed_client_id = matter.client_id
        else:
            parsed_matter_id = None
    document = Document(title=title, document_type=none_if_empty(document_type), client_id=parsed_client_id, matter_id=parsed_matter_id, uploaded_by_id=user.id, file_url=file_url, file_name=file_name, file_size=file_size, mime_type=mime_type, notes=none_if_empty(notes), is_confidential=bool(is_confidential))
    db.add(document)
    db.flush()
    log_action(
        db,
        user=user,
        action="upload_document",
        entity_type="document",
        entity_id=document.id,
        new_value={
            "title": title,
            "file_name": file_name,
            "client_id": document.client_id,
            "matter_id": document.matter_id,
        },
        request=request,
    )
    db.commit()
    return RedirectResponse("/documents", status_code=303)
