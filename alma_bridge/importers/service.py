from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from alma_bridge.config import settings
from alma_bridge.importers.resolve import import_resolve_audits
from alma_bridge.importers.sysdet import import_sysdet_history


class ImportService:
    def import_all(
        self,
        *,
        sysdet_db: Optional[Path] = None,
        resolve_audit_dir: Optional[Path] = None,
        limit: Optional[int] = None,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        sysdet_result = self.import_sysdet(
            db_path=sysdet_db,
            limit=limit,
            skip_existing=skip_existing,
        )
        resolve_result = self.import_resolve(
            audit_dir=resolve_audit_dir,
            skip_existing=skip_existing,
        )
        return {
            "almasysdet": sysdet_result,
            "alma_resolve": resolve_result,
            "total_sessions": (
                sysdet_result["imported_sessions"] + resolve_result["imported_sessions"]
            ),
            "total_attempts": (
                sysdet_result["imported_attempts"] + resolve_result["imported_attempts"]
            ),
        }

    def import_sysdet(
        self,
        *,
        db_path: Optional[Path] = None,
        limit: Optional[int] = None,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        return import_sysdet_history(
            db_path or settings.sysdet_db_path,
            limit=limit,
            skip_existing=skip_existing,
        )

    def import_resolve(
        self,
        *,
        audit_dir: Optional[Path] = None,
        skip_existing: bool = True,
    ) -> Dict[str, Any]:
        audit = audit_dir or settings.resolve_audit_dir
        runtime_data = audit.parent if audit else settings.resolve_audit_dir.parent
        return import_resolve_audits(
            audit,
            runtime_data_dir=runtime_data,
            skip_existing=skip_existing,
        )
