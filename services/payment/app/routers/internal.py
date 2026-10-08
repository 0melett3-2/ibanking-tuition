from fastapi import APIRouter, Depends

from ibanking_common.security import require_internal_key

from ..jobs import run_reconcile
from ..schemas import ReconcileResult

router = APIRouter(tags=["internal"], dependencies=[Depends(require_internal_key)])


@router.post("/internal/jobs/reconcile", response_model=ReconcileResult)
def reconcile_now():
    """Tùy chọn, dùng khi demo: chạy job đối soát ngay thay vì chờ chu kỳ."""
    return run_reconcile()
