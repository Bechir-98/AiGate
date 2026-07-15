from presidio_analyzer.nlp_engine import NlpEngine, NlpArtifacts
class NullNlpEngine(NlpEngine):
    def __init__(self):
        self._is_loaded = True

    def load(self):
        self._is_loaded = True

    def is_loaded(self):
        return self._is_loaded

    def process_text(self, text, language):
        return NlpArtifacts([], [], [], [], self, language)

    def process_batch(self, texts, language):
        return [self.process_text(t, language) for t in texts]

    def get_supported_entities(self):
        return []

    def get_supported_languages(self):
        return ["en"]

    def is_punct(self, word: str, language: str) -> bool:
        return False

    def is_stopword(self, word: str, language: str) -> bool:
        return False
