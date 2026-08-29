"""Chemistry behavior behind the generic educational provider boundary."""

from __future__ import annotations

from ai_brain.stage2.domains.chemistry.education.controlled import (
    parse_educational_request,
)
from ai_brain.stage2.domains.chemistry.education.graph_adapter import (
    ChemistryEducationAdapter,
)
from ai_brain.stage2.education.answer_parser import parse_student_answer
from ai_brain.stage2.education.catalog import EducationalCatalogV2


class ChemistryEducationalDomainProvider:
    def __init__(self, service, runtime) -> None:
        self.service = service
        self.runtime = runtime
        self.adapter = ChemistryEducationAdapter(service)

    def domain_runtime(self):
        return self.runtime

    def strict_answer_parser(self, raw, answer_type, *, confirmed=False):
        return parse_student_answer(
            raw,
            answer_type,
            supported_symbols=set(self.service.manifest["supported_elements"]),
            confirmed=confirmed,
        )

    def fact_resolver(self, knowledge_id):
        return self.runtime.resolve_fact_schema(knowledge_id)

    def catalog_provider(self, path):
        return EducationalCatalogV2.load(path, self.service)

    def graph_compiler_provider(self):
        return self.adapter

    def explanation_provider(self):
        return self.adapter

    def currentness_verifier(self):
        return self.runtime.verify_currentness()

    def controlled_language_provider(self, text, language):
        return parse_educational_request(text, language)

    def public_domain_metadata(self):
        return self.runtime.public_domain_summary()
