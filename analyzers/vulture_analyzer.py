from typing import Dict, Any, Optional
from interfaces.analyzer import Analyzer
from deadcode_runner import run_vulture_and_collect_deadcode

class VultureAnalyzer(Analyzer):
    def run(self, project_path: str, binary_path: Optional[str] = None) -> Dict[str, Any]:
        if not binary_path:
            return {}
        return run_vulture_and_collect_deadcode(project_path, binary_path)
