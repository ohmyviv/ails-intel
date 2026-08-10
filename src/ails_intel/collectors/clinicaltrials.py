from __future__ import annotations

import hashlib
import json
import re
from datetime import date

from ails_intel.collectors.base import Window
from ails_intel.models import CollectorOutcome, RawItem, SourceSpec
from ails_intel.query_utils import ctgov_search_expression, local_relevance


WS = re.compile(r"\s+")


def _norm(value: object) -> str:
    return WS.sub(" ", str(value or "").casefold()).strip()


def _contains_any(text: str, terms: list[str]) -> bool:
    hay = _norm(text)
    return any(_norm(term) in hay for term in terms if _norm(term))


def _note_fields(notes: object) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(notes or "").split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if key:
            out[key] = value.strip()
    return out


def _date_in_window(value: str, window: Window) -> bool:
    try:
        parsed = date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return False
    return window.start <= parsed <= window.end


def _legacy_fingerprint(title: str, snippet: str) -> str:
    payload = f"{_norm(title)}\n{_norm(snippet)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _material_state(study: dict[str, object]) -> dict[str, object]:
    protocol = study.get("protocolSection") or {}
    status = protocol.get("statusModule") or {}
    design = protocol.get("designModule") or {}
    arms = protocol.get("armsInterventionsModule") or {}
    outcomes = protocol.get("outcomesModule") or {}
    sponsor = protocol.get("sponsorCollaboratorsModule") or {}

    interventions = []
    for intervention in arms.get("interventions") or []:
        interventions.append({
            "type": intervention.get("type") or "",
            "name": intervention.get("name") or "",
        })

    def outcome_rows(name: str) -> list[dict[str, object]]:
        rows = []
        for item in outcomes.get(name) or []:
            rows.append({
                "measure": item.get("measure") or "",
                "timeFrame": item.get("timeFrame") or "",
            })
        return rows

    lead = sponsor.get("leadSponsor") or {}
    return {
        "overallStatus": status.get("overallStatus") or "",
        "enrollment": (design.get("enrollmentInfo") or {}).get("count") or "",
        "studyType": design.get("studyType") or "",
        "phases": sorted(str(x) for x in (design.get("phases") or [])),
        "allocation": (design.get("designInfo") or {}).get("allocation") or "",
        "interventionModel": (design.get("designInfo") or {}).get("interventionModel") or "",
        "interventions": sorted(interventions, key=lambda x: (str(x["type"]), str(x["name"]))),
        "primaryOutcomes": outcome_rows("primaryOutcomes"),
        "secondaryOutcomes": outcome_rows("secondaryOutcomes"),
        "startDate": (status.get("startDateStruct") or {}).get("date") or "",
        "primaryCompletionDate": (status.get("primaryCompletionDateStruct") or {}).get("date") or "",
        "completionDate": (status.get("completionDateStruct") or {}).get("date") or "",
        "leadSponsorName": lead.get("name") or "",
        "leadSponsorClass": lead.get("class") or "",
        "hasResults": bool(study.get("hasResults")),
    }


def _material_fingerprint(state: dict[str, object]) -> str:
    payload = json.dumps(state, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ClinicalTrialsCollector:
    collector_id = "COL-CTGOV"
    source_id = "SRC-021"
    channel_id = "C3"
    base = "https://clinicaltrials.gov/api/v2/studies"

    def __init__(self, *, gate_options: dict[str, object] | None = None, prior_signals: dict[str, dict[str, object]] | None = None):
        self.gate = dict(gate_options or {})
        self.prior_signals = dict(prior_signals or {})

    def _role_score(self, *, title: str, summary: str, interventions: str, outcomes: str, design_text: str) -> int:
        if not bool(self.gate.get("enabled", False)):
            return int(self.gate.get("core_threshold", 0) or 0)

        ai_terms = [str(x) for x in (self.gate.get("ai_terms") or [])]
        role_terms = [str(x) for x in (self.gate.get("role_terms") or [])]
        low_value_terms = [str(x) for x in (self.gate.get("low_value_terms") or [])]
        weights = dict(self.gate.get("weights") or {})
        score = 0
        if _contains_any(title, ai_terms):
            score += int(weights.get("title", 3))
        if _contains_any(interventions, ai_terms):
            score += int(weights.get("intervention", 4))
        if _contains_any(outcomes, ai_terms):
            score += int(weights.get("outcome", 3))
        if _contains_any(summary, ai_terms):
            score += int(weights.get("summary", 1))
        joined = "\n".join([title, summary, interventions, outcomes, design_text])
        if _contains_any(joined, role_terms):
            score += int(weights.get("role", 2))
        if _contains_any(joined, low_value_terms) and not (_contains_any(interventions, ai_terms) or _contains_any(outcomes, ai_terms)):
            score -= int(weights.get("low_value_penalty", 2))
        return score

    def _material_delta(
        self,
        *,
        nct: str,
        title: str,
        snippet: str,
        first_post: str,
        state: dict[str, object],
        fingerprint: str,
        window: Window,
    ) -> tuple[bool, str]:
        if not bool(self.gate.get("material_delta_enabled", False)):
            return True, "registry_update"

        prior = self.prior_signals.get(nct)
        if not prior:
            return True, "new_registration" if _date_in_window(first_post, window) else "first_seen_core"

        prior_meta = _note_fields(prior.get("notes", ""))
        prior_material = prior_meta.get("ctgov_material", "")
        if prior_material:
            if prior_material == fingerprint:
                return False, "unchanged_material"
            prior_status = prior_meta.get("ctgov_status", "")
            prior_enrollment = prior_meta.get("ctgov_enrollment", "")
            prior_results = prior_meta.get("ctgov_results", "")
            current_status = str(state.get("overallStatus") or "")
            current_enrollment = str(state.get("enrollment") or "")
            current_results = "1" if bool(state.get("hasResults")) else "0"
            if prior_results == "0" and current_results == "1":
                return True, "results_posted"
            if prior_status and prior_status != current_status:
                return True, "status_changed"
            if prior_enrollment and prior_enrollment != current_enrollment:
                return True, "enrollment_changed"
            return True, "protocol_material_updated"

        # Bootstrap compatibility for pre-Sprint-4.3 history: old Signals did not
        # carry structured material hashes. Exact title+stored-snippet equality is
        # used only to suppress obvious administrative refreshes. A changed core
        # description remains visible rather than being silently discarded.
        prior_legacy = _legacy_fingerprint(
            str(prior.get("raw_title", "")),
            str(prior.get("raw_snippet", "")),
        )
        if prior_legacy == _legacy_fingerprint(title, snippet):
            return False, "unchanged_legacy"
        return True, "protocol_material_updated_legacy"

    def collect(self, *, source: SourceSpec, window: Window, max_results: int, http) -> CollectorOutcome:
        term = ctgov_search_expression(source.query_template, window.start.isoformat(), window.end.isoformat())
        items: list[RawItem] = []
        seen = 0
        page_token = None
        saturated = False
        filtered_local = 0
        filtered_noncore = 0
        filtered_unchanged = 0
        p1_count = 0
        p2_count = 0

        while True:
            params = {"query.term": term, "pageSize": 100, "format": "json"}
            if page_token:
                params["pageToken"] = page_token
            payload = http.json(self.base, params)
            studies = payload.get("studies") or []
            seen += len(studies)

            for study in studies:
                protocol = study.get("protocolSection") or {}
                ident = protocol.get("identificationModule") or {}
                status = protocol.get("statusModule") or {}
                desc = protocol.get("descriptionModule") or {}
                arms = protocol.get("armsInterventionsModule") or {}
                conditions = protocol.get("conditionsModule") or {}
                outcomes_module = protocol.get("outcomesModule") or {}
                design = protocol.get("designModule") or {}

                nct = str(ident.get("nctId") or "").strip()
                title = str(ident.get("briefTitle") or ident.get("officialTitle") or "").strip()
                brief = str(desc.get("briefSummary") or "").strip()
                detailed = str(desc.get("detailedDescription") or "").strip()
                interventions = []
                for intervention in arms.get("interventions") or []:
                    interventions.extend([
                        str(intervention.get("name") or ""),
                        str(intervention.get("description") or ""),
                    ])
                keywords = [str(x) for x in (conditions.get("keywords") or [])]
                outcomes = []
                for field in ("primaryOutcomes", "secondaryOutcomes"):
                    for outcome in outcomes_module.get(field) or []:
                        outcomes.extend([
                            str(outcome.get("measure") or ""),
                            str(outcome.get("description") or ""),
                        ])
                relevance_text = "\n".join([title, brief, detailed, *interventions, *keywords, *outcomes])
                if not local_relevance(relevance_text, source.query_template):
                    filtered_local += 1
                    continue

                design_text = json.dumps(design, ensure_ascii=False, sort_keys=True)
                role_score = self._role_score(
                    title=title,
                    summary="\n".join([brief, detailed]),
                    interventions="\n".join(interventions),
                    outcomes="\n".join(outcomes),
                    design_text=design_text,
                )
                core_threshold = int(self.gate.get("core_threshold", 0) or 0)
                if bool(self.gate.get("enabled", False)) and role_score < core_threshold:
                    filtered_noncore += 1
                    continue

                last_update = str((status.get("lastUpdatePostDateStruct") or {}).get("date") or "").strip()
                first_post = str((status.get("studyFirstPostDateStruct") or {}).get("date") or "").strip()
                snippet = (brief or detailed)[:1200]
                material_state = _material_state(study)
                material_hash = _material_fingerprint(material_state)
                keep, delta = self._material_delta(
                    nct=nct,
                    title=title,
                    snippet=snippet,
                    first_post=first_post,
                    state=material_state,
                    fingerprint=material_hash,
                    window=window,
                )
                if not keep:
                    filtered_unchanged += 1
                    continue

                p1_threshold = int(self.gate.get("p1_threshold", core_threshold) or core_threshold)
                p1_deltas = {str(x) for x in (self.gate.get("p1_deltas") or [])}
                priority = "P1" if role_score >= p1_threshold or delta in p1_deltas else "P2"
                if priority == "P1":
                    p1_count += 1
                else:
                    p2_count += 1
                notes = ";".join([
                    f"ctgov_material={material_hash}",
                    f"ctgov_delta={delta}",
                    f"ctgov_ai_role={role_score}",
                    f"ctgov_status={material_state.get('overallStatus') or ''}",
                    f"ctgov_enrollment={material_state.get('enrollment') or ''}",
                    f"ctgov_results={'1' if material_state.get('hasResults') else '0'}",
                ])
                items.append(
                    RawItem(
                        stable_id=nct,
                        title=title,
                        url=f"https://clinicaltrials.gov/study/{nct}" if nct else "",
                        published_date=last_update,
                        event_date=last_update,
                        first_public_at=first_post or last_update,
                        snippet=snippet,
                        priority_hint=priority,
                        notes=notes,
                    )
                )
                if len(items) >= max_results:
                    break

            page_token = payload.get("nextPageToken")
            if len(items) >= max_results:
                saturated = bool(page_token)
                break
            if not page_token:
                break

        diagnostics = ";".join([
            f"filtered_local={filtered_local}",
            f"filtered_noncore={filtered_noncore}",
            f"filtered_unchanged={filtered_unchanged}",
            f"p1={p1_count}",
            f"p2={p2_count}",
        ])
        return CollectorOutcome(
            collector_id=self.collector_id,
            source_id=self.source_id,
            channel_id=self.channel_id,
            execution_status="partial" if saturated else "complete",
            saturation_status="saturated" if saturated else "clear",
            results_seen=seen,
            relevant_items=items[:max_results],
            representative_url=items[0].url if items else "",
            diagnostic_note=diagnostics,
        )
