import json
import re
from collections import Counter
from typing import List, Dict, Any, Optional

from openai import OpenAI


def sanitize_for_csv(value: Any) -> str:
    """
    Pulisce una stringa rimuovendo/sostituendo caratteri che possono rompere un CSV:
    - caratteri di controllo ASCII (inclusi \n, \r, \t)
    - virgole, punti e virgola
    - doppi apici

    Restituisce sempre una stringa "piatta" e sicura per il CSV.
    """
    if value is None:
        return ""

    text = str(value)

    # Rimuove caratteri di controllo (0x00-0x1F, 0x7F)
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)

    # Sostituisce newline espliciti se presenti in forma testuale
    text = text.replace("\\n", " ").replace("\\r", " ")

    # Rimuove newline reali (nel caso la stringa li contenga davvero)
    text = text.replace("\n", " ").replace("\r", " ")

    # Rimpiazza caratteri problematici per il CSV
    text = text.replace('"', "'")
    text = text.replace(",", " ")
    text = text.replace(";", " ")

    # Normalizza spazi multipli
    text = re.sub(r"\s+", " ", text).strip()

    return text


class OpenAIClassifier:
    """
    Classifies developers as ML-engineer, SE-engineer or Hybrid-engineer
    using an OpenAI chat model.
    Classification is done per author based on their commit patterns.
    """

    # Limiti sui dati usati nel prompt
    MAX_COMMITS = 30
    MAX_FILES = 80
    MAX_MESSAGES = 15
    MAX_ISSUES = 5

    # Parole chiave indicative di lavoro ML
    ML_KEYWORDS = [
        "model", "training", "train", "inference", "inferenza",
        "dataset", "data loader", "feature engineering", "experiment",
        "notebook", "pytorch", "torch", "tensorflow", "keras",
        "sklearn", "xgboost", "lightgbm", "mlflow",
        "metrics", "loss", "gradient", "optimizer"
    ]

    # Parole chiave indicative di lavoro SE
    SE_KEYWORDS = [
        "api", "endpoint", "controller", "service", "microservice",
        "repository", "usecase", "use case", "handler", "route", "router",
        "frontend", "backend", "ui", "ux", "view", "component",
        "kubernetes", "k8s", "docker", "pipeline ci", "ci/cd", "deploy",
        "deployment", "infrastructure", "terraform", "ansible",
        "logging", "monitoring", "database", "db", "sql", "nosql",
        "server", "client", "test", "testing", "unit test", "integration test",
        "utils", "util", "config", "configuration", "json", "xml", "yaml",
        "html", "css", "script", "bash", "shell", "main", "app",
        "class", "function", "method", "interface", "abstract",
        "requirements.txt", "setup.py", "pyproject.toml", "pipfile",
        "dockerfile", "makefile", "jenkinsfile", "readme", "license", "changelog"
    ]

    # Estensioni che danno un segnale più forte
    ML_EXTENSIONS = {".ipynb"}
    SE_EXTENSIONS = {
        ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".php",
        ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt", ".rs",
        ".html", ".css", ".scss", ".less", ".sql", ".sh", ".bat",
        ".yml", ".yaml", ".json", ".xml", ".dockerfile", "dockerfile",
        ".py"
    }

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4.1-mini"):
        """
        :param api_key: OpenAI API key. Se non fornita, la classificazione è disabilitata.
        :param model: nome del modello chat da usare.
        """
        self.api_key = api_key
        self.model = model

        if not self.api_key:
            print("[OpenAI] Warning: No API key provided. Classification will be skipped.")
            self.enabled = False
            self.client = None
        else:
            self.enabled = True
            self.client = OpenAI(api_key=self.api_key)

        # Cache per evitare di riclassificare lo stesso autore
        self.classification_cache: Dict[str, Dict[str, Any]] = {}

    # --------------------------------------------------------------------- #
    # API pubblica
    # --------------------------------------------------------------------- #
    def classify_author(self, author_name: str, author_commits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Classifica un autore usando un modello chat OpenAI sulla base dei suoi commit.

        Ritorna un dict con forma:
        {
            "developer_type": "ML-engineer" | "SE-engineer" | "Hybrid-engineer" | "Unknown",
            "developer_type_explanation": "<breve spiegazione o motivo del fallimento>",
            "ml_score": <int>,
            "se_score": <int>
        }

        Tutti i valori stringa ritornati sono sanitizzati per l'uso in CSV.
        """
        if not self.enabled:
            return {
                "developer_type": "Unknown",
                "developer_type_explanation": sanitize_for_csv("OpenAI API key not configured"),
                "ml_score": 0,
                "se_score": 0,
            }

        # Controllo cache
        if author_name in self.classification_cache:
            return self.classification_cache[author_name]

        # Estraggo le feature euristiche una sola volta
        features = self._extract_features(author_commits)

        # Costruisco i messaggi per il modello
        messages = self._build_messages(author_name, author_commits, features)

        # Chiamata al modello
        try:
            result = self._call_openai(messages)
            # result contiene già ml_score e se_score dal modello

            # Salvataggio in cache (già sanitizzato)
            self.classification_cache[author_name] = result
            return result
        except Exception as e:
            print(f"[OpenAI] Error classifying {author_name}: {e}")
            explanation = f"Classification failed: {str(e)[:80]}"
            return {
                "developer_type": "Unknown",
                "developer_type_explanation": sanitize_for_csv(explanation),
                "ml_score": 0,
                "se_score": 0,
            }

    # --------------------------------------------------------------------- #
    # Estrazione feature euristiche
    # --------------------------------------------------------------------- #
    def _extract_features(self, author_commits: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Estrae feature semplici dai commit: estensioni file, punteggi ML/SE, numero di commit.
        Queste feature vengono poi passate al modello come "hint" della classificazione.
        """
        ext_counter = Counter()
        ml_score = 0
        se_score = 0
        total_commits = len(author_commits)

        def score_keywords(text: str, keywords: List[str]) -> int:
            text_lower = text.lower()
            score = 0
            for kw in keywords:
                if kw in text_lower:
                    score += 1
            return score

        for commit in author_commits[: self.MAX_COMMITS]:
            # Files toccati
            files_raw = commit.get("commit_files")
            files: List[str] = []

            if isinstance(files_raw, str):
                files = [f.strip() for f in files_raw.split(",") if f.strip()]
            elif isinstance(files_raw, (list, tuple, set)):
                files = [str(f).strip() for f in files_raw if str(f).strip()]

            for fpath in files:
                # Estensione file
                m = re.search(r"\.[a-zA-Z0-9]+$", fpath)
                if m:
                    ext = m.group(0).lower()
                    ext_counter[ext] += 1

                # Keyword su path
                ml_score += score_keywords(fpath, self.ML_KEYWORDS)
                se_score += score_keywords(fpath, self.SE_KEYWORDS)

            # Commit message
            msg = str(commit.get("commit_message", "") or "")
            ml_score += score_keywords(msg, self.ML_KEYWORDS)
            se_score += score_keywords(msg, self.SE_KEYWORDS)

            # Issue bodies
            issues_raw = commit.get("issue_bodies")
            if isinstance(issues_raw, str):
                ml_score += score_keywords(issues_raw, self.ML_KEYWORDS)
                se_score += score_keywords(issues_raw, self.SE_KEYWORDS)
            elif isinstance(issues_raw, (list, tuple, set)):
                for issue in issues_raw:
                    txt = str(issue or "")
                    ml_score += score_keywords(txt, self.ML_KEYWORDS)
                    se_score += score_keywords(txt, self.SE_KEYWORDS)

        # Boost su alcune estensioni particolarmente indicative
        for ext, count in ext_counter.items():
            if ext in self.ML_EXTENSIONS:
                ml_score += 2 * count
            if ext in self.SE_EXTENSIONS:
                se_score += 2 * count

        top_ext = ext_counter.most_common(5)

        # Note: i punteggi euristici sono solo hint per il modello,
        # il punteggio finale arriva dalle confidence del modello.

        return {
            "total_commits": total_commits,
            "top_extensions": top_ext,  # lista di (ext, count)
            "ml_score": ml_score,
            "se_score": se_score,
        }

    # --------------------------------------------------------------------- #
    # Costruzione dei messaggi per il modello
    # --------------------------------------------------------------------- #
    def _build_messages(
        self,
        author_name: str,
        author_commits: List[Dict[str, Any]],
        features: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        """Costruisce i messaggi (system + user) da passare al modello chat."""

        # Aggrego dati grezzi come contesto
        all_messages: List[str] = []
        all_files = set()
        all_issues: List[str] = []

        for commit in author_commits[: self.MAX_COMMITS]:
            # Commit message
            msg = commit.get("commit_message")
            if msg:
                all_messages.append(str(msg))

            # Files
            files_raw = commit.get("commit_files")
            if files_raw:
                if isinstance(files_raw, str):
                    files = [f.strip() for f in files_raw.split(",") if f.strip()]
                elif isinstance(files_raw, (list, tuple, set)):
                    files = [str(f).strip() for f in files_raw if str(f).strip()]
                else:
                    files = []
                all_files.update(files)

            # Issues
            issues_raw = commit.get("issue_bodies")
            if issues_raw:
                if isinstance(issues_raw, str):
                    all_issues.append(issues_raw)
                elif isinstance(issues_raw, (list, tuple, set)):
                    all_issues.extend(
                        [str(i) for i in issues_raw if str(i).strip()]
                    )

        files_summary = (
            ", ".join(list(all_files)[: self.MAX_FILES])
            if all_files
            else "No files available"
        )
        messages_summary = (
            "\n".join(all_messages[: self.MAX_MESSAGES])
            if all_messages
            else "No commit messages available"
        )
        issues_summary = (
            "\n".join(all_issues[: self.MAX_ISSUES])
            if all_issues
            else "No issues available"
        )

        top_ext_str = ", ".join(
            f"{ext}({cnt})" for ext, cnt in features["top_extensions"]
        )

        system_prompt = """You are an expert at analyzing software developer profiles based on git activity.

You receive:
- Some heuristic features (ML vs SE scores, file extensions, number of commits).
- A sample of files, commit messages, and related issues.

Use the heuristic features as a strong hint, and the raw data as supporting evidence.

Classification rules:
- "ML-engineer": mainly machine learning, data science, model training, notebooks, PyTorch/TensorFlow, or AI-related tasks.
- "SE-engineer": mainly software engineering, infrastructure, web/backend/frontend, DevOps, or general programming tasks.
- "Hybrid-engineer": works significantly on both ML and general software engineering; ML and SE signals are both strong and comparable.

You must also provide a confidence score (1-10) for both ML and SE categories.
- 1: No evidence / Not sure at all.
- 5: Some evidence / Moderately sure.
- 10: Strong evidence / Very sure.

Return JSON only using this schema:
{
  "developer_type": "ML-engineer" or "SE-engineer" or "Hybrid-engineer",
  "explanation": "Brief explanation in max 30 words",
  "ml_confidence": <int 1-10>,
  "se_confidence": <int 1-10>
}"""

        user_prompt = f"""Analyze the following developer:

Developer: {author_name}

Heuristic features:
- Total commits: {features["total_commits"]}
- Top file extensions: {top_ext_str if top_ext_str else "None"}
- ML heuristic score: {features["ml_score"]}
- SE heuristic score: {features["se_score"]}

Files touched (sample):
{files_summary}

Recent commit messages:
{messages_summary}

Related issues:
{issues_summary}"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    # --------------------------------------------------------------------- #
    # Chiamata al modello OpenAI
    # --------------------------------------------------------------------- #
    def _call_openai(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Chiama l'API OpenAI e normalizza l'output in un dizionario standard.

        Le stringhe ritornate vengono sanitizzate per l'uso in CSV.
        """

        if not self.client:
            raise RuntimeError("OpenAI client not initialized")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format={"type": "json_object"},
        )

        response_text = response.choices[0].message.content

        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            return {
                "developer_type": "Unknown",
                "developer_type_explanation": sanitize_for_csv("JSON parsing error from model response"),
                "ml_score": 0,
                "se_score": 0,
            }

        developer_type_raw = result.get("developer_type", "Unknown")
        explanation_raw = result.get("explanation", "")
        ml_confidence = result.get("ml_confidence", 0)
        se_confidence = result.get("se_confidence", 0)

        developer_type = sanitize_for_csv(developer_type_raw)
        explanation = sanitize_for_csv(explanation_raw)[:200] if explanation_raw else ""

        return {
            "developer_type": developer_type,
            "developer_type_explanation": explanation,
            "ml_score": ml_confidence,
            "se_score": se_confidence,
        }