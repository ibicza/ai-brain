"""Chemistry-free educational runtime over an installed domain provider."""

from __future__ import annotations

from ai_brain.stage2.education.domain_provider import EducationalDomainProvider


class GenericEducationalService:
    """Small stable facade whose behavior is supplied entirely by a provider."""

    def __init__(self, provider: EducationalDomainProvider) -> None:
        self.provider = provider

    @property
    def domain_runtime(self):
        return self.provider.domain_runtime()

    def present(self, *args, **kwargs):
        return self.provider.present(*args, **kwargs)

    def grade(self, *args, **kwargs):
        return self.provider.grade(*args, **kwargs)

    def hint(self, *args, **kwargs):
        return self.provider.hint(*args, **kwargs)

    def explain(self, *args, **kwargs):
        return self.provider.explain(*args, **kwargs)

    def replay(self, *args, **kwargs):
        return self.provider.replay(*args, **kwargs)

    def progress(self):
        return self.provider.progress()

    def verify_currentness(self):
        return self.provider.currentness_verifier()
