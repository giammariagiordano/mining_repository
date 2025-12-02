import os
import json
from typing import List, Dict, Any, Optional
import google.generativeai as genai # Spostato l'import in alto per pulizia

class GeminiDeveloperClassifier:
    """
    Classifies developers as ML-engineer or SE-engineer using Google Gemini 1.5 Pro.
    Classification is done per author based on their commit patterns.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        if not self.api_key:
            print("[GEMINI] Warning: No API key provided. Classification will be skipped.")
            self.enabled = False
        else:
            self.enabled = True
            # Configura l'API una sola volta all'inizializzazione
            genai.configure(api_key=self.api_key)
            
        # Cache classifications to avoid re-classifying the same author
        self.classification_cache: Dict[str, Dict[str, str]] = {}
    
    def classify_author(self, author_name: str, author_commits: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Classify an author using Gemini based on their commits.
        """
        if not self.enabled:
            return {
                "developer_type": "Unknown",
                "developer_type_explanation": "Gemini API key not configured"
            }
        
        # Check cache
        if author_name in self.classification_cache:
            return self.classification_cache[author_name]
        
        # Build prompt
        prompt = self._build_prompt(author_name, author_commits)
        
        # Call Gemini
        try:
            result = self._call_gemini(prompt)
            self.classification_cache[author_name] = result
            return result
        except Exception as e:
            print(f"[GEMINI] Error classifying {author_name}: {e}")
            return {
                "developer_type": "Unknown",
                "developer_type_explanation": f"Classification failed: {str(e)[:50]}"
            }
    
    def _build_prompt(self, author_name: str, author_commits: List[Dict[str, Any]]) -> str:
        """Build the classification prompt for Gemini."""
        
        # Aggregate commit data
        all_messages = []
        all_files = set()
        all_issues = []
        
        # Aumentato leggermente il limite visto che 1.5 Pro ha una context window enorme
        for commit in author_commits[:30]: 
            if commit.get("commit_message"):
                all_messages.append(commit["commit_message"])
            if commit.get("commit_files"):
                # Gestione più sicura nel caso non sia stringa
                files_raw = commit["commit_files"]
                if isinstance(files_raw, str):
                    files = files_raw.split(",")
                    all_files.update(files)
            if commit.get("issue_bodies"):
                all_issues.append(commit["issue_bodies"])
        
        files_summary = ", ".join(list(all_files)[:80])  
        messages_summary = "\n".join(all_messages[:15])  
        issues_summary = "\n".join(all_issues[:5])  
        
        prompt = f"""You are an expert at analyzing software developer profiles based on git activity.

Analyze the following developer's activity and classify them.

Developer: {author_name}
Number of commits analyzed: {len(author_commits)}

Files touched (sample):
{files_summary}

Recent commit messages:
{messages_summary}

Related issues:
{issues_summary if issues_summary else "No issues available"}

TASK:
Classify the developer as:
- "ML-engineer": if they primarily work on machine learning, data science, model training, python notebooks, PyTorch/TensorFlow, or AI-related tasks.
- "SE-engineer": if they primarily work on software engineering, infrastructure, web development, backend/frontend, DevOps or general programming tasks.

Return JSON only using this schema:
{{
  "developer_type": "ML-engineer" or "SE-engineer",
  "explanation": "Brief explanation in max 30 words"
}}
"""
        return prompt
    
    def _call_gemini(self, prompt: str) -> Dict[str, str]:
        """Call Google Gemini API using JSON mode."""
        
        # Configurazione per output JSON deterministico
        generation_config = {
            "temperature": 0.1,  # Basso per risultati più coerenti e meno "creativi"
            "response_mime_type": "application/json",
        }

        # Usa il modello Pro (più intelligente) invece del Flash
        model = genai.GenerativeModel(
            model_name='models/gemini-3-pro-preview', 
            generation_config=generation_config
        )
        
        response = model.generate_content(prompt)
        
        # Grazie a response_mime_type="application/json", non servono pulizie di stringa
        try:
            result = json.loads(response.text)
        except json.JSONDecodeError:
            # Fallback in caso remoto di errore
            return {"developer_type": "Unknown", "explanation": "JSON parsing error"}
        
        return {
            "developer_type": result.get("developer_type", "Unknown"),
            "developer_type_explanation": result.get("explanation", "")[:200]
        }