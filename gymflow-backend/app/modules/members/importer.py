"""Bring members over from Excel / CSV (the owner's old register).

Forgiving about column names ("Name", "Member name", "Mobile", "Expiry", ...). A preview run returns what would
happen row by row; a real run creates members (de-duplicated by phone) and, when a plan and an end date are given,
their current membership.
"""
import csv
import io
import re
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.database.models import Member, Membership, MembershipPlan, Payment
from app.database.models.enums import Gender, MembershipStatus, MemberStatus, PaymentMethod, PaymentStatus
from app.database.repositories.base import TenantRepository

MAX_ROWS = 5000
ALIASES = {
    "name": ("name", "full name", "member name", "member", "customer name", "naam"),
    "phone": ("phone", "mobile", "mobile number", "phone number", "contact", "contact number", "whatsapp", "number"),
    "email": ("email", "email id", "e-mail", "mail"),
    "gender": ("gender", "sex"),
    "plan": ("plan", "membership", "package", "membership plan", "plan name"),
    "joined": ("joined", "joining date", "join date", "date of joining", "doj", "start date", "start"),
    "end": ("end", "end date", "expiry", "expiry date", "valid till", "valid upto", "due date", "renewal date"),
    "paid": ("paid", "fees paid", "payment status", "status of payment"),
    "amount": ("amount", "fees", "fee", "price"),
}


class ImportError_(ValueError):
    pass


def _norm(s: object) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(s or "").strip().lower().replace("_", " ").replace("-", " "))


def read_rows(filename: str, data: bytes) -> list[dict]:
    """Rows as {canonical_field: raw value}. Supports .csv and .xlsx."""
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        try:
            ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
        except Exception as exc:  # noqa: BLE001 - any parse failure is a bad file for the owner
            raise ImportError_("We couldn't read that Excel file. Save it as .xlsx or .csv and try again.") from exc
        table = [list(r) for r in ws.iter_rows(values_only=True)]
    elif name.endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        table = list(csv.reader(io.StringIO(text)))
    else:
        raise ImportError_("Upload an Excel (.xlsx) or CSV file.")
    table = [r for r in table if any(str(c or "").strip() for c in r)]
    if len(table) < 2:
        raise ImportError_("The file needs a header row and at least one member.")
    header = [_norm(h) for h in table[0]]
    cols: dict[str, int] = {}
    for field, names in ALIASES.items():
        for i, h in enumerate(header):
            if h in names and field not in cols:
                cols[field] = i
    if "name" not in cols or "phone" not in cols:
        raise ImportError_("We need at least a Name column and a Phone/Mobile column.")
    rows = []
    for r in table[1:MAX_ROWS + 1]:
        rows.append({f: (r[i] if i < len(r) else None) for f, i in cols.items()})
    return rows


def _date(v: object) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _phone(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    digits = re.sub(r"\D", "", str(v))
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    digits = digits.lstrip("0")
    return digits if 6 <= len(digits) <= 15 else None


def _gender(v: object) -> Gender | None:
    s = _norm(v)
    return {"m": Gender.MALE, "male": Gender.MALE, "f": Gender.FEMALE, "female": Gender.FEMALE}.get(s)


def _paid(v: object) -> bool:
    return _norm(v) in ("yes", "y", "paid", "1", "true", "done")


def run(db: Session, rows: list[dict], *, commit: bool) -> dict:
    members = TenantRepository(Member, db)
    plans = {_norm(p.name): p for p in TenantRepository(MembershipPlan, db).list(limit=500)}
    existing = {_phone(m.phone) for m in members.list(limit=100_000)}
    seen: set[str] = set()
    out = {"created": 0, "with_membership": 0, "skipped": 0, "rows": []}
    today = date.today()
    for n, row in enumerate(rows, start=2):  # spreadsheet row numbers (1 = header)
        name = str(row.get("name") or "").strip()
        phone = _phone(row.get("phone"))
        issue = ("Missing name" if not name else "Missing or invalid phone" if not phone
                 else "Already in GymFlow" if phone in existing else "Duplicate in file" if phone in seen else None)
        plan = plans.get(_norm(row.get("plan"))) if row.get("plan") else None
        end = _date(row.get("end"))
        joined = _date(row.get("joined"))
        note = None
        if not issue and row.get("plan") and plan is None:
            note = f"Plan '{row.get('plan')}' not found – member added without a membership"
        elif not issue and plan and end is None:
            note = "No end date – member added without a membership"
        result = {"row": n, "name": name, "phone": phone, "plan": plan.name if plan else None,
                  "end_date": end.isoformat() if end else None, "issue": issue, "note": note}
        out["rows"].append(result)
        if issue:
            out["skipped"] += 1
            continue
        seen.add(phone)
        out["created"] += 1
        with_ms = plan is not None and end is not None
        out["with_membership"] += int(with_ms)
        if not commit:
            continue
        start = end - timedelta(days=plan.duration_days - 1) if with_ms else None
        member = members.add(full_name=name[:200], phone=phone,
                             email=(str(row.get("email")).strip() or None) if row.get("email") else None,
                             gender=_gender(row.get("gender")),
                             joined_on=joined or start or today,
                             status=MemberStatus.ACTIVE if with_ms and end >= today else
                             MemberStatus.EXPIRED if with_ms else MemberStatus.ACTIVE)
        if with_ms:
            amount = float(row.get("amount") or plan.price) if str(row.get("amount") or "").replace(".", "", 1).isdigit() \
                else float(plan.price)
            ms = TenantRepository(Membership, db).add(
                member_id=member.id, plan_id=plan.id, start_date=start, end_date=end, amount=amount,
                status=MembershipStatus.ACTIVE if end >= today else MembershipStatus.EXPIRED, auto_renew=False)
            paid = _paid(row.get("paid")) if row.get("paid") is not None else True
            TenantRepository(Payment, db).add(
                member_id=member.id, membership_id=ms.id, amount=amount, due_date=start,
                status=PaymentStatus.PAID if paid else PaymentStatus.PENDING,
                method=PaymentMethod.CASH if paid else None,
                paid_at=datetime.combine(start, datetime.min.time()) if paid else None,
                verified_by="import" if paid else None, reference="Imported" if paid else None)
    if commit:
        db.commit()
    out["rows"] = out["rows"][:500]
    return out
