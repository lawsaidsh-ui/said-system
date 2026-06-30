from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal
from app.models import (
    AuditLog,
    CaseFee,
    Client,
    Consultation,
    Document,
    Installment,
    Invoice,
    Matter,
    PaymentVoucher,
    ReceiptVoucher,
    Task,
    WhatsAppLog,
)

DIACRITICS_RE = re.compile(r"[\u064b-\u065f\u0670\u0640]")
CLIENT_NAME_STOP_WORDS = {"بن", "بنت", "ابن", "إبن", "ابنة"}
CLIENT_FK_MODELS = (
    Matter,
    WhatsAppLog,
    Task,
    Document,
    Invoice,
    Consultation,
    CaseFee,
    ReceiptVoucher,
    PaymentVoucher,
    Installment,
)


def normalize_arabic(value: str | None) -> str:
    value = DIACRITICS_RE.sub("", value or "")
    value = (
        value.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )
    value = re.sub(r"[^\w\s\u0600-\u06ff]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def client_name_key(value: str | None) -> str:
    words = [
        word
        for word in normalize_arabic(value).split()
        if word not in CLIENT_NAME_STOP_WORDS
    ]
    return " ".join(words)


def is_subsequence(shorter: list[str], longer: list[str]) -> bool:
    position = 0
    for word in longer:
        if position < len(shorter) and shorter[position] == word:
            position += 1
    return position == len(shorter)


def same_client_name(left: Client, right: Client) -> bool:
    left_key = client_name_key(left.full_name)
    right_key = client_name_key(right.full_name)
    if left_key == right_key:
        return True

    left_words = left_key.split()
    right_words = right_key.split()
    if len(left_words) < 3 or len(right_words) < 3:
        return False

    shorter, longer = (left_words, right_words) if len(left_words) <= len(right_words) else (right_words, left_words)
    return is_subsequence(shorter, longer)


def has_conflict(left: Client, right: Client) -> bool:
    return any(
        getattr(left, field) and getattr(right, field) and getattr(left, field) != getattr(right, field)
        for field in ("phone", "civil_id", "commercial_registration")
    )


def preferred_client(left: Client, right: Client) -> tuple[Client, Client]:
    left_score = (len(client_name_key(left.full_name).split()), len(left.full_name or ""), -left.id)
    right_score = (len(client_name_key(right.full_name).split()), len(right.full_name or ""), -right.id)
    if left_score >= right_score:
        return left, right
    return right, left


def find_duplicate_pairs(clients: list[Client]) -> list[tuple[Client, Client]]:
    pairs: list[tuple[Client, Client]] = []
    for index, left in enumerate(clients):
        for right in clients[index + 1 :]:
            if has_conflict(left, right):
                continue
            if same_client_name(left, right):
                pairs.append(preferred_client(left, right))
    return pairs


def merge_client(db: Session, keep: Client, remove: Client) -> None:
    for field in ("phone", "email", "civil_id", "address", "company_name", "commercial_registration", "notes"):
        if not getattr(keep, field) and getattr(remove, field):
            setattr(keep, field, getattr(remove, field))

    for model in CLIENT_FK_MODELS:
        db.execute(update(model).where(model.client_id == remove.id).values(client_id=keep.id))

    db.execute(
        update(AuditLog)
        .where(AuditLog.entity_type == "client", AuditLog.entity_id == remove.id)
        .values(entity_id=keep.id)
    )
    db.delete(remove)


def backup_database() -> Path | None:
    database_path = Path("saeed_law.db")
    if not database_path.exists():
        return None
    backup_path = Path(f"saeed_law.backup-before-client-dedupe-{datetime.now():%Y%m%d-%H%M%S}.db")
    shutil.copy2(database_path, backup_path)
    return backup_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        clients = db.scalars(select(Client).order_by(Client.id)).all()
        pairs = find_duplicate_pairs(clients)
        print(f"clients_before={len(clients)}")
        print(f"duplicate_pairs={len(pairs)}")
        for keep, remove in pairs:
            print(f"merge remove_id={remove.id} into keep_id={keep.id}: {remove.full_name} -> {keep.full_name}")

        if args.dry_run or not pairs:
            return

        backup_path = backup_database()
        if backup_path:
            print(f"backup={backup_path}")

        removed_ids: set[int] = set()
        for keep, remove in pairs:
            if keep.id in removed_ids or remove.id in removed_ids:
                continue
            merge_client(db, keep, remove)
            removed_ids.add(remove.id)
        db.commit()

        clients_after = db.scalars(select(Client).order_by(Client.id)).all()
        print(f"clients_after={len(clients_after)}")


if __name__ == "__main__":
    main()
