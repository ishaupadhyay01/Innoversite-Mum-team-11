"""Rule → regulatory clause lineage.

Rules may declare ``source.clause_ref`` in JSON (MANUAL, confirmed). Otherwise we ask search-service for the
best-matching ACTIVE clause of the same regulator (AUTO_SEARCH, unconfirmed) so a reviewer can confirm it.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.models import Rule, RuleClauseLink
from app.schemas import ClauseLinkIn
from app.services.rulesets import get_rule_set
from iris_common.errors import NotFoundError
from iris_common.http import ServiceClient

log = logging.getLogger(__name__)


def auto_link_rule_set(db: Session, rule_set_id: uuid.UUID, search: ServiceClient) -> int:
    rs = get_rule_set(db, rule_set_id)
    linked = 0
    for rule in rs.rules:
        if rule.clause_link and rule.clause_link.method == "MANUAL":
            continue
        try:
            resp = search.get(
                "/api/v1/search",
                params={"q": f"{rule.description} {rule.impact or ''}", "regulator": rs.regulator, "size": 1},
            )
        except Exception:  # noqa: BLE001 - search is optional; never block rule upload on it
            log.warning("auto_link_failed", extra={"rule": rule.code})
            continue
        if not resp or not resp.get("hits"):
            continue
        hit = resp["hits"][0]
        c = hit["citation"]
        rule.clause_link = RuleClauseLink(
            document_id=c["document_id"],
            version_id=c["version_id"],
            clause_id=hit["clause_id"],
            clause_ref=c["clause_ref"],
            page=c["page"],
            citation_label=c["label"],
            file_url=c["file_url"],
            excerpt=hit["text"][:500],
            method="AUTO_SEARCH",
            score=hit["score"],
            confirmed=False,
        )
        linked += 1
    db.commit()
    return linked


def set_manual_link(db: Session, rule_id: uuid.UUID, body: ClauseLinkIn) -> Rule:
    rule = db.get(Rule, rule_id)
    if rule is None:
        raise NotFoundError(f"Rule {rule_id} not found")
    rule.clause_link = RuleClauseLink(**body.model_dump(), method="MANUAL", confirmed=True)
    db.commit()
    return rule
