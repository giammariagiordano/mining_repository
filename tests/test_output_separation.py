import unittest
import os
import json
import pandas as pd
from unittest.mock import patch, MagicMock
from core.engine import process_one_project
from config import MiningConfig

class TestOutputSeparation(unittest.TestCase):
    def setUp(self):
        self.output_csv = "test_output.csv"
        self.issues_dir = "issues"
        self.config = MiningConfig(
            input_csv="dummy.csv",
            output_csv=self.output_csv,
            repos_dir="repos",
            dpy_binary="dpy"
        )
        
    def tearDown(self):
        if os.path.exists(self.output_csv):
            os.remove(self.output_csv)
        if os.path.exists(self.issues_dir):
            import shutil
            shutil.rmtree(self.issues_dir)

    @patch('core.engine.get_issue_comments')
    @patch('core.engine.get_all_issues')
    @patch('core.engine.RepositoryMiner')
    @patch('core.engine.clone_or_update_repo')
    @patch('core.engine.get_github_repo_stats')
    @patch('git.Repo')
    def test_issue_separation(self, mock_repo, mock_stats, mock_clone, mock_miner_cls, mock_get_issues, mock_get_comments):
        # Setup mocks
        mock_clone.return_value = "/tmp/repo"
        mock_stats.return_value = (10, 5)
        
        # Mock issues with some dirty text
        mock_get_issues.return_value = [
            {"number": 1, "body": "Fixing  bug #123!"},
            {"number": 2, "body": "Feature request: @user"}
        ]
        
        # Mock comments - return value for each call
        def get_comments_side_effect(project, issue_num, token):
            if issue_num == 1:
                return [{"user": "dev1", "body": "Fixed it!", "created_at": "2023-01-01"}]
            return []
        
        mock_get_comments.side_effect = get_comments_side_effect
        
        # Mock miner to return a simple DataFrame
        mock_miner_instance = mock_miner_cls.return_value
        mock_miner_instance.mine.return_value = pd.DataFrame([{"commit_sha": "abc", "project_name": "test/repo"}])
        
        # Run process_one_project
        project_name = "test/repo"
        process_one_project(project_name, self.config, set())
        
        # Verify JSON file creation
        safe_name = "test_repo"
        json_path = os.path.join(self.issues_dir, f"{safe_name}_issues.json")
        self.assertTrue(os.path.exists(json_path), "Issues JSON file should exist")
        
        with open(json_path, "r") as f:
            issues = json.load(f)
            self.assertEqual(len(issues), 2)
            # Verify cleaning
            self.assertEqual(issues[0]["body"], "Fixing bug 123") # Assuming clean_text_for_json logic
            self.assertEqual(len(issues[0]["comments"]), 1)
            self.assertEqual(issues[0]["comments"][0]["body"], "Fixed it")
            
            self.assertEqual(issues[1]["body"], "Feature request user")
            self.assertEqual(len(issues[1]["comments"]), 0)
            
        # Verify CSV DataFrame (returned from function)
        # Note: process_one_project returns (project_name, df)
        # We need to check if the returned df has 'repo_all_issues' column
        # But wait, process_one_project calls miner.mine which returns a df.
        # The modification was to NOT add 'repo_all_issues' to this df.
        
        # We can check the arguments passed to miner.mine, but better to check the return value of process_one_project
        # We need to capture the return value of process_one_project, but we called it directly.
        # Wait, process_one_project returns (project_name, df).
        
        # Let's call it again and capture return
        _, df = process_one_project(project_name, self.config, set())
        self.assertNotIn("repo_all_issues", df.columns, "CSV DataFrame should not contain repo_all_issues")

if __name__ == '__main__':
    unittest.main()
