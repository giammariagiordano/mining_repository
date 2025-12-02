import os
import json
from typing import List, Dict, Any, Optional
from huggingface_hub import InferenceClient

class HuggingFaceClassifier:
    """
    Classifies developers as ML-engineer or SE-engineer using Hugging Face Inference API.
    Classification is done per author based on their commit patterns.
    """
    
    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token
        if not self.api_token:
            print("[HF] Warning: No API token provided. Classification will be skipped.")
            self.enabled = False
        else:
            self.enabled = True
            self.client = InferenceClient(token=self.api_token)
            
        # Cache classifications to avoid re-classifying the same author
        self.classification_cache: Dict[str, Dict[str, str]] = {}
    
    def classify_author(self, author_name: str, author_commits: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Classify an author using HF Inference API based on their commits.
        """
        if not self.enabled:
            return {
                "developer_type": "Unknown",
                "developer_type_explanation": "HF Token not configured"
            }
        
        # Check cache
        if author_name in self.classification_cache:
            return self.classification_cache[author_name]
        
        # Build prompt
        prompt = self._build_prompt(author_name, author_commits)
        
        # Call HF
        try:
            result = self._call_hf(prompt)
            self.classification_cache[author_name] = result
            return result
        except Exception as e:
            print(f"[HF] Error classifying {author_name}: {e}")
            return {
                "developer_type": "Unknown",
                "developer_type_explanation": f"Classification failed: {str(e)[:50]}"
            }
    
    def _build_prompt(self, author_name: str, author_commits: List[Dict[str, Any]]) -> str:
        """Build the classification prompt for Llama 3."""
        
        # Aggregate commit data
        all_messages = []
        all_files = set()
        all_issues = []
        
        for commit in author_commits[:30]: 
            if commit.get("commit_message"):
                all_messages.append(commit["commit_message"])
            if commit.get("commit_files"):
                files_raw = commit["commit_files"]
                if isinstance(files_raw, str):
                    files = files_raw.split(",")
                    all_files.update(files)
            if commit.get("issue_bodies"):
                all_issues.append(commit["issue_bodies"])
        
        files_summary = ", ".join(list(all_files)[:80])  
        messages_summary = "\n".join(all_messages[:15])  
        issues_summary = "\n".join(all_issues[:5])  
        
        # Llama 3 prompt format
        prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are an expert at analyzing software developer profiles based on git activity.
Classify the developer as:
- "ML-engineer": if they primarily work on machine learning, data science, model training, python notebooks, PyTorch/TensorFlow, or AI-related tasks.
- "SE-engineer": if they primarily work on software engineering, infrastructure, web development, backend/frontend, DevOps or general programming tasks.

Return JSON only using this schema:
{{
  "developer_type": "ML-engineer" or "SE-engineer",
  "explanation": "Brief explanation in max 30 words"
}}<|eot_id|><|start_header_id|>user<|end_header_id|>

Analyze the following developer:

Developer: {author_name}
Number of commits analyzed: {len(author_commits)}

Files touched (sample):
{files_summary}

Recent commit messages:
{messages_summary}

Related issues:
{issues_summary if issues_summary else "No issues available"}<|eot_id|><|start_header_id|>assistant<|end_header_id|>"""
        return prompt
    
    def _call_hf(self, prompt: str) -> Dict[str, str]:
        """Call Hugging Face Inference API."""
        
        # Use Llama 3 8B Instruct (free and good)
        model_id = "meta-llama/Meta-Llama-3-8B-Instruct"
        
        response = self.client.text_generation(
            prompt,
            model=model_id,
            max_new_tokens=200,
            temperature=0.1,
            return_full_text=False
        )
        
        response_text = response.strip()
        
        # Clean up JSON
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # Fallback: try to find JSON-like structure
            import re
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group(0))
                except:
                    return {"developer_type": "Unknown", "explanation": "JSON parsing error"}
            else:
                return {"developer_type": "Unknown", "explanation": "Invalid response format"}
        
        return {
            "developer_type": result.get("developer_type", "Unknown"),
            "developer_type_explanation": result.get("explanation", "")[:200]
        }
