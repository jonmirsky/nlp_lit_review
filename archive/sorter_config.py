"""
Configuration file for paper sorting pipeline.
Contains model patterns and medical field keywords.
"""

# Model name patterns for detection
# These patterns are used to identify which models are mentioned in papers
MODEL_PATTERNS = {
    'GPT-4': [
        r'GPT-4',
        r'GPT4',
        r'gpt-4',
        r'gpt4',
    ],
    'GPT-4o': [
        r'GPT-4o',
        r'GPT4o',
        r'gpt-4o',
        r'gpt4o',
    ],
    'GPT-3.5': [
        r'GPT-3\.5',
        r'GPT3\.5',
        r'gpt-3\.5',
        r'gpt3\.5',
    ],
    'GPT-3': [
        r'GPT-3',
        r'GPT3',
        r'gpt-3',
        r'gpt3',
    ],
    'BERT': [
        r'\bBERT\b',
        r'\bbert\b',
        r'Bidirectional Encoder Representations',
    ],
    'RoBERTa': [
        r'\bRoBERTa\b',
        r'\broberta\b',
    ],
    'Llama-2': [
        r'Llama-2',
        r'llama-2',
        r'LLAMA-2',
        r'Llama 2',
        r'llama 2',
    ],
    'Llama-3': [
        r'Llama-3',
        r'llama-3',
        r'LLAMA-3',
        r'Llama 3',
        r'llama 3',
    ],
    'T5': [
        r'\bT5\b',
        r'\bt5\b',
    ],
    'BioBERT': [
        r'\bBioBERT\b',
        r'\bbiobert\b',
    ],
    'ClinicalBERT': [
        r'\bClinicalBERT\b',
        r'\bclinicalbert\b',
    ],
    'DistilBERT': [
        r'\bDistilBERT\b',
        r'\bdistilbert\b',
    ],
    'ALBERT': [
        r'\bALBERT\b',
        r'\balbert\b',
    ],
    'DeBERTa': [
        r'\bDeBERTa\b',
        r'\bdeberta\b',
    ],
    'ELECTRA': [
        r'\bELECTRA\b',
        r'\belectra\b',
    ],
    'ChatGPT': [
        r'\bChatGPT\b',
        r'\bchatgpt\b',
    ],
}

# Medical field keywords for detection
# Maps field names to lists of keywords that indicate that field
FIELD_KEYWORDS = {
    'neuro': [
        'neurology', 'neurological', 'neuroimaging', 'brain', 'cerebral',
        'stroke', 'ischemic stroke', 'hemorrhagic stroke', 'thrombectomy',
        'intracranial', 'hemorrhage', 'traumatic brain injury', 'TBI',
        'epilepsy', 'seizure', 'dementia', 'alzheimer', 'parkinson',
        'neurotrauma', 'head CT', 'brain MRI', 'neuroradiology',
        'neurological', 'neurosurgery', 'neurocritical',
    ],
    'radiology': [
        'radiology', 'radiologist', 'radiological', 'imaging',
        'CT scan', 'MRI', 'PET', 'ultrasound', 'X-ray',
        'radiology report', 'imaging report', 'diagnostic imaging',
    ],
    'oncology': [
        'cancer', 'tumor', 'tumour', 'oncology', 'oncological',
        'malignancy', 'metastasis', 'carcinoma', 'screening',
        'lung cancer', 'prostate cancer', 'thyroid nodule',
    ],
    'cardiology': [
        'cardiac', 'cardiovascular', 'heart', 'coronary',
        'CAD-RADS', 'pulmonary embolism', 'PE', 'cardiac imaging',
    ],
    'orthopedic': [
        'orthopedic', 'orthopaedic', 'fracture', 'bone',
        'musculoskeletal', 'spine', 'spinal',
    ],
    'pulmonology': [
        'pulmonary', 'lung', 'respiratory', 'pneumonia',
        'Lung-RADS', 'pulmonary nodule',
    ],
    'pathology': [
        'pathology', 'pathological', 'biopsy', 'histopathology',
        'pathology report', 'surgical pathology',
    ],
    'emergency': [
        'emergency', 'trauma', 'acute', 'critical care',
        'emergency department', 'ED', 'triage',
    ],
    'immunology': [
        'immune', 'immunology', 'autoimmune', 'allergy',
        'immunodeficiency',
    ],
}

# Section keywords to identify methods/results sections
# Used to focus model detection on primary models used in the study
METHODS_SECTION_KEYWORDS = [
    'methods', 'methodology', 'materials and methods',
    'implementation', 'model', 'models', 'architecture',
    'we used', 'we employed', 'we applied',
]

RESULTS_SECTION_KEYWORDS = [
    'results', 'findings', 'performance', 'evaluation',
    'accuracy', 'sensitivity', 'specificity', 'F1',
    'our model', 'the model', 'model performance',
]



