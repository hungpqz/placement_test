import json
from typing import Any, Dict, Optional

import frappe
from frappe.utils import get_datetime

DOC_TYPE = "Placement Test Result"


def _load_payload() -> Dict[str, Any]:
    """Extract the incoming payload regardless of content type."""
    try:
        data = frappe.request.get_json()  # type: ignore[attr-defined]
        if data:
            return data
    except Exception:
        pass

    if frappe.form_dict:
        # Accept either a direct dict or a JSON string nested under a key.
        form_dict = frappe.form_dict
        if isinstance(form_dict, dict):
            if len(form_dict) == 1:
                sole_value = next(iter(form_dict.values()))
                if isinstance(sole_value, str):
                    try:
                        return json.loads(sole_value)
                    except (TypeError, ValueError):
                        return {}
            try:
                return json.loads(json.dumps(form_dict))
            except (TypeError, ValueError):
                return {}
    return {}


def _to_int(value: Any) -> Optional[int]:
    if value in (None, "", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> Optional[float]:
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_datetime(value: Any) -> Optional[str]:
    if not value:
        return None
    try:
        dt = get_datetime(value)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _extract_custom_value(payload: Dict[str, Any], slug: str, label: str) -> Optional[str]:
    fields = payload.get("fields") or {}
    if isinstance(fields, dict):
        item = fields.get(slug)
        if not item:
            for field_value in fields.values():
                if isinstance(field_value, dict) and field_value.get("label") == label:
                    item = field_value
                    break
        if isinstance(item, dict):
            candidate = item.get("value")
            if candidate not in (None, ""):
                return str(candidate)

    custom_fields = payload.get("custom_fields") or []
    if isinstance(custom_fields, list):
        for entry in custom_fields:
            if not isinstance(entry, dict):
                continue
            if entry.get("slug") == slug or entry.get("label") == label:
                candidate = entry.get("value")
                if candidate not in (None, ""):
                    return str(candidate)

    custom_field_values = payload.get("custom_field_values") or {}
    if isinstance(custom_field_values, dict):
        candidate = custom_field_values.get(slug)
        if candidate not in (None, ""):
            return str(candidate)

    return None


@frappe.whitelist(allow_guest=True)
def submit_quiz_result() -> Dict[str, Any]:
    payload = _load_payload()

    if not payload:
        return {"status": "error", "message": "Missing payload."}

    result_id = _to_int(payload.get("result_id"))
    quiz_title = payload.get("quiz_title")

    if not result_id or not quiz_title:
        return {
            "status": "error",
            "message": "Both result_id and quiz_title are required.",
        }

    doc_values = {
        "result_id": result_id,
        "quiz_id": _to_int(payload.get("quiz_id")),
        "quiz_title": str(quiz_title),
        "score_percentage": _to_float(payload.get("score_percentage")),
        "final_score": _to_float(payload.get("final_score")),
        "score_by": _to_float(payload.get("score_by")),
        "score_type": payload.get("score_type"),
        "points": _to_float(payload.get("points")),
        "duration_seconds": _to_int(payload.get("duration_seconds")),
        "start_time": _to_datetime(payload.get("start_date")),
        "end_time": _to_datetime(payload.get("end_date")),
        "submitted_at": _to_datetime(payload.get("submitted_at")),
        "student_name": _extract_custom_value(payload, "quiz_attr_2", "Student's Name"),
        "student_id": _extract_custom_value(payload, "quiz_attr_1", "Student's ID"),
        "tester_name": _extract_custom_value(payload, "quiz_attr_6", "Tester's Name"),
        "user_email": (payload.get("user") or {}).get("email"),
        "user_phone": (payload.get("user") or {}).get("phone"),
        "user_ip": payload.get("user_ip"),
        "integration_source": payload.get("integration"),
        "raw_payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    }

    existing = frappe.get_all(
        DOC_TYPE,
        filters={"result_id": result_id},
        pluck="name",
        limit=1,
    )

    try:
        if existing:
            doc = frappe.get_doc(DOC_TYPE, existing[0])
            doc.update({k: v for k, v in doc_values.items() if v is not None})
            doc.save(ignore_permissions=True)
        else:
            doc = frappe.new_doc(DOC_TYPE)
            doc.update({k: v for k, v in doc_values.items() if v is not None})
            doc.insert(ignore_permissions=True)

        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "Placement Test Result API Error")
        return {"status": "error", "message": "An unexpected error occurred."}

    return {
        "status": "success",
        "docname": doc.name,
        "result_id": result_id,
    }
