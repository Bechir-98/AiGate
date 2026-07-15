import onnxruntime as ort
from presidio_analyzer.nlp_engine import NlpEngine, NlpArtifacts
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.predefined_recognizers import GLiNERRecognizer

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

def create_gliner_analyzer():
    entity_mapping = {
    # Personnes
    "person": "PERSON",
    "date_of_birth": "DATE_TIME",

    # Contact / adresse
    "email": "EMAIL_ADDRESS",
    "phone_number": "PHONE_NUMBER",
    "address": "LOCATION",

    # IDs gouvernementaux
    "national_id_number": "US_SSN",
    "passport_number": "US_PASSPORT",
    "drivers_license_number": "US_DRIVER_LICENSE",
    "tax_id": "US_ITIN",

    # Bancaire / paiement
    "account_number": "IBAN_CODE",
    "routing_number": "US_BANK_NUMBER",
    "iban": "IBAN_CODE",
    "card_number": "CREDIT_CARD",
    "card_expiry": "CREDIT_CARD",
    "card_cvv": "CREDIT_CARD",

    # Identité numérique
    "username": "CREDENTIAL",
    "ip_address": "IP_ADDRESS",
    "account_id": "CREDENTIAL",
    "sensitive_account_id": "CREDENTIAL",

    # Secrets
    "password": "CREDENTIAL",
    "api_key": "CREDENTIAL",
    "access_token": "CREDENTIAL",
    "recovery_code": "CREDENTIAL",

    # Dates sensibles
    "document_date": "DATE_TIME",
    "expiration_date": "DATE_TIME",
    "transaction_date": "DATE_TIME",
}

    # Optimize ONNX Runtime for CPU usage to prevent thread context-switching overhead
    session_options = ort.SessionOptions()
    session_options.intra_op_num_threads = 2
    session_options.inter_op_num_threads = 2
    session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    gliner_recognizer = GLiNERRecognizer(
        model_name="rpeel/glitext-pii-edge",
        entity_mapping=entity_mapping,
        flat_ner=False,
        multi_label=True,
        map_location="cpu",
        load_onnx_model=True,
        onnx_model_file="model.onnx",
        threshold=0.5,
        session_options=session_options,
    )

    analyzer_engine = AnalyzerEngine(
        nlp_engine=NullNlpEngine()
    )

    for recognizer in analyzer_engine.registry.recognizers.copy():
        analyzer_engine.registry.remove_recognizer(recognizer.name)

    analyzer_engine.registry.add_recognizer(gliner_recognizer)
    
    return analyzer_engine

def create_gliner2_analyzer(load_onnx_model: bool = True, model_name: str = "gliner2-PII"):
    from utils.gliner2Recognizer import GLiNER2Recognizer
    
    entity_mapping = {
    # Personnes
    "person": "PERSON",
    "date_of_birth": "DATE_TIME",

    # Contact / adresse
    "email": "EMAIL_ADDRESS",
    "phone_number": "PHONE_NUMBER",
    "address": "LOCATION",

    # IDs gouvernementaux
    "national_id_number": "US_SSN",
    "passport_number": "US_PASSPORT",
    "drivers_license_number": "US_DRIVER_LICENSE",
    "tax_id": "US_ITIN",

    # Bancaire / paiement
    "account_number": "IBAN_CODE",
    "routing_number": "US_BANK_NUMBER",
    "iban": "IBAN_CODE",
    "card_number": "CREDIT_CARD",
    "card_expiry": "CREDIT_CARD",
    "card_cvv": "CREDIT_CARD",

    # Identité numérique
    "username": "CREDENTIAL",
    "ip_address": "IP_ADDRESS",
    "account_id": "CREDENTIAL",
    "sensitive_account_id": "CREDENTIAL",

    # Secrets
    "password": "CREDENTIAL",
    "api_key": "CREDENTIAL",
    "access_token": "CREDENTIAL",
    "recovery_code": "CREDENTIAL",

    # Dates sensibles
    "document_date": "DATE_TIME",
    "expiration_date": "DATE_TIME",
    "transaction_date": "DATE_TIME",
}

    session_options = ort.SessionOptions()
    session_options.intra_op_num_threads = 2
    session_options.inter_op_num_threads = 1
    session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

    gliner2_recognizer = GLiNER2Recognizer(
        model_name="gliner2-PII",
        entity_mapping=entity_mapping,
        threshold=0.5,
        map_location="cpu",
        load_onnx_model=True,
    )

    analyzer_engine = AnalyzerEngine(
        nlp_engine=NullNlpEngine()
    )

    for recognizer in analyzer_engine.registry.recognizers.copy():
        analyzer_engine.registry.remove_recognizer(recognizer.name)

    analyzer_engine.registry.add_recognizer(gliner2_recognizer)
    
    return analyzer_engine