import unittest
from unittest.mock import MagicMock, patch
from analyzers.openai_classifier import OpenAIClassifier

class TestLLMConfidence(unittest.TestCase):
    def setUp(self):
        self.classifier = OpenAIClassifier(api_key="fake_key")
        
    @patch('analyzers.openai_classifier.OpenAI')
    def test_confidence_parsing(self, mock_openai):
        # Mock the OpenAI client and response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '''
        {
            "developer_type": "SE-engineer",
            "explanation": "Mostly works on backend code.",
            "ml_confidence": 2,
            "se_confidence": 9
        }
        '''
        mock_client.chat.completions.create.return_value = mock_response
        self.classifier.client = mock_client
        
        commits = [
            {
                "commit_message": "update api",
                "commit_files": ["api.py"],
                "issue_bodies": []
            }
        ]
        
        result = self.classifier.classify_author("Test Author", commits)
        
        print(f"Result: {result}")
        self.assertEqual(result["ml_score"], 2)
        self.assertEqual(result["se_score"], 9)
        self.assertEqual(result["developer_type"], "SE-engineer")

    @patch('analyzers.openai_classifier.OpenAI')
    def test_missing_confidence(self, mock_openai):
        # Test fallback when confidence is missing
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '''
        {
            "developer_type": "ML-engineer",
            "explanation": "Works on models."
        }
        '''
        mock_client.chat.completions.create.return_value = mock_response
        self.classifier.client = mock_client
        
        commits = [{"commit_message": "train", "commit_files": [], "issue_bodies": []}]
        
        result = self.classifier.classify_author("Test Author", commits)
        
        self.assertEqual(result["ml_score"], 0)
        self.assertEqual(result["se_score"], 0)

if __name__ == '__main__':
    unittest.main()
