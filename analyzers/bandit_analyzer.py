from typing import Dict, Any, Optional
from interfaces.analyzer import Analyzer
from analyzers.bandit_runner import run_bandit_and_collect_vulns

class BanditAnalyzer(Analyzer):
    def run(self, project_path: str, binary_path: Optional[str] = None) -> Dict[str, Any]:
        if not binary_path:
            return {}
        return run_bandit_and_collect_vulns(project_path, binary_path)
