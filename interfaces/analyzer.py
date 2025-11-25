from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class Analyzer(ABC):
    @abstractmethod
    def run(self, project_path: str, binary_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Run the analyzer on the given project path.
        """
        pass
