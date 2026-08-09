from __future__ import annotations

from ails_intel.collectors.base import Window
from ails_intel.models import CollectorOutcome, RawItem, SourceSpec
from ails_intel.query_utils import ctgov_search_expression, local_relevance


class ClinicalTrialsCollector:
    collector_id = "COL-CTGOV"
    source_id = "SRC-021"
    channel_id = "C3"
    base = "https://clinicaltrials.gov/api/v2/studies"

    def collect(self, *, source: SourceSpec, window: Window, max_results: int, http) -> CollectorOutcome:
        term = ctgov_search_expression(source.query_template, window.start.isoformat(), window.end.isoformat())
        items: list[RawItem] = []
        seen = 0
        page_token = None
        saturated = False

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

                nct = str(ident.get("nctId") or "").strip()
                title = str(ident.get("briefTitle") or ident.get("officialTitle") or "").strip()
                brief = str(desc.get("briefSummary") or "").strip()
                detailed = str(desc.get("detailedDescription") or "").strip()
                interventions = []
                for intervention in arms.get("interventions") or []:
                    interventions.extend(
                        [
                            str(intervention.get("name") or ""),
                            str(intervention.get("description") or ""),
                        ]
                    )
                keywords = [str(x) for x in (conditions.get("keywords") or [])]
                relevance_text = "\n".join([title, brief, detailed, *interventions, *keywords])
                if not local_relevance(relevance_text, source.query_template):
                    continue

                last_update = str((status.get("lastUpdatePostDateStruct") or {}).get("date") or "").strip()
                first_post = str((status.get("studyFirstPostDateStruct") or {}).get("date") or "").strip()
                items.append(
                    RawItem(
                        stable_id=nct,
                        title=title,
                        url=f"https://clinicaltrials.gov/study/{nct}" if nct else "",
                        published_date=last_update,
                        event_date=last_update,
                        first_public_at=first_post or last_update,
                        snippet=(brief or detailed)[:1200],
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

        return CollectorOutcome(
            collector_id=self.collector_id,
            source_id=self.source_id,
            channel_id=self.channel_id,
            execution_status="partial" if saturated else "complete",
            saturation_status="saturated" if saturated else "clear",
            results_seen=seen,
            relevant_items=items[:max_results],
            representative_url=items[0].url if items else "",
        )
