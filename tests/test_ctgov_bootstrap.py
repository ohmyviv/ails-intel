from datetime import date

from ails_intel.collectors.base import Window
from ails_intel.collectors.clinicaltrials import ClinicalTrialsCollector
from ails_intel.models import SourceSpec


class FakeHttp:
    def __init__(self, payload):
        self.payload = payload

    def json(self, url, params=None):
        return self.payload


def _gate():
    return {
        "enabled": True,
        "ai_terms": ["artificial intelligence", "AI", "machine learning"],
        "role_terms": ["clinical validation", "diagnostic", "prospective"],
        "weights": {"title": 3, "intervention": 4, "outcome": 3, "summary": 1, "role": 2},
        "core_threshold": 5,
        "p1_threshold": 8,
        "material_delta_enabled": True,
        "p1_deltas": ["new_registration", "status_changed", "results_posted"],
    }


def _study():
    return {
        "protocolSection": {
            "identificationModule": {"nctId": "NCTLEGACY", "briefTitle": "Artificial intelligence diagnostic validation"},
            "statusModule": {
                "overallStatus": "RECRUITING",
                "lastUpdatePostDateStruct": {"date": "2026-08-11"},
                "studyFirstPostDateStruct": {"date": "2026-07-01"},
            },
            "descriptionModule": {"briefSummary": "Prospective clinical validation of an AI diagnostic system."},
            "armsInterventionsModule": {
                "interventions": [{"type": "DEVICE", "name": "AI diagnostic software"}]
            },
            "outcomesModule": {
                "primaryOutcomes": [{"measure": "AI diagnostic sensitivity", "timeFrame": "Day 1"}]
            },
            "designModule": {
                "studyType": "INTERVENTIONAL",
                "enrollmentInfo": {"count": 120},
            },
        },
        "hasResults": False,
    }


def test_pre_gate_history_emits_one_baseline_instead_of_guessing_unchanged():
    prior = {
        "NCTLEGACY": {
            "raw_title": "Artificial intelligence diagnostic validation",
            "raw_snippet": "Prospective clinical validation of an AI diagnostic system.",
            "notes": "",
        }
    }
    source = SourceSpec("SRC-021", "CTG", "P0", '("artificial intelligence" OR AI OR "machine learning")')
    out = ClinicalTrialsCollector(gate_options=_gate(), prior_signals=prior).collect(
        source=source,
        window=Window(date(2026, 8, 8), date(2026, 8, 11)),
        max_results=10,
        http=FakeHttp({"studies": [_study()]}),
    )
    assert len(out.relevant_items) == 1
    assert "ctgov_delta=baseline_core" in out.relevant_items[0].notes
    assert "ctgov_material=" in out.relevant_items[0].notes
