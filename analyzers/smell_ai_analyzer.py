# smell_ai_analyzer.py

from typing import Dict, Any, Optional
from analyzers.smell_ai_runner import run_smell_ai_and_collect_smells, ML_SMELL_TYPES


class SmellAiAnalyzer:
    """
    Analyzer for ML-specific code smells using the smell_ai tool.
    """
    
    def run(
        self,
        repo_path: str,
        smell_ai_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Runs smell_ai analysis on the given repository path.
        
        Args:
            repo_path: Path to the repository to analyze
            smell_ai_path: Path to the smell_ai tool directory
            
        Returns:
            Dictionary with ML smell metrics, or empty dict if analysis fails
        """
        # Prepare default metrics (all zeros/empty)
        default_metrics = {
            "mlsmell_total": 0,
            "mlsmell_files": "-",
            "mlsmell_details": "-",
        }
        for smell_type in ML_SMELL_TYPES:
            default_metrics[f"mlsmell_{smell_type}"] = 0

        if not smell_ai_path:
            # smell_ai explicitly disabled or not configured
            return default_metrics
        
        try:
            return run_smell_ai_and_collect_smells(
                project_path=repo_path,
                smell_ai_path=smell_ai_path
            )
        except Exception as e:
            print(f"[SMELL_AI] Error during analysis: {e}")
            return default_metrics
