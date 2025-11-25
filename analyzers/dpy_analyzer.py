from typing import Dict, Any, Optional
from interfaces.analyzer import Analyzer
from dpy_runner import run_dpy_and_collect_smells

class DPyAnalyzer(Analyzer):
    def run(self, project_path: str, binary_path: Optional[str] = None) -> Dict[str, Any]:
        if not binary_path:
            # DPy is usually required, but we'll handle it gracefully
            return {}
        return run_dpy_and_collect_smells(project_path, binary_path)
